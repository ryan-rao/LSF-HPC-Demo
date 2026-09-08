# HPC 环境部署步骤（node211-215，参考老板的物理机步骤适配 VM）

时间：2026-09-01 20:27 起
参考：老板的 mmdsh 步骤 + /root/ccf-test/01-image/hpc-bench-main 介质
适配差异：VM 无 GPFS/mmdsh（改 SSH 循环）、无外网 repo（用 node181 本地 ISO）

## 一、本地 yum 源（替代 mlnx-ofed 在线源）
1. node181 启动 NFS 并导出 ISO：
   echo "/mnt/iso *(ro,insecure,no_subtree_check)" >> /etc/exports
   systemctl enable --now nfs-server && exportfs -rv
2. 4 台 VM：/etc/hosts 加 "172.16.12.181 node181"（否则挂载解析失败）
3. 4 台 VM 挂载 + 配 repo：
   mount 172.16.12.181:/mnt/iso /mnt/iso（fstab 已加，开机自动）
   /etc/yum.repos.d/local-iso.repo：BaseOS + AppStream 两个 file:///mnt/iso 段

## 二、安装开发环境（等价 dnf groupinstall Development Tools）
4 台 VM 执行：
   dnf -y groupinstall "Development Tools"
   dnf -y install numactl-devel mpich mpich-devel openmpi openmpi-devel environment-modules cmake
结果：gcc 11.5.0 / openmpi 4.1.1 / mpich 4.1.1（VM 上是 ISO 里的 4.1.1，
      物理机用的 4.1.7rc1 是 AppStream 更新版本，路径也不同：
      VM openmpi=/usr/lib64/openmpi，物理机=/usr/mpi/gcc/openmpi-4.1.7rc1）

## 三、共享存储（替代 GPFS）
node211 建共享目录并 NFS 导出：
   mkdir -p /data/hpc
   echo "/data/hpc *(rw,no_root_squash,no_subtree_check)" >> /etc/exports && exportfs -rv
node212/213/215 挂载：node211:/data/hpc → /data/hpc（fstab 已配）

## 四、配置 MPI 环境（~/.bashrc）
cat >> /root/.bashrc：
    export MPI_HOME=/usr/lib64/openmpi
    export MPICH_HOME=/usr/lib64/mpich
    export PATH=$MPI_HOME/bin:$MPICH_HOME/bin:$PATH
    export LD_LIBRARY_PATH=$MPI_HOME/lib:$MPICH_HOME/lib:$LD_LIBRARY_PATH
    export LIBRARY_PATH=$MPI_HOME/lib:$MPICH_HOME/lib:$LIBRARY_PATH
    export INSTALL_PATH=/data/hpc/hpc-bench-main

## 五、复制介质 + 编译
1. 介质从 node181 拷到共享盘：
   cd /root/ccf-test/01-image && tar cf - --exclude=build --exclude=result hpc-bench-main | ssh root@172.16.12.211 "cd /data/hpc && tar xf -"
2. 4 台 VM 各自编译（INSTALL_PATH 为共享盘）：
   cd $INSTALL_PATH && rm -rf build
   cmake -DCMAKE_INSTALL_PREFIX=$INSTALL_PATH -DCMAKE_BUILD_TYPE=Release -B build -S .
   cmake --build build -j
   cmake --install build
   → 产出 bin/：BTIO HACC_IO HACC_OPEN_CLOSE MADbench s3d_io（与物理机一致）

## 六、验证
1. 跨节点 MPI hello（hostfile /data/hpc/hostfile，4 节点 slots=8）：
   mpirun --allow-run-as-root --hostfile /data/hpc/hostfile --map-by node -np 8 /data/hpc/hello
   → rank 均匀分布 4 节点 ✅
   注意：不加 --map-by node 时 8 rank 会全落 node211（slot 填充策略）
2. HACC_IO 实测（写）：
   mpirun --allow-run-as-root --hostfile /data/hpc/hostfile --map-by node -np 8 \
     $INSTALL_PATH/bin/HACC_IO 1000000 /data/hpc/test_out/HACCIO_1 -w
   → total size: 0.31 GiB, total time: 91s, write bw ≈ 3.4 MiB/s ✅（跑通）
   用法：HACC_IO <粒子数/rank> <目录> [-i] <-w写/-r读>（来自 hpc_bench.sh）

## 七、踩坑记录
- VM 无 node181 主机名解析 → hosts 加 IP 条目
- node181 nfs-server 没启动 → mount 报 Connection refused，enable --now
- hello.c 嵌套引号被转义破坏、--host 逗号后不能有空格
- HACC_IO 裸跑无参数会段错误，必须按 hpc_bench.sh 的参数格式调用
- 写带宽仅 ~3.4 MiB/s：NFS 单服务器 + virtio 虚拟盘 + 虚拟环境，属预期

## 八、结论
4 节点 HPC 环境（编译工具链 + 双 MPI + 共享存储 + hpc-bench 五件套）部署完成，
跨节点 MPI 与 HACC_IO 实测通过，环境 OK。

# 基于 LSF 的 HPC 平台实施手册

> 版本：v1.0 ｜ 日期：2026-09-01
> 全部命令与输出取自实际部署记录（node181 + node211/212/213/215）
> 环境约定：宿主机 node181=172.16.12.181；VM 密码均为 Redhat@123；SSH 从 node181 到 VM 需 sshpass 或已配免密

---

# 第一部分 KVM 虚拟机部署

## 1.1 安装虚拟化组件（node181）

```bash
dnf -y install qemu-kvm libvirt virt-install guestfs-tools
```

## 1.2 准备 ISO（qemu 低权限读不了 /root）

```bash
cp /root/RHEL-9.6.0-x86_64-dvd1.iso /home/kvm/
```

## 1.3 配置网桥 br0（保留原 IP）

```bash
nmcli con add type bridge con-name br0 ifname br0 \
  ipv4.method manual ipv4.addresses 172.16.12.181/24
nmcli con add type bridge-slave con-name br0-port ifname ens1f0 master br0
nmcli con down "Profile 1" && nmcli con mod "Profile 1" connection.autoconnect no
nmcli con up br0
```

## 1.4 编写 kickstart（关键：显式分区，不能用 autopart，否则 anaconda 卡死）

`/root/kvm-setup/ks211.cfg` 要点：
```
rootpw Redhat@123
bootloader --location=mbr
clearpart --all --initlabel
part /boot --fstype=xfs --size=1024
part pv.01 --grow --size=1
volgroup rhel pv.01
logvol / --vgname=rhel --name=root --grow --size=2048
part /data --fstype=xfs --onvdb=vdb --grow --size=1024
network --bootproto=static --ip=172.16.12.211 --netmask=255.255.255.0 --activate
reboot
```

## 1.5 创建 VM（示例 node211，其余类推，MAC d3→d6）

```bash
virt-install --name node211 --memory 16384 --vcpus 8 \
  --disk path=/home/kvm/node211/os.qcow2,size=100,bus=virtio \
  --disk path=/home/kvm/node211/data.qcow2,size=100,bus=virtio \
  --network bridge=br0,mac=52:54:00:12:00:d3 \
  --cdrom /home/kvm/RHEL-9.6.0-x86_64-dvd1.iso \
  --initrd-inject /root/kvm-setup/ks211.cfg \
  --extra-args "inst.ks=file:/ks211.cfg inst.repo=cdrom" --noautoconsole
```

## 1.6 装后补 root SSH 登录（RHEL9 默认禁）

```bash
virt-customize -a /home/kvm/node211/os.qcow2 \
  --run-command "sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config"
```

## 1.7 验证

```bash
virsh list --all
 Id   Name       State
----------------------------
 1    node211    running
 2    node212    running
 3    node213    running
 4    node215    running

sshpass -p 'Redhat@123' ssh root@172.16.12.211 "hostname; lsblk | grep vdb"
node211
vdb    253:16   0  100G  0 disk /data
```

> ⚠️ 注意：172.16.12.214 被物理机占用（MAC E4:1F:13:5E:36:81），第 4 台用 .215。

---

# 第二部分 LSF 集群安装

## 2.1 前置依赖（4 节点，rpm 来自 node181:/mnt/iso/BaseOS/Packages）

```bash
rpm -Uvh /tmp/libnsl-2.34-168.el9.x86_64.rpm     # LSF 二进制需要 libnsl.so.1
rpm -Uvh /tmp/info-6.7-15.el9.x86_64.rpm /tmp/ed-1.14.2-12.el9.x86_64.rpm   # 安装器需要
useradd -m lsfadmin; echo lsfadmin:Redhat@123 | chpasswd   # LSF 管理员不能用 root
```

## 2.2 NFS 共享 LSF_TOP（node211 导出，212/213/215 挂载）

```bash
# node211：
mkdir -p /data/lsf
echo "/data/lsf *(rw,no_root_squash,no_subtree_check)" >> /etc/exports && exportfs -rv
# exporting *:/data/lsf

# workers：
mkdir -p /data/lsf
echo "node211:/data/lsf /data/lsf nfs defaults,_netdev 0 0" >> /etc/fstab && mount -a
```

## 2.3 解压安装器并配置（node211）

```bash
mkdir -p /data/lsf_inst/installer && cd /data/lsf_inst/installer
gzip -dc ../lsf10.1_lsfinstall_linux_x86_64.tar.Z | tar xf -
cat > lsf10.1_lsfinstall/install.config <<EOF
LSF_TOP="/data/lsf"
LSF_ADMINS="lsfadmin"
LSF_CLUSTER_NAME="cluster1"
LSF_MASTER_LIST="node211"
LSF_TARDIR="/data/lsf_inst"
LSF_ADD_SERVERS="node211 node212 node213 node215"
LSF_QUIET_INST="Y"
EOF
```

## 2.4 执行安装（license 交互输入 1）

```bash
cd lsf10.1_lsfinstall
printf "1\ny\ny\ny\n" | ./lsfinstall -f install.config
```
输出（节选）：
```
LSFINSTALL_EXIT=0
lsfinstall completed successfully...
see "/data/lsf/10.1/lsf_quick_admin.html"
```

## 2.5 hostsetup（4 节点都执行）

```bash
. /data/lsf/conf/profile.lsf
/data/lsf/10.1/install/hostsetup --top=/data/lsf --boot=y --start=n --profile=y --silent
```

## 2.6 启动集群

```bash
# 4 节点：
. /data/lsf/conf/profile.lsf
$LSF_SERVERDIR/lim
$LSF_SERVERDIR/res
$LSF_SERVERDIR/sbatchd

# 仅 node211：
$LSF_SERVERDIR/mbatchd
```

## 2.7 验证

```bash
# node211：
lsid
IBM Spectrum LSF Community Edition 10.1.0.15, May 13 2025
Copyright IBM Corp. 1992, 2016. All rights reserved.

lshosts
HOST_NAME      type    model  cpuf ncpus maxmem maxswp server RESOURCES
node211      X86_64 Intel_EM  60.0     8  15.3G      -    Yes (mg)
node212      X86_64    !        1.0     8      -      -    Yes ()
node213      X86_64    !        1.0     8      -      -    Yes ()
node215      X86_64    !        1.0     8      -      -    Yes ()

lsload
HOST_NAME       status  r15s   r1m  r15m   ut    pg  ls    it   tmp   swp   mem
node211             ok   0.0   0.0   0.0   1%   0.0   0     1   98G    0M 14.5G
node212             ok   0.0   0.0   0.0  16%   0.0   0     0   98G    0M 14.9G
node213             ok   0.2   0.0   0.0  12%   0.0   0     1   98G    0M 14.8G
node215             ok   0.0   0.0   0.0  16%   0.0   0     0   98G    0M 14.8G

su - lsfadmin -c ". /data/lsf/conf/profile.lsf; bhosts"
HOST_NAME          STATUS       JL/U    MAX  NJOBS    RUN  SSUSP  USUSP    RSV
node211            ok              -      8      0      0      0      0      0
node212            ok              -      8      0      0      0      0      0
node213            ok              -      8      0      0      0      0      0
node215            ok              -      8      0      0      0      0      0
```

## 2.8 LSF WebService（可选，node211）

```bash
cd /data/lsf_inst/lws/lws10.1.0.16_linux-x86_64
sed -i "/# . \$LSF_ENVDIR\/profile.lsf/a . /data/lsf/conf/profile.lsf" lwsinstall.sh
./lwsinstall.sh -s -y
```
输出：
```
IBM Spectrum LSF Webservice has been successfully installed under /opt/ibm/lsfsuite/ext
System service lwsd has been started.
Use the following URL to connect to IBM Spectrum LSF Webservice:
https://node211:8448
```

REST API 验证：
```bash
TOK=$(curl -sk -X POST -H "Content-Type: application/json" \
  -d '{"name":"lsfadmin","pass":"Redhat@123"}' \
  https://node211:8448/lsf/v1/auth/logon | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')

curl -sk -X POST -H "Authorization: $TOK" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "command=bhosts" https://node211:8448/lsf/v1/cluster/usercmd
{"output":"HOST_NAME          STATUS       JL/U    MAX  NJOBS    RUN  SSUSP  USUSP    RSV \nnode211            ok ..."}
```

---

# 第三部分 HPC 环境部署

## 3.1 node181 导出 ISO 为 yum 源

```bash
# node181：
echo "/mnt/iso *(ro,insecure,no_subtree_check)" >> /etc/exports
systemctl enable --now nfs-server && exportfs -rv
# exporting *:/mnt/iso
```

## 3.2 4 节点配置本地源（先 hosts 加解析！）

```bash
echo "172.16.12.181 node181" >> /etc/hosts     # 不加会 mount 报 Name or service not known
echo "node181:/mnt/iso /mnt/iso nfs ro,defaults,_netdev 0 0" >> /etc/fstab
mount -a
cat > /etc/yum.repos.d/local-iso.repo <<EOF
[local-baseos]
name=RHEL9-BaseOS
baseurl=file:///mnt/iso/BaseOS
enabled=1
gpgcheck=0
[local-appstream]
name=RHEL9-AppStream
baseurl=file:///mnt/iso/AppStream
enabled=1
gpgcheck=0
EOF
```

## 3.3 安装工具链与 MPI（4 节点）

```bash
dnf -y groupinstall "Development Tools"
dnf -y install numactl-devel mpich mpich-devel openmpi openmpi-devel environment-modules cmake
```
验证输出：
```
gcc (GCC) 11.5.0 20240719 (Red Hat 11.5.0-5)
mpich-4.1.1-1.el9.x86_64 openmpi-4.1.1-7.el9.x86_64
```

## 3.4 共享存储 /data/hpc

```bash
# node211：
mkdir -p /data/hpc
echo "/data/hpc *(rw,no_root_squash,no_subtree_check)" >> /etc/exports && exportfs -rv
# workers：
echo "node211:/data/hpc /data/hpc nfs defaults,_netdev 0 0" >> /etc/fstab && mount -a
```

## 3.5 拷贝介质（node181 → 共享盘）

```bash
# node181：
cd /root/ccf-test/01-image
tar cf - --exclude=build --exclude=result hpc-bench-main | \
  ssh root@172.16.12.211 "cd /data/hpc && tar xf -"
```

## 3.6 配置 MPI 环境（4 节点 ~/.bashrc 追加）

```bash
export MPI_HOME=/usr/lib64/openmpi
export MPICH_HOME=/usr/lib64/mpich
export PATH=$MPI_HOME/bin:$MPICH_HOME/bin:$PATH
export LD_LIBRARY_PATH=$MPI_HOME/lib:$MPICH_HOME/lib:$LD_LIBRARY_PATH
export LIBRARY_PATH=$MPI_HOME/lib:$MPICH_HOME/lib:$LIBRARY_PATH
export INSTALL_PATH=/data/hpc/hpc-bench-main
```
验证：
```bash
. ~/.bashrc && which mpicc
/usr/lib64/openmpi/bin/mpicc
```

## 3.7 编译（4 节点各执行）

```bash
cd $INSTALL_PATH && rm -rf build
cmake -DCMAKE_INSTALL_PREFIX=$INSTALL_PATH -DCMAKE_BUILD_TYPE=Release -B build -S .
cmake --build build -j
cmake --install build
```
输出：
```
[100%] Built target HACC_IO
-- Installing: /data/hpc/hpc-bench-main/bin/s3d_io
-- Installing: /data/hpc/hpc-bench-main/bin/HACC_IO
-- Installing: /data/hpc/hpc-bench-main/bin/HACC_OPEN_CLOSE
-- Installing: /data/hpc/hpc-bench-main/bin/MADbench
-- Installing: /data/hpc/hpc-bench-main/bin/BTIO
```

## 3.8 跨节点 MPI 验证

```bash
cat > /data/hpc/hostfile <<EOF
node211 slots=8
node212 slots=8
node213 slots=8
node215 slots=8
EOF
mpirun --allow-run-as-root --hostfile /data/hpc/hostfile --map-by node -np 8 /data/hpc/hello
```
输出（--map-by node 保证均布，不加会全落首节点）：
```
rank 0 of 8 on node211
rank 1 of 8 on node212
rank 2 of 8 on node213
rank 3 of 8 on node215
rank 4 of 8 on node211
rank 5 of 8 on node212
rank 6 of 8 on node213
rank 7 of 8 on node215
```

---

# 第四部分 LSF 与 HPC 集成

## 4.1 lsfadmin 全互信 SSH（集成成败的关键！）

LSF 作业以 lsfadmin 运行，mpirun 可能从**任意节点**发起，必须全量配置：

```bash
# ① node211 生成密钥
su - lsfadmin -c "ssh-keygen -t rsa -N '' -f ~/.ssh/id_rsa"

# ② 公钥追加到 4 节点 authorized_keys（.ssh 700，文件 600，属主 lsfadmin）
PUB=$(su - lsfadmin -c "cat ~/.ssh/id_rsa.pub")
for H in node211 node212 node213 node215; do
  ssh $H "mkdir -p /home/lsfadmin/.ssh; echo '$PUB' >> /home/lsfadmin/.ssh/authorized_keys; \
    chmod 700 /home/lsfadmin/.ssh; chmod 600 /home/lsfadmin/.ssh/authorized_keys; \
    chown -R lsfadmin:lsfadmin /home/lsfadmin/.ssh"
done

# ③ ⚠️ 私钥也要分发到 4 节点（只发公钥的话非首节点发起的 mpirun 会 Permission denied）
for H in node212 node213 node215; do
  scp /home/lsfadmin/.ssh/id_rsa $H:/tmp/ && ssh $H \
    "mv /tmp/id_rsa /home/lsfadmin/.ssh/; chown lsfadmin /home/lsfadmin/.ssh/id_rsa; chmod 600 /home/lsfadmin/.ssh/id_rsa"
done

# ④ known_hosts 4 节点互扫（否则 "Host key verification failed"）
for H in node211 node212 node213 node215; do
  ssh $H "su - lsfadmin -c 'for T in node211 node212 node213 node215; do ssh-keyscan -H \$T >> ~/.ssh/known_hosts 2>/dev/null; done'"
done

# 验证（4×4 全通才算过）
for H in node211 node212 node213 node215; do
  ssh $H "su - lsfadmin -c 'ssh -o BatchMode=yes node213 hostname'"
done
node213
node213
node213
node213
```

## 4.2 目录权限

```bash
chmod -R a+rwX /data/hpc     # root 建的目录 lsfadmin 要能写
mkdir -p /data/hpc/lsf_logs && chmod 777 /data/hpc/lsf_logs
```

## 4.3 通用调度脚本 /data/hpc/lsf_bench.sh

```bash
#!/bin/bash
# 通用 LSF -> MPI 调度器: lsf_bench.sh <BTIO|MADbench|s3d_io|HACC_OPEN_CLOSE|HACC_IO>
BENCH=$1
export MPI_HOME=/usr/lib64/openmpi
export PATH=$MPI_HOME/bin:$PATH
export LD_LIBRARY_PATH=$MPI_HOME/lib:$LD_LIBRARY_PATH
INSTALL_PATH=/data/hpc/hpc-bench-main

# 从 LSF 分配结果动态生成 hostfile（LSB_MCPU_HOSTS: host1 n1 host2 n2 ...）
HF=/tmp/hf.$LSB_JOBID; : > $HF
set -- $LSB_MCPU_HOSTS
while [ $# -ge 2 ]; do echo "$1 slots=$2" >> $HF; shift 2; done
NP=$(awk -F"slots=" '{s+=$2} END{print s}' $HF)
OUT=/data/hpc/test_out/lsf_$BENCH/$LSB_JOBID
mkdir -p $OUT
echo "=== LSF job $LSB_JOBID bench=$BENCH NP=$NP hosts: $LSB_MCPU_HOSTS"

case $BENCH in
  BTIO)
    mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP \
      $INSTALL_PATH/bin/BTIO -m w -t 0 -g 32,32,32 -i 1 -o $OUT ;;
  MADbench)
    mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP \
      $INSTALL_PATH/bin/MADbench 512 $NP 1 UNIQUE $OUT ;;
  s3d_io)
    mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP \
      $INSTALL_PATH/bin/s3d_io -g 32,32,32 -p 2,2,2 -i 1 -d $OUT ;;
  HACC_OPEN_CLOSE)
    mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP \
      $INSTALL_PATH/bin/HACC_OPEN_CLOSE 1000000 $OUT ;;
  HACC_IO)
    mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP \
      $INSTALL_PATH/bin/HACC_IO 1000000 $OUT -w ;;
esac
RC=$?; rm -f $HF
echo "=== $BENCH exit=$RC"
exit $RC
```
```bash
chmod +x /data/hpc/lsf_bench.sh && chown lsfadmin /data/hpc/lsf_bench.sh
```

> `--prefix $MPI_HOME` 不可省：LSF 作业是非登录 shell，远端节点无 MPI PATH，
> 缺了会报 "ORTE was unable to reliably start daemons"（exit 127/255）。

## 4.4 集成验证（实际输出）

```bash
su - lsfadmin -c ". /data/lsf/conf/profile.lsf
bsub -J btio    -n 4 -R "span[ptile=1]" -o /data/hpc/lsf_logs/btio.%J.out  /data/hpc/lsf_bench.sh BTIO
bsub -J madbench -n 4 -R "span[ptile=1]" -o /data/hpc/lsf_logs/mad.%J.out   /data/hpc/lsf_bench.sh MADbench
bsub -J s3dio   -n 8 -R "span[ptile=2]" -o /data/hpc/lsf_logs/s3d.%J.out   /data/hpc/lsf_bench.sh s3d_io
bsub -J hocc    -n 8 -R "span[ptile=2]" -o /data/hpc/lsf_logs/hocc.%J.out  /data/hpc/lsf_bench.sh HACC_OPEN_CLOSE"
Job <8> is submitted to default queue <normal>.
Job <9> is submitted to default queue <normal>.
Job <10> is submitted to default queue <normal>.
Job <11> is submitted to default queue <normal>.
```

运行中查看分配：
```bash
bjobs
JOBID   USER    STAT  QUEUE      FROM_HOST   EXEC_HOST   JOB_NAME   SUBMIT_TIME
7       lsfadmi RUN   normal     node211     node215     haccio     Sep  1 20:53
                                             node215
                                             node212
                                             node212
                                             node213
                                             node213
                                             node211
                                             node211
```

完成后日志验证：
```bash
$ grep -E "^=== " /data/hpc/lsf_logs/btio.8.out
=== LSF job 8 bench=BTIO NP=4 hosts: node212 1 node213 1 node215 1 node211 1
=== BTIO exit=0

$ grep -E "^=== " /data/hpc/lsf_logs/s3d.13.out
=== LSF job 13 bench=s3d_io NP=8 hosts: node213 2 node215 2 node212 2 node211 2
=== s3d_io exit=0
```

---

# 第五部分 HPC 集成 LSF 环境使用

## 5.1 五基准提交速查

| 基准 | 提交命令 | 约束 |
|---|---|---|
| HACC_IO | `bsub -n 8 -R "span[ptile=2]" /data/hpc/lsf_bench.sh HACC_IO` | 无 |
| HACC_OPEN_CLOSE | `bsub -n 8 -R "span[ptile=2]" ... HACC_OPEN_CLOSE` | 无 |
| s3d_io | `bsub -n 8 -R "span[ptile=2]" ... s3d_io` | -p 乘积=进程数；**必须 -d 目录** |
| BTIO | `bsub -n 4 -R "span[ptile=1]" ... BTIO` | **进程数完全平方数** |
| MADbench | `bsub -n 4 -R "span[ptile=1]" ... MADbench` | **平方数且 n_bin 整除 NP** |

> 均需先 `su - lsfadmin` 并 `. /data/lsf/conf/profile.lsf`，建议加
> `-o /data/hpc/lsf_logs/<名>.%J.out` 收集日志。

## 5.2 日常操作

```bash
bjobs            # 作业状态
bjobs -a         # 含历史
bjobs -l <ID>    # 详情（节点分配）
bhosts / lshosts / lsload    # 节点与负载
bqueues          # 队列
tail -f /data/hpc/lsf_logs/8.out    # 跟踪作业日志
```

## 5.3 集群启停

```bash
# 启动（hostsetup --boot=y 已配自启，正常无需手工）
for H in node211 node212 node213 node215; do
  ssh $H ". /data/lsf/conf/profile.lsf; \$LSF_SERVERDIR/lim; \$LSF_SERVERDIR/res; \$LSF_SERVERDIR/sbatchd"
done
ssh node211 ". /data/lsf/conf/profile.lsf; \$LSF_SERVERDIR/mbatchd"
```

## 5.4 REST API（程序集成）

```bash
TOK=$(curl -sk -X POST -H "Content-Type: application/json" \
  -d '{"name":"lsfadmin","pass":"Redhat@123"}' \
  https://node211:8448/lsf/v1/auth/logon | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')

curl -sk -X POST -H "Authorization: $TOK" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "command=bsub sleep 60" https://node211:8448/lsf/v1/cluster/usercmd
{"output":"Job <2> is submitted to default queue <normal>.\n","exitcode":0,...}
```

## 5.5 故障排查表（按实际踩坑整理）

| 症状 | 原因 | 解决 |
|---|---|---|
| lim 静默 exit 255 | 真实报错在 syslog | `journalctl -x | grep lim` |
| 作业 mpirun 报 Host key verification failed | lsfadmin known_hosts 缺 | 4.1 ④ 全节点互扫 |
| 作业报 Permission denied | 私钥只在 node211 | 4.1 ③ 分发私钥 |
| ORTE unable to start daemons / no-path (127/255) | 远端无 MPI PATH | mpirun 加 `--prefix $MPI_HOME` |
| BTIO/MADbench "square number" 报错 | 进程数非平方 | 改 `-n 4`（或 9/16） |
| s3d_io "MPI_File_open Not a directory" | 缺 -d 输出目录 | 脚本里带 `-d $OUT` |
| 作业日志无输出 | cwd/home 不可写 | /data/hpc 开 a+rwX |
| mount Connection refused | NFS server 未启动 | `systemctl enable --now nfs-server` |

---

# 第六部分 弹性扩容：定制镜像部署新节点（node216 实战）

> 场景：用现有节点（node212，含 LSF 客户端 + HPC 应用）制作黄金镜像，
> 定制两个参数（LSF服务器IP、虚拟机IP）后部署新节点，验证自动入集群 + 作业负载。

## 6.1 制作黄金镜像（node181）

```bash
# ① 关闭模板机，拷盘，再启回（保证文件系统一致性）
virsh shutdown node212
# 等待 shut off 后：
mkdir -p /home/kvm/node216
cp /home/kvm/node212/node212-os.qcow2 /home/kvm/node216/node216-os.qcow2
cp /home/kvm/node212/node212-data.qcow2 /home/kvm/node216/node216-data.qcow2
virsh start node212
```

## 6.2 定制参数与首次开机脚本

两个定制参数写入 /root/node-params.env（随镜像分发）：
```bash
LSF_SERVER_IP=172.16.12.211    # 参数一：LSF 服务器 IP
VM_IP=172.16.12.216            # 参数二：虚拟机 IP
VM_HOSTNAME=node216
```

firstboot 脚本（开机自动执行，日志 /var/log/firstboot.log）：
```bash
#!/bin/bash
. /root/node-params.env
hostnamectl set-hostname $VM_HOSTNAME
nmcli con mod enp1s0 ipv4.addresses ${VM_IP}/24   # ⚠️ 连接名以 nmcli con show 为准！
nmcli con up enp1s0
# hosts 替换克隆残留地址，追加集群解析
sed -i "s/^172.16.12.212.*/${VM_IP} ${VM_HOSTNAME}/" /etc/hosts
echo "$LSF_SERVER_IP node211" >> /etc/hosts
# NFS 挂载 LSF_TOP 和 HPC 共享盘（指向 LSF 服务器）
echo "$LSF_SERVER_IP:/data/lsf /data/lsf nfs defaults,_netdev 0 0" >> /etc/fstab
echo "$LSF_SERVER_IP:/data/hpc /data/hpc nfs defaults,_netdev 0 0" >> /etc/fstab
mount -a
su - lsfadmin -c "ssh-keyscan -H $VM_HOSTNAME >> ~/.ssh/known_hosts"
. /data/lsf/conf/profile.lsf
$LSF_SERVERDIR/lim; $LSF_SERVERDIR/res; $LSF_SERVERDIR/sbatchd
```

注入镜像：
```bash
virt-customize -a /home/kvm/node216/node216-os.qcow2 \
  --hostname node216 \
  --copy-in /root/kvm-setup/node216-params.env:/root/ \
  --firstboot /root/kvm-setup/firstboot-node216.sh
# 输出：[29.7] Finishing off / RC=0
```
⚠️ `--firstboot` 读的是宿主机路径，`--copy-in` 的参数文件名必须与脚本内 source 的一致。

## 6.3 定义并启动新 VM

```bash
virt-install --import --name node216 --memory 16384 --vcpus 8 \
  --disk path=/home/kvm/node216/node216-os.qcow2,bus=virtio \
  --disk path=/home/kvm/node216/node216-data.qcow2,bus=virtio \
  --network bridge=br0,mac=52:54:00:12:00:d7 \
  --osinfo rhel9.0 --noautoconsole
```

## 6.4 master 侧两步配置（一次性）

```bash
# ① 共享集群文件加新节点（所有节点共享此文件，唯一真相源）
#    在 node211 的 /data/lsf/conf/lsf.cluster.cluster1 增加：
node216	!	!	1	()
# ② 重载配置
su - lsfadmin -c '. /data/lsf/conf/profile.lsf; printf "y\ny\ny\n" | lsadmin reconfig'
su - lsfadmin -c '. /data/lsf/conf/profile.lsf; printf "y\ny\n" | badmin reconfig'
# ③ 其余节点 hosts + lsfadmin known_hosts 补 node216（MPI 跨节点需要）
```
> 说明：LSF_DYNAMIC_HOSTS=Y 动态注册在社区版未生效，实际采用共享集群文件方式
> （新节点 firstboot 起 lim 后即可被 master 收录，效果等同）。

## 6.5 验证结果（实际输出）

```bash
# 节点自动入集群：
bhosts
node211  ok  -  8 ...
node212  ok  -  8 ...
node213  ok  -  8 ...
node215  ok  -  8 ...
node216  ok  -  8 ...          # ← 新节点 8 slot 就绪

# 作业负载到新节点：
bsub -m node216 sleep 30                 # Job 14 → DONE @ node216
bsub -m node216 -n 4 -R "span[hosts=1]" \
     /data/hpc/lsf_bench.sh HACC_IO      # Job 15
# === LSF job 15 bench=HACC_IO NP=4 hosts: node216 4
# === HACC_IO exit=0
```

## 6.6 本次踩坑记录（重要）

| 坑 | 现象 | 解决 |
|---|---|---|
| 参数文件名不一致 | firstboot 报 No such file | --copy-in 文件名与脚本 source 严格一致 |
| 网卡连接名假设错误 | nmcli 报 unknown connection | 先 nmcli con show 确认（本环境 enp1s0 非 ens3） |
| --firstboot 路径 | virt-customize 报 No such file | 用宿主机路径 |
| 克隆 IP 冲突 | 新 VM 带旧 IP .212 上网 | firstboot 必须先改 IP 再做其它事；故障时用 virsh console（serial）修复 |
| virsh console 交互 | ssh 无 TTY 报错 | ssh -tt + PTY 会话 |
| 动态注册未生效 | lim 起了但 master 不收录 | 共享 lsf.cluster 文件 + lsadmin reconfig |

## 6.7 扩容标准流程（复用）

```
① 关模板机 → 拷盘到 /home/kvm/nodeNNN → 启回模板
② 写参数文件（LSF_SERVER_IP + VM_IP + VM_HOSTNAME）
③ virt-customize 注入参数 + firstboot（先验证连接名！）
④ master 集群文件加一行 + lsadmin/badmin reconfig
⑤ 其余节点 hosts/known_hosts 补新节点
⑥ virt-install --import 启动 → bhosts 验证 → bsub 验证
```

---

# 附录：平台信息卡

- 集群：cluster1（master=node211），32 slot 总算力
- 关键路径：LSF_TOP=/data/lsf｜HPC=/data/hpc｜日志=/data/hpc/lsf_logs
- 账户：root / lsfadmin（密码 Redhat@123）
- 服务：lwsd（REST，8448）｜nfs-server（181/211）｜LSF 开机自启已配
- 详见配套文档：《基于LSF的HPC解决方案》《KVM虚拟机部署步骤》《LSF安装步骤》《HPC环境部署步骤》《LSF调度HPC基准集成步骤》

# LSF + 全部 HPC 基准集成步骤（五件套调度指南）

通用调度脚本：/data/hpc/lsf_bench.sh <基准名>，自动从 $LSB_MCPU_HOSTS 生成 hostfile、建输出目录、按基准适配参数。

## 各基准参数与调度约束（踩坑总结，重要！）
| 基准 | LSF 提交 | 进程约束 | 关键参数 |
|---|---|---|---|
| HACC_IO | -n 8 span[ptile=2] | 无 | <粒子数> <目录> -w/-r |
| HACC_OPEN_CLOSE | -n 8 span[ptile=2] | 无 | 同上（不带 -w 默认写）|
| s3d_io | -n 8 span[ptile=2] | -p 乘积=进程数 | -g X,Y,Z -p npx,npy,npz -i N **-d 输出目录** |
| BTIO | **-n 4** span[ptile=1] | **进程数必须是平方数** | -m w -t 0 -g 32,32,32 -i 1 -o 目录 |
| MADbench | **-n 4** span[ptile=1] | **进程数平方数且整除 n_bin** | <no_pix> <n_bin=NP> 1 UNIQUE 目录 |

- BTIO 报 "Number of processes must be a square number"、MADbench 报 "non-square no_pe"：8 进程不行，用 4（或 9/16）
- MADbench 的 no_gang=no_bin，NP%no_bin 必须=0，用 n_bin=NP 最简单
- s3d_io 不带 -d 时 out_dir 为空 → MPI_File_open "Not a directory"（root 手工跑碰巧写到 cwd 掩盖了问题）

## 提交命令（su - lsfadmin）
bsub -J btio    -n 4 -R "span[ptile=1]" -o ... /data/hpc/lsf_bench.sh BTIO
bsub -J madbench -n 4 -R "span[ptile=1]" -o ... /data/hpc/lsf_bench.sh MADbench
bsub -J s3dio   -n 8 -R "span[ptile=2]" -o ... /data/hpc/lsf_bench.sh s3d_io
bsub -J hocc    -n 8 -R "span[ptile=2]" -o ... /data/hpc/lsf_bench.sh HACC_OPEN_CLOSE

## 测试结果（2026-09-01 21:05 全部通过 ✅）
| Job | 基准 | LSF 分配 | exit |
|---|---|---|---|
| 7 | HACC_IO | 4节点×2 | 0 |
| 8 | BTIO | 4节点×1 | 0 |
| 9 | MADbench | 4节点×1 | 0 |
| 10/12 | s3d_io（修参前失败） | - | 255/1 |
| 13 | s3d_io（-d 修正后） | 4节点×2 | 0 |
| 11 | HACC_OPEN_CLOSE | 4节点×2 | 0 |

以下为最初 HACC_IO 集成的原始记录。

# LSF + HACC_IO 集成步骤（LSF 调度 HPC 作业）

时间：2026-09-01 20:45
环境：LSF Community Edition 10.1.0.15（master node211），HPC 环境（openmpi 4.1.1 + hpc-bench）
原理：bsub 申请 slot → LSF 分配节点 → 作业脚本从 $LSB_MCPU_HOSTS 动态生成 mpirun hostfile → 跨节点执行

## 一、前置条件（关键！）
1. lsfadmin 用户 4 节点 SSH 全互信（LSF 作业以 lsfadmin 跑，mpirun 要 SSH 各节点）：
   - node211 生成密钥：su - lsfadmin -c "ssh-keygen -t rsa -N '' -f ~/.ssh/id_rsa"
   - 公钥追加到 4 节点 /home/lsfadmin/.ssh/authorized_keys（700/.ssh，600 文件，属主 lsfadmin）
   - **私钥 id_rsa 也要复制到 4 节点**（只发公钥的话，非首节点发起的 mpirun 会失败）
   - known_hosts 4 节点互相 ssh-keyscan -H（否则 "Host key verification failed"）
2. 共享目录可写：chmod -R a+rwX /data/hpc（root 建的目录 lsfadmin 要能写）
3. LSF 集群健康：bhosts 4 节点 ok

## 二、作业脚本 /data/hpc/lsf_haccio.sh
#!/bin/bash
#BSUB -J haccio
#BSUB -n 8                          # 申请 8 个 slot
#BSUB -R "span[ptile=2]"           # 每节点 2 slot → 分散 4 节点
#BSUB -o /data/hpc/lsf_logs/%J.out
#BSUB -e /data/hpc/lsf_logs/%J.err

export MPI_HOME=/usr/lib64/openmpi   # 非登录 shell，环境要自己设
export PATH=$MPI_HOME/bin:$PATH
export LD_LIBRARY_PATH=$MPI_HOME/lib:$LD_LIBRARY_PATH
INSTALL_PATH=/data/hpc/hpc-bench-main

# 从 LSF 分配结果生成 hostfile（LSB_MCPU_HOSTS 格式: host1 n1 host2 n2 ...）
HF=/tmp/hostfile.$LSB_JOBID; : > $HF
set -- $LSB_MCPU_HOSTS
while [ $# -ge 2 ]; do echo "$1 slots=$2" >> $HF; shift 2; done
NP=$(awk -F"slots=" '{s+=$2} END{print s}' $HF)
echo "=== LSF job $LSB_JOBID hosts: $LSB_MCPU_HOSTS"

mkdir -p /data/hpc/test_out/lsf_HACCIO/$LSB_JOBID
mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP \
  $INSTALL_PATH/bin/HACC_IO 1000000 /data/hpc/test_out/lsf_HACCIO/$LSB_JOBID -w
RC=$?; rm -f $HF
echo "=== HACC_IO exit=$RC"; exit $RC

## 三、提交与验证
su - lsfadmin -c ". /data/lsf/conf/profile.lsf; bsub < /data/hpc/lsf_haccio.sh"
bjobs 查看状态/分配；完成后看 /data/hpc/lsf_logs/7.out

## 四、测试结果（Job 7 ✅）
- LSF 分配：node215/node212/node213/node211 各 2 slot（span[ptile=2] 生效）
- HACC_IO：8 rank × 100万粒子，total size 0.30656 GiB，151.5 秒，exit=0

## 五、踩坑记录（Job 3-6 失败原因递进）
1. Job 3：脚本里嵌套 tr 转义弄脏 hostfile → 简化日志行
2. Job 3/5：lsfadmin 节点间无 SSH 互信 → 配公钥+known_hosts
3. Job 5：known_hosts 只配了 node211，但 LSF 把首节点调度到 node213 → 4 节点都配
4. Job 6：私钥只在 node211 → 私钥也分发 4 节点
5. Job 6：远端找不到 orted（非交互 SSH 无 PATH）→ mpirun 加 --prefix $MPI_HOME
6. 经验：LSF 调度 MPI 作业的两大依赖 = 执行用户全互信 SSH + mpirun --prefix

## 六、使用模板
改 #BSUB -n / ptile / HACC_IO 参数即可调度其它基准（BTIO、MADbench、s3d_io 同理）。

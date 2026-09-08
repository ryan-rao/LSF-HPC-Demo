# LSF HPC 集群 · 用户使用手册

> 版本 v1.0 ｜ 2026-09-01 ｜ 命令与输出均为实测
> 登录集群：`ssh lsfadmin@172.16.12.211`，进入 LSF 环境：`. /data/lsf/conf/profile.lsf`
> 可用算力：5 节点 × 8 核 = 40 slot ｜ 共享目录 /data/hpc（NFS，全节点可见）

---

## 一、快速上手（三分钟跑通第一个作业）

```bash
# 1. 登录并进入 LSF 环境
ssh lsfadmin@172.16.12.211
. /data/lsf/conf/profile.lsf

# 2. 提交一个最简单的作业
bsub -J myfirst -o /data/hpc/lsf_logs/myfirst.%J.out hostname
Job <21> is submitted to default queue <normal>.

# 3. 查看状态，等 STAT 变 DONE
bjobs
# 4. 看结果
cat /data/hpc/lsf_logs/myfirst.21.out
node212
```

## 二、提交作业（bsub 全场景）

### 2.1 基本语法
```bash
bsub [选项] 命令
常用：-J 名字  -o 输出文件（%J=作业号 %I=数组序号）  -e 错误文件
     -n 总进程数  -R "span[ptile=N]" 每节点N进程  -R "span[hosts=1]" 单节点
     -m node216 指定节点  -q 队列  -W 限额(分钟)
```

### 2.2 串行作业（实测）
```bash
bsub -J serial_test -o /data/hpc/lsf_logs/serial.%J.out sleep 20
Job <16> is submitted to default queue <normal>.
```

### 2.3 数组作业——批量参数扫描（实测）
```bash
bsub -J "array_test[1-4]" -o /data/hpc/lsf_logs/array.%J.%I.out sleep 15
Job <17> is submitted to default queue <normal>.
# 一条命令四个子作业并行，$LSB_JOBINDEX 区分各自序号
```

### 2.4 依赖链式作业（实测）
```bash
bsub -J chain_a sleep 10
Job <19> is submitted to default queue <normal>.
bsub -w "done(chain_a)" -J chain_b -o /data/hpc/lsf_logs/chainb.%J.out hostname
Job <20> is submitted to default queue <normal>.
# chain_b 保持 PEND，chain_a 完成后自动执行，输出 node212
```
> 依赖类型：done() 完成 / ended() 结束(含失败) / exit() 失败 / started() 启动

### 2.5 五大 HPC 基准（MPI 并行，实测）
```bash
# HACC_IO：8 进程跨 4 节点（每节点 2 进程）
bsub -n 8 -R "span[ptile=2]" -J haccio \
     -o /data/hpc/lsf_logs/haccio.%J.out /data/hpc/lsf_bench.sh HACC_IO

# HACC_OPEN_CLOSE：同上
bsub -n 8 -R "span[ptile=2]" ... /data/hpc/lsf_bench.sh HACC_OPEN_CLOSE

# s3d_io：8 进程跨 4 节点
bsub -n 8 -R "span[ptile=2]" ... /data/hpc/lsf_bench.sh s3d_io

# BTIO / MADbench：⚠️ 进程数必须完全平方数，用 4
bsub -n 4 -R "span[ptile=1]" ... /data/hpc/lsf_bench.sh BTIO
bsub -n 4 -R "span[ptile=1]" ... /data/hpc/lsf_bench.sh MADbench

# 指定新节点 node216 跑（实测）
bsub -m node216 -n 4 -R "span[hosts=1]" -J hacc216 \
     -o /data/hpc/lsf_logs/hacc216.%J.out /data/hpc/lsf_bench.sh HACC_IO
Job <15> is submitted to default queue <normal>.
```

### 2.6 作业脚本方式（#BSUB 指令）
```bash
cat > myjob.lsf <<'EOF'
#BSUB -J mympi
#BSUB -n 8
#BSUB -R "span[ptile=2]"
#BSUB -o /data/hpc/lsf_logs/mympi.%J.out
#BSUB -e /data/hpc/lsf_logs/mympi.%J.err
/data/hpc/lsf_bench.sh HACC_IO
EOF
bsub < myjob.lsf
```

## 三、监控作业

### 3.1 常用命令
```bash
bjobs          # 我的运行中/排队作业（实测见下）
bjobs -a       # 含历史
bjobs -A       # 数组作业汇总
bjobs -l 18    # 单作业全详情
bjobs -p       # 只看排队（并显示排队原因）
bjobs -r       # 只看运行
watch -n5 bjobs
```

实测输出（MPI 作业分配明细，EXEC_HOST 每行一个进程）：
```bash
bjobs
JOBID   USER    STAT  QUEUE   FROM_HOST  EXEC_HOST   JOB_NAME  SUBMIT_TIME
16      lsfadmi RUN   normal  node211    node212     *rial_test Sep  1 21:58
17      lsfadmi RUN   normal  node211    node212     *y_test[1] Sep  1 21:58
20      lsfadmi PEND  normal  node211                chain_b    Sep  1 21:58
```

### 3.2 在作业脚本里获取调度信息
```bash
$LSB_JOBID          # 作业号
$LSB_JOBNAME        # 作业名
$LSB_MCPU_HOSTS     # "节点1 进程数 节点2 进程数 ..."（生成 MPI hostfile 用）
$LSB_JOBINDEX       # 数组作业序号
```

## 四、作业结果查看

### 4.1 结果文件（实测路径约定）
```bash
ls /data/hpc/lsf_logs/ | tail
array.17.1.out  chainb.20.out  haccio.7.out  hacc216.15.out  ...

# 判断成功标志：日志末尾
grep "^=== " /data/hpc/lsf_logs/hacc216.15.out
=== LSF job 15 bench=HACC_IO NP=4 hosts: node216 4
=== HACC_IO exit=0        ← exit=0 即成功

# MPI 应用自身输出（HACC_IO 的吞吐）
grep -i "GiB/s" /data/hpc/lsf_logs/hacc216.15.out
```

### 4.2 历史详情
```bash
bjobs -a                          # 列表
bhist -l 15                       # 生命周期：提交→分发→完成+CPU时间
bhist 15                          # 简版
Tue Sep  1 21:58:07: Submitted from host <node211>, to Queue <normal> ...
Tue Sep  1 21:58:08: Dispatched 4 Task(s) on Host(s) <node212> <node212> ...
Tue Sep  1 21:58:09: Done successfully. The CPU time used is 0.1 seconds;
```

## 五、结果汇总统计

### 5.1 个人作业记账（实测输出）
```bash
bacct                       # 我的全部作业汇总
bacct -S 2026/09/01/20:00   # 从某时刻起
SUMMARY:      ( time unit: second )
 Total number of done jobs:      17      Total number of exited jobs:     6
 Total CPU time consumed:     160.6      Average CPU time consumed:    7.0
 Average turnaround time:        16 (seconds/job)
 Total throughput:            12.36 (jobs/hour)  during    1.86 hours
```

### 5.2 管理员视角全集群统计
```bash
bacct -u all                        # 全部用户
busers                              # 用户级 slot 占用
bacct -C 172.16.12.216/172.16.12.216   # 按执行节点过滤
```

## 六、控制自己的作业

```bash
bkill 21            # 终止
bkill -s STOP 21    # 暂停
bkill -s CONT 21    # 恢复
bstop 21 / bresume 21
bmod -n 4 21        # 改进程数（排队中）
bmod -J newname 21  # 改名
```

## 七、常见问题（FAQ）

| 问题 | 原因/解决 |
|---|---|
| 作业一直 PEND | `bjobs -p` 看原因：槽位不足则错峰；依赖未满足等前置完成 |
| 结果文件是空的 | 作业可能还在跑；或脚本无 stdout；错误看 .err |
| BTIO/MADbench 报 square number | 进程数改完全平方数（4/9/16） |
| s3d_io 报 Not a directory | 用 lsf_bench.sh 包装（已带 -d） |
| 提交被拒 not in LSF cluster | 换 lsfadmin 用户；root 不能跑 bsub |
| 输出文件权限拒绝 | /data/hpc/lsf_logs 需可写（管理员已配） |

## 八、礼貌用集群公约

- 大作业错峰提交；数组作业子任务数 ≤ 40（集群总 slot）
- 长时间作业加 `-W` 预计时限，便于调度器排队优化
- 结果文件定期清理 /data/hpc/test_out（共享盘 100G）
- 异常先自查 FAQ，再联系管理员（见《系统管理员手册》）

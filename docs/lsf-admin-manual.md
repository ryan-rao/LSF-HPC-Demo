# LSF HPC 集群 · 系统管理员手册

> 版本 v1.0 ｜ 2026-09-01 ｜ 全部命令与输出取自实际运行记录
> 集群：cluster1（master=node211，worker=212/213/215/216，40 slot）
> 登录：`ssh lsfadmin@172.16.12.211`（或 root），LSF 环境：`. /data/lsf/conf/profile.lsf`

---

## 一、集群日常巡检

### 1.1 节点状态
```bash
bhosts
HOST_NAME          STATUS       JL/U    MAX  NJOBS    RUN  SSUSP  USUSP    RSV
node211            ok              -      8      0      0      0      0      0
node212            ok              -      8      5      5      0      0      0
node213            ok              -      8      0      0      0      0      0
node215            ok              -      8      0      0      0      0      0
node216            ok              -      8      0      0      0      0      0
```
> STATUS 含义：ok（正常）/ closed_Adm（管理员关闭）/ unreach（sbatchd 断连）/ unlim（lim 断连）

### 1.2 主机与负载
```bash
lshosts        # 静态配置（型号/核数/资源）
lsload         # 实时负载
HOST_NAME       status  r15s   r1m  r15m   ut    pg  ls    it   tmp   swp   mem
node212             ok   0.0   0.0   0.1   0%   0.0   0    24   96G    0M 14.8G
node216             ok   0.0   0.2   0.2   0%   0.0   1    16   96G  14.8G ...
```

### 1.3 队列与调度器
```bash
bqueues                # 队列状态
lsadmin liminfo        # LIM 层信息
badmin qinfo normal    # 队列详细参数
```

## 二、作业监控与干预

### 2.1 运行中作业
```bash
bjobs
JOBID   USER    STAT  QUEUE   FROM_HOST  EXEC_HOST   JOB_NAME   SUBMIT_TIME
16      lsfadmi RUN   normal  node211    node212     *rial_test Sep  1 21:58
17      lsfadmi RUN   normal  node211    node212     *y_test[1] Sep  1 21:58
20      lsfadmi PEND  normal  node211                chain_b    Sep  1 21:58
```
> STAT：PEND（排队）/ RUN / DONE / EXIT / PSUSP（管理员暂停）

### 2.2 数组作业展开
```bash
bjobs -A
JOBID    ARRAY_SPEC  OWNER   NJOBS PEND DONE  RUN EXIT SSUSP USUSP PSUSP
17       array_te lsfadmin       4    0    0    4    0     0     0     0
```

### 2.3 单作业详情
```bash
bjobs -l 18
Job <18>, Job Name <mpi_2node>, User <lsfadmin>, Project <default>, Status <DONE>
 ...
Tue Sep  1 21:58:08: Dispatched 4 Task(s) on Host(s) <node212> <node212> ...
```

### 2.4 实时刷新
```bash
bjobs -w -r            # 仅运行中，宽格式
watch -n5 bjobs        # 5 秒刷新
```

### 2.5 管理干预
```bash
bkill <JOBID>                  # 终止作业
bkill -s STOP <JOBID>          # 暂停（SIGSTOP）
bkill -s CONT <JOBID>          # 恢复
bstop <JOBID> / bresume <JOBID> # 队列层暂停/恢复
bbot -f -q normal              # 队列内作业排到最前
btop -f -q normal
```

## 三、历史查询与记账汇总（实测输出）

### 3.1 全部历史
```bash
bjobs -a | head -12
JOBID   USER    STAT  QUEUE   FROM_HOST  EXEC_HOST   JOB_NAME  SUBMIT_TIME
14      lsfadmi DONE  normal  node211    node216     test216    Sep  1 21:46
15      lsfadmi DONE  normal  node211    node216     hacc216    Sep  1 21:47
16      lsfadmi DONE  normal  node211    node212     *rial_test Sep  1 21:58
17      lsfadmi DONE  normal  node211    node212     *y_test   Sep  1 21:58
...
```

### 3.2 作业生命周期历史
```bash
bhist -l 18 | grep -E "Submitted|Dispatched|Completed|CPU time"
Tue Sep  1 21:58:07: Submitted from host <node211>, to Queue <normal>, CWD <$HOME...
Tue Sep  1 21:58:08: Dispatched 4 Task(s) on Host(s) <node212> <node212> ...
Tue Sep  1 21:58:09: Done successfully. The CPU time used is 0.1 seconds;
```

### 3.3 记账汇总（bacct）
```bash
bacct
SUMMARY:      ( time unit: second )
 Total number of done jobs:      17      Total number of exited jobs:     6
 Total CPU time consumed:     160.6      Average CPU time consumed:    7.0
 Maximum CPU time of a job:   152.6      Minimum CPU time of a job:   0.0
 Total wait time in queues:    30.0      Average wait time in queue:   1.3
 Average turnaround time:        16 (seconds/job)
 Average hog factor of a job:  0.15 ( cpu time / turnaround time )
 Average expansion factor of a job:  1.69
 Total throughput:            12.36 (jobs/hour)  during    1.86 hours
 Beginning time:       Sep  1 20:06      Ending time:          Sep  1 21:58
```
按用户/时间/主机过滤：
```bash
bacct -u lsfadmin -S "2026/09/01/20:00" -E "2026/09/01/22:00"
bacct -C 172.16.12.216/172.16.12.216     # 指定执行节点
lsacct -b 2026-09-01                     # LSF 分析版
```

### 3.4 作业结果文件位置
```
作业标准输出 : /data/hpc/lsf_logs/<name>.<JOBID>.out   （-o 参数指定）
作业标准错误 : /data/hpc/lsf_logs/<name>.<JOBID>.err
MPI 应用输出 : /data/hpc/test_out/<bench>/<JOBID>/
脚本执行标记 : 日志尾 "=== <bench> exit=0" 即成功
```

## 四、集群启停与配置管理

### 4.1 守护进程启停
```bash
# 全集群重启 LIM（交互确认用 printf 应答）
su - lsfadmin -c '. /data/lsf/conf/profile.lsf; printf "y\ny\ny\n" | lsadmin reconfig'
# 重载 mbatchd 配置
su - lsfadmin -c '. /data/lsf/conf/profile.lsf; printf "y\ny\n" | badmin reconfig'
# 单节点补启客户端守护
ssh root@<node> '. /data/lsf/conf/profile.lsf; $LSF_SERVERDIR/lim; $LSF_SERVERDIR/res; $LSF_SERVERDIR/sbatchd'
```

### 4.2 节点上下线维护
```bash
badmin hclose node213     # 关闭接纳（存量作业继续跑完）
badmin hopen node213      # 恢复
badmin hboot -H node213   # 重启该节点 LSF 守护
lsadmin limboot node213
```

### 4.3 关键配置文件（共享 NFS，改 master 即全集群生效）
```
/data/lsf/conf/lsf.conf               # 全局参数（当前含 LSF_DYNAMIC_HOSTS=Y）
/data/lsf/conf/lsf.cluster.cluster1   # 节点名单（扩容加一行后 lsadmin reconfig）
/data/lsf/conf/lsbatch/cluster1/configdir/lsb.queues  # 队列定义
```

## 五、故障排查速查

| 症状 | 排查命令 | 常见根因 |
|---|---|---|
| 节点 unreach | `ssh <node> pgrep sbatchd` | sbatchd 挂了，补启 |
| 作业 PEND 不动 | `bjobs -p <ID>` | 资源不足/依赖未满足 |
| 作业 EXIT | `bjobs -le <ID>`；看 .err | 脚本权限/路径/NFS 挂载 |
| lim 异常退出 | `journalctl \| grep lim` | 报错进 syslog 而非 logdir |
| lim 静默 255 | journalctl | 缺 libnsl / 配置错误 |
| mpirun 127/255 | 查脚本 --prefix | 非登录 shell 无 MPI PATH |
| MPI ssh 失败 | 各节点 lsfadmin known_hosts | 新节点未互扫 |

## 六、REST API 管理（LWS）

```bash
# 登录取 token
TOK=$(curl -sk -X POST -H "Content-Type: application/json" \
  -d '{"name":"lsfadmin","pass":"Redhat@123"}' \
  https://node211:8448/lsf/v1/auth/logon | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')

# 远程执行管理命令（bjobs/bhosts/badmin 均可）
curl -sk -X POST -H "Authorization: $TOK" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "command=bjobs" https://node211:8448/lsf/v1/cluster/usercmd
# OpenAPI 文档：/data/lsf_inst/lws/*/openapi.yaml
```

## 七、扩容流程（详见实施手册第六部分）

关模板机拷盘 → 注入参数(LSF_SERVER_IP/VM_IP) + firstboot → master 集群文件加行 + reconfig → 补 hosts/known_hosts → bhosts 验证 → bsub 验证。全程约 15 分钟/节点。

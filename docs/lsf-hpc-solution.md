# 基于 LSF 的 HPC 解决方案

> 版本：v1.0 ｜ 日期：2026-09-01 ｜ 环境：RHEL 9.6 + KVM + IBM Spectrum LSF Community Edition 10.1
> 依据文档：《KVM虚拟机部署步骤》《LSF安装步骤》《HPC环境部署步骤》《LSF调度HPC基准集成步骤》

---

## 1. 方案概述

本方案在一台物理服务器上，通过 **KVM 虚拟化 → LSF 作业调度 → MPI 并行应用** 三层架构，
构建一套完整、可扩展、可复现的企业级 HPC 计算平台：

- **计算资源池化**：4 台虚拟机组成计算集群，LSF 统一调度，按需分配 CPU slot
- **应用标准化集成**：五种 HPC 基准（HACC_IO / HACC_OPEN_CLOSE / BTIO / MADbench / s3d_io）
  通过统一调度脚本接入，`bsub` 一条命令跨节点并行
- **管理手段多样**：命令行（bjobs/bhosts）、REST API（LWS，HTTPS:8448）、可扩展 Web 控制台
- **成本友好**：LSF 社区版免费，无需 entitlement 授权文件

---

## 2. 总体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        物理服务器 node181                             │
│                     172.16.12.181  RHEL 9.6  128核/251G              │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    KVM 虚拟化层（qemu-kvm/libvirt）              │  │
│  │              网桥 br0（物理口 ens1f0，桥接 172.16.12.0/24）      │  │
│  │                                                               │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │  │
│  │  │  node211 │ │  node212 │ │  node213 │ │  node215 │          │  │
│  │  │ master + │ │ worker   │ │ worker   │ │ worker   │          │  │
│  │  │ worker   │ │          │ │          │ │          │          │  │
│  │  │ 8C/16G   │ │ 8C/16G   │ │ 8C/16G   │ │ 8C/16G   │          │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │  │
│  │       │   NFS(/data/hpc) │ NFS(LSF_TOP) │     │                │  │
│  │       └───────┴──────┴──────┴────────────────┘                 │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 LSF 集群逻辑架构

```
┌────────────────────────── node211（Master）─────────────────────────┐
│  mbatchd（批处理主守护）── mbschd（调度器）                            │
│       │  调度决策：按 slot/ptile/资源需求分配节点                       │
│  lim（负载信息）+ res（远程执行）+ sbatchd（作业执行）                   │
│  LWS WebService（REST API，https://node211:8448/lsf/v1/...）         │
└──────────────┬──────────────────────────────────────────────────────┘
               │ LSB_MCPU_HOSTS（分配结果下发给作业）
   ┌───────────┼──────────────┬─────────────────┐
   ▼           ▼              ▼                 ▼
┌─────────┐ ┌─────────┐  ┌─────────┐      ┌─────────┐
│ node211  │ │ node212  │  │ node213  │      │ node215  │
│ lim/res/ │ │ lim/res/ │  │ lim/res/ │      │ lim/res/ │
│ sbatchd  │ │ sbatchd  │  │ sbatchd  │      │ sbatchd  │
│ 执行作业  │ │ 执行作业  │  │ 执行作业 │      │ 执行作业  │
└─────────┘ └─────────┘  └─────────┘      └─────────┘
```

### 2.2 作业执行流水线

```
 用户 ──bsub──▶ LSF 队列(normal) ──调度──▶ 选择节点 ──下发──▶ 作业脚本
                                                                    │
      ◀──bjobs── 作业状态/日志                                       ▼
                                                    ① 读取 LSB_MCPU_HOSTS
                                                    ② 动态生成 MPI hostfile
                                                    ③ mpirun 跨节点启动 N 进程
                                                    ④ HPC 应用并行执行
                                                    ⑤ 结果写入共享存储 /data/hpc
```

---

## 3. 资源规划

### 3.1 节点规划

| 节点 | IP | 角色 | vCPU | 内存 | 系统盘 | 数据盘 | LSF 角色 |
|---|---|---|---|---|---|---|---|
| node181 | 172.16.12.181 | KVM 宿主机 | 128 | 251G | - | - | 介质/ISO/跳板 |
| node211 | 172.16.12.211 | VM | 8 | 16G | 100G | 100G(/data) | **Master** + worker |
| node212 | 172.16.12.212 | VM | 8 | 16G | 100G | 100G(/data) | worker |
| node213 | 172.16.12.213 | VM | 8 | 16G | 100G | 100G(/data) | worker |
| node215 | 172.16.12.215 | VM | 8 | 16G | 100G | 100G(/data) | worker |

> 说明：172.16.12.214 被现有物理机占用，第 4 台 VM 启用 .215。

### 3.2 共享存储规划

| 共享路径 | 提供者 | 挂载点 | 用途 |
|---|---|---|---|
| node181:/mnt/iso | node181 | /mnt/iso（只读） | RHEL 9.6 本地 yum 源 |
| node211:/data/lsf | node211 | /data/lsf | LSF_TOP（LSF 安装与配置，四节点共享） |
| node211:/data/hpc | node211 | /data/hpc | HPC 应用、介质、作业输出（四节点共享） |

### 3.3 关键软件规划

| 组件 | 版本 | 部署位置 | 说明 |
|---|---|---|---|
| IBM Spectrum LSF | Community Edition 10.1.0.15 | /data/lsf（共享） | 社区版，免授权 |
| LSF WebService | 10.1.0.16 | node211 /opt/ibm/lsfsuite | REST API，systemd 服务 lwsd |
| OpenMPI | 4.1.1（rpm） | 各节点 /usr/lib64/openmpi | 主 MPI 运行时 |
| MPICH | 4.1.1（rpm） | 各节点 /usr/lib64/mpich | 备用 MPI |
| GCC 工具链 | 11.5.0 + make/cmake | 各节点 | 编译环境 |
| HPC-Bench | 五基准 | /data/hpc/hpc-bench-main | IO/计算评测应用 |

### 3.4 账户规划

| 账户 | 密码 | 用途 | 备注 |
|---|---|---|---|
| root | Redhat@123 | 系统管理 | 四节点 + 宿主机互信 |
| lsfadmin | Redhat@123 | **LSF 主管理员/作业用户** | 四节点 SSH 全互信（公钥+私钥+known_hosts） |

---

## 4. 部署实施（按序执行，详见对应文档）

### 阶段一：KVM 虚拟机（参考《KVM虚拟机部署步骤》）

```
宿主机装虚拟化 → 建网桥 br0 → ISO 放 /home/kvm/ → kickstart 批量装 4 台 VM
→ virt-customize 开 PermitRootLogin → hosts 互解 + root 免密
```
关键点：kickstart 用显式分区（autopart 会卡死 anaconda）；qemu 读不了 /root 下的 ISO。

### 阶段二：LSF 集群（参考《LSF安装步骤》）

```
① 四节点装依赖：libnsl、ed、info（ISO rpm）+ 建 lsfadmin 用户
② node211 解压安装器，编辑 install.config：
     LSF_TOP=/data/lsf  LSF_CLUSTER_NAME=cluster1  LSF_MASTER_LIST=node211
     LSF_ADMINS=lsfadmin  LSF_TARDIR=介质目录
     LSF_ADD_SERVERS="node211 node212 node213 node215"
③ printf "1\ny\ny\ny\n" | ./lsfinstall -f install.config   # 1=接受license
④ 四节点执行 hostsetup --top=/data/lsf --boot=y --start=n --profile=y --silent
⑤ NFS 共享 LSF_TOP；worker 清理旧 /etc/lsf.conf 残留
⑥ 启动：各节点 lim/res/sbatchd，master 再起 mbatchd
⑦ 验证：lsid → lshosts → lsload → bhosts 全 ok
```

### 阶段三：HPC 环境（参考《HPC环境部署步骤》）

```
① node181 导出 ISO 为 NFS 源 → 四节点配本地 yum repo
② dnf groupinstall "Development Tools" + openmpi/mpich/cmake/numactl-devel
③ node211 建 /data/hpc NFS 共享，拷入 hpc-bench-main 介质
④ 四节点 ~/.bashrc 配 MPI 路径（MPI_HOME=/usr/lib64/openmpi）
⑤ 四节点 cmake 编译安装 → 产出 5 个基准二进制
⑥ 验证：mpirun --map-by node 跨节点 hello；HACC_IO 实测跑通
```

### 阶段四：LSF × HPC 集成（参考《LSF调度HPC基准集成步骤》）

```
① lsfadmin 四节点 SSH 全互信（公钥+私钥+known_hosts 全量分发）
② /data/hpc 开放写权限
③ 部署通用调度脚本 /data/hpc/lsf_bench.sh（见下章）
④ 逐个 bsub 测试五基准 → 全部 exit=0
```

---

## 5. HPC 应用集成

### 5.1 通用调度脚本设计（/data/hpc/lsf_bench.sh）

脚本核心逻辑（适用于任何 MPI 应用）：

```bash
#!/bin/bash
BENCH=$1                                    # 基准名
# ① MPI 环境（LSF 作业是非登录 shell，必须显式设）
export MPI_HOME=/usr/lib64/openmpi
export PATH=$MPI_HOME/bin:$PATH
export LD_LIBRARY_PATH=$MPI_HOME/lib:$LD_LIBRARY_PATH

# ② 感知 LSF 分配结果，动态生成 hostfile
#    LSB_MCPU_HOSTS 格式："host1 slot数 host2 slot数 ..."
HF=/tmp/hf.$LSB_JOBID; : > $HF
set -- $LSB_MCPU_HOSTS
while [ $# -ge 2 ]; do echo "$1 slots=$2" >> $HF; shift 2; done
NP=$(awk -F"slots=" '{s+=$2} END{print s}' $HF)

# ③ 启动 MPI 应用（--prefix 解决远端节点 PATH 问题）
mpirun --allow-run-as-root --prefix $MPI_HOME --hostfile $HF -np $NP \
  /data/hpc/hpc-bench-main/bin/$BENCH <应用参数...>
```

**设计要点：** 不写死节点名——无论 LSF 把作业调到哪几台，脚本自动适配，
这是"调度器与 MPI 解耦"的关键，扩容新节点零改动。

### 5.2 五基准参数与调度约束速查表

| 基准 | bsub 提交 | 进程约束 | 应用参数 |
|---|---|---|---|
| HACC_IO | -n 8 -R "span[ptile=2]" | 无 | 粒子数 输出目录 -w/-r |
| HACC_OPEN_CLOSE | -n 8 -R "span[ptile=2]" | 无 | 粒子数 输出目录 |
| s3d_io | -n 8 -R "span[ptile=2]" | -p 乘积 = 进程数 | -g 32,32,32 -p 2,2,2 -i 1 **-d 目录** |
| BTIO | **-n 4** -R "span[ptile=1]" | **完全平方数** | -m w -t 0 -g 32,32,32 -i 1 -o 目录 |
| MADbench | **-n 4** -R "span[ptile=1]" | **平方数且整除 n_bin** | 512 NP 1 UNIQUE 目录 |

> ⚠️ 高频踩坑：BTIO/MADbench 用 8 进程必报 "square number" 错误；
> s3d_io 不带 -d 会报 MPI_File_open "Not a directory"。

### 5.3 集成新应用的三步法

1. **本地验证**：先在单节点用 mpirun 直接跑通，确认参数格式（必要时查源码 getopt）
2. **适配脚本**：在 lsf_bench.sh 加一个 case 分支，写对参数和输出目录
3. **LSF 验证**：bsub 提交 → bjobs 看分配 → 日志确认 exit=0 → 检查输出文件

---

## 6. 方案使用手册

### 6.1 日常启停

```bash
# 集群启动（如重启后）：四节点 + master
for H in node211 node212 node213 node215; do
  ssh $H ". /data/lsf/conf/profile.lsf; \$LSF_SERVERDIR/lim; \$LSF_SERVERDIR/res; \$LSF_SERVERDIR/sbatchd"
done
ssh node211 ". /data/lsf/conf/profile.lsf; \$LSF_SERVERDIR/mbatchd"

# 集群停止（可选）：lim 需加 -z 参数优雅退出
```
> hostsetup --boot=y 已配置开机自启，正常重启无需手工干预。

### 6.2 提交作业

```bash
su - lsfadmin   # 切到 LSF 管理员
. /data/lsf/conf/profile.lsf

# 一键跑基准（推荐）
bsub -J haccio -n 8 -R "span[ptile=2]" -o /data/hpc/lsf_logs/%J.out \
     /data/hpc/lsf_bench.sh HACC_IO

# 交互式作业（直接占终端）
bsub -Is -n 8 /bin/bash

# 常用资源控制
# -n 16                申请16 slot（超集群总量会排队）
# -R "span[ptile=1]"   每节点1进程（最大分散）
# -R "span[hosts=1]"   全部进程挤在单节点（最大聚合）
# -q queue名           指定队列（当前默认 normal）
```

### 6.3 监控与查询

```bash
bjobs          # 我的作业状态（RUN/PEND/DONE）
bjobs -a       # 含历史作业
bhosts         # 节点状态与 slot 占用
lshosts        # 节点配置信息
lsload         # 实时负载（CPU/内存/交换）
bqueues        # 队列状态
bjobs -l <ID>  # 作业详情（分配了哪些节点）
tail -f /data/hpc/lsf_logs/<ID>.out   # 作业日志
```

### 6.4 REST API 使用（供程序/平台集成）

```bash
BASE=https://node211:8448
# ① 登录拿 token
TOK=$(curl -sk -X POST -H "Content-Type: application/json" \
  -d '{"name":"lsfadmin","pass":"<密码>"}' \
  $BASE/lsf/v1/auth/logon | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
# ② 执行 LSF 命令
curl -sk -X POST -H "Authorization: $TOK" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "command=bjobs" $BASE/lsf/v1/cluster/usercmd
# ③ 集群信息
curl -sk -H "Authorization: $TOK" $BASE/lsf/v1/cluster
```
> 证书为自签名，客户端需 `curl -k` 或导入 CA。
> 图形化控制台需另购 IBM Spectrum LSF Application Center，当前未部署。

### 6.5 健康检查清单（故障排查顺序）

```
① bhosts 全 ok？ ──否──▶ 该节点 lim/sbatchd 是否活着（ps）
② lsload 正常？  ──否──▶ 看 syslog/journalctl（LSF 错误默认进 syslog）
③ 作业 PEND？    ──▶ bjobs -l 看原因；slot 是否被占满
④ MPI 作业失败？ ─▶ 依次查：lsfadmin SSH 互信 → NFS 挂载 → 应用参数（-d 目录等）
⑤ 作业日志去哪了 ─▶ /data/hpc/lsf_logs/，stdout/stderr 分文件
```

---

## 7. 扩展路线

| 方向 | 做法 | 收益 |
|---|---|---|
| 算力扩容 | 宿主机再建 VM（照 KVM 文档）→ hostsetup 加节点 → 集群文件加一行 | 10 分钟级扩容 |
| 真实业务应用 | 按 5.3 三步法集成（本地验证→适配脚本→bsub 验证） | 任何 MPI 程序 |
| 队列分级 | lsb.queues 增加队列（如 debug/long），分 slot 配额 | 多租户隔离 |
| 资源管理 | lsf.shared/lsf.cluster 定义资源（mem/gpu），bsub -R 过滤 | 精细调度 |
| 性能基线 | 用五基准扫不同 ptile/规模，建立存储-网络-计算基线 | 容量规划依据 |
| Web 控制台 | 申请 IBM Spectrum LSF Application Center | 图形化管理 |

---

## 8. 已验证的测试基线（2026-09-01）

| 测试项 | 结果 | 说明 |
|---|---|---|
| LSF 集群健康 | ✅ | 4 节点 × 8 slot，lshosts/lsload/bhosts 全 ok |
| LSF 基础调度 | ✅ | sleep 作业 DONE（Job 1/2） |
| 跨节点 MPI | ✅ | 8 rank 均布 4 节点 |
| HACC_IO | ✅ Job 7 | 8×100万粒子，0.31GiB/151s |
| BTIO | ✅ Job 8 | np=4，写测试通过 |
| MADbench | ✅ Job 9 | np=4，UNIQUE 模式 |
| s3d_io | ✅ Job 13 | 8 rank，.nc 数据文件落盘 |
| HACC_OPEN_CLOSE | ✅ Job 11 | 8 rank 通过 |
| REST API | ✅ | 登录/bhosts/bsub 全通（HTTPS:8448） |

---

*文档结束。部署细节请配合引用的四份步骤文档使用；遇到问题先查 6.5 排查清单。*

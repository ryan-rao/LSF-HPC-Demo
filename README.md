# LSF HPC Demo — 高性能计算调度演示平台

基于 IBM Spectrum LSF 构建的 HPC 解决方案演示环境，覆盖**集群部署 → 作业调度 → HPC 应用运行 → 监控告警**的全链路。本仓库为统一 monorepo，包含全部自研代码。

---

## 一、方案架构

**拓扑总览**（5 初始节点 × 8 槽 = 40 槽起步，支持参数化扩容到任意节点数）：

```
┌─────────────────────────────────────────────────────────────┐
│  Demo Portal 容器 (node181:8080, 需登录 admin/lsfhpcdemo)    │
│  FastAPI + 前端页面 + Ansible 任务 + 作业提交/监控            │
└──────────────┬──────────────────────────────┬───────────────┘
               │ SSH/bsub                     │ iframe 嵌入
               ▼                              ▼
┌──────────────────────────┐   ┌──────────────────────────────┐
│  LSF 集群 cluster1       │   │ Grafana(:3000) 15面板大盘    │
│  node211 Master + 计算   │   │ Prometheus(:9090) TSDB       │
│  node212/213/215/219     │   │ node_exporter(:9100) ×N      │
│  /data/hpc NFS 共享      │   │ lsf_exporter(:9109) 自研     │
└──────────────────────────┘   └──────────────────────────────┘
```

| 组件 | 说明 |
|------|------|
| LSF Master (node211) | mbatchd 调度核心，NFS 导出 /data/lsf 与 /data/hpc |
| 计算节点 | KVM 虚机，每节点 8 slot，lsfd.service 管理守护 |
| Demo Portal | 任务执行页一键提交 LSF/HPC 作业；Ansible 全生命周期管理（安装/配置/测试/扩容/缩容） |
| 监控栈 | Prometheus 采集 node_exporter + lsf_exporter，Grafana 可视化 |
| KVM 宿主机 (node181) | 模板机 node212 黄金镜像，新节点按需克隆部署 |

## 二、HPC 应用场景与背景

| 应用 | 场景背景 |
|------|----------|
| HACC_IO | 宇宙学模拟粒子集体 IO（Argonne 实验室） |
| HACC_OPEN_CLOSE | HACC 变体：元数据与小 IO 压力 |
| BTIO | NAS Parallel Benchmark 块状 IO（CFD 检查点） |
| MADbench | 宇宙微波背景分析 IO（MAP/Planck 卫星） |
| s3d_io | 湍流燃烧直接数值模拟 IO |
| MIXED 混合应用 | 六阶段流水线（串行→MPI→数组→IO→依赖链→校验），~30min |
| STRESS 压力测试 | 3 批次×7 子作业 48 槽压满集群，~15min |

## 三、Demo 中 HPC 如何使用

1. **登录**：浏览器访问 `http://<host>:8080`，账号 `admin / lsfhpcdemo`
2. **提交作业**：「任务执行」页选择 HPC 应用 → EXECUTE，等价
   `bsub -J demo_HACC_IO -n 8 -R "span[ptile=2]" -o /data/hpc/lsf_logs/%J.out /data/hpc/lsf_bench.sh HACC_IO`
3. **监控**：「LSF 集群」页实时 bhosts/bqueues/bjobs（5/10/20/30 秒自动刷新 + 负载趋势图）；「性能监控」页内嵌 Grafana
4. **查看结果**：「作业历史」页回放终端输出；日志在 `/data/hpc/lsf_logs/`
5. **扩容/缩容**（参数化，输入 IP 即可）：
   - 「新节点部署+加入 LSF」：输入 Master IP + 新节点 IP（可选主机名）→ 镜像克隆→入集群→验证全自动
   - 「删除 LSF 节点与 VM」：输入节点 IP → 出集群→销毁 VM→删镜像（初始节点受保护）
6. **取消作业**：执行页「取消全部作业」一键 bkill

> 门户页面的可视化介绍见 `lsf-hpc-demo/backend/static/intro.html`（含 SVG 架构图与页面截图）。

## 四、HPC 应用与 LSF 的集成

| 环节 | 实现 |
|------|------|
| 通用调度脚本 | 所有基准经 `/data/hpc/lsf_bench.sh` 统一入口，从 `$LSB_MCPU_HOSTS` 动态生成 MPI hostfile |
| 槽位↔进程映射 | `-n 8 -R "span[ptile=2]"` → 4 节点×2 slot，MPI rank 与 slot 对齐 |
| 共享存储 | master NFS 导出 /data/hpc，全节点读写 |
| 免密互信 | lsfadmin 全节点 SSH 互信（MPI 可能从任意首节点发起） |
| 并行环境 | OpenMPI，mpirun `--prefix` 解决非交互 SSH 的 PATH |
| 应用约束 | BTIO/MADbench 需平方数进程；s3d_io 必须指定 -d 输出目录 |
| 状态回流 | 门户轮询 bjobs 至 DONE/EXIT，解析带宽/GiB/exit code 汇总展示 |
| 指标采集 | 自研 lsf_exporter：bjobs/bhosts → Prometheus 指标（作业状态/槽位/队列/24h 完成量） |

---

## 五、仓库结构

```
├── ansible/        # 集群自动化：site.yml + 14 roles（安装/配置/集成/测试/镜像/扩缩容）
├── lsf-hpc-demo/   # Web 门户：FastAPI 后端 + 前端 + 登录认证 + 离线 wheels
├── monitoring/     # 监控栈：lsf_exporter + Prometheus + Grafana 配置 + deploy.sh
├── docs/REBUILD.md # 全新环境重建手册（含介质清单与执行顺序）
└── README.md       # 本文件
```

## 六、快速开始

```bash
# 1) 集群部署（前置：介质就位、inventory/group_vars 已按环境修改）
cd ansible
ansible-playbook site.yml --tags install        # LSF 安装
ansible-playbook site.yml --tags config         # 集群配置
ansible-playbook site.yml --tags integration    # HPC 基准 + 互信 + 脚本分发
ansible-playbook site.yml --tags test           # 五基准验证（全 DONE）

# 2) 监控栈
bash monitoring/deploy.sh <master_ip>

# 3) 门户
cd lsf-hpc-demo && cp .env.example .env   # 填写地址/密码
podman build --network=host -t lsf-hpc-demo:latest .
podman run -d --name lsf-hpc-demo --network host --user 0 --security-opt label=disable \
  --env-file .env --entrypoint uvicorn -v .ssh:/sshkey:ro \
  -v <ansible目录>:/mnt/ansible:ro -v /var/lib/lsf-demo:/var/lib/lsf-demo \
  lsf-hpc-demo:latest app:app --host 0.0.0.0 --port 8080 --app-dir /app/backend --workers 1
```

完整重建步骤与验证清单见 [docs/REBUILD.md](docs/REBUILD.md)。

## 七、注意事项

- **介质不入库**：LSF 安装包（*.tar.Z ~1.7G）、hpc-bench-main 源码、容器镜像需单独备份（见 REBUILD.md 前置条件）
- **机密不入库**：`.env`、`.ssh/` 已 gitignore；登录密码可用环境变量 `DEMO_USER/DEMO_PASS` 覆盖
- 演示期间请勿重启门户容器（会中断作业轮询，LSF 侧作业不受影响）
- 集群当前规模：9 节点 72 槽（211/212/213/215/219 + 参数化扩容的 220/221/222/224）

---
*LSF HPC Demo · 更新: 2026-09-08*

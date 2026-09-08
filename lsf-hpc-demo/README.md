# LSF HPC Demo Portal

真实执行的 LSF HPC 演示门户：Web → Ansible → LSF → HPC 应用 → 真实输出回显。

## 架构

- **前端**: 单页应用（深色终端风），无构建依赖
- **后端**: FastAPI（容器内 8000 端口）
- **Grafana 代理**: nginx 8081 端口（反代 172.16.12.182:30000，去除 X-Frame-Options 以支持 iframe）
- **执行链**: 容器 --ssh--> 181 (ansible-playbook) / 211 (bsub/bjobs/lsf_bench.sh)

## 任务白名单（映射 /home/lsf/ansible/site.yml 真实 roles/tags）

| 分类 | 任务 | site.yml tag |
|---|---|---|
| LSF | 安装/配置/状态检查/卸载 | lsf_install / lsf_config / lsf_test / lsf_uninstall |
| HPC | 安装/环境配置/功能测试/卸载/集成验证 | hpc_install / hpc_config / hpc_test / hpc_uninstall / integrate |
| HPC Applications | HACC_IO / HACC_OPEN_CLOSE / s3dio / BTIO / MADbench | bsub 直接经 lsf_bench.sh 提交 LSF |
| 集群扩容 | 镜像制作/节点部署/节点删除 | image / deploy / remove (⚠ 高风险) |

## 部署（在 172.16.12.181 上）

```bash
cd /home/lsf/lsf-hpc-demo
podman build -t lsf-hpc-demo .
podman run -d --name lsf-hpc-demo \
  -p 8080:8000 -p 8081:8081 \
  -v /home/lsf/ansible:/mnt/ansible:ro \
  -v /var/lib/lsf-demo:/var/lib/lsf-demo \
  --env-file .env lsf-hpc-demo
```

访问: http://172.16.12.181:8080/
Grafana 性能页内嵌于 Web（经 8081 代理），原始地址: http://172.16.12.182:30000/

## API

```
GET  /api/health | /api/tasks | /api/jobs | /api/jobs/{id} | /api/jobs/{id}/output
POST /api/jobs {task_id} | /api/jobs/{id}/cancel
GET  /api/cluster | /api/dashboards
```

## 说明

- 环境中不存在 uid 为 `lsf-hpc` 的 Grafana dashboard，实际可用的是 GPFS 系列
  (gpfs-cluster-health / gpfs-overview 等)，Web 页面提供下拉切换。
- 作业日志持久化于 /var/lib/lsf-demo/jobs/<job_id>/ (metadata.json / stdout.log / hpc.log)，
  容器重启后历史保留。

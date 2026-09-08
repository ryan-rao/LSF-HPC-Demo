# LSF HPC Demo 统一仓库

- ansible/       集群自动化（site.yml + 14 roles）
- lsf-hpc-demo/  Web 门户（FastAPI + 前端，podman 容器）
- monitoring/    监控栈（lsf_exporter + Prometheus + Grafana，deploy.sh 一键部署）
- docs/REBUILD.md 全新环境重建手册

LSF 安装介质（*.tar.Z）与 hpc-bench-main 源码不入库，见重建手册「前置条件」。

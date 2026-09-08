# LSF HPC Demo 环境 — 全新重建手册

## 一、前置条件
1. **硬件/网络**：1 台 KVM 宿主机/控制机（如 172.16.12.181，RHEL9 + libvirt + podman + ansible），
   1 台 master、≥4 台计算节点（KVM 虚机或物理机，RHEL9，root SSH 可达）
2. **介质目录**（不入 git，需单独备份到离线介质库）：
   - /home/lsf/lsf10.1_lsfinstall_linux_x86_64.tar.Z（131M）
   - /home/lsf/lsf10.1_lnx310-lib217-x86_64.tar.Z（867M）
   - /home/lsf/hpc-bench-main/（HPC 基准源码，800K，可入 git LFS 或介质库）
   - node_exporter-1.8.2 linux-amd64（各节点 :9100）
   - prometheus/grafana 容器镜像（离线 load）
3. **三个代码仓库**（git）：ansible/（集群自动化）、lsf-hpc-demo/（门户）、monitoring/（监控栈）

## 二、重建步骤（按序）
1. **网络与互信**：控制机→各节点 root 免密（`ssh-copy-id`）；各节点主机名按 nodeXXX 规划
2. **ansible 仓库**：
   - 改 `inventory/hosts`（IP 清单）和 `group_vars/all.yml`（node_ips、密码、介质路径）
   - 模板机先手工装好 LSF 客户端+OpenMPI+HPC（或首次跑 site.yml 的 install/config 打到 node212，再将其定为模板）
   - `ansible-playbook site.yml --tags install`   # LSF 安装（master+workers）
   - `ansible-playbook site.yml --tags config`    # 集群配置
   - `ansible-playbook site.yml --tags integration` # HPC 基准+互信+lsf_bench/mixed/stress
   - 验证: `--tags test`（五基准 bsub 全 DONE）
3. **监控栈**：`bash monitoring/deploy.sh <master_ip>`（exporter+prometheus+grafana）
4. **门户**：
   - `cd lsf-hpc-demo && cp .env.example .env`（填 LSF/SSH/Grafana 地址密码）
   - `podman build --network=host -t lsf-hpc-demo:latest .`
   - `podman run -d --name lsf-hpc-demo --network host --user 0 --security-opt label=disable \
      --env-file .env --entrypoint uvicorn -v .ssh:/sshkey:ro -v <ansible目录>:/mnt/ansible:ro \
      -v /var/lib/lsf-demo:/var/lib/lsf-demo lsf-hpc-demo:latest app:app --host 0.0.0.0 --port 8080 \
      --app-dir /app/backend --workers 1`
5. **验证**：门户 :8080 首页 → LSF 集群页 bhosts 全 ok → 跑一个 HPC 基准 → Grafana :3000 有数据

## 三、扩容/缩容（参数化，已验证）
- 部署新节点：门户「新节点部署+加入 LSF」输入 Master IP + 新节点 IP（镜像克隆→入集群→验证全自动）
- 删除节点：门户「删除 LSF 节点与 VM」输入节点 IP（出集群→销毁 VM→删镜像；初始节点受保护）

## 四、安全注意
- `.env`、`.ssh/`、`ansible.log`、各密码（group_vars 中 lsf_admin_pass）不入 git
- grafana 数据目录 /var/lib/grafana、prometheus TSDB /var/lib/prometheus 不入 git（可备份）

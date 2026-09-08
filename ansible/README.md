# LSF HPC 平台 Ansible 自动化部署方案

## 目录结构
```
ansible/
├── ansible.cfg / inventory/hosts / group_vars/all.yml / site.yml
├── dev/                    # 开发与测试脚本
│   ├── dev-check.sh        # 语法+连通性检查
│   ├── test-lsf.sh         # LSF 测试（T1-T4）
│   ├── test-hpc.sh         # HPC/集成测试（H1-H3, I1-I2）
│   └── run-all.sh          # 一键 install->config->test
└── roles/
    ├── lsf_install   # 依赖/用户/介质/lsfinstall/NFS/hostsetup
    ├── lsf_config    # 守护进程启动与就绪验证
    ├── lsf_test      # T1 lsid / T2 lshosts / T3 bhosts ok / T4 bsub DONE
    ├── lsf_uninstall # 停守护/卸 NFS/清目录
    ├── hpc_install   # 工具链+openmpi/mpich/cmake
    ├── hpc_config    # 共享盘/环境变量/编译五基准
    ├── hpc_test      # H1 二进制 / H2 本地 MPI / H3 跨节点 MPI
    ├── hpc_uninstall # 卸载共享盘/清目录
    ├── lsf_hpc_integration  # lsfadmin 全互信 + lsf_bench.sh + 五基准调度验证
    ├── kvm_image_build # 模板机拷盘 + virt-customize 定制（LSF服务器IP/虚机IP 两参数）
    ├── node_deploy     # 镜像部署新节点 + 收录集群 + D1-D11 验证
    └── node_remove     # 删除节点（退集群 R1-R9 + 销毁 VM/镜像）
```

## 前置条件
1. 控制机（node181）已有 ansible-core，可 SSH 到全部 VM（root/Redhat@123）
2. 介质在控制机：/home/lsf/{lsf10.1_lsfinstall*,lsf10.1_lnx310-lib217*}.tar.Z
3. 基准源码在控制机：/home/lsf/hpc-bench-main/
4. node181 已导出 /mnt/iso（NFS，yum 源）
5. VM 已有 /data 分区（第二块盘）

## 使用
```bash
cd /home/lsf/ansible
./dev/dev-check.sh                    # 语法+连通性
ansible-playbook site.yml --tags install    # 安装 LSF+HPC
ansible-playbook site.yml --tags config     # 配置启动
ansible-playbook site.yml --tags test       # 功能测试
ansible-playbook site.yml --tags uninstall  # 卸载
./dev/run-all.sh                      # 一键全流程
./dev/test-deploy.sh                  # 制作镜像+部署新节点（默认 node217）
./dev/test-remove.sh                  # 删除节点（默认 node217）
```

## 扩容
inventory 加主机 + group_vars 的 node_ips 加一行 → 重跑 install/config 即可。

## 测试断言清单
| 编号 | 内容 | 通过标准 |
|---|---|---|
| T1-T4 | LSF | lsid 含 IBM Spectrum LSF；节点数达标；bhosts 全 ok；bsub→DONE |
| H1-H3 | HPC | 五基准二进制存在；本地 MPI 2 rank ok；跨节点覆盖全部节点 |
| I1-I2 | 集成 | lsfadmin 全互信；五基准经 LSF 调度 exit=0 |
| D1-D11 | 扩容 | 新节点环境就绪；自动入集群 ok；bsub 作业 DONE；HACC_IO exit=0 |
| R1-R9 | 缩容 | 守护停止；集群文件移除；VM 销毁；集群无该节点 |

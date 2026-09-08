#!/bin/bash
# 开发检查：语法 + 参数完整性
cd "$(dirname "$0")/.."
echo "== 语法检查 =="
ansible-playbook site.yml --syntax-check || exit 1
echo "== 主机清单 =="
ansible lsf_cluster --list-hosts
echo "== 连通性 =="
ansible lsf_cluster -m ping -o


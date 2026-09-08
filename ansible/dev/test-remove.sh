#!/bin/bash
# 删除节点（退出 LSF 集群 + 销毁 KVM VM）
# 用法: ./dev/test-remove.sh [-e remove_node_name=node218 -e remove_node_ip=172.16.12.218]
cd "$(dirname "$0")/.."
ansible-playbook site.yml --tags remove "$@"

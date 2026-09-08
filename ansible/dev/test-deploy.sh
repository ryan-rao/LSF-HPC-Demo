#!/bin/bash
# 镜像制作 + 新节点部署 + 入集群验证（D1-D11）
# 用法: ./dev/test-deploy.sh [-e new_node_name=node218 -e new_node_ip=172.16.12.218 -e new_node_mac=52:54:00:12:00:d9]
cd "$(dirname "$0")/.."
ansible-playbook site.yml --tags image "$@"
ansible-playbook site.yml --tags deploy "$@"


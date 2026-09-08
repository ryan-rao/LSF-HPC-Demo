#!/bin/bash
# 一键全生命周期：安装->配置->集成->测试
cd "$(dirname "$0")/.."
set -e
ansible-playbook site.yml --tags install
ansible-playbook site.yml --tags config
ansible-playbook site.yml --tags test
echo "=== 全流程完成 ==="


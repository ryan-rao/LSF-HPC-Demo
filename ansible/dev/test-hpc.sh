#!/bin/bash
# 测试脚本：HPC + 集成（H1-H3, I1-I2）
cd "$(dirname "$0")/.."
ansible-playbook site.yml --tags hpc_test "$@"
ansible-playbook site.yml --tags integrate --skip-tags config "$@"


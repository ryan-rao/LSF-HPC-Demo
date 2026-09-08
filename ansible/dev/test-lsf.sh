#!/bin/bash
# 测试脚本：LSF 功能（T1-T4）
cd "$(dirname "$0")/.."
ansible-playbook site.yml --tags lsf_test "$@"


#!/bin/bash
# 监控栈部署：lsf_exporter → master(:9109) + Prometheus/Grafana → 控制机(:9090/:3000)
# 用法: 在控制机(181)上 bash deploy.sh <master_ip>
set -e
MASTER=${1:-172.16.12.211}
DIR=$(cd "$(dirname "$0")" && pwd)

# 1) lsf_exporter 到 master（systemd 常驻）
scp -o StrictHostKeyChecking=no "$DIR/lsf_exporter.py" root@$MASTER:/usr/local/bin/lsf_exporter.py
scp -o StrictHostKeyChecking=no "$DIR/lsf-exporter.service" root@$MASTER:/etc/systemd/system/lsf-exporter.service
ssh root@$MASTER 'systemctl daemon-reload && systemctl enable --now lsf-exporter && systemctl is-active lsf-exporter'

# 2) Prometheus 容器（host network, :9090）
podman rm -f lsf-prometheus >/dev/null 2>&1 || true
podman run -d --name lsf-prometheus --network host \
  -v $DIR/prometheus.yml:/etc/prometheus/prometheus.yml:ro \
  -v /var/lib/prometheus:/prometheus \
  quay.io/prometheus/prometheus:v2.53.0 \
  --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus

# 3) Grafana 容器（host network, :3000, 匿名查看, 自动 provisioning）
podman rm -f lsf-grafana >/dev/null 2>&1 || true
podman run -d --name lsf-grafana --network host \
  -e GF_AUTH_ANONYMOUS_ENABLED=true -e GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer \
  -e GF_AUTH_DISABLE_LOGIN_FORM=true \
  -v $DIR/provisioning:/etc/grafana/provisioning:ro \
  -v $DIR/dashboards:/var/lib/grafana/dashboards:ro \
  -v /var/lib/grafana:/var/lib/grafana \
  docker.io/grafana/grafana:11.2.0

echo "监控栈部署完成: exporter=$MASTER:9109 prometheus=:9090 grafana=:3000"

#!/bin/sh
set -e
GRAFANA_URL="${GRAFANA_URL:-http://172.16.12.182:30000}"
GRAFANA_HOST=$(echo "$GRAFANA_URL" | sed -E 's#https?://([^/:]+).*#\1#')
GRAFANA_UPSTREAM=$(echo "$GRAFANA_URL" | sed -E 's#(https?://[^/]+).*#\1#')
sed -e "s/GRAFANA_UPSTREAM/${GRAFANA_UPSTREAM//\//\\/}/g" -e "s/\$grafana_host/${GRAFANA_HOST}/" \
    /app/config/nginx.conf.tmpl > /etc/nginx/nginx.conf
mkdir -p /var/lib/lsf-demo/jobs /run
nginx
exec uvicorn app:app --host 0.0.0.0 --port 8000 --app-dir /app/backend --workers 1

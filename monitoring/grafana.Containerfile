FROM quay.io/ansible/ansible-runner:latest
COPY grafana/ /grafana/
ENV GF_PATHS_DATA=/grafana/data GF_PATHS_PLUGINS=/grafana/plugins GF_PATHS_PROVISIONING=/grafana/conf/provisioning GF_SERVER_HTTP_ADDR=0.0.0.0
ENTRYPOINT ["/grafana/bin/grafana","server","--homepath=/grafana"]

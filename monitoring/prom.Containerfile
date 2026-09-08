FROM quay.io/ansible/ansible-runner:latest
COPY prom/ /prometheus/
VOLUME /prometheus/data
ENTRYPOINT ["/prometheus/prometheus","--config.file=/etc/prometheus/prometheus.yml","--storage.tsdb.path=/prometheus/data"]

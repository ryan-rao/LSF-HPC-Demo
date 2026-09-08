#!/usr/bin/env python3
"""LSF metrics exporter for Prometheus (port 9109, node211).

Runs as a simple HTTP server; on /metrics scrape it executes LSF commands
(bjobs/bhosts/bqueues/bhosts -a) as lsfadmin and converts to Prometheus gauges.
Designed for demo environments (single-threaded, on-demand collection).
"""
import http.server
import re
import subprocess
import sys

LSF_ENV = ". /data/lsf/conf/profile.lsf"


def sh(cmd):
    p = subprocess.run(f"su - lsfadmin -c '{LSF_ENV}; {cmd}'", shell=True,
                       capture_output=True, text=True, timeout=30)
    return p.stdout, p.returncode


def parse_bjobs():
    out, _ = sh('bjobs -a -noheader -o "stat queue"')
    stats = {}   # stat -> count
    queues = {}  # queue -> count
    for line in out.splitlines():
        f = line.split()
        if len(f) >= 2:
            stats[f[0]] = stats.get(f[0], 0) + 1
            queues[f[1]] = queues.get(f[1], 0) + 1
    return stats, queues


def parse_bhosts():
    out, _ = sh("bhosts")
    hosts = []
    # default: HOST_NAME STATUS JL/U MAX NJOBS RUN SSUSP USUSP RSV
    for line in out.splitlines():
        f = line.split()
        if len(f) >= 6 and f[3].isdigit():
            hosts.append(dict(name=f[0], status=f[1], njobs=int(f[4]),
                              nrun=int(f[5]), npend=0, maxslots=int(f[3])))
    return hosts


def parse_hist_24h(stats):
    # bhist has no usable output in this env; use bjobs -a DONE/EXIT counts
    return stats.get("DONE", 0), stats.get("EXIT", 0)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        lines = []
        try:
            stats, queues = parse_bjobs()
            # always emit canonical states so panels never lose series (No Data fix)
            for st in ("RUN", "PEND", "DONE", "EXIT", "SSUSP", "USUSP", "PSUSP"):
                stats.setdefault(st, 0)
            for st, n in stats.items():
                lines.append(f'lsf_jobs_state{{stat="{st}"}} {n}')
            lines.append(f'lsf_jobs_total {sum(stats.values())}')
            for q, n in queues.items():
                lines.append(f'lsf_jobs_queue{{queue="{q}"}} {n}')

            hosts = parse_bhosts()
            for h in hosts:
                hn = h["name"]
                ok = 1 if h["status"] == "ok" else 0
                lines.append(f'lsf_host_status_ok{{host="{hn}"}} {ok}')
                lines.append(f'lsf_host_slots_max{{host="{hn}"}} {h["maxslots"]}')
                lines.append(f'lsf_host_slots_busy{{host="{hn}"}} {h["nrun"]}')
                lines.append(f'lsf_host_jobs_pending{{host="{hn}"}} {h["npend"]}')
            lines.append(f'lsf_hosts_total {len(hosts)}')
            lines.append(f'lsf_slots_max {sum(h["maxslots"] for h in hosts)}')
            lines.append(f'lsf_slots_busy {sum(h["nrun"] for h in hosts)}')

            d, e = parse_hist_24h(stats)
            lines.append(f'lsf_jobs_done_24h {d}')
            lines.append(f'lsf_jobs_exit_24h {e}')
        except Exception as ex:
            lines.append(f'lsf_exporter_error 1')
            print(f"export error: {ex}", file=sys.stderr)
        body = ("\n".join(lines) + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    http.server.HTTPServer(("0.0.0.0", 9109), Handler).serve_forever()

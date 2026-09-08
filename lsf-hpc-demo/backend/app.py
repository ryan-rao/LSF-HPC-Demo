# -*- coding: utf-8 -*-
"""LSF HPC Demo Portal - Backend (FastAPI)

Real execution only:
- Ansible tasks  -> ssh to KVM host, ansible-playbook /home/lsf/ansible/site.yml --tags <tag>
- HPC benchmarks -> ssh to LSF master, bsub /data/hpc/lsf_bench.sh <bench>, poll bjobs, fetch real output
- Cluster info   -> ssh to LSF master, bhosts/bqueues/bjobs
"""
import os, json, time, uuid, asyncio, re, signal
from pathlib import Path
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

TZ = timezone(offset=__import__("datetime").timedelta(hours=8))
def now(): return datetime.now(TZ).isoformat(timespec="seconds")

CONF = {
    "kvm_host":    os.getenv("KVM_HOST", "172.16.12.181"),
    "lsf_master":  os.getenv("LSF_MASTER", "172.16.12.211"),
    "ansible_dir": os.getenv("ANSIBLE_DIR", "/home/lsf/ansible"),
    "grafana_url": os.getenv("GRAFANA_URL", "http://172.16.12.182:30000"),
    "ssh_user":    os.getenv("SSH_USER", "root"),
    "ssh_key":     os.getenv("SSH_KEY", "/sshkey/id_demo"),
    "log_dir":     os.getenv("LOG_DIR", "/var/lib/lsf-demo/jobs"),
    "web_host":    os.getenv("WEB_PUBLIC_HOST", "172.16.12.181"),
    "web_port":    os.getenv("WEB_PUBLIC_PORT", "8080"),
}
LOG_DIR = Path(CONF["log_dir"]); LOG_DIR.mkdir(parents=True, exist_ok=True)

START_TS = time.time()

# ---------------------------------------------------------------- task registry
# Ansible tasks map 1:1 onto real roles/tags of /home/lsf/ansible/site.yml
ANSIBLE_TASKS = [
    dict(id="lsf_install",  name="LSF 安装",        cat="LSF", tags="lsf_install",
         desc="roles/lsf_install  · site.yml --tags lsf_install", danger=False),
    dict(id="lsf_config",   name="LSF 配置",        cat="LSF", tags="lsf_config",
         desc="roles/lsf_config · site.yml --tags lsf_config", danger=False),
    dict(id="lsf_test",     name="LSF 状态检查",    cat="LSF", tags="lsf_test",
         desc="roles/lsf_test  · 集群标识/节点/作业全流程断言", danger=False),
    dict(id="lsf_uninstall",name="LSF 卸载",        cat="LSF", tags="lsf_uninstall",
         desc="roles/lsf_uninstall · 高风险，将卸载 LSF", danger=True),
    dict(id="hpc_install",  name="HPC 安装",        cat="HPC", tags="hpc_install",
         desc="roles/hpc_install · 部署 MPI 与五套基准", danger=False),
    dict(id="hpc_config",   name="HPC 环境配置",    cat="HPC", tags="hpc_config",
         desc="roles/hpc_config · /etc/profile.d/hpc.sh 等", danger=False),
    dict(id="hpc_test",     name="HPC 功能测试",    cat="HPC", tags="hpc_test",
         desc="roles/hpc_test · 基准二进制/MPI 本地/跨节点自检", danger=False),
    dict(id="hpc_uninstall",name="HPC 卸载",        cat="HPC", tags="hpc_uninstall",
         desc="roles/hpc_uninstall · 高风险，将删除 HPC 环境", danger=True),
    dict(id="integrate",    name="LSF+HPC 集成验证(五基准全部跑)", cat="HPC", tags="integrate",
         desc="roles/lsf_hpc_integration · bsub 五基准并等待 DONE", danger=False),
    dict(id="kvm_image_build", name="KVM 黄金镜像制作", cat="集群扩容", tags="image",
         desc="roles/kvm_image_build · 模板机拷盘定制", danger=True),
    dict(id="node_deploy",  name="新节点部署+加入 LSF", cat="集群扩容", tags="deploy",
         desc="roles/node_deploy · 镜像部署 node217 并加入集群", danger=True),
    dict(id="node_remove",  name="删除 LSF 节点与 VM", cat="集群扩容", tags="remove",
         desc="roles/node_remove · 高风险，删除 node217", danger=True),
]
# Benchmark tasks: real bsub via /data/hpc/lsf_bench.sh on LSF master
# (n / ptile values taken from roles/lsf_hpc_integration/tasks/main.yml)
BENCH_TASKS = [
    dict(id="bench_stress",  name="STRESS 压力测试", cat="HPC Applications", bench="STRESS", n=2, p=1,
         desc="bsub /data/hpc/lsf_bench.sh STRESS · 3批次×7子作业 48槽需求压满集群 · ~15min", danger=False),
    dict(id="bench_mixed",   name="MIXED 混合应用", cat="HPC Applications", bench="MIXED", n=8, p=2,
         desc="bsub -n 8 -R span[ptile=2] /data/hpc/lsf_bench.sh MIXED · 串行/MPI计算/MPI IO/数组式/依赖链 六阶段 ~30min", danger=False),
    dict(id="bench_hacc_io",  name="HACC_IO",  cat="HPC Applications", bench="HACC_IO",  n=8, p=2,
         desc="bsub -n 8 -R span[ptile=2] /data/hpc/lsf_bench.sh HACC_IO", danger=False),
    dict(id="bench_hacc_oc",  name="HACC_OPEN_CLOSE", cat="HPC Applications", bench="HACC_OPEN_CLOSE", n=8, p=2,
         desc="bsub -n 8 -R span[ptile=2] /data/hpc/lsf_bench.sh HACC_OPEN_CLOSE", danger=False),
    dict(id="bench_s3dio",    name="s3dio",    cat="HPC Applications", bench="s3d_io",  n=8, p=2,
         desc="bsub -n 8 -R span[ptile=2] /data/hpc/lsf_bench.sh s3d_io", danger=False),
    dict(id="bench_btio",     name="BTIO",     cat="HPC Applications", bench="BTIO",    n=4, p=1,
         desc="bsub -n 4 -R span[ptile=1] /data/hpc/lsf_bench.sh BTIO", danger=False),
    dict(id="bench_madbench", name="MADbench", cat="HPC Applications", bench="MADbench", n=4, p=1,
         desc="bsub -n 4 -R span[ptile=1] /data/hpc/lsf_bench.sh MADbench", danger=False),
]
TASKS = {t["id"]: t for t in ANSIBLE_TASKS + BENCH_TASKS}

# ---------------------------------------------------------------- ssh runner
def _ssh_base(host):
    return ["ssh", "-i", CONF["ssh_key"], "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10", "-o", "LogLevel=ERROR",
            f"{CONF['ssh_user']}@{host}"]

LSF_ENV = ". /data/lsf/conf/profile.lsf"

async def ssh(host, cmd, timeout=60):
    """Run a short command, return (rc, out, err)."""
    p = await asyncio.create_subprocess_exec(
        *_ssh_base(host), cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
    except asyncio.TimeoutError:
        p.kill()
        return 124, b"SSH command timeout", b""
    return p.returncode, out.decode(errors="replace"), b""

# ---------------------------------------------------------------- job manager
JOBS: dict = {}

def job_dir(jid): return LOG_DIR / jid

def new_meta(jid, task_id, params=None):
    t = TASKS[task_id]
    return dict(job_id=jid, task=task_id, task_name=t["name"], category=t["cat"],
                params=params or {},
                status="PENDING", start_time=now(), end_time=None,
                lsf_job_id=None, return_code=None, error=None, summary={})

def save_meta(m):
    d = job_dir(m["job_id"]); d.mkdir(parents=True, exist_ok=True)
    (d / "metadata.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))

def append_log(jid, fname, text):
    p = job_dir(jid) / fname
    with open(p, "a") as f:
        f.write(text)

def load_jobs_from_disk():
    for meta_p in LOG_DIR.glob("*/metadata.json"):
        try:
            m = json.loads(meta_p.read_text())
            if m.get("status") in ("PENDING", "RUNNING"):
                m["status"] = "FAILED"; m["error"] = "container restarted during job"
                m["end_time"] = now()
                meta_p.write_text(json.dumps(m, ensure_ascii=False, indent=2))
            JOBS[m["job_id"]] = m
        except Exception:
            pass

RUNNING_PROCS: dict = {}  # jid -> subprocess

async def stream_process(jid, argv, logfile):
    """Run subprocess, stream stdout lines to logfile, return rc."""
    p = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        preexec_fn=os.setsid)
    RUNNING_PROCS[jid] = p
    loop = asyncio.get_event_loop()
    while True:
        line = await p.stdout.readline()
        if not line: break
        text = line.decode(errors="replace")
        append_log(jid, logfile, text)
    rc = await p.wait()
    RUNNING_PROCS.pop(jid, None)
    return rc

# ---- HPC output parsing (only real values, others -> "N/A") ----
def parse_bench_output(text):
    s = {}
    m = re.search(r"=== LSF job (\d+) bench=(\S+) NP=(\d+) hosts:\s*(.*)", text)
    if m:
        s["lsf_job_id"] = m.group(1); s["application"] = m.group(2)
        s["np"] = m.group(3)
        hosts = m.group(4).strip().split()
        s["nodes"] = ", ".join(sorted({h for h in hosts if not h.isdigit()}))
    m = re.search(r"total size:\s*([\d.]+ \w+)", text)
    if m: s["total_size"] = m.group(1)
    for key, pat in [("total_time", r"total time:\s*([\d.]+ sec)"),
                     ("write_bw",  r"write bw:\s*([\d.]+ \w+/s)"),
                     ("read_bw",   r"read bw:\s*([\d.]+ \w+/s)"),
                     ("write_time", r"write time:\s*([\d.]+ s\w*)"),
                     ("read_time",  r"read time:\s*([\d.]+ s\w*)"),
                     ("io_bw",     r"I/O\s+bandwidth\s*:\s*([\d.]+\s*\w+/s)"),
                     ("write_size", r"write size:\s*([\d.]+ \w+)"),
                     ]:
        m = re.search(pat, text)
        if m: s[key] = m.group(1)
    m = re.search(r"Run time\s*:\s*(.+)", text)
    if m: s["run_time"] = m.group(1).strip()
    m = re.search(r"Max Memory\s*:\s*(.+)", text)
    if m: s["max_memory"] = m.group(1).strip()
    m = re.search(r"Started at (.+)", text)
    if m: s["start_time"] = m.group(1).strip()
    m = re.search(r"Terminated at (.+)", text)
    if m: s["end_time"] = m.group(1).strip()
    m = re.search(r"=== \S+ exit=(\d+)", text)
    if m: s["app_exit"] = m.group(1)
    return s

async def run_bench_job(jid, task):
    m = JOBS[jid]
    bench, n, ptile = task["bench"], task["n"], task["p"]
    jname = f"demo_{bench}"
    submit = (f'su - lsfadmin -c \'{LSF_ENV}; bsub -J {jname} -n {n} -R "span[ptile={ptile}]" '
              f"-o /data/hpc/lsf_logs/{jname}.%J.out /data/hpc/lsf_bench.sh {bench}\'")
    rc, out, _ = await ssh(CONF["lsf_master"], submit, timeout=60)
    append_log(jid, "stdout.log", f"$ {submit}\n{out}\n")
    mm = re.search(r"Job <(\d+)> is submitted", out)
    if not mm:
        m["status"] = "FAILED"; m["error"] = "LSF job submission failed"; m["return_code"] = rc
        m["end_time"] = now(); save_meta(m); return
    lsf_id = mm.group(1); m["lsf_job_id"] = lsf_id; m["status"] = "RUNNING"; save_meta(m)
    # poll bjobs
    deadline = time.time() + 3600
    st = "PEND"
    while time.time() < deadline:
        rc, out, _ = await ssh(CONF["lsf_master"],
            f"su - lsfadmin -c '{LSF_ENV}; bjobs -noheader -o \"stat queue exec_host\" {lsf_id}'", timeout=30)
        append_log(jid, "hpc.log", f"[{now()}] bjobs {lsf_id}: {out.strip()}\n")
        st = out.split()[0] if out.split() else "UNK"
        if st in ("DONE", "EXIT"): break
        await asyncio.sleep(5)
    # fetch real output
    outfile = f"/data/hpc/lsf_logs/{jname}.{lsf_id}.out"
    rc, out, _ = await ssh(CONF["lsf_master"], f"cat {outfile}", timeout=30)
    append_log(jid, "hpc.log", f"$ cat {outfile}\n{out}\n")
    summary = parse_bench_output(out)
    summary["lsf_status"] = st
    m["summary"] = summary
    m["end_time"] = now()
    if st == "DONE" and summary.get("app_exit") == "0":
        m["status"] = "SUCCESS"; m["return_code"] = 0
    else:
        m["status"] = "FAILED"; m["return_code"] = 1
        m["error"] = f"LSF job {lsf_id} final status: {st}"
    save_meta(m)

async def resolve_master(master_ip):
    """Reverse-map master IP -> inventory hostname via group_vars node_ips."""
    rc, out, _ = await ssh(CONF["kvm_host"],
        r"awk '/^ +node[0-9]+: +172[.]16[.][0-9]+[.][0-9]+$/ {print $1, $2}' "
        f"{CONF['ansible_dir']}/group_vars/all.yml", timeout=30)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == master_ip:
            return parts[0].rstrip(":")
    return None

async def run_ansible_job(jid, task):
    m = JOBS[jid]
    extra = ""
    params = m.get("params") or {}
    if task["id"] == "node_deploy":
        master_ip = str(params.get("master_ip", "")).strip()
        node_ip = str(params.get("node_ip", "")).strip()
        if not master_ip or not node_ip:
            m["status"] = "FAILED"; m["error"] = "缺少参数: master_ip / node_ip"
            m["end_time"] = now(); save_meta(m); return
        mh = await resolve_master(master_ip)
        if not mh:
            m["status"] = "FAILED"; m["error"] = f"master IP {master_ip} 不是集群已知节点"
            m["end_time"] = now(); save_meta(m); return
        last = node_ip.rsplit(".", 1)[-1]
        node_name = str(params.get("node_name", "")).strip() or f"node{last}"
        node_mac = "52:54:00:12:00:" + format(int(last) % 256, "02x")
        extra = (f" -e new_node_ip={node_ip} -e new_node_name={node_name}"
                 f" -e new_node_mac={node_mac} -e lsf_master={mh} -e lsf_master_ip={master_ip}"
                 f" -e remove_node_name={node_name} -e remove_node_ip={node_ip}")
        append_log(jid, "stdout.log",
                   f"[params] master={master_ip}({mh}) new_node={node_ip}({node_name}, {node_mac})\n")
    if task["id"] == "node_remove":
        rm_ip = str(params.get("node_ip", "")).strip()
        if not rm_ip:
            m["status"] = "FAILED"; m["error"] = "缺少参数: 待删除节点 IP"
            m["end_time"] = now(); save_meta(m); return
        last = rm_ip.rsplit(".", 1)[-1]
        rm_name = str(params.get("node_name", "")).strip() or f"node{last}"
        orig = await resolve_master(rm_ip)
        if orig is not None:
            m["status"] = "FAILED"; m["error"] = f"禁止删除原有集群节点 {rm_name}（{orig} 为初始部署节点）"
            m["end_time"] = now(); save_meta(m); return
        extra = f" -e remove_node_name={rm_name} -e remove_node_ip={rm_ip}"
        append_log(jid, "stdout.log", f"[params] remove node={rm_ip} ({rm_name})\n")

    tags = "image,deploy" if task["id"] == "node_deploy" else task["tags"]
    cmd = (f"cd {CONF['ansible_dir']} && ansible-playbook site.yml --tags {tags}{extra}")
    argv = _ssh_base(CONF["kvm_host"]) + [cmd]
    append_log(jid, "stdout.log", f"$ ssh {CONF['ssh_user']}@{CONF['kvm_host']} \"{cmd}\"\n")
    m["status"] = "RUNNING"; save_meta(m)
    rc = await stream_process(jid, argv, "stdout.log")
    m["return_code"] = rc; m["end_time"] = now()
    m["status"] = "SUCCESS" if rc == 0 else "FAILED"
    if rc != 0:
        m["error"] = f"ansible-playbook exited with rc={rc}"
    save_meta(m)

async def job_wrapper(jid, task_id):
    try:
        task = TASKS[task_id]
        if "bench" in task:
            await run_bench_job(jid, task)
        else:
            await run_ansible_job(jid, task)
    except Exception as e:
        m = JOBS[jid]; m["status"] = "FAILED"; m["error"] = f"internal error: {e}"
        m["end_time"] = now(); save_meta(m)

# ---------------------------------------------------------------- app
app = FastAPI(title="LSF HPC Demo Portal")

# ===== 登录认证 =====
DEMO_USER = os.environ.get("DEMO_USER", "admin")
DEMO_PASS = os.environ.get("DEMO_PASS", "lsfhpcdemo")
SESSIONS = set()
PUBLIC_PATHS = {"/login", "/api/login", "/favicon.ico"}

@app.middleware("http")
async def auth_mw(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    tok = request.cookies.get("demo_token")
    if tok in SESSIONS:
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    resp = HTMLResponse('<meta http-equiv="refresh" content="0;url=/login">', status_code=302)
    resp.headers["location"] = "/login"
    return resp

@app.post("/api/login")
async def login(body: dict):
    if body.get("user") != DEMO_USER or body.get("pass") != DEMO_PASS:
        return JSONResponse({"detail": "bad credentials"}, status_code=401)
    tok = uuid.uuid4().hex
    SESSIONS.add(tok)
    resp = JSONResponse({"ok": True})
    resp.set_cookie("demo_token", tok, httponly=True, samesite="lax")
    return resp

@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("demo_token")
    return resp

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return FileResponse(Path(__file__).parent / "static" / "login.html",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.on_event("startup")
def _startup():
    load_jobs_from_disk()

@app.get("/api/health")
def health():
    return dict(status="ok", service="lsf-hpc-demo", version="1.0.0",
                uptime_sec=int(time.time() - START_TS), time=now())

@app.post("/api/lsf/killall")
async def lsf_killall():
    rc, out, _ = await ssh(CONF["lsf_master"],
        f"su - lsfadmin -c '{LSF_ENV}; bkill -u lsfadmin'", timeout=120)
    return dict(ok=rc == 0, output=out.strip())

@app.get("/api/tasks")
def tasks():
    cats = {}
    for t in TASKS.values():
        cats.setdefault(t["cat"], []).append(
            {k: t.get(k) for k in ("id", "name", "cat", "desc", "danger")})
    return dict(categories=cats,
                grafana_url=f"{CONF['grafana_url']}/d/gpfs-cluster-health/",
                grafana_embed="/d/gpfs-cluster-health/?kiosk")

@app.post("/api/jobs")
async def create_job(body: dict):
    task_id = body.get("task_id")
    if task_id not in TASKS:
        raise HTTPException(400, f"unknown task_id '{task_id}' (whitelist only)")
    jid = f"demo-{datetime.now(TZ):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    JOBS[jid] = new_meta(jid, task_id, body.get("params"))
    save_meta(JOBS[jid])
    asyncio.create_task(job_wrapper(jid, task_id))
    return dict(job_id=jid)

@app.get("/api/jobs")
def list_jobs():
    out = sorted(JOBS.values(), key=lambda m: m["start_time"], reverse=True)
    return [dict(job_id=m["job_id"], task=m["task"], task_name=m["task_name"],
                 status=m["status"], start_time=m["start_time"], end_time=m["end_time"],
                 lsf_job_id=m["lsf_job_id"]) for m in out]

@app.get("/api/jobs/{jid}")
def get_job(jid):
    if jid not in JOBS: raise HTTPException(404, "job not found")
    return JOBS[jid]

@app.get("/api/jobs/{jid}/output")
def job_output(jid: str, tail: int = 0):
    if jid not in JOBS: raise HTTPException(404, "job not found")
    def read(name):
        p = job_dir(jid) / name
        if not p.exists(): return ""
        t = p.read_text(errors="replace")
        if tail > 0:
            lines = t.splitlines()
            t = "\n".join(lines[-tail:])
        return t
    return dict(stdout=read("stdout.log"), hpc=read("hpc.log"))

@app.post("/api/jobs/{jid}/cancel")
async def cancel_job(jid):
    if jid not in JOBS: raise HTTPException(404, "job not found")
    m = JOBS[jid]
    # if it is an LSF job, also bkill on the master (real cancellation)
    if m.get("lsf_job_id"):
        lid = m["lsf_job_id"]
        await ssh(CONF["lsf_master"],
                  f"su - lsfadmin -c '{LSF_ENV}; bkill {lid}'", timeout=30)
    p = RUNNING_PROCS.get(jid)
    if p:
        try: os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except Exception: p.kill()
    m["status"] = "CANCELLED"; m["end_time"] = now(); save_meta(m)
    return dict(job_id=jid, status="CANCELLED")

_cluster_cache = dict(ts=0, data=None)
@app.get("/api/cluster")
async def cluster():
    if time.time() - _cluster_cache["ts"] < 10:
        return _cluster_cache["data"]
    rc_h, hosts, _ = await ssh(CONF["lsf_master"], f"su - lsfadmin -c '{LSF_ENV}; bhosts'", 30)
    rc_q, queues, _ = await ssh(CONF["lsf_master"], f"su - lsfadmin -c '{LSF_ENV}; bqueues'", 30)
    rc_j, jobs, _ = await ssh(CONF["lsf_master"], f"su - lsfadmin -c '{LSF_ENV}; bjobs'", 30)
    hlist = [l.split() for l in hosts.strip().splitlines()[1:] if l.strip()]
    ok = sum(1 for h in hlist if len(h) > 1 and h[1] == "ok")
    data = dict(hosts=hosts, queues=queues, jobs=jobs,
                total_hosts=len(hlist), ok_hosts=ok, lsf_ok=(rc_h == 0 and ok > 0),
                master=CONF["lsf_master"])
    _cluster_cache.update(ts=time.time(), data=data)
    return data

@app.get("/api/ui-dashboards")
async def ui_dashboards():
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{CONF['grafana_url']}/api/search?type=dash-db")
            items = [{"uid": d["uid"], "title": d["title"]} for d in r.json()]
            return dict(ok=True, base=CONF["grafana_url"], dashboards=items)
    except Exception as e:
        return dict(ok=False, error=str(e), dashboards=[])

# ------------------------------------------------------ grafana same-origin proxy
# Strips X-Frame-Options / CSP so dashboards can be iframed from this origin.
from fastapi.responses import Response
HOP_HEADERS = {"host", "connection", "accept-encoding", "content-length", "keep-alive",
               "proxy-authenticate", "proxy-authorization", "te", "upgrade", "transfer-encoding"}
PROXY_HIDE = {"x-frame-options", "content-security-policy", "content-security-policy-report-only",
              "content-encoding", "content-length", "transfer-encoding", "strict-transport-security"}

async def _gproxy(request: Request, path: str):
    url = f"{CONF['grafana_url']}/{path}"
    try:
        hdrs = {k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS}
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as c:
            rp = await c.request(request.method, url, headers=hdrs,
                                 params=request.query_params,
                                 content=await request.body())
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"grafana unreachable: {e}"})
    rh: dict = {}
    cookies = []
    for k, v in rp.headers.items():
        lk = k.lower()
        if lk in PROXY_HIDE: continue
        if lk == "set-cookie": cookies.append(v); continue
        if lk == "location":
            v = v.replace(CONF["grafana_url"] + "/", "/").replace(CONF["grafana_url"], "/")
        rh[k] = v
    r = Response(content=rp.content, status_code=rp.status_code, headers=rh)
    for cv in cookies: r.headers.append("set-cookie", cv)
    return r

for _pfx in ["public", "avatar", "img", "plugins", "d", "dashboards", "dashboard",
             "login", "logout", "user", "org", "profile", "metrics", "healthz",
             "frontend", "api/admin", "api/auth", "api/user", "api/org", "api/search",
             "api/dashboards", "api/ds", "api/annotations", "api/metrics", "api/queries",
             "api/plugins", "api/lookups", "api/ngalert", "api/alertmanager", "api/ruler",
             "api/datasources", "api/sessions", "api/preferences", "api/live", "api/shortcuts"]:
    def _mk(p):
        async def h(request: Request, path: str = ""): return await _gproxy(request, p + ("/" + path if path else ""))
        return h
    app.add_api_route(f"/{_pfx}", _mk(_pfx), methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"])
    app.add_api_route(f"/{_pfx}/{{path:path}}", _mk(_pfx), methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"])

@app.get("/intro", response_class=HTMLResponse)
async def intro():
    return HTMLResponse((Path(__file__).parent / "static" / "intro.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/favicon.ico")
async def favicon():
    async with httpx.AsyncClient(timeout=10) as c:
        rp = await c.get(f"{CONF['grafana_url']}/public/img/fav32.png")
    return Response(content=rp.content, media_type="image/png")

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

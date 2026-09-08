# LSF 10.1 社区版集群安装步骤（完整记录）

安装时间：2026-09-01 19:58 - 20:10
集群拓扑：node211 = master（172.16.12.211），node212/213/215 = worker
所有 VM：RHEL 9.6，8核/16G/双盘100G，KVM 跑在 node181 上

## 一、介质（node181:/home/lsf）
- lsf10.1_lsfinstall_linux_x86_64.tar.Z（131M，标准安装器）
- lsf10.1_lnx310-lib217-x86_64.tar.Z（867M，社区版二进制，无需 entitlement）
- 注意：603045 那个包是 Fix 补丁包（需 base + 授权），社区版用 lnx310-lib217 这个

## 二、前置准备
1. 4 节点 /etc/hosts 互相解析（node211/212/213/215）
2. node211 到各节点 root SSH 免密
3. node211 NFS 导出 LSF_TOP（/data/lsf），worker 挂载到相同路径（rw,no_root_squash）
4. 4 节点安装依赖：libnsl（RHEL9 默认没有，rpm 从 ISO 拿）、ed + info（安装器需要）
5. 创建 LSF 管理员用户 lsfadmin（4 节点都要，不能直接用 root）

## 三、安装步骤（master = node211）
1. 传输介质到 node211:/data/lsf_inst/
2. 解压安装器：
   mkdir -p /data/lsf_inst/installer && cd /data/lsf_inst/installer
   gzip -dc ../lsf10.1_lsfinstall_linux_x86_64.tar.Z | tar xf -
3. 编辑 lsf10.1_lsfinstall/install.config：
   LSF_TOP="/data/lsf"
   LSF_ADMINS="lsfadmin"
   LSF_CLUSTER_NAME="cluster1"
   LSF_MASTER_LIST="node211"
   LSF_TARDIR="/data/lsf_inst"          # 放社区版 tar.Z 的目录
   LSF_ADD_SERVERS="node211 node212 node213 node215"
   LSF_QUIET_INST="Y"
4. 执行安装（注意 license 交互要输入 1 接受）：
   printf "1\ny\ny\ny\n" | ./lsfinstall -f install.config
   - 安装器自动完成：解压二进制到 /data/lsf/10.1/linux3.10-glibc2.17-x86_64、
     生成 conf/（lsf.conf、lsf.cluster.cluster1、lsf.shared、profile.lsf 等）、
     自动把 LSF_ADD_SERVERS 的主机写入集群文件
   - LSF_TOP 必须为空（残留文件会被拒）

## 四、安装后配置
1. 确认 /data/lsf/conf/lsf.cluster.cluster1 Host 段包含 4 台节点（server=1）
2. 各节点执行 hostsetup（装开机自启脚本 + profile）：
   . /data/lsf/conf/profile.lsf
   /data/lsf/10.1/install/hostsetup --top=/data/lsf --boot=y --start=n --profile=y --silent
3. worker 节点清理旧 /etc/lsf.conf 等残留（踩过的坑）

## 五、启动集群
1. 所有节点（含 master）：
   . /data/lsf/conf/profile.lsf
   $LSF_SERVERDIR/lim
   $LSF_SERVERDIR/res
   $LSF_SERVERDIR/sbatchd
2. 仅 master：
   $LSF_SERVERDIR/mbatchd
3. 验证：
   lsid          → IBM Spectrum LSF Community Edition 10.1.0.15
   lshosts       → 4 节点全部列出
   lsload        → 全部 ok
   bhosts        → 全部 ok（用 lsfadmin 执行，root 不是 LSF 管理员）
   su - lsfadmin -c ". /data/lsf/conf/profile.lsf; bsub sleep 30" → 正常派发执行

## 六、关键排错经验
- Fix 包（603045）缺 lsfinstall 且守护进程要 EGO entitlement → 用社区版
- lim 静默 exit 255 不写日志 → 真实报错在 journalctl（syslog）里
- RHEL9 缺 libnsl.so.1 → rpm 装 ISO 里的 libnsl
- lsfinstall 预检查缺 ed 命令 → ed 依赖 info，两个 rpm 一起装
- LSF_ADMINS 不能是 root → 建 lsfadmin 用户
- LSF_ENVDIR 由 profile.lsf 设为 $LSF_TOP/conf，不要手工放 /etc/lsf.conf

## 七、LWS WebService 部署（20:15 完成 ✅）
1. 解压 lws10.1.0.16_linux-x86_64.tar.Z 到 /data/lsf_inst/lws/
2. 在 lwsinstall.sh 的 `# . $LSF_ENVDIR/profile.lsf` 后加一行：`. /data/lsf/conf/profile.lsf`
3. 静默安装：`./lwsinstall.sh -s -y`（-s 静默 -y 接受license；交互模式会卡 HTTPS 询问的 read 循环，stdin EOF 时死循环）
4. 安装到 /opt/ibm/lsfsuite/ext，systemd 服务 lwsd 已自启+开机自启
5. 访问：**https://node211:8448**（自签名证书，curl 加 -k）
6. REST API 用法（openapi.yaml 在介质目录）：
   - 登录：`curl -sk -X POST -H "Content-Type: application/json" -d '{"name":"lsfadmin","pass":"Redhat@123"}' https://node211:8448/lsf/v1/auth/logon` → 返回 token（token 含引号，用 python json 提取）
   - 执行 LSF 命令：`curl -sk -X POST -H "Authorization: $TOK" -H "Content-Type: application/x-www-form-urlencoded" -d "command=bhosts" https://node211:8448/lsf/v1/cluster/usercmd`
   - 集群信息：GET /lsf/v1/cluster
   - 验证：REST bhosts 4节点ok，REST bsub 提交 Job 2 成功
7. 坑：pkill -f lwsinstall 会匹配到自己所在 ssh 命令行（自杀），要用 PID 排除法

## 八、账户信息
- root / lsfadmin 密码：Redhat@123（4 节点相同）

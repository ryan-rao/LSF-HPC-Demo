#!/bin/bash
# 镜像首次开机自动配置：读两个参数（LSF_SERVER_IP / VM_IP）自动入集群
exec >/var/log/firstboot.log 2>&1
. /root/node-params.env
echo "firstboot: LSF_SERVER=$LSF_SERVER_IP VM_IP=$VM_IP HOST=$VM_HOSTNAME"

# 1. 主机名
hostnamectl set-hostname $VM_HOSTNAME

# 2. 静态 IP（连接名以 nmcli con show 实际为准，双保险）
CON=$(nmcli -t -f NAME,DEVICE con show --active | cut -d: -f1 | head -1)
nmcli con mod "$CON" ipv4.method manual ipv4.addresses ${VM_IP}/24
nmcli con up "$CON"

# 3. hosts：替换克隆残留行，补集群解析
sed -i "s/^172\.16\.12\.212[[:space:]].*/${VM_IP} ${VM_HOSTNAME}/" /etc/hosts
for E in "$LSF_SERVER_IP node211" "172.16.12.212 node212" "172.16.12.213 node213" \
         "172.16.12.215 node215" "172.16.12.216 node216" "172.16.12.217 node217" \
         "172.16.12.181 node181"; do
  grep -qF "$E" /etc/hosts || echo "$E" >> /etc/hosts
done

# 4. 挂载 LSF/HPC 共享存储（指向 LSF 服务器参数）
mkdir -p /data/lsf /data/hpc
grep -q " /data/lsf " /etc/fstab || echo "$LSF_SERVER_IP:/data/lsf /data/lsf nfs defaults,_netdev 0 0" >> /etc/fstab
grep -q " /data/hpc " /etc/fstab || echo "$LSF_SERVER_IP:/data/hpc /data/hpc nfs defaults,_netdev 0 0" >> /etc/fstab
mount -a

# 5. lsfadmin 自身 known_hosts
su - lsfadmin -c "ssh-keyscan -H $VM_HOSTNAME >> ~/.ssh/known_hosts 2>/dev/null || true"

# 6. 启动 LSF 客户端守护（读取共享 lsf.conf，向 master 注册）
. /data/lsf/conf/profile.lsf
$LSF_SERVERDIR/lim
sleep 2
$LSF_SERVERDIR/res
$LSF_SERVERDIR/sbatchd
echo "firstboot done"


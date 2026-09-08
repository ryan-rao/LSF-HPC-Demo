# KVM 虚拟机部署步骤（node181，LSF/HPC 集群用）

时间：2026-09-01
宿主机：node181（172.16.12.181，RHEL 9.6，128核/251G）
产物：4 台 VM —— node211(master)/node212/node213/node215(worker)
VM 配置：8核 vCPU / 16G 内存 / 双盘各100G（vda 系统 + vdb /data xfs）/ RHEL 9.6
存储位置：/home/kvm/nodeNNN/（qcow2）

## 一、宿主机准备
1. 安装虚拟化（本地 ISO repo，未注册订阅）：
   dnf -y install qemu-kvm libvirt virt-install guestfs-tools
2. ISO 复制到 /home/kvm/RHEL-9.6.0-x86_64-dvd1.iso（qemu 低权限用户读不了 /root）
3. 配置网桥 br0（nmcli，物理口 ens1f0 为端口，保留原 IP 172.16.12.181）：
   nmcli con add type bridge con-name br0 ifname br0 ipv4.method manual ipv4.addresses 172.16.12.181/24 ...
   nmcli con add type bridge-slave con-name br0-port ifname ens1f0 master br0
   注意：原 "Profile 1" 的 autoconnect 要关掉；切换日志 /root/switch-br0.log

## 二、批量创建 VM
脚本与 kickstart：/root/kvm-setup/{create-vms.sh, ksNNN.cfg, create-vms.log}
1. 每个 VM 写 kickstart（关键：**显式 part 分区，不能用 autopart**——两者冲突会卡死 anaconda）
   root 密码 Redhat@123；/data 单独分区 xfs
2. virt-install 示例：
   virt-install --name node211 --memory 16384 --vcpus 8 \
     --disk path=/home/kvm/node211/node211.os.qcow2,size=100 \
     --disk path=/home/kvm/node211/node211.data.qcow2,size=100 \
     --network bridge=br0,mac=52:54:00:12:00:d3 \
     --cdrom /home/kvm/RHEL-9.6.0-x86_64-dvd1.iso \
     --initrd-inject /root/kvm-setup/ks211.cfg --extra-args "inst.ks=cdrom:/ks211.cfg inst.repo=cdrom" ...
3. MAC 规划：52:54:00:12:00:d3-d6（211→d3 ... 215 用 d6）
4. 装后补 root SSH 登录（RHEL9 默认禁）：
   virt-customize -a node211.os.qcow2 --run-command "sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config"

## 三、注意事项
- ⚠️ 172.16.12.214 被一台物理机占用（MAC E4:1F:13:5E:36:81），第 4 台改用 172.16.12.215（node215）
- 182/183/184 上原有 OpenShift VM，未受影响；185 SSH 不通未处理
- VM 网络走 br0 桥接，与物理机同网段 172.16.12.x
- 账户：root / Redhat@123（4 台相同）

## 四、后续环境（详见其它文档）
- LSF 集群：见《LSF安装步骤》
- HPC 环境：见《HPC环境部署步骤》
- LSF 调度 HPC 基准：见《LSF调度HACCIO集成步骤》

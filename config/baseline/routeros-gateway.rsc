# routeros-gateway.rsc — ЭТАЛОННЫЙ КОНФИГ для шлюза RouterOS 7.25
# Хранится в Git, правится здесь, раскатывается плейбуком 04-baseline-apply.yml на все gw-*
# Архитектура ТЗ: ether1 WAN 111.111.111.111, bridge1 LAN 192.168.0.50/16 (ether2-10)
# Применение: ansible-playbook playbooks/04-baseline-apply.yml --tags apply
# Версия: 1.0 — 2026-10-29 — sha256 см. ERROR_JOURNAL.md

# === System ===
/system identity set name=gw-core-01
/system clock set time-zone-name=Europe/Moscow
/system ntp client set enabled=yes servers=pool.ntp.org,time.cloudflare.com

# === Bridge LAN ===
/interface bridge add name=bridge1 protocol-mode=rstp comment="LAN bridge ether2-10"
/interface bridge port add bridge=bridge1 interface=ether2 comment="LAN"
/interface bridge port add bridge=bridge1 interface=ether3 comment="LAN"
/interface bridge port add bridge=bridge1 interface=ether4 comment="LAN"
/interface bridge port add bridge=bridge1 interface=ether5 comment="LAN"
/interface bridge port add bridge=bridge1 interface=ether6 comment="LAN"
/interface bridge port add bridge=bridge1 interface=ether7 comment="LAN"
/interface bridge port add bridge=bridge1 interface=ether8 comment="LAN"
/interface bridge port add bridge=bridge1 interface=ether9 comment="LAN"
/interface bridge port add bridge=bridge1 interface=ether10 comment="LAN"

# === IP ===
/ip address add address=192.168.0.50/16 interface=bridge1 comment="LAN gateway"
/ip address add address=111.111.111.111/24 interface=ether1 comment="WAN"
/ip route add dst-address=0.0.0.0/0 gateway=111.111.111.1 comment="WAN GW"

# === DNS ===
/ip dns set servers=1.1.1.1,8.8.8.8 allow-remote-requests=no cache-size=2048KiB

# === DHCP (опционально, для LAN) ===
/ip pool add name=lan-pool ranges=192.168.0.100-192.168.0.200 comment="LAN pool"
/ip dhcp-server add name=lan-dhcp interface=bridge1 address-pool=lan-pool lease-time=1d disabled=no comment="LAN DHCP"
/ip dhcp-server network add address=192.168.0.0/16 gateway=192.168.0.50 dns-server=1.1.1.1,8.8.8.8 domain=lan

# === Firewall (best practice для шлюза) ===
/ip firewall filter
# Input
add chain=input action=accept connection-state=established,related,untracked comment="defconf: accept established"
add chain=input action=drop connection-state=invalid comment="defconf: drop invalid"
add chain=input action=accept protocol=icmp comment="accept ICMP"
add chain=input action=accept in-interface-list=LAN comment="accept LAN"
add chain=input action=drop comment="drop all not LAN"

# Forward
add chain=forward action=accept connection-state=established,related,untracked comment="defconf: accept established"
add chain=forward action=drop connection-state=invalid comment="defconf: drop invalid"
add chain=forward action=accept in-interface-list=LAN out-interface-list=WAN comment="LAN → WAN"
add chain=forward action=drop comment="drop rest"

# NAT
/ip firewall nat add chain=srcnat action=masquerade out-interface=ether1 comment="defconf: masquerade"

# Interface lists (для firewall)
/interface list add name=WAN comment="WAN"
/interface list add name=LAN comment="LAN"
/interface list member add list=WAN interface=ether1
/interface list member add list=LAN interface=bridge1

# === Services ===
/ip service set telnet disabled=yes
/ip service set ftp disabled=yes
/ip service set www disabled=yes
/ip service set api disabled=yes
/ip service set api-ssl disabled=no address=192.168.0.0/16 port=8729
/ip service set ssh disabled=no address=192.168.0.0/16 port=22
/ip service set winbox disabled=no address=192.168.0.0/16 port=8291
/ip ssh set strong-crypto=yes forwarding-enabled=no

# === Users ===
/user add name=ansible group=full address=192.168.0.0/16 comment="Ansible" password="SET_VIA_VAULT"

# === Discovery ===
/ip neighbor discovery-settings set discover-interface-list=LAN
/tool mac-server set allowed-interface-list=LAN
/tool mac-server mac-winbox set allowed-interface-list=LAN

# === SNMP ===
/snmp set enabled=yes contact="noc@example.com" location="gw-core-01"
/snmp community set [find default=yes] addresses=192.168.0.0/16 name=mikrotik-ro

# === Logging ===
/system logging action add name=remote target=remote remote=192.168.0.10 remote-port=514
/system logging add topics=info action=remote
/system logging add topics=warning action=remote
/system logging add topics=error action=remote
/system logging add topics=firewall action=remote

# === Cloud ===
/ip cloud set ddns-enabled=no update-time=no

# === Backup scheduler ===
/system scheduler add name=backup-daily start-time=02:00 interval=1d on-event="/system backup save name=auto-backup; /export file=auto-export" comment="daily backup"

# === Конец эталона ===

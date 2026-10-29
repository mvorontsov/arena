# CHR 7.25 gw-lab-01 — НЕСООТВЕТСТВУЕТ best practice (для debug раскатки)
# Сломанные: неверный LAN IP, нет bridge ports, старый ROS, без firewall, без NTP
/system identity set name=gw-lab-01
/system clock set time-zone-name=UTC
/system ntp client set enabled=no servers=""
/interface bridge add name=bridge1 protocol-mode=rstp
# Сломано: только 3 порта в бридже вместо 9
/interface bridge port add bridge=bridge1 interface=ether2
/interface bridge port add bridge=bridge1 interface=ether3
/interface bridge port add bridge=bridge1 interface=ether4
/ip address add address=192.168.88.1/24 interface=bridge1 comment="WRONG LAN!"
/ip address add address=111.111.111.112/24 interface=ether1 comment="WAN lab"
/ip route add dst-address=0.0.0.0/0 gateway=111.111.111.1
/ip dns set servers=8.8.8.8 allow-remote-requests=yes
/ip pool add name=lan-pool ranges=192.168.88.10-192.168.88.100
# Без firewall вообще
# Без NAT
/interface list add name=WAN
/interface list add name=LAN
/interface list member add list=WAN interface=ether1
/ip service set telnet disabled=no
/ip service set ftp disabled=no
/ip service set www disabled=no
/ip service set api disabled=no port=8728
/user add name=admin group=full

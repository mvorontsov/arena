# CHR 7.25 gw-core-01 — почти эталон (2 отклонения для аудита)
# WAN ether1 111.111.111.111/24 GW 111.111.111.1
# LAN bridge1 192.168.0.50/16 ether2-10 RSTP, DHCP 100-200, DNS 1.1.1.1/8.8.8.8
# Firewall best practice, NAT masquerade, users
/system identity set name=gw-core-01
/system clock set time-zone-name=Europe/Moscow
/system ntp client set enabled=yes servers=pool.ntp.org,time.cloudflare.com
/interface bridge add name=bridge1 protocol-mode=rstp comment="LAN"
/interface bridge port add bridge=bridge1 interface=ether2
/interface bridge port add bridge=bridge1 interface=ether3
/interface bridge port add bridge=bridge1 interface=ether4
/interface bridge port add bridge=bridge1 interface=ether5
/interface bridge port add bridge=bridge1 interface=ether6
/interface bridge port add bridge=bridge1 interface=ether7
/interface bridge port add bridge=bridge1 interface=ether8
/interface bridge port add bridge=bridge1 interface=ether9
/interface bridge port add bridge=bridge1 interface=ether10
/ip address add address=192.168.0.50/16 interface=bridge1 comment="LAN GW"
/ip address add address=111.111.111.111/24 interface=ether1 comment="WAN"
/ip route add dst-address=0.0.0.0/0 gateway=111.111.111.1 comment="WAN GW"
/ip dns set servers=1.1.1.1,8.8.8.8 allow-remote-requests=no
/ip pool add name=lan-pool ranges=192.168.0.100-192.168.0.200
/ip dhcp-server add name=lan-dhcp interface=bridge1 address-pool=lan-pool disabled=no
/ip dhcp-server network add address=192.168.0.0/16 gateway=192.168.0.50 dns-server=1.1.1.1,8.8.8.8
/ip firewall filter add chain=input action=accept connection-state=established,related,untracked comment="established"
add chain=input action=drop connection-state=invalid
add chain=input action=accept protocol=icmp
add chain=input action=accept in-interface-list=LAN
add chain=input action=drop comment="final drop"
/ip firewall nat add chain=srcnat action=masquerade out-interface=ether1
/interface list add name=WAN
/interface list add name=LAN
/interface list member add list=WAN interface=ether1
/interface list member add list=LAN interface=bridge1
# Отклонения: нет ansible-учётки, telnet включен (для аудита)
# /user add name=ansible group=full address=192.168.0.0/16
/ip service set telnet disabled=no
/ip service set api address=192.168.0.0/16 port=8728 disabled=no

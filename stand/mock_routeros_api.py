#!/usr/bin/env python3
"""
Mock RouterOS API server for стенд — эмуляция RouterOS 7.25 gateway
- Слушает 0.0.0.0:8728 (API без TLS)
- Отвечает на /login и основные print-запросы, используемые в ролях
- Данные соответствуют ТЗ: ether1 WAN 111.111.111.111, bridge1 LAN 192.168.0.50/16, ether2-10
- Часть проверок намеренно провалена для демонстрации аудита (Compliance ~75%)

Запуск: python3 stand/mock_routeros_api.py &
Проверка: python3 -c "import librouteros; api=librouteros.connect(host='127.0.0.1', username='admin', password='demo-only-changeme'); print(list(api.path('system','resource')))"
"""
import socket
import threading
import struct
import hashlib
import binascii
import time
import random

# Логика кодирования длин — копия из librouteros.protocol
def encode_length(length: int) -> bytes:
    if length < 0x80:
        return length.to_bytes(1, 'big')
    elif length < 0x4000:
        val = length | 0x8000
        return val.to_bytes(2, 'big')
    elif length < 0x200000:
        val = length | 0xC00000
        return val.to_bytes(3, 'big')
    elif length < 0x10000000:
        val = length | 0xE0000000
        return val.to_bytes(4, 'big')
    else:
        raise ValueError(f"Unable to encode length {length!r}")

def encode_word(word: str, encoding: str = 'ASCII') -> bytes:
    encoded = word.encode(encoding=encoding, errors='strict')
    return encode_length(len(encoded)) + encoded

def encode_sentence(*words: str, encoding: str = 'ASCII') -> bytes:
    return b"".join(encode_word(w, encoding) for w in words) + b"\x00"

def decode_length(data: bytes, offset: int = 0) -> tuple[int, int]:
    ctl = data[offset]
    if ctl < 0x80:
        return (ctl, 1)
    elif ctl < 0xC0:
        val = int.from_bytes(data[offset:offset+2], 'big')
        return (val ^ 0x8000, 2)
    elif ctl < 0xE0:
        val = int.from_bytes(data[offset:offset+3], 'big')
        return (val ^ 0xC00000, 3)
    elif ctl < 0xF0:
        val = int.from_bytes(data[offset:offset+4], 'big')
        return (val ^ 0xE0000000, 4)
    else:
        raise ValueError(f"Unknown length byte {data[offset]:x}")

def read_word(sock, encoding='ASCII'):
    first = sock.recv(1)
    if not first:
        return None
    if first == b'\x00':
        return ""
    # need to peek length
    ctl = first[0]
    to_read = 0
    if ctl < 0x80:
        length = ctl
    elif ctl < 0xC0:
        second = sock.recv(1)
        if not second:
            return None
        length = int.from_bytes(first + second, 'big') ^ 0x8000
    elif ctl < 0xE0:
        second = sock.recv(2)
        length = int.from_bytes(first + second, 'big') ^ 0xC00000
    elif ctl < 0xF0:
        second = sock.recv(3)
        length = int.from_bytes(first + second, 'big') ^ 0xE0000000
    else:
        raise ValueError(f"Unknown ctl {ctl}")

    if length == 0:
        return ""
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            break
        data += chunk
    return data.decode(encoding, errors='ignore')

def read_sentence(sock, encoding='ASCII'):
    words = []
    while True:
        w = read_word(sock, encoding)
        if w is None:
            return None
        if w == "":
            break
        words.append(w)
    if not words:
        return []
    return words

def send_sentence(sock, words, encoding='ASCII'):
    sock.sendall(encode_sentence(*words, encoding=encoding))

# Mock данные — соответствуют ТЗ и частично нарушают best practice для аудита
MOCK_DATA = {
    "/system/resource/print": [
        {
            ".id": "*1",
            "board-name": "CCR2116-12G-4S+",
            "version": "7.25 (stable)",
            "build-time": "2025-04-10 10:00:00",
            "factory-software": "7.25",
            "total-memory": "1610612736",
            "free-memory": "1200000000",
            "total-hdd-space": "128000000",
            "free-hdd-space": "100000000",
            "architecture-name": "arm64",
            "cpu": "ARM64",
            "cpu-count": "16",
            "cpu-frequency": "2000",
            "cpu-load": "12",
            "free-memory": "800MiB",
            "uptime": "5d12:34:56",
            "write-sect-since-reboot": "12345",
            "write-sect-total": "234567",
            "bad-blocks": "0.0",
        }
    ],
    "/system/identity/print": [
        {".id": "*1", "name": "gw-core-01"}
    ],
    "/system/clock/print": [
        {".id": "*1", "time": "10:30:00", "date": "2026-10-29", "time-zone-name": "Europe/Moscow", "gmt-offset": "+03:00", "dst-active": "no"}
    ],
    "/system/routerboard/print": [
        {".id": "*1", "routerboard": "yes", "board-name": "CCR2116-12G-4S+", "model": "CCR2116-12G-4S+", "serial-number": "STAND123", "firmware-type": "alpine", "factory-firmware": "7.25", "current-firmware": "7.25", "upgrade-firmware": "7.25"}
    ],
    "/system/ntp/client/print": [
        {".id": "*1", "enabled": "yes", "mode": "unicast", "servers": "pool.ntp.org,time.cloudflare.com", "status": "synchronized", "synced-server": "pool.ntp.org"}
    ],
    "/ip/address/print": [
        {".id": "*1", "address": "192.168.0.50/16", "network": "192.168.0.0", "interface": "bridge1", "actual-interface": "bridge1", "disabled": "false", "comment": "LAN gateway"},
        {".id": "*2", "address": "111.111.111.111/24", "network": "111.111.111.0", "interface": "ether1", "actual-interface": "ether1", "disabled": "false", "comment": "WAN"},
    ],
    "/interface/print": [
        {".id": "*1", "name": "ether1", "type": "ether", "mtu": "1500", "actual-mtu": "1500", "running": "true", "disabled": "false", "comment": "WAN"},
        {".id": "*2", "name": "ether2", "type": "ether", "mtu": "1500", "running": "true", "disabled": "false"},
        {".id": "*3", "name": "ether3", "type": "ether", "mtu": "1500", "running": "true", "disabled": "false"},
        {".id": "*10", "name": "bridge1", "type": "bridge", "mtu": "1500", "running": "true", "disabled": "false", "comment": "LAN bridge ether2-10"},
    ],
    "/interface/bridge/port/print": [
        {".id": "*1", "interface": "ether2", "bridge": "bridge1", "priority": "0x80", "path-cost": "10", "edge": "no", "point-to-point": "no", "learn": "auto", "horizon": "none", "auto-isolate": "no", "restricted-role": "no", "restricted-tcn": "no", "pvid": "1", "frame-types": "admit-all", "ingress-filtering": "no"},
        {".id": "*2", "interface": "ether3", "bridge": "bridge1"},
        {".id": "*3", "interface": "ether4", "bridge": "bridge1"},
        {".id": "*4", "interface": "ether5", "bridge": "bridge1"},
        {".id": "*5", "interface": "ether6", "bridge": "bridge1"},
        {".id": "*6", "interface": "ether7", "bridge": "bridge1"},
        {".id": "*7", "interface": "ether8", "bridge": "bridge1"},
        {".id": "*8", "interface": "ether9", "bridge": "bridge1"},
        {".id": "*9", "interface": "ether10", "bridge": "bridge1"},
    ],
    "/ip/route/print": [
        {".id": "*1", "dst-address": "0.0.0.0/0", "gateway": "111.111.111.1", "gateway-status": "111.111.111.1 reachable via ether1", "distance": "1", "scope": "30", "target-scope": "10", "active": "true", "comment": "WAN GW"},
        {".id": "*2", "dst-address": "192.168.0.0/16", "gateway": "bridge1", "pref-src": "192.168.0.50", "distance": "0", "scope": "10", "active": "true"},
    ],
    "/ip/firewall/filter/print": [
        # Намеренно неполный — аудит найдет несоответствия: нет final drop, но есть established
        {".id": "*1", "chain": "input", "action": "accept", "connection-state": "established,related,untracked", "comment": "defconf: accept established"},
        {".id": "*2", "chain": "input", "action": "drop", "connection-state": "invalid", "comment": "defconf: drop invalid"},
        {".id": "*3", "chain": "input", "action": "accept", "protocol": "icmp", "comment": "accept ICMP"},
        {".id": "*4", "chain": "input", "action": "accept", "in-interface-list": "LAN", "comment": "accept LAN"},
        # Нет final drop — будет FAIL для FW-003
        {".id": "*10", "chain": "forward", "action": "accept", "connection-state": "established,related,untracked", "comment": "defconf: accept established"},
        {".id": "*11", "chain": "forward", "action": "drop", "connection-state": "invalid"},
        {".id": "*12", "chain": "forward", "action": "accept", "in-interface-list": "LAN", "out-interface-list": "WAN", "comment": "LAN -> WAN"},
    ],
    "/ip/firewall/nat/print": [
        {".id": "*1", "chain": "srcnat", "action": "masquerade", "out-interface": "ether1", "comment": "defconf: masquerade"},
    ],
    "/ip/service/print": [
        # Намеренно — telnet включен (нарушение best practice)
        {".id": "*1", "name": "telnet", "port": "23", "address": "", "disabled": "false"},
        {".id": "*2", "name": "ftp", "port": "21", "address": "", "disabled": "true"},
        {".id": "*3", "name": "www", "port": "80", "address": "", "disabled": "true"},
        {".id": "*4", "name": "ssh", "port": "22", "address": "192.168.0.0/16", "disabled": "false"},
        {".id": "*5", "name": "www-ssl", "port": "443", "address": "", "disabled": "true"},
        {".id": "*6", "name": "api", "port": "8728", "address": "", "disabled": "false"},
        {".id": "*7", "name": "winbox", "port": "8291", "address": "192.168.0.0/16", "disabled": "false"},
        {".id": "*8", "name": "api-ssl", "port": "8729", "address": "192.168.0.0/16", "disabled": "false"},
    ],
    "/ip/dns/print": [
        {".id": "*1", "servers": "1.1.1.1,8.8.8.8", "dynamic-servers": "", "allow-remote-requests": "no", "max-udp-packet-size": "4096", "query-server-timeout": "2s", "query-total-timeout": "10s", "cache-size": "2048KiB", "cache-max-ttl": "1w", "cache-used": "100KiB"}
    ],
    "/ip/dhcp-server/print": [
        {".id": "*1", "name": "lan-dhcp", "interface": "bridge1", "lease-time": "1d", "address-pool": "lan-pool", "disabled": "false", "comment": "LAN DHCP"}
    ],
    "/ip/dhcp-server/network/print": [
        {".id": "*1", "address": "192.168.0.0/16", "gateway": "192.168.0.50", "dns-server": "1.1.1.1,8.8.8.8", "domain": "lan", "comment": "LAN"}
    ],
    "/ip/pool/print": [
        {".id": "*1", "name": "lan-pool", "ranges": "192.168.0.100-192.168.0.200"}
    ],
    "/user/print": [
        {".id": "*1", "name": "admin", "group": "full", "address": "", "last-logged-in": "2026-10-29 10:00:00", "comment": ""},
        # Тех.учётки нет — будет FAIL для USR-001
    ],
    "/ip/ssh/print": [
        {".id": "*1", "strong-crypto": "yes", "forwarding-enabled": "no", "host-key-size": "2048", "allow-none-crypto": "no"}
    ],
    "/snmp/print": [
        {".id": "*1", "enabled": "yes", "contact": "noc@example.com", "location": "gw-core-01", "trap-community": "public", "trap-version": "1"}
    ],
    "/snmp/community/print": [
        {".id": "*1", "name": "public", "addresses": "::/0", "security": "none", "read-access": "yes", "write-access": "no", "authentication-protocol": "MD5", "encryption-protocol": "DES"}
        # community public на 0.0.0.0/0 — нарушение MON-001
    ],
    "/system/logging/print": [
        {".id": "*1", "topics": "info", "action": "memory", "prefix": ""},
        {".id": "*2", "topics": "error", "action": "memory"},
        {".id": "*3", "topics": "warning", "action": "memory"},
    ],
    "/system/logging/action/print": [
        {".id": "*1", "name": "memory", "target": "memory", "memory-lines": "1000", "memory-stop-on-full": "no"},
        {".id": "*2", "name": "remote", "target": "remote", "remote": "192.168.0.10", "remote-port": "514", "bsd-syslog": "no", "syslog-facility": "daemon"},
    ],
    "/ip/neighbor/discovery-settings/print": [
        {".id": "*1", "discover-interface-list": "all"}
        # должен быть LAN — нарушение SVC-004
    ],
    "/tool/mac-server/print": [
        {".id": "*1", "allowed-interface-list": "all"}
    ],
    "/tool/mac-server/mac-winbox/print": [
        {".id": "*1", "allowed-interface-list": "all"}
    ],
    "/ip/cloud/print": [
        {".id": "*1", "ddns-enabled": "yes", "dns-update-interval": "1m", "update-time": "yes", "status": "updated"}
        # должен быть no — нарушение MNT-002
    ],
    "/system/scheduler/print": [
        {".id": "*1", "name": "backup-daily", "start-date": "2026-01-01", "start-time": "02:00:00", "interval": "1d", "on-event": "/system backup save name=auto-backup; /export file=auto-export", "owner": "admin", "policy": "ftp,reboot,read,write,policy,test,password,sniff,sensitive,romon", "disabled": "false"}
    ],
    "/interface/list/print": [
        {".id": "*1", "name": "WAN", "comment": "WAN", "include": "dynamic", "exclude": ""},
        {".id": "*2", "name": "LAN", "comment": "LAN"},
    ],
    "/interface/list/member/print": [
        {".id": "*1", "list": "WAN", "interface": "ether1", "comment": ""},
        {".id": "*2", "list": "LAN", "interface": "bridge1"},
    ],
    # Для baseline проверки export
    "/export": [
        {"ret": "# RouterOS export mock for gw-core-01\n/interface bridge add name=bridge1\n/ip address add address=192.168.0.50/16 interface=bridge1\n"}
    ],
}

# Для второго хоста (gw-lab-01) — почти идентично, но с другими IP для теста раскатки
MOCK_DATA_GW_LAB = {
    **MOCK_DATA,
    "/system/identity/print": [{".id": "*1", "name": "gw-lab-01"}],
    "/ip/address/print": [
        {".id": "*1", "address": "192.168.88.1/24", "network": "192.168.88.0", "interface": "bridge1", "actual-interface": "bridge1", "disabled": "false"},
        {".id": "*2", "address": "111.111.111.112/24", "network": "111.111.111.0", "interface": "ether1", "actual-interface": "ether1", "disabled": "false"},
    ],
}

def get_mock_data(command: str, hostname: str = "gw-core-01"):
    # Выбираем данные по хосту (если gw-lab, то lab-мок)
    data_map = MOCK_DATA_GW_LAB if "lab" in hostname.lower() else MOCK_DATA
    # Прямое совпадение
    if command in data_map:
        return data_map[command]
    # Попробовать без print суффикса
    if command + "/print" in data_map:
        return data_map[command + "/print"]
    # Для /login и др.
    if command.startswith("/login"):
        return None
    # Для неизвестных — пусто, но не ошибка
    return []

def handle_client(conn, addr):
    encoding = 'ASCII'
    print(f"[mock] new connection from {addr}")
    peer_host = "gw-core-01"  # можно определить по времени или по login user?
    current_user = "admin"
    try:
        while True:
            sentence = read_sentence(conn, encoding)
            if sentence is None:
                break
            if not sentence:
                continue
            cmd = sentence[0]
            print(f"[mock] {addr} -> {sentence}")
            # Login handling
            if cmd == "/login":
                # Plain: /login + =name=xxx + =password=xxx
                # Token: /login (no args) -> respond with ret, then second /login with name/response
                has_name = any(w.startswith("=name=") for w in sentence)
                has_password = any(w.startswith("=password=") for w in sentence)
                has_response = any(w.startswith("=response=") for w in sentence)
                if not has_name and not has_password and not has_response:
                    # old token method — send challenge
                    token = "AABBCCDDEEFF00112233445566778899"
                    send_sentence(conn, ["!done", f"=ret={token}"], encoding)
                else:
                    # plain login — accept any user/pass
                    # extract user for possible host differentiation
                    for w in sentence:
                        if w.startswith("=name="):
                            current_user = w.split("=", 2)[2]
                            if "lab" in current_user:
                                peer_host = current_user
                    send_sentence(conn, ["!done"], encoding)
                continue
            # Handle api search
            # cmd is like /system/resource/print or /ip/address/print etc.
            # sentence may include query params already? But simple print handling
            # For community.routeros.api with path, it may send just path without print? Let's handle both
            # Use first word as command path
            data = get_mock_data(cmd, peer_host)
            if data is not None:
                # Возможно, клиент ожидает выборку через select — но наш мок просто возвращает все
                for row in data:
                    words = ["!re"]
                    for k, v in row.items():
                        words.append(f"={k}={v}")
                    send_sentence(conn, words, encoding)
                send_sentence(conn, ["!done"], encoding)
            else:
                # Try to handle add/remove/update — для bootstrap
                if cmd.endswith("/print"):
                    # already handled
                    send_sentence(conn, ["!done"], encoding)
                elif "/user/add" in cmd or cmd == "/user/add":
                    send_sentence(conn, ["!done", "=ret=*100"], encoding)
                elif "/user/set" in cmd or "/user/remove" in cmd:
                    send_sentence(conn, ["!done"], encoding)
                elif "add" in cmd or "set" in cmd or "remove" in cmd:
                    send_sentence(conn, ["!done"], encoding)
                else:
                    # default empty
                    print(f"[mock] unknown command {cmd}, returning empty")
                    send_sentence(conn, ["!done"], encoding)
    except Exception as e:
        print(f"[mock] error {addr}: {e}")
    finally:
        try:
            conn.close()
        except:
            pass
        print(f"[mock] closed {addr}")

def start_server(host="0.0.0.0", port=8728):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(100)
    print(f"[mock] RouterOS API mock listening on {host}:{port} — version 7.25, board CCR2116, WAN 111.111.111.111")
    print(f"[mock] Mock data: {list(MOCK_DATA.keys())[:5]} ... total {len(MOCK_DATA)} paths")
    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        t.start()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8728)
    args = parser.parse_args()
    start_server(args.host, args.port)

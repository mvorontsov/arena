from __future__ import annotations
import asyncio
import time
import json
from typing import Any, Optional
import httpx
from ros_orchestrator.config import RouterEntry
from ros_orchestrator.client.base import RouterClient, ExecutionResult

# RouterOS REST API mapping: CLI -> REST
# e.g. "/system/resource/print" -> GET /rest/system/resource
#      "/ip/address/print" -> GET /rest/ip/address
# For generic exec, we support both raw REST path and mikrotik CLI.

CLI_TO_REST = {
    "/system/resource/print": ("GET", "/rest/system/resource"),
    "/system/routerboard/print": ("GET", "/rest/system/routerboard"),
    "/system/identity/print": ("GET", "/rest/system/identity"),
    "/ip/address/print": ("GET", "/rest/ip/address"),
    "/ip/route/print": ("GET", "/rest/ip/route"),
    "/interface/print": ("GET", "/rest/interface"),
    "/interface/wireguard/print": ("GET", "/rest/interface/wireguard"),
}

class RouterOSRestClient(RouterClient):
    def __init__(self, entry: RouterEntry, demo: bool = False):
        self.entry = entry
        self.demo = demo
        self.base_url = f"{'https' if entry.auth.api_ssl else 'http'}://{entry.host}:{entry.auth.port}"
        self.auth = (entry.auth.username, entry.auth.password or "")
        self.timeout = entry.auth.timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                auth=self.auth,
                timeout=self.timeout,
                verify=False,
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _demo_response(self, command: str) -> Any:
        # Synthetic responses for demo mode
        cmd = command.strip()
        if "resource" in cmd:
            return {
                "board-name": "hAP ax3",
                "version": "7.14.2 (stable)",
                "uptime": "14d 03:21:11",
                "cpu-load": "7%",
                "free-memory": "412.3MiB",
                "total-memory": "1024.0MiB",
                "free-hdd-space": "78.2MiB",
                "write-sect-total": "184932",
                "architecture-name": "arm64",
            }
        if "identity" in cmd:
            return {"name": self.entry.name}
        if "interface" in cmd and "wireguard" in cmd:
            return [
                {"name": "wg0", "running": True, "mtu": 1420, "listen-port": 13231, "private-key": "***"},
                {"name": "wg1", "running": False, "mtu": 1420},
            ]
        if "interface" in cmd:
            return [
                {"name": "ether1", "type": "ether", "running": True, "rx-byte": 1234567890, "tx-byte": 987654321, "disabled": False},
                {"name": "ether2", "type": "ether", "running": False, "disabled": True},
                {"name": "bridge1", "type": "bridge", "running": True},
                {"name": "wlan1", "type": "wifi", "running": True},
                {"name": "wg0", "type": "wireguard", "running": True},
            ]
        if "ip/address" in cmd:
            return [
                {"address": "10.10.0.1/24", "interface": "ether1", "network": "10.10.0.0", "disabled": False},
                {"address": "192.168.88.1/24", "interface": "bridge1", "network": "192.168.88.0"},
            ]
        if "ip/route" in cmd:
            return [
                {"dst-address": "0.0.0.0/0", "gateway": "10.10.0.254", "distance": 1, "active": True},
            ]
        if "firewall" in cmd:
            return [
                {"chain": "forward", "action": "accept", "comment": "established"},
                {"chain": "input", "action": "drop", "comment": "defconf: drop all not coming from LAN"},
            ]
        if "capsman" in cmd:
            return [{"name": "cap1", "interface": "wifi1", "radio-mac": "48:8F:5A:11:22:33", "state": "running"}]
        # generic
        return {"message": f"[DEMO] executed: {command}", "host": self.entry.host}

    async def exec(self, command: str) -> ExecutionResult:
        start = time.time()
        cmd = command.strip()
        # Normalize: allow both "/system resource print" and "/system/resource/print"
        normalized = cmd.replace(" ", "/").replace("//", "/")
        # demo mode
        if self.demo or self.entry.host.startswith("10.") or self.entry.host.startswith("192.168."):
            # auto demo for example hosts (so it works without real routers)
            # But allow real if ROS_DEMO=0
            import os
            if os.getenv("ROS_DEMO", "1") != "0":
                await asyncio.sleep(0.08)  # simulate latency
                output = self._demo_response(cmd)
                return ExecutionResult(
                    host=self.entry.host,
                    name=self.entry.name,
                    success=True,
                    command=command,
                    output=output,
                    duration_ms=int((time.time() - start) * 1000),
                )

        # Real execution via REST
        try:
            client = await self._get_client()
            # Determine REST endpoint
            # For simplicity: try to map CLI to REST GET
            # If command ends with print -> GET collection
            # If contains add/set/remove -> POST/PATCH/DELETE
            method = "GET"
            path = "/rest" + normalized if normalized.startswith("/") else "/rest/" + normalized
            # Remove trailing /print for REST
            if path.endswith("/print"):
                path = path[:-6]
            # Clean double slashes
            path = path.replace("//", "/")

            # Detect mutation
            low = cmd.lower()
            if "add" in low or "set" in low or "enable" in low or "disable" in low:
                method = "POST"
            if "remove" in low:
                method = "DELETE"

            # Parse params for POST
            params = {}
            if method == "POST" and "=" in cmd:
                # very naive parser: key=value pairs after command
                parts = cmd.split()
                for p in parts:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        params[k] = v

            if method == "GET":
                resp = await client.get(path)
            elif method == "POST":
                resp = await client.post(path, json=params if params else None)
            else:
                resp = await client.delete(path)

            resp.raise_for_status()
            try:
                data = resp.json()
            except Exception:
                data = resp.text

            return ExecutionResult(
                host=self.entry.host,
                name=self.entry.name,
                success=True,
                command=command,
                output=data,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return ExecutionResult(
                host=self.entry.host,
                name=self.entry.name,
                success=False,
                command=command,
                error=str(e),
                duration_ms=int((time.time() - start) * 1000),
            )

    async def get_resource(self) -> dict:
        res = await self.exec("/system/resource/print")
        return res.output if res.success else {}

    async def backup(self) -> bytes:
        # In real RouterOS: /export -> text backup
        res = await self.exec("/export")
        if res.success:
            text = json.dumps(res.output, ensure_ascii=False, indent=2) if isinstance(res.output, (dict, list)) else str(res.output)
            return text.encode()
        return b""

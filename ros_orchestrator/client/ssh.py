from __future__ import annotations
import asyncio
import time
from typing import Optional
from ros_orchestrator.config import RouterEntry
from ros_orchestrator.client.base import RouterClient, ExecutionResult

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

class RouterOSSSHClient(RouterClient):
    def __init__(self, entry: RouterEntry, demo: bool = False):
        self.entry = entry
        self.demo = demo
        self.timeout = entry.auth.timeout

    async def exec(self, command: str) -> ExecutionResult:
        start = time.time()
        if self.demo:
            await asyncio.sleep(0.05)
            return ExecutionResult(
                host=self.entry.host,
                name=self.entry.name,
                success=True,
                command=command,
                output=f"[DEMO SSH] {command} -> ok",
                duration_ms=int((time.time() - start) * 1000),
            )

        if not HAS_PARAMIKO:
            return ExecutionResult(
                host=self.entry.host,
                name=self.entry.name,
                success=False,
                command=command,
                error="paramiko not installed",
                duration_ms=int((time.time() - start) * 1000),
            )

        def _run():
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                c.connect(
                    hostname=self.entry.host,
                    port=self.entry.auth.ssh_port,
                    username=self.entry.auth.username,
                    password=self.entry.auth.password,
                    key_filename=self.entry.auth.key_file,
                    timeout=self.timeout,
                    banner_timeout=10,
                    auth_timeout=10,
                )
                stdin, stdout, stderr = c.exec_command(command, timeout=self.timeout)
                out = stdout.read().decode(errors="ignore")
                err = stderr.read().decode(errors="ignore")
                exit_code = stdout.channel.recv_exit_status()
                c.close()
                return out, err, exit_code
            except Exception as e:
                return "", str(e), 1

        out, err, code = await asyncio.to_thread(_run)
        return ExecutionResult(
            host=self.entry.host,
            name=self.entry.name,
            success=(code == 0),
            command=command,
            output=out,
            error=err if err else None,
            duration_ms=int((time.time() - start) * 1000),
        )

    async def get_resource(self) -> dict:
        res = await self.exec("/system resource print")
        return {"raw": res.output} if res.success else {}

    async def close(self):
        pass

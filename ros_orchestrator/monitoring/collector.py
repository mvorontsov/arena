from __future__ import annotations
import asyncio
import random
from datetime import datetime
from typing import List, Dict, Optional
from ros_orchestrator.config import RouterEntry
from ros_orchestrator.client.rest import RouterOSRestClient

class MonitoringCollector:
    def __init__(self, demo: bool = True):
        self.demo = demo
        self.history: Dict[str, List[dict]] = {}

    async def collect(self, entries: List[RouterEntry], parallel: int = 20) -> List[dict]:
        sem = asyncio.Semaphore(parallel)
        results = []

        async def one(entry: RouterEntry):
            async with sem:
                client = RouterOSRestClient(entry, demo=self.demo)
                try:
                    if self.demo:
                        await asyncio.sleep(0.04)
                        data = self._demo_stats(entry)
                    else:
                        res = await client.exec("/system/resource/print")
                        data = res.output if res.success else {"error": res.error}
                        data["host"] = entry.host
                        data["name"] = entry.name
                        data["group"] = entry.group
                        data["timestamp"] = datetime.now().isoformat()
                    # store history
                    self.history.setdefault(entry.name, []).append(data)
                    if len(self.history[entry.name]) > 100:
                        self.history[entry.name] = self.history[entry.name][-100:]
                    return data
                finally:
                    await client.close()

        results = await asyncio.gather(*(one(e) for e in entries))
        return results

    def _demo_stats(self, entry: RouterEntry) -> dict:
        # realistic demo with variation
        base_cpu = random.randint(2, 18)
        base_mem_used = random.randint(30, 65)
        uptime_h = random.randint(5, 800)
        return {
            "name": entry.name,
            "host": entry.host,
            "group": entry.group,
            "board-name": random.choice(["hAP ax3", "CCR2116", "CRS326", "RB5009", "Chateau 5G"]),
            "version": "7.14.2",
            "uptime": f"{uptime_h//24}d {uptime_h%24:02d}:{(random.randint(0,59)):02d}:{(random.randint(0,59)):02d}",
            "cpu-load": f"{base_cpu}%",
            "cpu-count": random.choice([4, 8, 16]),
            "free-memory": f"{random.randint(300, 800)}MiB",
            "total-memory": "1024MiB",
            "free-hdd-space": f"{random.randint(50, 120)}MiB",
            "bad-blocks": "0%",
            "write-sect-total": str(random.randint(100000, 500000)),
            "rx-byte": random.randint(1_000_000_000, 9_000_000_000),
            "tx-byte": random.randint(1_000_000_000, 9_000_000_000),
            "clients": random.randint(5, 120),
            "status": "online" if random.random() > 0.07 else "offline",
            "timestamp": datetime.now().isoformat(),
        }

    def alerts(self, stats: List[dict]) -> List[dict]:
        alerts = []
        for s in stats:
            try:
                cpu = int(s.get("cpu-load", "0%").replace("%", ""))
                if cpu > 85:
                    alerts.append({"host": s["name"], "level": "critical", "msg": f"CPU {cpu}%", "type": "cpu"})
                elif cpu > 70:
                    alerts.append({"host": s["name"], "level": "warning", "msg": f"CPU {cpu}%", "type": "cpu"})
                if s.get("status") == "offline":
                    alerts.append({"host": s["name"], "level": "critical", "msg": "offline", "type": "availability"})
                # memory
                free = s.get("free-memory", "500MiB")
                try:
                    free_val = int(free.replace("MiB", ""))
                    if free_val < 100:
                        alerts.append({"host": s["name"], "level": "warning", "msg": f"low memory {free}", "type": "memory"})
                except:
                    pass
            except:
                continue
        return alerts

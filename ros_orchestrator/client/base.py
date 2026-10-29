from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any, Literal
from datetime import datetime

@dataclass
class ExecutionResult:
    host: str
    name: str
    success: bool
    command: str
    output: Any = None
    error: Optional[str] = None
    duration_ms: int = 0
    changed: bool = False
    diff: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self):
        return {
            "host": self.host,
            "name": self.name,
            "success": self.success,
            "command": self.command,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "changed": self.changed,
            "diff": self.diff,
            "timestamp": self.timestamp.isoformat(),
        }

class RouterClient:
    async def exec(self, command: str) -> ExecutionResult:
        raise NotImplementedError

    async def get_resource(self) -> dict:
        raise NotImplementedError

    async def close(self):
        pass

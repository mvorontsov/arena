from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Literal
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ROS_", env_file=".env", extra="ignore")

    inventory_path: Path = Field(default=Path("inventory.yml"), description="Путь к inventory")
    playbooks_dir: Path = Field(default=Path("playbooks"))
    templates_dir: Path = Field(default=Path("templates"))
    backups_dir: Path = Field(default=Path("backups"))
    db_path: Path = Field(default=Path("ros.db"))
    log_level: str = Field(default="INFO")
    default_timeout: int = Field(default=10)
    default_parallel: int = Field(default=20)
    demo_mode: bool = Field(default=False, description="Демо без реальных роутеров")

    # API server
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    secret_key: str = Field(default="change-me-in-production-please")

def get_config() -> AppConfig:
    return AppConfig()

def resolve_path(p: Path) -> Path:
    if p.is_absolute():
        return p
    # search in cwd, then in arena root
    candidates = [Path.cwd() / p, Path(__file__).parent.parent / p, Path.home() / ".ros" / p]
    for c in candidates:
        if c.exists():
            return c
    return Path.cwd() / p

class RouterAuth(BaseModel):
    username: str = "admin"
    password: Optional[str] = None
    key_file: Optional[str] = None
    port: int = 8728  # api
    api_ssl: bool = False
    ssh_port: int = 22
    timeout: int = 10

class RouterEntry(BaseModel):
    name: str
    host: str
    group: str = "default"
    tags: list[str] = []
    auth: RouterAuth = Field(default_factory=RouterAuth)
    vars: dict = Field(default_factory=dict)
    comment: Optional[str] = None
    # capabilities
    board: Optional[str] = None
    version: Optional[str] = None

class InventoryFile(BaseModel):
    defaults: RouterAuth = Field(default_factory=RouterAuth)
    groups: dict[str, dict] = Field(default_factory=dict)
    hosts: list[RouterEntry]

    @classmethod
    def example(cls) -> dict:
        return {
            "defaults": {"username": "admin", "password": "changeme", "api_ssl": False, "timeout": 10},
            "groups": {
                "edge": {"vars": {"dns": "1.1.1.1", "ntp": "pool.ntp.org"}, "comment": "Пограничные роутеры"},
                "branch": {"vars": {"capsman": "10.0.0.1"}},
                "lab": {"vars": {}, "comment": "Лаборатория"},
            },
            "hosts": [
                {"name": "gw-msk-01", "host": "10.10.0.1", "group": "edge", "tags": ["msk", "prod"], "comment": "GW Москва"},
                {"name": "gw-spb-01", "host": "10.10.0.2", "group": "edge", "tags": ["spb", "prod"]},
                {"name": "cap-branch-11", "host": "10.20.11.1", "group": "branch", "tags": ["retail"]},
                {"name": "lab-hap-ax3", "host": "192.168.88.1", "group": "lab", "tags": ["lab", "wifi6"]},
            ],
        }

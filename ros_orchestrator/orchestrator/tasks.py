from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Literal, Any, Dict
from pydantic import BaseModel, Field
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

class Task(BaseModel):
    name: str = Field(description="Человекочитаемое имя задачи")
    command: Optional[str] = None  # raw RouterOS command
    template: Optional[str] = None  # path to jinja2 template
    vars: Dict[str, Any] = Field(default_factory=dict)
    when: Optional[str] = None  # jinja condition
    tags: List[str] = Field(default_factory=list)
    ignore_errors: bool = False
    register_var: Optional[str] = Field(default=None, alias="register")  # save output to variable
    loop: Optional[List[Any]] = None
    notify: Optional[str] = None

class Play(BaseModel):
    name: str
    hosts: str = Field(description="group/tag/pattern like 'edge' or 'lab,*prod*'")
    vars: Dict[str, Any] = Field(default_factory=dict)
    tasks: List[Task]
    strategy: Literal["parallel", "sequential", "rolling"] = "parallel"
    parallel: int = 20
    become: bool = False
    serial: Optional[int] = None  # for rolling

class Playbook(BaseModel):
    name: str = Field(default="Playbook")
    description: Optional[str] = None
    plays: List[Play]

    @classmethod
    def from_file(cls, path: Path, extra_vars: Optional[dict] = None) -> "Playbook":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # supports two formats:
        # 1. list of plays directly (like Ansible)
        # 2. dict with 'plays' key
        if isinstance(data, list):
            data = {"name": path.stem, "plays": data}
        if "plays" not in data:
            # maybe single play with hosts+tasks
            if "hosts" in data and "tasks" in data:
                data = {"name": data.get("name", path.stem), "plays": [data]}

        pb = cls(**data)
        # inject extra_vars into each play
        if extra_vars:
            for play in pb.plays:
                play.vars.update(extra_vars)
        return pb

    def to_dict(self):
        return self.model_dump()

    def render_command(self, task: Task, host_vars: dict, templates_dir: Path) -> str:
        # combine vars
        ctx = {**host_vars, **task.vars}
        if task.template:
            env = Environment(
                loader=FileSystemLoader(str(templates_dir)),
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
            )
            tmpl = env.get_template(task.template)
            return tmpl.render(**ctx)
        elif task.command:
            env = Environment(undefined=StrictUndefined)
            tmpl = env.from_string(task.command)
            return tmpl.render(**ctx)
        else:
            raise ValueError(f"Task '{task.name}' должен иметь command или template")

    def filter_tasks_by_tags(self, tags: Optional[List[str]] = None, skip_tags: Optional[List[str]] = None):
        if not tags and not skip_tags:
            return
        for play in self.plays:
            filtered = []
            for t in play.tasks:
                if tags and not any(tag in t.tags for tag in tags):
                    continue
                if skip_tags and any(tag in t.tags for tag in skip_tags):
                    continue
                filtered.append(t)
            play.tasks = filtered

class BackupSpec(BaseModel):
    name: str
    schedule: Optional[str] = None  # cron
    retention: int = 30
    include: List[str] = Field(default_factory=lambda: ["export", "backup"])
    encrypt: bool = False

class RollbackPoint(BaseModel):
    id: str
    host: str
    timestamp: str
    commands: List[str]
    diff: Optional[str] = None

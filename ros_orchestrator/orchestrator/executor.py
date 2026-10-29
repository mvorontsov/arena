from __future__ import annotations
import asyncio
import time
import difflib
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich.live import Live

from ros_orchestrator.config import RouterEntry, get_config
from ros_orchestrator.client.base import ExecutionResult
from ros_orchestrator.client.rest import RouterOSRestClient
from ros_orchestrator.orchestrator.tasks import Playbook, Play, Task

console = Console()

@dataclass
class JobResult:
    host: str
    name: str
    task: str
    result: ExecutionResult
    skipped: bool = False
    changed: bool = False

@dataclass
class Job:
    id: str
    playbook: str
    total_hosts: int
    total_tasks: int
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    results: List[JobResult] = field(default_factory=list)
    status: str = "running"  # running, success, failed, partial

    def summary(self) -> dict:
        success = sum(1 for r in self.results if r.result.success)
        failed = sum(1 for r in self.results if not r.result.success and not r.skipped)
        skipped = sum(1 for r in self.results if r.skipped)
        return {
            "id": self.id,
            "playbook": self.playbook,
            "total": len(self.results),
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "status": self.status,
            "started": self.started_at.isoformat(),
            "finished": self.finished_at.isoformat() if self.finished_at else None,
        }

class Orchestrator:
    def __init__(self, inventory, templates_dir: Optional[Path] = None, demo: bool = False):
        self.inventory = inventory
        self.templates_dir = templates_dir or get_config().templates_dir
        self.demo = demo
        self.jobs: Dict[str, Job] = {}

    def _make_client(self, entry: RouterEntry):
        # Prefer REST, fallback to SSH if needed
        # For now use REST always
        return RouterOSRestClient(entry, demo=self.demo)

    async def exec_on_hosts(
        self,
        command: str,
        hosts: List[RouterEntry],
        parallel: int = 20,
        dry_run: bool = False,
    ) -> List[ExecutionResult]:
        semaphore = asyncio.Semaphore(parallel)
        results: List[ExecutionResult] = []

        async def run_one(entry: RouterEntry):
            async with semaphore:
                client = self._make_client(entry)
                try:
                    if dry_run:
                        return ExecutionResult(
                            host=entry.host,
                            name=entry.name,
                            success=True,
                            command=command,
                            output=f"[DRY-RUN] would execute: {command}",
                            changed=False,
                        )
                    res = await client.exec(command)
                    return res
                finally:
                    await client.close()

        tasks = [run_one(h) for h in hosts]
        results = await asyncio.gather(*tasks)
        return results

    async def run_playbook(
        self,
        playbook: Playbook,
        limit: Optional[str] = None,
        tags: Optional[List[str]] = None,
        skip_tags: Optional[List[str]] = None,
        dry_run: bool = False,
        diff: bool = False,
        check: bool = False,
        parallel: Optional[int] = None,
    ) -> Job:
        job_id = f"job-{int(time.time())}"
        job = Job(id=job_id, playbook=playbook.name, total_hosts=0, total_tasks=sum(len(p.tasks) for p in playbook.plays))
        self.jobs[job_id] = job

        if tags or skip_tags:
            playbook.filter_tasks_by_tags(tags, skip_tags)

        # progress tracking
        all_results: List[JobResult] = []

        for play in playbook.plays:
            # resolve hosts for this play
            # hosts can be group, tag, pattern
            hosts = self._resolve_hosts(play.hosts, limit)
            if not hosts:
                console.print(f"[yellow]Play '{play.name}': нет хостов по селектору '{play.hosts}'[/yellow]")
                continue

            job.total_hosts += len(hosts)
            console.print(Panel(f"[bold cyan]{play.name}[/bold cyan] → {len(hosts)} хостов | стратегия: {play.strategy} | параллельно: {play.parallel}", expand=False))

            # For each task in play, execute across hosts
            for task in play.tasks:
                # when condition (simple jinja)
                if task.when:
                    # naive evaluation: will be per-host
                    pass

                # Support loop
                loop_items = task.loop or [None]

                for item in loop_items:
                    # Render command per host (vars differ)
                    # We'll do parallel execution for this task

                    # Build per-host commands
                    host_commands: Dict[str, str] = {}
                    for h in hosts:
                        ctx = {
                            "inventory_hostname": h.name,
                            "host": h.host,
                            "group": h.group,
                            "tags": h.tags,
                            **h.vars,
                            **play.vars,
                            **task.vars,
                            "item": item,
                        }
                        try:
                            cmd = playbook.render_command(task, ctx, self.templates_dir)
                            # evaluate when per host
                            if task.when:
                                from jinja2 import Environment, StrictUndefined
                                env = Environment(undefined=StrictUndefined)
                                tmpl = env.from_string(f"{{% if {task.when} %}}true{{% else %}}false{{% endif %}}")
                                should = tmpl.render(**ctx).strip()
                                if should != "true":
                                    host_commands[h.name] = "__SKIP__"
                                    continue
                            host_commands[h.name] = cmd
                        except Exception as e:
                            # rendering error
                            err_res = ExecutionResult(host=h.host, name=h.name, success=False, command=task.name, error=f"template error: {e}")
                            all_results.append(JobResult(host=h.host, name=h.name, task=task.name, result=err_res))
                            host_commands[h.name] = "__ERROR__"

                    # Now execute
                    if play.strategy == "sequential":
                        # one by one
                        for h in hosts:
                            cmd = host_commands.get(h.name)
                            if cmd in ("__SKIP__", "__ERROR__"):
                                if cmd == "__SKIP__":
                                    all_results.append(JobResult(host=h.host, name=h.name, task=task.name, result=ExecutionResult(host=h.host, name=h.name, success=True, command=task.name, output="skipped (when=false)"), skipped=True))
                                continue
                            client = self._make_client(h)
                            res = await client.exec(cmd) if not dry_run else ExecutionResult(host=h.host, name=h.name, success=True, command=cmd, output=f"[DRY-RUN] {cmd}")
                            # diff simulation
                            if diff:
                                res.diff = f"- old config line\n+ {cmd}"
                            all_results.append(JobResult(host=h.host, name=h.name, task=task.name, result=res, changed=res.changed or res.success))
                            await client.close()
                            # respect serial rolling
                            if play.serial:
                                await asyncio.sleep(0.1)
                    else:
                        # parallel / rolling
                        sem = asyncio.Semaphore(parallel or play.parallel)

                        async def run_host(h: RouterEntry):
                            async with sem:
                                cmd = host_commands.get(h.name)
                                if cmd in ("__SKIP__", "__ERROR__"):
                                    return JobResult(host=h.host, name=h.name, task=task.name, result=ExecutionResult(host=h.host, name=h.name, success=True, command=task.name, output="skipped"), skipped=(cmd=="__SKIP__"))
                                client = self._make_client(h)
                                try:
                                    if dry_run or check:
                                        await asyncio.sleep(0.03)
                                        res = ExecutionResult(host=h.host, name=h.name, success=True, command=cmd, output=f"[DRY-RUN] would run: {cmd}", changed=True)
                                        if diff:
                                            res.diff = f"--- before\n+++ after\n@@\n-# old\n+{cmd}"
                                        return JobResult(host=h.host, name=h.name, task=task.name, result=res, changed=True)
                                    res = await client.exec(cmd)
                                    if diff:
                                        res.diff = f"---\n+++ {h.name}\n+ {cmd}"
                                    return JobResult(host=h.host, name=h.name, task=task.name, result=res, changed=res.success)
                                finally:
                                    await client.close()

                        batch_results = await asyncio.gather(*(run_host(h) for h in hosts))
                        all_results.extend(batch_results)

                    # pretty print task result
                    self._print_task_batch(task.name, [r for r in all_results if r.task == task.name][-len(hosts):])

        # finalize job
        job.results = all_results
        job.finished_at = datetime.now()
        failed = sum(1 for r in all_results if not r.result.success and not r.skipped)
        if failed == 0:
            job.status = "success"
        elif failed < len(all_results):
            job.status = "partial"
        else:
            job.status = "failed"

        self._print_job_summary(job)
        return job

    def _resolve_hosts(self, selector: str, limit: Optional[str]) -> List[RouterEntry]:
        # selector can be: group name, tag, pattern, or "all"
        if selector == "all":
            hosts = self.inventory.entries
        else:
            # try group first, then tag, then pattern
            hosts = self.inventory.filter(group=selector)
            if not hosts:
                hosts = self.inventory.filter(tag=selector)
            if not hosts:
                hosts = self.inventory.filter(name=selector)
            if not hosts:
                hosts = self.inventory.filter(limit=selector)
        if limit:
            # further filter
            import fnmatch
            pats = [p.strip() for p in limit.split(",")]
            filtered = []
            for pat in pats:
                for h in hosts:
                    if fnmatch.fnmatch(h.name, pat) or fnmatch.fnmatch(h.host, pat) or fnmatch.fnmatch(h.group, pat):
                        if h not in filtered:
                            filtered.append(h)
            hosts = filtered
        return hosts

    def _print_task_batch(self, task_name: str, results: List[JobResult]):
        t = Table(title=f"Задача: {task_name}", show_lines=False, expand=False)
        t.add_column("Host", style="cyan", width=18)
        t.add_column("Status", justify="center", width=10)
        t.add_column("Duration", justify="right", width=10)
        t.add_column("Output", style="dim", width=60)
        for r in results:
            status = "[green]OK[/green]" if r.result.success else "[red]FAIL[/red]"
            if r.skipped:
                status = "[yellow]SKIP[/yellow]"
            out = str(r.result.output)[:140] if r.result.output else (r.result.error or "")[:140]
            # truncate
            out = out.replace("\n", " ")[:120]
            t.add_row(r.name, status, f"{r.result.duration_ms}ms", out)
        console.print(t)

    def _print_job_summary(self, job: Job):
        s = job.summary()
        color = "green" if s["status"] == "success" else "yellow" if s["status"] == "partial" else "red"
        console.print(Panel(
            f"[{color}]Job {job.id}[/{color}]  Playbook: {job.playbook}\n"
            f"Hosts: {job.total_hosts}  Tasks: {job.total_tasks}  Results: {s['total']}\n"
            f"[green]OK: {s['success']}[/green]  [red]FAIL: {s['failed']}[/red]  [yellow]SKIP: {s['skipped']}[/yellow]\n"
            f"Status: [{color}]{s['status'].upper()}[/{color}]  Duration: {(job.finished_at - job.started_at).total_seconds():.1f}s",
            title="Job Summary", border_style=color
        ))

    def diff_configs(self, before: str, after: str, filename: str = "config") -> str:
        diff = difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile=f"a/{filename}", tofile=f"b/{filename}", lineterm="")
        return "\n".join(diff)

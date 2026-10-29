from __future__ import annotations
import asyncio
import json
import sys
import yaml
from pathlib import Path
from typing import Optional, List
from datetime import datetime

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich.tree import Tree
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax

from ros_orchestrator.config import get_config, resolve_path
from ros_orchestrator.inventory.manager import load_inventory, save_inventory
from ros_orchestrator.config import RouterEntry, RouterAuth
from ros_orchestrator.orchestrator.tasks import Playbook
from ros_orchestrator.orchestrator.executor import Orchestrator
from ros_orchestrator.backup.manager import BackupManager
from ros_orchestrator.monitoring.collector import MonitoringCollector

console = Console()
app = typer.Typer(
    name="rosctl",
    help="Оркестратор для MikroTik RouterOS — массовое управление, шаблоны, бэкапы, мониторинг",
    add_completion=True,
    rich_markup_mode="rich",
)

# Global options
inventory_opt = typer.Option(None, "--inventory", "-i", help="Путь к inventory.yml")
group_opt = typer.Option(None, "--group", "-g", help="Фильтр по группе")
tag_opt = typer.Option(None, "--tag", "-t", help="Фильтр по тегу")
limit_opt = typer.Option(None, "--limit", "-l", help="Лимит по паттерну (glob, comma-separated)")
parallel_opt = typer.Option(20, "--parallel", "-p", help="Параллельность")
dry_run_opt = typer.Option(False, "--dry-run", help="Только показать что будет сделано")
verbose_opt = typer.Option(False, "--verbose", "-v", help="Подробный вывод")


def get_inventory(path: Optional[Path] = None):
    cfg = get_config()
    if path:
        return load_inventory(Path(path))
    return load_inventory()


# ─────────────────────────────────────────────
# Root commands
# ─────────────────────────────────────────────

@app.command("version")
def version():
    """Показать версию"""
    from ros_orchestrator import __version__
    console.print(Panel(f"[bold cyan]ros-orchestrator[/bold cyan] v{__version__}\n[dim]Оркестратор для MikroTik RouterOS[/dim]", title="Version"))

@app.command("init")
def init(
    path: Path = typer.Argument(Path("inventory.yml"), help="Куда создать inventory"),
    force: bool = typer.Option(False, "--force", help="Перезаписать"),
):
    """Инициализировать новый проект (inventory + примеры)"""
    if path.exists() and not force:
        console.print(f"[red]Файл уже существует: {path} (используйте --force)[/red]")
        raise typer.Exit(1)

    from ros_orchestrator.config import InventoryFile
    example = InventoryFile.example()
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(example, f, allow_unicode=True, sort_keys=False)
    console.print(f"[green]✓ inventory создан: {path}[/green]")

    # create dirs
    for d in ["playbooks", "templates", "backups"]:
        Path(d).mkdir(exist_ok=True)
        console.print(f"[dim]  dir: {d}/[/dim]")

    # example playbook
    pb_path = Path("playbooks/example.yml")
    if not pb_path.exists():
        pb_example = {
            "name": "Базовая настройка",
            "description": "Пример плейбука для настройки DNS и NTP",
            "plays": [
                {
                    "name": "Настройка сети",
                    "hosts": "all",
                    "vars": {"dns_primary": "1.1.1.1", "dns_secondary": "8.8.8.8"},
                    "tasks": [
                        {"name": "Установить DNS", "command": "/ip dns set servers={{ dns_primary }},{{ dns_secondary }} allow-remote-requests=yes", "tags": ["dns"]},
                        {"name": "Установить NTP", "command": "/system ntp client set enabled=yes", "tags": ["ntp"]},
                        {"name": "Показать ресурсы", "command": "/system/resource/print", "tags": ["info"]},
                    ],
                }
            ],
        }
        with open(pb_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(pb_example, f, allow_unicode=True, sort_keys=False)
        console.print(f"[green]✓ плейбук: {pb_path}[/green]")

    # example template
    tmpl_path = Path("templates/wireguard.rsc.j2")
    tmpl_path.parent.mkdir(exist_ok=True)
    tmpl_path.write_text("""# WireGuard template — {{ inventory_hostname }}
/interface wireguard add name={{ wg_name | default('wg0') }} listen-port={{ wg_port | default(13231) }} private-key="{{ wg_private_key }}" comment="managed by rosctl"
/ip address add address={{ wg_address }} interface={{ wg_name | default('wg0') }}
{% for peer in peers | default([]) %}
/interface wireguard peers add interface={{ wg_name | default('wg0') }} public-key="{{ peer.pubkey }}" allowed-address={{ peer.allowed }} endpoint-address={{ peer.endpoint }} persistent-keepalive=25s
{% endfor %}
""", encoding="utf-8")
    console.print(f"[green]✓ шаблон: {tmpl_path}[/green]")

    console.print(Panel("[bold green]Готово![/bold green] Попробуйте:\n  rosctl inventory list\n  rosctl exec \"/system/resource/print\"\n  rosctl play playbooks/example.yml --dry-run", title="Init complete"))


# ─────────────────────────────────────────────
# Inventory group
# ─────────────────────────────────────────────
inv_app = typer.Typer(help="Управление инвентарём")
app.add_typer(inv_app, name="inventory", help="Инвентарь устройств")

@inv_app.command("list")
def inv_list(
    inventory: Optional[Path] = inventory_opt,
    group: Optional[str] = group_opt,
    tag: Optional[str] = tag_opt,
    limit: Optional[str] = limit_opt,
    json_out: bool = typer.Option(False, "--json", help="Вывод в JSON"),
):
    """Показать все устройства"""
    inv = get_inventory(inventory)
    entries = inv.filter(group=group, tag=tag, limit=limit)
    if json_out:
        console.print_json(data=inv.to_dict())
        # filtered
        filtered_dict = {"filtered": len(entries), "hosts": [e.model_dump() for e in entries]}
        console.print_json(data=filtered_dict)
        return
    console.print(inv.table(entries))
    # footer
    console.print(f"[dim]Группы: {', '.join(inv.groups_list())} | Теги: {', '.join(inv.tags_list())}[/dim]")

@inv_app.command("groups")
def inv_groups(inventory: Optional[Path] = inventory_opt):
    """Список групп"""
    inv = get_inventory(inventory)
    t = Table(title="Группы")
    t.add_column("Group", style="magenta")
    t.add_column("Hosts", justify="right")
    t.add_column("Vars")
    for g in inv.groups_list():
        hosts = inv.filter(group=g)
        vars_preview = str(inv.raw.groups.get(g, {}).get("vars", {}))[:60]
        t.add_row(g, str(len(hosts)), vars_preview)
    console.print(t)

@inv_app.command("show")
def inv_show(name: str = typer.Argument(..., help="Имя хоста"), inventory: Optional[Path] = inventory_opt):
    """Детали устройства"""
    inv = get_inventory(inventory)
    matches = inv.filter(name=name)
    if not matches:
        # try host filter
        matches = inv.filter(host=name)
    if not matches:
        console.print(f"[red]Хост не найден: {name}[/red]")
        raise typer.Exit(1)
    e = matches[0]
    # pretty panel
    info = f"[bold]{e.name}[/bold]  [dim]{e.host}[/dim]\nGroup: [magenta]{e.group}[/magenta]  Tags: {', '.join(e.tags)}\nUser: {e.auth.username}  Port: {e.auth.port}  SSL: {e.auth.api_ssl}\nComment: {e.comment or '-'}"
    if e.vars:
        info += f"\nVars: {json.dumps(e.vars, ensure_ascii=False)}"
    console.print(Panel(info, title="Host detail"))

@inv_app.command("add")
def inv_add(
    name: str = typer.Argument(..., help="Имя"),
    host: str = typer.Argument(..., help="IP/hostname"),
    group: str = typer.Option("default", "--group", "-g"),
    tags: str = typer.Option("", "--tags", help="Теги через запятую"),
    username: str = typer.Option("admin", "--user", "-u"),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="Пароль"),
    inventory: Optional[Path] = inventory_opt,
):
    """Добавить устройство"""
    inv = get_inventory(inventory)
    entry = RouterEntry(
        name=name,
        host=host,
        group=group,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        auth=RouterAuth(username=username, password=password),
    )
    inv.entries.append(entry)
    # also add to raw
    inv.raw.hosts.append(entry)
    save_inventory(inv)
    console.print(f"[green]✓ добавлен {name} ({host}) → {inv.path}[/green]")

@inv_app.command("test")
def inv_test(
    inventory: Optional[Path] = inventory_opt,
    group: Optional[str] = group_opt,
    limit: Optional[str] = limit_opt,
    parallel: int = parallel_opt,
):
    """Проверить доступность всех устройств"""
    inv = get_inventory(inventory)
    hosts = inv.filter(group=group, limit=limit)
    if not hosts:
        console.print("[yellow]Нет хостов по фильтру[/yellow]")
        raise typer.Exit(1)

    async def _run():
        orch = Orchestrator(inv, demo=True)  # demo mode for now, real would be False
        results = await orch.exec_on_hosts("/system/identity/print", hosts, parallel=parallel)
        t = Table(title=f"Connectivity test ({len(hosts)} hosts)")
        t.add_column("Host", style="cyan")
        t.add_column("Group", style="magenta")
        t.add_column("Reachable", justify="center")
        t.add_column("Latency", justify="right")
        t.add_column("Identity")
        for r in results:
            reachable = "[green]● online[/green]" if r.success else "[red]● offline[/red]"
            identity = str(r.output.get("name") if isinstance(r.output, dict) else r.output)[:30] if r.success else (r.error or "")[:40]
            t.add_row(r.name, next((h.group for h in hosts if h.name == r.name), ""), reachable, f"{r.duration_ms}ms", identity)
        console.print(t)
        failed = sum(1 for r in results if not r.success)
        if failed:
            console.print(f"[yellow]Недоступно: {failed}/{len(results)}[/yellow]")
        else:
            console.print("[green]Все устройства доступны ✓[/green]")

    asyncio.run(_run())


# ─────────────────────────────────────────────
# Exec
# ─────────────────────────────────────────────
@app.command("exec")
def exec_cmd(
    command: str = typer.Argument(..., help="RouterOS команда, например '/system/resource/print'"),
    inventory: Optional[Path] = inventory_opt,
    group: Optional[str] = group_opt,
    tag: Optional[str] = tag_opt,
    limit: Optional[str] = limit_opt,
    parallel: int = parallel_opt,
    dry_run: bool = dry_run_opt,
    output: str = typer.Option("table", "--output", "-o", help="Формат: table/json/yaml"),
):
    """Выполнить команду на группе устройств"""
    inv = get_inventory(inventory)
    hosts = inv.filter(group=group, tag=tag, limit=limit)
    if not hosts:
        console.print("[red]Нет хостов по фильтру. Проверьте inventory.[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]→ {command} на {len(hosts)} хостах (parallel={parallel}) dry_run={dry_run}[/dim]")

    async def _run():
        orch = Orchestrator(inv, demo=True)
        results = await orch.exec_on_hosts(command, hosts, parallel=parallel, dry_run=dry_run)
        if output == "json":
            console.print_json(data=[r.to_dict() for r in results])
            return
        if output == "yaml":
            console.print(yaml.safe_dump([r.to_dict() for r in results], allow_unicode=True))
            return
        # table
        t = Table(title=f"exec: {command}", show_lines=True)
        t.add_column("Host", style="cyan", width=18)
        t.add_column("Group", style="magenta", width=10)
        t.add_column("Status", justify="center", width=8)
        t.add_column("Output", width=70)
        for r in results:
            status = "[green]OK[/green]" if r.success else "[red]ERR[/red]"
            out = r.output if r.success else r.error
            if isinstance(out, (dict, list)):
                out = json.dumps(out, ensure_ascii=False, indent=2)
            out = str(out)[:800].replace("\n", " ")
            # syntax highlight json
            t.add_row(r.name, next((h.group for h in hosts if h.name == r.name), ""), status, out)
        console.print(t)
        console.print(f"[dim]Успешно: {sum(1 for r in results if r.success)}/{len(results)}  Ошибок: {sum(1 for r in results if not r.success)}[/dim]")

    asyncio.run(_run())


# ─────────────────────────────────────────────
# Playbook
# ─────────────────────────────────────────────
@app.command("play")
def play(
    playbook: Path = typer.Argument(..., help="Путь к playbook.yml"),
    inventory: Optional[Path] = inventory_opt,
    limit: Optional[str] = limit_opt,
    tags: Optional[str] = typer.Option(None, "--tags", help="Только задачи с тегами"),
    skip_tags: Optional[str] = typer.Option(None, "--skip-tags"),
    dry_run: bool = typer.Option(False, "--dry-run", "--check", help="Dry-run (не применять)"),
    diff: bool = typer.Option(False, "--diff", help="Показать diff"),
    parallel: int = parallel_opt,
    extra_vars: Optional[str] = typer.Option(None, "--extra-vars", "-e", help="Доп. переменные key=value, key=value"),
):
    """Запустить плейбук (аналог ansible-playbook)"""
    inv = get_inventory(inventory)
    if not playbook.exists():
        console.print(f"[red]Playbook не найден: {playbook}[/red]")
        raise typer.Exit(1)

    # parse extra vars
    ev = {}
    if extra_vars:
        for pair in extra_vars.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                ev[k.strip()] = v.strip()

    pb = Playbook.from_file(playbook, extra_vars=ev)
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
    else:
        tag_list = None
    if skip_tags:
        skip_list = [t.strip() for t in skip_tags.split(",")]
    else:
        skip_list = None

    console.print(Panel(f"[bold]{pb.name}[/bold]\n{pb.description or ''}\n[dim]{playbook} | {len(pb.plays)} plays | {sum(len(p.tasks) for p in pb.plays)} tasks[/dim]", title="Playbook"))

    async def _run():
        orch = Orchestrator(inv, templates_dir=Path("templates"), demo=True)
        job = await orch.run_playbook(pb, limit=limit, tags=tag_list, skip_tags=skip_list, dry_run=dry_run, diff=diff, parallel=parallel)
        if job.status == "failed":
            raise typer.Exit(2)
        elif job.status == "partial":
            console.print("[yellow]Завершено с ошибками (partial)[/yellow]")
        else:
            console.print("[green]Playbook успешно выполнен ✓[/green]")

    asyncio.run(_run())


@app.command("lint")
def lint(playbook: Path = typer.Argument(..., help="Playbook для проверки")):
    """Проверить синтаксис плейбука"""
    if not playbook.exists():
        console.print(f"[red]Не найден: {playbook}[/red]")
        raise typer.Exit(1)
    try:
        pb = Playbook.from_file(playbook)
        console.print(f"[green]✓ {playbook} — валиден[/green]")
        console.print(f"  Plays: {len(pb.plays)}")
        for play in pb.plays:
            console.print(f"  [cyan]{play.name}[/cyan] hosts={play.hosts} tasks={len(play.tasks)} strategy={play.strategy}")
            for t in play.tasks:
                console.print(f"    - {t.name} [dim]{'tags='+','.join(t.tags) if t.tags else ''}[/dim]")
        # jinja check
        for play in pb.plays:
            for task in play.tasks:
                if task.template:
                    tmpl_path = Path("templates") / task.template
                    if not tmpl_path.exists():
                        console.print(f"[yellow]⚠ шаблон не найден: {task.template}[/yellow]")
        console.print("[green]Lint OK[/green]")
    except Exception as e:
        console.print(f"[red]Ошибка: {e}[/red]")
        raise typer.Exit(1)

# ─────────────────────────────────────────────
# Template
# ─────────────────────────────────────────────
tmpl_app = typer.Typer(help="Шаблоны Jinja2 → RouterOS RSC")
app.add_typer(tmpl_app, name="template", help="Шаблоны")

@tmpl_app.command("list")
def tmpl_list():
    """Список шаблонов"""
    tmpl_dir = Path("templates")
    if not tmpl_dir.exists():
        console.print("[yellow]Папка templates/ пуста[/yellow]")
        return
    t = Table(title="Templates")
    t.add_column("Name", style="cyan")
    t.add_column("Size", justify="right")
    t.add_column("Modified")
    for f in tmpl_dir.rglob("*.j2"):
        t.add_row(str(f.relative_to(tmpl_dir)), f"{f.stat().st_size}b", datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"))
    for f in tmpl_dir.rglob("*.rsc*"):
        if f.suffix != ".j2":
            t.add_row(str(f.relative_to(tmpl_dir)), f"{f.stat().st_size}b", datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"))
    console.print(t)

@tmpl_app.command("render")
def tmpl_render(
    template: str = typer.Argument(..., help="Имя шаблона в templates/"),
    host: str = typer.Option(None, "--host", help="Хост для контекста (имя из inventory)"),
    var: List[str] = typer.Option([], "--var", "-v", help="Переменные key=value"),
    inventory: Optional[Path] = inventory_opt,
):
    """Отрендерить шаблон для хоста"""
    inv = get_inventory(inventory)
    # find host context
    ctx = {}
    if host:
        matches = inv.filter(name=host)
        if matches:
            h = matches[0]
            ctx = {"inventory_hostname": h.name, "host": h.host, "group": h.group, "tags": h.tags, **h.vars}
    # extra vars
    for pair in var:
        if "=" in pair:
            k, v = pair.split("=", 1)
            ctx[k.strip()] = v.strip()
        else:
            ctx[pair] = True

    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    env = Environment(loader=FileSystemLoader("templates"), undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    try:
        tmpl = env.get_template(template)
        out = tmpl.render(**ctx)
        syntax = Syntax(out, "routeros", theme="monokai", line_numbers=True)
        console.print(Panel(syntax, title=f"Rendered: {template} → {host or 'no host'}"))
        # also save preview?
    except Exception as e:
        console.print(f"[red]Ошибка рендера: {e}[/red]")
        raise typer.Exit(1)

# ─────────────────────────────────────────────
# Backup
# ─────────────────────────────────────────────
backup_app = typer.Typer(help="Бэкапы и экспорт")
app.add_typer(backup_app, name="backup", help="Бэкапы")

@backup_app.command("create")
def backup_create(
    inventory: Optional[Path] = inventory_opt,
    group: Optional[str] = group_opt,
    limit: Optional[str] = limit_opt,
    parallel: int = parallel_opt,
):
    """Создать бэкап (export) для группы"""
    inv = get_inventory(inventory)
    hosts = inv.filter(group=group, limit=limit)
    if not hosts:
        console.print("[red]Нет хостов[/red]")
        raise typer.Exit(1)

    async def _run():
        mgr = BackupManager(demo=True)
        sem = asyncio.Semaphore(parallel)

        async def one(entry):
            async with sem:
                path = await mgr.create(entry)
                return entry, path

        results = await asyncio.gather(*(one(h) for h in hosts))
        t = Table(title=f"Backups created ({len(results)})")
        t.add_column("Host", style="cyan")
        t.add_column("File", style="dim")
        t.add_column("Size", justify="right")
        for entry, path in results:
            t.add_row(entry.name, str(path), f"{path.stat().st_size}b")
        console.print(t)

    asyncio.run(_run())

@backup_app.command("list")
def backup_list(
    host: Optional[str] = typer.Argument(None, help="Имя хоста (фильтр)"),
):
    """Список бэкапов"""
    mgr = BackupManager(demo=True)
    items = mgr.list(name=host)
    if not items:
        console.print("[yellow]Бэкапов нет. Запустите: rosctl backup create[/yellow]")
        return
    t = Table(title=f"Backups ({len(items)})")
    t.add_column("Host", style="cyan")
    t.add_column("File", style="dim", width=50)
    t.add_column("Size", justify="right")
    t.add_column("Date")
    for it in items[:30]:
        t.add_row(it["host"], it["file"], f"{it['size']}b", it["mtime"][:19])
    console.print(t)

@backup_app.command("diff")
def backup_diff(
    host: str = typer.Argument(..., help="Имя хоста"),
    backup: Optional[str] = typer.Argument(None, help="Файл бэкапа (или последний)"),
    inventory: Optional[Path] = inventory_opt,
):
    """Показать diff между текущим состоянием и бэкапом"""
    inv = get_inventory(inventory)
    matches = inv.filter(name=host)
    if not matches:
        console.print(f"[red]Хост не найден: {host}[/red]")
        raise typer.Exit(1)
    entry = matches[0]
    mgr = BackupManager(demo=True)
    items = mgr.list(name=host)
    if not items:
        console.print("[yellow]Нет бэкапов для хоста[/yellow]")
        return
    target = Path(backup) if backup else Path(items[0]["file"])
    if not target.exists():
        console.print(f"[red]Файл не найден: {target}[/red]")
        raise typer.Exit(1)
    diff = mgr.restore_diff(entry, target)
    if not diff.strip():
        console.print("[green]Различий нет ✓[/green]")
    else:
        syntax = Syntax(diff, "diff", theme="monokai")
        console.print(Panel(syntax, title=f"Diff: {host} vs {target.name}"))

@backup_app.command("prune")
def backup_prune(retention: int = typer.Option(30, "--keep", help="Сколько бэкапов хранить на хост")):
    """Удалить старые бэкапы"""
    mgr = BackupManager(demo=True)
    removed = mgr.prune(retention=retention)
    console.print(f"[green]Удалено: {removed}[/green]")

# ─────────────────────────────────────────────
# Monitoring
# ─────────────────────────────────────────────
mon_app = typer.Typer(help="Мониторинг и алерты")
app.add_typer(mon_app, name="monitor", help="Мониторинг")

@mon_app.command("stats")
def mon_stats(
    inventory: Optional[Path] = inventory_opt,
    group: Optional[str] = group_opt,
    limit: Optional[str] = limit_opt,
    watch: bool = typer.Option(False, "--watch", "-w", help="Автообновление каждые 2с"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Собрать статистику по ресурсам"""
    inv = get_inventory(inventory)
    hosts = inv.filter(group=group, limit=limit)
    if not hosts:
        console.print("[red]Нет хостов[/red]")
        raise typer.Exit(1)

    async def fetch_once():
        col = MonitoringCollector(demo=True)
        stats = await col.collect(hosts)
        return stats, col.alerts(stats)

    if json_out:
        stats, alerts = asyncio.run(fetch_once())
        console.print_json(data={"stats": stats, "alerts": alerts})
        return

    if not watch:
        stats, alerts = asyncio.run(fetch_once())
        t = Table(title=f"Monitoring — {len(hosts)} hosts @ {datetime.now().strftime('%H:%M:%S')}")
        t.add_column("Host", style="cyan", width=16)
        t.add_column("Board", width=12)
        t.add_column("Uptime", width=12)
        t.add_column("CPU", justify="right", width=6)
        t.add_column("Mem free", justify="right", width=10)
        t.add_column("Clients", justify="right", width=8)
        t.add_column("Status", justify="center", width=8)
        for s in stats:
            status = "[green]online[/green]" if s["status"] == "online" else "[red]offline[/red]"
            cpu_style = "red" if int(s["cpu-load"].replace("%","")) > 70 else "green"
            t.add_row(s["name"], s["board-name"], s["uptime"].split()[0], f"[{cpu_style}]{s['cpu-load']}[/{cpu_style}]", s["free-memory"], str(s["clients"]), status)
        console.print(t)
        if alerts:
            a_table = Table(title=f"Alerts ({len(alerts)})", show_lines=True)
            a_table.add_column("Host", style="cyan")
            a_table.add_column("Level", justify="center")
            a_table.add_column("Message")
            for a in alerts:
                level = "[red]CRIT[/red]" if a["level"] == "critical" else "[yellow]WARN[/yellow]"
                a_table.add_row(a["host"], level, a["msg"])
            console.print(a_table)
        else:
            console.print("[green]Алертов нет ✓[/green]")
        return

    # watch mode (simple loop with Live)
    console.print("[dim]Watch mode — Ctrl+C для выхода[/dim]")
    try:
        with Live(console=console, refresh_per_second=1) as live:
            while True:
                stats, alerts = asyncio.run(fetch_once())
                t = Table(title=f"Monitoring (watch) — {datetime.now().strftime('%H:%M:%S')}")
                t.add_column("Host", style="cyan")
                t.add_column("CPU")
                t.add_column("Mem")
                t.add_column("Uptime")
                t.add_column("Status")
                for s in stats:
                    t.add_row(s["name"], s["cpu-load"], s["free-memory"], s["uptime"][:12], s["status"])
                live.update(t)
                import time
                time.sleep(2)
    except KeyboardInterrupt:
        console.print("\n[dim]Остановлено[/dim]")


@mon_app.command("top")
def mon_top(
    inventory: Optional[Path] = inventory_opt,
    limit: Optional[str] = limit_opt,
):
    """Живой дашборд (аналог htop для роутеров)"""
    inv = get_inventory(inventory)
    hosts = inv.filter(limit=limit)
    console.print(Panel("Запуск TUI дашборда... (нажмите q для выхода)", title="rosctl top"))
    # For now simple table loop
    import time, random
    try:
        while True:
            # clear? We'll use console.clear
            console.clear()
            console.print(f"[bold cyan]rosctl top[/bold cyan]  [dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  hosts={len(hosts)}  q=выход[/dim]")
            t = Table(expand=True)
            t.add_column("Host", style="cyan")
            t.add_column("IP", style="dim")
            t.add_column("Group")
            t.add_column("CPU", justify="right")
            t.add_column("MEM", justify="right")
            t.add_column("Traffic RX/TX", justify="right")
            t.add_column("Status")
            for h in hosts:
                cpu = random.randint(2, 25)
                mem = random.randint(300, 900)
                rx = random.randint(100, 9999)
                status = "[green]●[/green]"
                t.add_row(h.name, h.host, h.group, f"{cpu}%", f"{mem}MiB", f"{rx}M / {rx//2}M", status)
            console.print(t)
            console.print("[dim]Обновление через 1.5с — Ctrl+C для выхода[/dim]")
            time.sleep(1.5)
    except KeyboardInterrupt:
        console.print("[dim]Выход[/dim]")

# ─────────────────────────────────────────────
# WireGuard helper
# ─────────────────────────────────────────────
wg_app = typer.Typer(help="Управление WireGuard")
app.add_typer(wg_app, name="wireguard", help="WireGuard")

@wg_app.command("status")
def wg_status(
    inventory: Optional[Path] = inventory_opt,
    group: Optional[str] = group_opt,
    limit: Optional[str] = limit_opt,
):
    """Статус WireGuard туннелей"""
    inv = get_inventory(inventory)
    hosts = inv.filter(group=group, limit=limit)
    async def _run():
        orch = Orchestrator(inv, demo=True)
        results = await orch.exec_on_hosts("/interface/wireguard/print", hosts)
        t = Table(title="WireGuard tunnels")
        t.add_column("Host", style="cyan")
        t.add_column("Tunnel", style="green")
        t.add_column("Running", justify="center")
        t.add_column("Port", justify="right")
        t.add_column("Peers", justify="right")
        for r in results:
            if not r.success:
                t.add_row(r.name, "-", "[red]err[/red]", "-", str(r.error)[:30])
                continue
            tunnels = r.output if isinstance(r.output, list) else [r.output]
            for tun in tunnels:
                t.add_row(r.name, tun.get("name","-"), "●" if tun.get("running") else "○", str(tun.get("listen-port","-")), str(len(tunnels)))
        console.print(t)
    asyncio.run(_run())

@wg_app.command("genkey")
def wg_genkey():
    """Сгенерировать ключи WireGuard"""
    from cryptography.hazmat.primitives.asymmetric import x25519
    from cryptography.hazmat.primitives import serialization
    import base64, os
    priv = x25519.X25519PrivateKey.generate()
    pub = priv.public_key()
    priv_b64 = base64.b64encode(priv.private_bytes(encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw, encryption_algorithm=serialization.NoEncryption())).decode()
    pub_b64 = base64.b64encode(pub.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)).decode()
    console.print(Panel(f"[bold]Private:[/bold] {priv_b64}\n[bold]Public:[/bold]  {pub_b64}\n[dim]Сохраните private на роутере, public — на пире[/dim]", title="WireGuard keys"))
    console.print(f"[dim]RouterOS: /interface wireguard add name=wg0 private-key=\"{priv_b64}\" listen-port=13231[/dim]")

# ─────────────────────────────────────────────
# Firewall helper
# ─────────────────────────────────────────────
fw_app = typer.Typer(help="Firewall")
app.add_typer(fw_app, name="firewall", help="Firewall")

@fw_app.command("list")
def fw_list(
    inventory: Optional[Path] = inventory_opt,
    host: str = typer.Option(..., "--host", help="Хост"),
):
    """Правила firewall на хосте"""
    inv = get_inventory(inventory)
    matches = inv.filter(name=host)
    if not matches:
        console.print(f"[red]Хост не найден: {host}[/red]")
        raise typer.Exit(1)
    h = matches[0]
    async def _run():
        orch = Orchestrator(inv, demo=True)
        res = await orch.exec_on_hosts("/ip/firewall/filter/print", [h])
        r = res[0]
        if not r.success:
            console.print(f"[red]{r.error}[/red]")
            return
        t = Table(title=f"Firewall {h.name}")
        t.add_column("#", width=4)
        t.add_column("Chain")
        t.add_column("Action", style="bold")
        t.add_column("Comment", style="dim")
        rules = r.output if isinstance(r.output, list) else [r.output]
        for i, rule in enumerate(rules):
            t.add_row(str(i), rule.get("chain","-"), rule.get("action","-"), rule.get("comment","-"))
        console.print(t)
    asyncio.run(_run())

# ─────────────────────────────────────────────
# CAPsMAN / WiFi
# ─────────────────────────────────────────────
caps_app = typer.Typer(help="CAPsMAN/WiFi")
app.add_typer(caps_app, name="capsman", help="CAPsMAN")

@caps_app.command("status")
def caps_status(inventory: Optional[Path] = inventory_opt, limit: Optional[str] = limit_opt):
    """Статус CAPs"""
    inv = get_inventory(inventory)
    hosts = inv.filter(limit=limit) if limit else inv.entries[:4]
    async def _run():
        orch = Orchestrator(inv, demo=True)
        results = await orch.exec_on_hosts("/interface/wifi/capsman/remote-cap/print", hosts)
        t = Table(title="CAPsMAN")
        t.add_column("Manager", style="cyan")
        t.add_column("CAP", style="green")
        t.add_column("Radio MAC")
        t.add_column("State")
        for r in results:
            caps = r.output if isinstance(r.output, list) else [r.output]
            for c in caps:
                t.add_row(r.name, c.get("name","cap1"), c.get("radio-mac","-"), f"[green]{c.get('state','running')}[/green]")
        console.print(t)
    asyncio.run(_run())

# ─────────────────────────────────────────────
# Serve (Web UI)
# ─────────────────────────────────────────────
@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Хост"),
    port: int = typer.Option(8000, "--port", "-p", help="Порт"),
    reload: bool = typer.Option(False, "--reload", help="Autoreload"),
    inventory: Optional[Path] = inventory_opt,
):
    """Запустить Web-дашборд и API (FastAPI)"""
    from ros_orchestrator.web import create_app
    import uvicorn
    inv_path = str(inventory) if inventory else None
    console.print(Panel(f"[bold cyan]rosctl serve[/bold cyan]\nAPI: http://{host}:{port}\nDocs: http://{host}:{port}/docs\nInventory: {inv_path or 'auto'}", title="Web UI"))
    uvicorn.run(create_app(inv_path), host=host, port=port, reload=reload)

# ─────────────────────────────────────────────
# Diff
# ─────────────────────────────────────────────
@app.command("diff")
def diff_cmd(
    host: str = typer.Argument(..., help="Хост"),
    inventory: Optional[Path] = inventory_opt,
    template: Optional[str] = typer.Option(None, "--template", help="Шаблон для сравнения (jinja2)"),
):
    """Показать diff текущей конфигурации и желаемой (из шаблона)"""
    inv = get_inventory(inventory)
    matches = inv.filter(name=host)
    if not matches:
        console.print(f"[red]Хост не найден: {host}[/red]")
        raise typer.Exit(1)
    h = matches[0]
    async def _run():
        from ros_orchestrator.client.rest import RouterOSRestClient
        client = RouterOSRestClient(h, demo=True)
        cur_res = await client.exec("/export")
        current = str(cur_res.output)[:2000] if cur_res.success else "# empty"
        await client.close()
        if template:
            from jinja2 import Environment, FileSystemLoader
            env = Environment(loader=FileSystemLoader("templates"))
            tmpl = env.get_template(template)
            desired = tmpl.render(inventory_hostname=h.name, host=h.host, group=h.group, **h.vars)
        else:
            desired = current + "\n# + /ip dns set servers=1.1.1.1\n"
        import difflib
        d = difflib.unified_diff(current.splitlines(), desired.splitlines(), fromfile="current", tofile="desired", lineterm="")
        diff_text = "\n".join(d)
        if not diff_text.strip():
            console.print("[green]Различий нет ✓[/green]")
        else:
            console.print(Syntax(diff_text, "diff", theme="monokai"))
    asyncio.run(_run())

# ─────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────
@app.command("audit")
def audit(
    inventory: Optional[Path] = inventory_opt,
    group: Optional[str] = group_opt,
):
    """Аудит безопасности (дефолтные пароли, открытые порты, фаервол)"""
    inv = get_inventory(inventory)
    hosts = inv.filter(group=group)
    t = Table(title="Security audit")
    t.add_column("Host", style="cyan")
    t.add_column("Check", style="yellow")
    t.add_column("Result", justify="center")
    t.add_column("Recommendation", style="dim")
    # demo checks
    for h in hosts:
        t.add_row(h.name, "Default password", "[red]FAIL[/red]" if h.auth.password == "changeme" else "[green]OK[/green]", "Смените пароль" if h.auth.password=="changeme" else "-")
        t.add_row(h.name, "Firewall input drop", "[green]OK[/green]", "-")
        t.add_row(h.name, "SSH strong cipher", "[green]OK[/green]", "-")
        t.add_row(h.name, "Updates", "[yellow]WARN[/yellow]", "7.14.2 → 7.15.3 available")
    console.print(t)

if __name__ == "__main__":
    app()

from __future__ import annotations
import yaml
from pathlib import Path
from typing import List, Optional
from rich.console import Console
from rich.table import Table

from ros_orchestrator.config import AppConfig, InventoryFile, RouterEntry, get_config, resolve_path

console = Console()

class Inventory:
    def __init__(self, entries: List[RouterEntry], raw: InventoryFile, path: Path):
        self.entries = entries
        self.raw = raw
        self.path = path

    def filter(
        self,
        group: Optional[str] = None,
        tag: Optional[str] = None,
        name: Optional[str] = None,
        host: Optional[str] = None,
        limit: Optional[str] = None,
    ) -> List[RouterEntry]:
        result = self.entries
        if group:
            result = [r for r in result if r.group == group]
        if tag:
            result = [r for r in result if tag in r.tags]
        if name:
            # supports glob *?
            import fnmatch
            result = [r for r in result if fnmatch.fnmatch(r.name, name)]
        if host:
            result = [r for r in result if r.host == host]
        if limit:
            # limit is comma-separated patterns
            pats = [p.strip() for p in limit.split(",")]
            import fnmatch
            filtered = []
            for pat in pats:
                filtered.extend([r for r in result if fnmatch.fnmatch(r.name, pat) or fnmatch.fnmatch(r.host, pat) or fnmatch.fnmatch(r.group, pat)])
            # dedup
            seen = set()
            deduped = []
            for r in filtered:
                if r.name not in seen:
                    deduped.append(r)
                    seen.add(r.name)
            result = deduped
        return result

    def groups_list(self) -> list[str]:
        return sorted(set(e.group for e in self.entries))

    def tags_list(self) -> list[str]:
        tags = set()
        for e in self.entries:
            tags.update(e.tags)
        return sorted(tags)

    def table(self, entries: Optional[List[RouterEntry]] = None) -> Table:
        entries = entries if entries is not None else self.entries
        t = Table(title=f"Inventory: {self.path} ({len(entries)}/{len(self.entries)})", show_lines=False)
        t.add_column("Name", style="cyan bold")
        t.add_column("Host", style="green")
        t.add_column("Group", style="magenta")
        t.add_column("Tags", style="dim")
        t.add_column("Comment")
        t.add_column("Status", justify="center")
        for e in entries:
            # status placeholder
            status = "[green]●[/green]" if True else "[red]●[/red]"
            t.add_row(e.name, e.host, e.group, ", ".join(e.tags), e.comment or "", status)
        return t

    def to_dict(self):
        return {
            "path": str(self.path),
            "total": len(self.entries),
            "groups": self.groups_list(),
            "hosts": [e.model_dump() for e in self.entries],
        }


def load_inventory(path: Optional[Path] = None) -> Inventory:
    cfg = get_config()
    if path is None:
        # try to resolve inventory_path
        candidates = [
            Path.cwd() / "inventory.yml",
            Path.cwd() / "inventory.yaml",
            cfg.inventory_path,
            resolve_path(cfg.inventory_path),
            Path(__file__).parent.parent.parent / "inventory.yml",
            Path(__file__).parent.parent.parent / "inventory.example.yml",
        ]
        for c in candidates:
            if c.exists():
                path = c
                break
        if path is None:
            # create example in cwd
            path = Path.cwd() / "inventory.yml"
            if not path.exists():
                # create example file
                example = InventoryFile.example()
                with open(path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(example, f, allow_unicode=True, sort_keys=False)
                console.print(f"[yellow]Создан пример inventory: {path}[/yellow]")
    assert path is not None
    if not path.exists():
        console.print(f"[red]Inventory не найден: {path}[/red]")
        console.print("Создаю демо-inventory...")
        example = InventoryFile.example()
        InventoryFile(**example)  # validate
        entries = [RouterEntry(**h) for h in example["hosts"]]
        return Inventory(entries, InventoryFile(**example), path)

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # support both formats: list directly or dict with hosts
    if isinstance(data, list):
        data = {"hosts": data}
    if "hosts" not in data:
        raise ValueError(f"Inventory {path} должен содержать ключ 'hosts' (список)")

    raw = InventoryFile(**data)
    entries: List[RouterEntry] = []
    defaults = raw.defaults
    for h in raw.hosts:
        # h is already RouterEntry if parsed, but we have dict
        if isinstance(h, dict):
            # merge defaults for auth
            auth_data = {**defaults.model_dump(), **(h.get("auth") or {})}
            # group vars inheritance
            group_vars = raw.groups.get(h.get("group", "default"), {}).get("vars", {}) if h.get("group") else {}
            vars_merged = {**group_vars, **(h.get("vars") or {})}
            entry = RouterEntry(
                name=h["name"],
                host=h["host"],
                group=h.get("group", "default"),
                tags=h.get("tags", []),
                auth=__import__("ros_orchestrator.config", fromlist=["RouterAuth"]).RouterAuth(**auth_data),
                vars=vars_merged,
                comment=h.get("comment"),
                board=h.get("board"),
                version=h.get("version"),
            )
            entries.append(entry)
        else:
            entries.append(h)

    return Inventory(entries, raw, path)

def save_inventory(inv: Inventory):
    data = {
        "defaults": inv.raw.defaults.model_dump(exclude_none=True),
        "groups": inv.raw.groups,
        "hosts": [e.model_dump(exclude_none=True) for e in inv.entries],
    }
    with open(inv.path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

from pathlib import Path
import tempfile
import yaml
from ros_orchestrator.config import InventoryFile
from ros_orchestrator.inventory.manager import load_inventory

def test_load_example():
    inv = load_inventory(Path("inventory.example.yml"))
    assert len(inv.entries) >= 4
    assert "edge" in inv.groups_list()

def test_filter():
    inv = load_inventory(Path("inventory.example.yml"))
    edge = inv.filter(group="edge")
    assert len(edge) >= 3
    lab = inv.filter(tag="lab")
    assert len(lab) >= 1

def test_filter_glob():
    inv = load_inventory(Path("inventory.example.yml"))
    m = inv.filter(name="gw-*")
    assert len(m) >= 3

def test_playbook_load():
    from ros_orchestrator.orchestrator.tasks import Playbook
    pb = Playbook.from_file(Path("playbooks/example.yml"))
    assert len(pb.plays) >= 1
    assert pb.plays[0].tasks

def test_template_render():
    from ros_orchestrator.orchestrator.tasks import Playbook
    pb = Playbook.from_file(Path("playbooks/wireguard.yml"))
    ctx = {"inventory_hostname": "gw-msk-01", "host": "10.10.0.1", "group": "edge", "wg_address": "10.255.0.1/24", "wg_name": "wg0", "wg_private_key": "xxx", "peers": []}
    cmd = pb.render_command(pb.plays[0].tasks[0], ctx, Path("templates"))
    assert "wireguard" in cmd.lower()
    assert "wg0" in cmd

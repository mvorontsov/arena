from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Optional, List, Any
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ros_orchestrator.inventory.manager import load_inventory
from ros_orchestrator.orchestrator.executor import Orchestrator
from ros_orchestrator.orchestrator.tasks import Playbook
from ros_orchestrator.backup.manager import BackupManager
from ros_orchestrator.monitoring.collector import MonitoringCollector

DASHBOARD_HTML = r"""
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>rosctl — Оркестратор RouterOS</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fontsource/jetbrains-mono@5.0.18/index.css">
<style>
*{font-family: Inter, system-ui, -apple-system, sans-serif}
.mono{font-family: "JetBrains Mono", monospace}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-thumb{background:#3a3a4a;border-radius:6px}
</style>
</head>
<body class="bg-[#0b0b0e] text-zinc-100 min-h-screen">
<!-- Header -->
<header class="sticky top-0 z-40 backdrop-blur bg-[#0b0b0e]/80 border-b border-zinc-800">
  <div class="max-w-[1600px] mx-auto px-4 py-3 flex items-center justify-between gap-4">
    <div class="flex items-center gap-3">
      <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center font-black">◈</div>
      <div>
        <div class="font-bold leading-none">rosctl <span class="text-zinc-500 font-normal">оркестратор RouterOS</span></div>
        <div class="text-xs text-zinc-500">MikroTik fleet management • REST + SSH • Jinja2 + playbooks</div>
      </div>
      <span class="hidden md:inline-flex ml-3 px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs">● demo mode</span>
    </div>
    <div class="flex items-center gap-2">
      <button onclick="runQuick('/system/resource/print')" class="px-3 py-2 rounded-xl bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-sm">⚡ Exec</button>
      <button onclick="document.getElementById('playModal').showModal()" class="px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-medium text-sm">▶ Playbook</button>
      <a href="/docs" target="_blank" class="px-3 py-2 rounded-xl bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-sm">API docs</a>
    </div>
  </div>
</header>

<div class="max-w-[1600px] mx-auto px-4 py-6 grid grid-cols-12 gap-5">
  <!-- Left: inventory -->
  <aside class="col-span-12 lg:col-span-3 space-y-4">
    <div class="rounded-2xl bg-zinc-900 border border-zinc-800 p-4">
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold">Инвентарь</h2>
        <span id="invCount" class="text-xs px-2 py-1 rounded-full bg-zinc-800 border border-zinc-700">—</span>
      </div>
      <div class="flex gap-2 mb-3">
        <input id="search" placeholder="Поиск хоста, группы, тега..." class="w-full px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm outline-none focus:border-violet-600"/>
        <select id="groupFilter" class="px-2 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm">
          <option value="">Все группы</option>
          <option value="edge">edge</option>
          <option value="branch">branch</option>
          <option value="lab">lab</option>
        </select>
      </div>
      <div id="inventory" class="space-y-2 max-h-[62vh] overflow-auto pr-1"></div>
      <div class="mt-3 grid grid-cols-2 gap-2">
        <button onclick="loadBackups()" class="px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm hover:bg-zinc-800">📦 Бэкапы</button>
        <button onclick="loadAudit()" class="px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm hover:bg-zinc-800">🛡️ Аудит</button>
      </div>
    </div>

    <div class="rounded-2xl bg-zinc-900 border border-zinc-800 p-4">
      <h3 class="font-semibold mb-2">Группы</h3>
      <div id="groups" class="flex flex-wrap gap-2"></div>
    </div>

    <div class="rounded-2xl bg-gradient-to-br from-violet-600 to-fuchsia-600 p-4">
      <div class="font-bold">CLI — как Ansible</div>
      <div class="text-sm opacity-90 mt-1">rosctl play playbooks/edge.yml --diff --dry-run</div>
      <div class="mt-3 mono text-xs bg-black/30 rounded-xl p-3">
        rosctl exec "/ip route print" -g edge -p 20<br/>
        rosctl backup create -g branch<br/>
        rosctl monitor stats --watch
      </div>
      <div class="mt-3 text-xs opacity-80">Документация в README + /docs</div>
    </div>
  </aside>

  <!-- Center: main -->
  <main class="col-span-12 lg:col-span-6 space-y-4">
    <!-- Stats cards -->
    <div class="grid grid-cols-3 gap-3">
      <div class="rounded-2xl bg-zinc-900 border border-zinc-800 p-4">
        <div class="text-xs text-zinc-500">Устройств онлайн</div>
        <div class="text-2xl font-bold mt-1"><span id="onlineCount">—</span> <span class="text-sm font-normal text-zinc-500">/ <span id="totalCount">—</span></span></div>
        <div class="mt-2 h-1.5 bg-zinc-800 rounded-full overflow-hidden"><div id="onlineBar" class="h-full bg-emerald-500" style="width:70%"></div></div>
      </div>
      <div class="rounded-2xl bg-zinc-900 border border-zinc-800 p-4">
        <div class="text-xs text-zinc-500">Алерты</div>
        <div class="text-2xl font-bold mt-1" id="alertCount">—</div>
        <div class="text-xs mt-1 text-amber-400" id="alertHint">—</div>
      </div>
      <div class="rounded-2xl bg-zinc-900 border border-zinc-800 p-4">
        <div class="text-xs text-zinc-500">Последний бэкап</div>
        <div class="text-sm font-mono mt-1" id="lastBackup">—</div>
        <div class="text-xs mt-1 text-zinc-500" id="lastBackupMeta">—</div>
      </div>
    </div>

    <!-- Monitoring table -->
    <div class="rounded-2xl bg-zinc-900 border border-zinc-800 overflow-hidden">
      <div class="p-4 flex items-center justify-between">
        <h2 class="font-semibold">Мониторинг</h2>
        <div class="flex items-center gap-2">
          <span class="text-xs text-zinc-500" id="monTime">—</span>
          <button onclick="refreshMonitoring()" class="px-3 py-1.5 rounded-full bg-violet-600 hover:bg-violet-500 text-white text-xs">↻ Обновить</button>
          <label class="flex items-center gap-1 text-xs text-zinc-400"><input id="autoRefresh" type="checkbox" checked/> auto 3s</label>
        </div>
      </div>
      <div class="overflow-auto max-h-[42vh]">
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-zinc-900/90 backdrop-blur text-xs text-zinc-400">
            <tr>
              <th class="text-left p-2 pl-4">Хост</th>
              <th class="text-left p-2">Board</th>
              <th class="text-left p-2">Uptime</th>
              <th class="text-right p-2">CPU</th>
              <th class="text-right p-2">MEM</th>
              <th class="text-center p-2">Статус</th>
            </tr>
          </thead>
          <tbody id="monTable"></tbody>
        </table>
      </div>
    </div>

    <!-- Jobs / Exec output -->
    <div class="rounded-2xl bg-zinc-900 border border-zinc-800 overflow-hidden">
      <div class="p-4 flex items-center justify-between">
        <h2 class="font-semibold">Задания</h2>
        <div class="flex gap-2">
          <button onclick="runQuick('/ip/address/print')" class="px-3 py-1.5 rounded-full bg-zinc-800 border border-zinc-700 text-xs hover:bg-zinc-700">/ip addr</button>
          <button onclick="runQuick('/interface/print')" class="px-3 py-1.5 rounded-full bg-zinc-800 border border-zinc-700 text-xs hover:bg-zinc-700">/interface</button>
          <button onclick="runQuick('/system/resource/print')" class="px-3 py-1.5 rounded-full bg-zinc-800 border border-zinc-700 text-xs hover:bg-zinc-700">/resource</button>
        </div>
      </div>
      <div class="p-4">
        <div class="flex gap-2 mb-3">
          <input id="execCmd" value="/system/resource/print" class="flex-1 px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 mono text-sm outline-none focus:border-violet-600" placeholder="/system/resource/print"/>
          <select id="execScope" class="px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm">
            <option value="all">all</option>
            <option value="edge">edge</option>
            <option value="branch">branch</option>
            <option value="lab">lab</option>
          </select>
          <button onclick="execCustom()" class="px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium">Выполнить</button>
        </div>
        <div id="execOutput" class="rounded-xl bg-zinc-950 border border-zinc-800 p-3 max-h-[38vh] overflow-auto mono text-xs whitespace-pre-wrap"></div>
      </div>
    </div>
  </main>

  <!-- Right: detail -->
  <aside class="col-span-12 lg:col-span-3 space-y-4">
    <div class="rounded-2xl bg-zinc-900 border border-zinc-800 p-4">
      <h3 class="font-semibold">Детали хоста</h3>
      <div id="hostDetail" class="mt-3 text-sm text-zinc-400">Выберите хост слева</div>
      <div id="hostActions" class="mt-3 hidden grid grid-cols-2 gap-2">
        <button onclick="hostBackup()" class="px-3 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-sm">📦 Бэкап</button>
        <button onclick="hostDiff()" class="px-3 py-2 rounded-xl bg-zinc-800 border border-zinc-700 text-sm hover:bg-zinc-700">Diff</button>
        <button onclick="hostExec('/system/resource/print')" class="px-3 py-2 rounded-xl bg-zinc-800 border border-zinc-700 text-sm hover:bg-zinc-700">Resource</button>
        <button onclick="hostExec('/export')" class="px-3 py-2 rounded-xl bg-zinc-800 border border-zinc-700 text-sm hover:bg-zinc-700">Export</button>
      </div>
      <div id="hostExport" class="mt-3 hidden">
        <div class="text-xs text-zinc-500 mb-1">Export / Diff</div>
        <pre id="hostExportPre" class="mono text-[11px] bg-zinc-950 border border-zinc-800 rounded-xl p-3 max-h-[36vh] overflow-auto whitespace-pre-wrap"></pre>
      </div>
    </div>

    <div class="rounded-2xl bg-zinc-900 border border-zinc-800 p-4">
      <h3 class="font-semibold">Топология</h3>
      <div class="mt-3 h-[220px] rounded-xl bg-zinc-950 border border-zinc-800 flex items-center justify-center relative overflow-hidden">
        <svg viewBox="0 0 400 220" class="w-full h-full">
          <!-- simple topo -->
          <circle cx="200" cy="30" r="18" fill="#7c3aed" stroke="#a78bfa" stroke-width="2"/>
          <text x="200" y="35" text-anchor="middle" font-size="9" fill="white" font-weight="700">CCR</text>
          <line x1="200" y1="48" x2="90" y2="90" stroke="#3f3f46" stroke-width="2"/>
          <line x1="200" y1="48" x2="200" y2="90" stroke="#3f3f46" stroke-width="2"/>
          <line x1="200" y1="48" x2="310" y2="90" stroke="#3f3f46" stroke-width="2"/>
          <g id="branchNodes"></g>
          <circle cx="90" cy="110" r="14" fill="#27272a" stroke="#52525b"/><text x="90" y="114" text-anchor="middle" font-size="7" fill="white">MSK</text>
          <circle cx="200" cy="110" r="14" fill="#27272a" stroke="#52525b"/><text x="200" y="114" text-anchor="middle" font-size="7" fill="white">SPB</text>
          <circle cx="310" cy="110" r="14" fill="#27272a" stroke="#52525b"/><text x="310" y="114" text-anchor="middle" font-size="7" fill="white">LAB</text>
          <line x1="90" y1="124" x2="60" y2="170" stroke="#27272a"/><line x1="90" y1="124" x2="120" y2="170" stroke="#27272a"/>
          <circle cx="60" cy="185" r="10" fill="#18181b" stroke="#3f3f46"/><circle cx="120" cy="185" r="10" fill="#18181b" stroke="#3f3f46"/>
        </svg>
        <div class="absolute bottom-2 left-2 right-2 flex justify-between text-[10px] text-zinc-500"><span>gw-msk-01 • 10.10.0.1</span><span>WireGuard mesh</span></div>
      </div>
      <div class="mt-3 grid grid-cols-3 gap-2 text-xs">
        <div class="px-2 py-2 rounded-xl bg-zinc-950 border border-zinc-800"><div class="text-zinc-500">CAPs</div><div class="font-bold">12 online</div></div>
        <div class="px-2 py-2 rounded-xl bg-zinc-950 border border-zinc-800"><div class="text-zinc-500">WG</div><div class="font-bold">8 tunnels</div></div>
        <div class="px-2 py-2 rounded-xl bg-zinc-950 border border-zinc-800"><div class="text-zinc-500">VLAN</div><div class="font-bold">6 tagged</div></div>
      </div>
    </div>

    <div class="rounded-2xl bg-zinc-900 border border-zinc-800 p-4">
      <h3 class="font-semibold">Последние бэкапы</h3>
      <div id="backupList" class="mt-2 space-y-2 max-h-[26vh] overflow-auto text-xs"></div>
    </div>
  </aside>
</div>

<dialog id="playModal" class="rounded-2xl bg-zinc-900 border border-zinc-700 p-0 backdrop:bg-black/60 w-[min(720px,96vw)]">
  <div class="p-5">
    <h3 class="font-bold text-lg">Запуск плейбука</h3>
    <p class="text-sm text-zinc-400 mt-1">Выберите плейбук или вставьте YAML. Поддерживается --dry-run, --diff, --limit</p>
    <div class="mt-4 grid grid-cols-2 gap-3">
      <select id="playbookSelect" class="px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm">
        <option value="example">playbooks/example.yml — Базовая настройка</option>
        <option value="wireguard">playbooks/wireguard.yml — WireGuard mesh</option>
        <option value="vlan">playbooks/vlan.yml — VLAN + bridge</option>
        <option value="harden">playbooks/harden.yml — Харденинг</option>
      </select>
      <select id="playLimit" class="px-3 py-2 rounded-xl bg-zinc-950 border border-zinc-800 text-sm">
        <option value="">all</option><option value="edge">edge</option><option value="branch">branch</option><option value="lab">lab</option>
      </select>
    </div>
    <div class="mt-3 flex gap-2 text-xs">
      <label class="flex items-center gap-1"><input id="optDry" type="checkbox"/> dry-run</label>
      <label class="flex items-center gap-1"><input id="optDiff" type="checkbox" checked/> diff</label>
      <span class="ml-auto text-zinc-500">parallel 20</span>
    </div>
    <pre id="playPreview" class="mt-3 mono text-xs bg-zinc-950 border border-zinc-800 rounded-xl p-3 max-h-[28vh] overflow-auto"># preview</pre>
    <div class="mt-4 flex justify-end gap-2">
      <button onclick="document.getElementById('playModal').close()" class="px-4 py-2 rounded-xl bg-zinc-800 border border-zinc-700 text-sm">Отмена</button>
      <button onclick="runPlaybook()" class="px-5 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium">▶ Запустить</button>
    </div>
    <div id="playOutput" class="mt-4 mono text-xs bg-zinc-950 border border-zinc-800 rounded-xl p-3 max-h-[30vh] overflow-auto whitespace-pre-wrap hidden"></div>
  </div>
</dialog>

<script>
let selectedHost=null;
let inventoryCache=[];
async function api(path, opts={}){ const r=await fetch(path, opts); if(!r.ok) throw new Error(await r.text()); return r.json(); }

async function loadInventory(){
  const data=await api('/api/inventory');
  inventoryCache=data.hosts;
  document.getElementById('invCount').textContent=data.total+' хостов';
  document.getElementById('totalCount').textContent=data.total;
  renderGroups(data.groups);
  renderInventory(inventoryCache);
}
function renderGroups(groups){
  const el=document.getElementById('groups');
  el.innerHTML='';
  groups.forEach(g=>{
    const count=inventoryCache.filter(h=>h.group===g).length;
    const span=document.createElement('span');
    span.className='px-2.5 py-1 rounded-full bg-zinc-800 border border-zinc-700 text-xs';
    span.textContent=g+' • '+count;
    span.onclick=()=>{document.getElementById('groupFilter').value=g; filterInv();};
    span.style.cursor='pointer';
    el.appendChild(span);
  });
}
function renderInventory(hosts){
  const el=document.getElementById('inventory');
  el.innerHTML='';
  hosts.forEach(h=>{
    const div=document.createElement('div');
    div.className='flex items-center justify-between p-3 rounded-xl bg-zinc-950 border border-zinc-800 hover:border-zinc-700 cursor-pointer';
    div.innerHTML=`
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 flex items-center justify-center text-xs font-bold">${h.name.slice(0,2).toUpperCase()}</div>
        <div>
          <div class="text-sm font-medium leading-none">${h.name}</div>
          <div class="text-xs text-zinc-500">${h.host} • ${h.group} ${h.tags.length? '• '+h.tags.join(','):''}</div>
        </div>
      </div>
      <div class="text-xs"><span class="w-2 h-2 inline-block rounded-full bg-emerald-500"></span></div>
    `;
    div.onclick=()=>selectHost(h.name);
    el.appendChild(div);
  });
}
function filterInv(){
  const q=(document.getElementById('search').value||'').toLowerCase();
  const g=document.getElementById('groupFilter').value;
  let filtered=inventoryCache;
  if(q) filtered=filtered.filter(h=> (h.name+h.host+h.group+h.tags.join(' ')).toLowerCase().includes(q));
  if(g) filtered=filtered.filter(h=>h.group===g);
  renderInventory(filtered);
}
document.getElementById('search').addEventListener('input', filterInv);
document.getElementById('groupFilter').addEventListener('change', filterInv);

async function selectHost(name){
  selectedHost=name;
  document.getElementById('hostActions').classList.remove('hidden');
  const h=inventoryCache.find(x=>x.name===name);
  document.getElementById('hostDetail').innerHTML=`
    <div class="font-bold text-zinc-100">${h.name}</div>
    <div class="text-xs text-zinc-500">${h.host} • ${h.group}</div>
    <div class="mt-2 flex flex-wrap gap-1">${h.tags.map(t=>'<span class="px-2 py-0.5 rounded-full bg-zinc-800 border border-zinc-700 text-[10px]">'+t+'</span>').join('')}</div>
    <div class="mt-3 mono text-xs bg-zinc-950 border border-zinc-800 rounded-xl p-2">
      user: ${h.auth.username}<br/>port: ${h.auth.port}<br/>comment: ${h.comment||'-'}<br/>vars: ${JSON.stringify(h.vars)}
    </div>
  `;
  // fetch export preview
  try{
    const data=await api(`/api/hosts/${name}/export`);
    document.getElementById('hostExport').classList.remove('hidden');
    document.getElementById('hostExportPre').textContent=data.export.slice(0,3000);
  }catch(e){}
}
async function refreshMonitoring(){
  try{
    const scope=document.getElementById('execScope').value;
    const q=scope && scope!=='all' ? '?group='+scope : '';
    const data=await api('/api/monitoring'+q);
    document.getElementById('monTime').textContent=new Date().toLocaleTimeString();
    document.getElementById('onlineCount').textContent=data.stats.filter(s=>s.status==='online').length;
    const alertCount=data.alerts.length;
    document.getElementById('alertCount').textContent=alertCount;
    document.getElementById('alertHint').textContent=alertCount? data.alerts.map(a=>a.host+': '+a.msg).join(' • ') : 'всё спокойно ✓';
    document.getElementById('onlineBar').style.width=(data.stats.filter(s=>s.status==='online').length/data.stats.length*100)+'%';
    const tbody=document.getElementById('monTable');
    tbody.innerHTML='';
    data.stats.forEach(s=>{
      const tr=document.createElement('tr');
      tr.className='border-t border-zinc-800 hover:bg-zinc-800/50';
      const cpu=parseInt(s['cpu-load']);
      const cpuColor=cpu>70?'text-red-400':cpu>45?'text-amber-400':'text-emerald-400';
      tr.innerHTML=`
        <td class="p-2 pl-4"><span class="font-medium text-zinc-100">${s.name}</span><div class="text-[11px] text-zinc-500">${s.host}</div></td>
        <td class="p-2 text-zinc-300">${s['board-name']}</td>
        <td class="p-2 mono text-xs">${s.uptime.split(' ')[0]}</td>
        <td class="p-2 text-right mono ${cpuColor}">${s['cpu-load']}</td>
        <td class="p-2 text-right mono text-xs">${s['free-memory']}</td>
        <td class="p-2 text-center">${s.status==='online' ? '<span class="px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[11px]">● online</span>' : '<span class="px-2 py-1 rounded-full bg-red-500/10 text-red-400 border border-red-500/20 text-[11px]">● offline</span>'}</td>
      `;
      tbody.appendChild(tr);
    });
  }catch(e){console.error(e)}
}
async function loadBackups(){
  try{
    const data=await api('/api/backups');
    const el=document.getElementById('backupList');
    el.innerHTML='';
    document.getElementById('lastBackup').textContent=data[0] ? data[0].file.split('/').pop() : '—';
    document.getElementById('lastBackupMeta').textContent=data[0] ? data[0].host+' • '+data[0].mtime.slice(0,19) : '';
    data.slice(0,8).forEach(b=>{
      const d=document.createElement('div');
      d.className='flex items-center justify-between p-2 rounded-xl bg-zinc-950 border border-zinc-800';
      d.innerHTML=`<div><div class="font-medium">${b.host}</div><div class="text-[11px] text-zinc-500">${b.file.split('/').pop()}</div></div><div class="text-right"><div class="text-[11px]">${b.size}b</div><div class="text-[11px] text-zinc-500">${b.mtime.slice(0,19).replace('T',' ')}</div></div>`;
      el.appendChild(d);
    });
  }catch(e){}
}
async function loadAudit(){
  try{
    const data=await api('/api/audit');
    const out=document.getElementById('execOutput');
    out.textContent=JSON.stringify(data, null, 2);
  }catch(e){}
}
async function runQuick(cmd){
  document.getElementById('execCmd').value=cmd;
  execCustom();
}
async function execCustom(){
  const cmd=document.getElementById('execCmd').value;
  const scope=document.getElementById('execScope').value;
  const out=document.getElementById('execOutput');
  out.textContent='⏳ выполнение...';
  try{
    const data=await api('/api/exec', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({command:cmd, group: scope==='all'?null:scope, parallel:20})});
    out.textContent=JSON.stringify(data, null, 2);
  }catch(e){ out.textContent='Ошибка: '+e.message }
}
async function hostExec(cmd){
  if(!selectedHost) return;
  document.getElementById('execCmd').value=cmd;
  document.getElementById('execScope').value='all';
  // run with limit to selected
  const out=document.getElementById('execOutput');
  out.textContent='⏳ '+cmd+' @ '+selectedHost;
  try{
    const data=await api('/api/exec', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({command:cmd, limit:selectedHost})});
    out.textContent=JSON.stringify(data, null, 2);
  }catch(e){ out.textContent=e.message }
}
async function hostBackup(){
  if(!selectedHost) return;
  const out=document.getElementById('execOutput');
  out.textContent='⏳ создание бэкапа '+selectedHost+'...';
  try{
    const data=await api('/api/backups/create', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({host:selectedHost})});
    out.textContent='✓ бэкап создан: '+JSON.stringify(data,null,2);
    loadBackups();
  }catch(e){ out.textContent=e.message }
}
async function hostDiff(){
  if(!selectedHost) return;
  const pre=document.getElementById('hostExportPre');
  document.getElementById('hostExport').classList.remove('hidden');
  pre.textContent='⏳ diff...';
  try{
    const data=await api(`/api/hosts/${selectedHost}/diff`);
    pre.textContent=data.diff || 'различий нет';
  }catch(e){ pre.textContent=e.message }
}
async function runPlaybook(){
  const pb=document.getElementById('playbookSelect').value;
  const limit=document.getElementById('playLimit').value;
  const dry=document.getElementById('optDry').checked;
  const diff=document.getElementById('optDiff').checked;
  const out=document.getElementById('playOutput');
  out.classList.remove('hidden');
  out.textContent='⏳ запуск плейбука '+pb+' (limit='+ (limit||'all')+') dry='+dry+' diff='+diff+' ...';
  try{
    const data=await api('/api/playbook/run', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({playbook:pb, limit:limit||null, dry_run: dry, diff: diff})});
    out.textContent=JSON.stringify(data, null, 2);
    refreshMonitoring();
  }catch(e){ out.textContent='Ошибка: '+e.message }
}
// playbook preview
document.getElementById('playbookSelect').addEventListener('change', async (e)=>{
  const v=e.target.value;
  const map={
    example: `name: Базовая настройка\nplays:\n  - name: Сеть\n    hosts: all\n    tasks:\n      - name: DNS\n        command: /ip dns set servers=1.1.1.1,8.8.8.8\n      - name: NTP\n        command: /system ntp client set enabled=yes`,
    wireguard: `name: WireGuard mesh\nplays:\n  - name: WG tunnels\n    hosts: edge\n    tasks:\n      - name: Создать wg0\n        template: wireguard.rsc.j2\n        vars: {wg_address: 10.0.0.1/24}`,
    vlan: `name: VLAN\nplays:\n  - name: VLAN 10\n    hosts: branch\n    tasks:\n      - name: VLAN interface\n        command: /interface vlan add name=vlan10 vlan-id=10 interface=bridge1`,
    harden: `name: Харденинг\nplays:\n  - name: security\n    hosts: all\n    tasks:\n      - name: Disable telnet\n        command: /ip service disable telnet\n      - name: Firewall\n        command: /ip firewall filter add chain=input action=drop in-interface-list=!LAN`,
  };
  document.getElementById('playPreview').textContent=map[v]||'';
});
document.getElementById('playbookSelect').dispatchEvent(new Event('change'));

loadInventory(); refreshMonitoring(); loadBackups();
setInterval(()=>{ if(document.getElementById('autoRefresh').checked) refreshMonitoring(); }, 3000);
setInterval(loadBackups, 7000);
</script>
</body>
</html>
"""

def create_app(inventory_path: Optional[str] = None):
    app = FastAPI(
        title="rosctl API",
        description="Оркестратор для MikroTik RouterOS — REST API для инвентаря, exec, playbook, backups, monitoring",
        version="0.2.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_inv():
        return load_inventory(Path(inventory_path) if inventory_path else None)

    # ── Inventory
    @app.get("/api/inventory")
    def api_inventory():
        inv = get_inv()
        return inv.to_dict()

    @app.get("/api/inventory/groups")
    def api_groups():
        inv = get_inv()
        return {"groups": inv.groups_list(), "tags": inv.tags_list()}

    @app.get("/api/hosts/{name}")
    def api_host(name: str):
        inv = get_inv()
        m = inv.filter(name=name)
        if not m:
            m = inv.filter(host=name)
        if not m:
            raise HTTPException(404, f"host {name} not found")
        return m[0].model_dump()

    @app.get("/api/hosts/{name}/export")
    async def api_host_export(name: str):
        inv = get_inv()
        m = inv.filter(name=name)
        if not m:
            raise HTTPException(404, "not found")
        entry = m[0]
        from ros_orchestrator.backup.manager import BackupManager
        mgr = BackupManager(demo=True)
        content = mgr._synthetic_export(entry)
        return {"host": name, "export": content}

    @app.get("/api/hosts/{name}/diff")
    async def api_host_diff(name: str):
        inv = get_inv()
        m = inv.filter(name=name)
        if not m:
            raise HTTPException(404, "not found")
        entry = m[0]
        mgr = BackupManager(demo=True)
        # find latest backup or use empty
        items = mgr.list(name=name)
        if items:
            target = Path(items[0]["file"])
            diff = mgr.restore_diff(entry, target)
        else:
            diff = "# нет бэкапов — diff с синтетическим desired\n- /ip dns set servers=8.8.8.8\n+ /ip dns set servers=1.1.1.1,8.8.8.8\n"
        return {"host": name, "diff": diff}

    # ── Exec
    class ExecRequest(BaseModel):
        command: str
        group: Optional[str] = None
        tag: Optional[str] = None
        limit: Optional[str] = None
        parallel: int = 20
        dry_run: bool = False

    @app.post("/api/exec")
    async def api_exec(req: ExecRequest):
        inv = get_inv()
        hosts = inv.filter(group=req.group, tag=req.tag, limit=req.limit)
        if not hosts:
            raise HTTPException(400, "no hosts matched filter")
        orch = Orchestrator(inv, demo=True)
        results = await orch.exec_on_hosts(req.command, hosts, parallel=req.parallel, dry_run=req.dry_run)
        return [r.to_dict() for r in results]

    # ── Monitoring
    @app.get("/api/monitoring")
    async def api_monitoring(group: Optional[str] = None, tag: Optional[str] = None, limit: Optional[str] = None):
        inv = get_inv()
        hosts = inv.filter(group=group, tag=tag, limit=limit)
        if not hosts:
            hosts = inv.entries
        col = MonitoringCollector(demo=True)
        stats = await col.collect(hosts)
        alerts = col.alerts(stats)
        return {"stats": stats, "alerts": alerts, "collected_at": datetime.now().isoformat()}

    # ── Backups
    @app.get("/api/backups")
    def api_backups(host: Optional[str] = None):
        mgr = BackupManager(demo=True)
        return mgr.list(name=host)

    class BackupCreateReq(BaseModel):
        host: Optional[str] = None
        group: Optional[str] = None
        limit: Optional[str] = None

    @app.post("/api/backups/create")
    async def api_backup_create(req: BackupCreateReq):
        inv = get_inv()
        if req.host:
            hosts = inv.filter(name=req.host)
            if not hosts:
                hosts = inv.filter(host=req.host)
        else:
            hosts = inv.filter(group=req.group, limit=req.limit)
            if not hosts:
                hosts = inv.entries[:4]  # demo fallback
        mgr = BackupManager(demo=True)
        results = []
        for h in hosts:
            path = await mgr.create(h)
            results.append({"host": h.name, "file": str(path), "size": path.stat().st_size})
        return results

    # ── Playbook
    class PlaybookRunReq(BaseModel):
        playbook: str  # name or path
        limit: Optional[str] = None
        tags: Optional[List[str]] = None
        skip_tags: Optional[List[str]] = None
        dry_run: bool = False
        diff: bool = False
        parallel: int = 20
        extra_vars: Optional[dict] = None

    @app.post("/api/playbook/run")
    async def api_playbook_run(req: PlaybookRunReq):
        inv = get_inv()
        # resolve playbook path
        # support logical names: example, wireguard etc -> map to /home/user/arena/playbooks/*.yml
        mapping = {
            "example": "playbooks/example.yml",
            "wireguard": "playbooks/wireguard.yml",
            "vlan": "playbooks/vlan.yml",
            "harden": "playbooks/harden.yml",
        }
        pb_path = Path(mapping.get(req.playbook, req.playbook))
        if not pb_path.is_absolute():
            # try cwd and repo
            candidates = [Path.cwd() / pb_path, Path(__file__).parent.parent.parent / pb_path]
            for c in candidates:
                if c.exists():
                    pb_path = c
                    break
        if not pb_path.exists():
            raise HTTPException(404, f"playbook {pb_path} not found")
        pb = Playbook.from_file(pb_path, extra_vars=req.extra_vars)
        orch = Orchestrator(inv, templates_dir=Path("templates"), demo=True)
        job = await orch.run_playbook(pb, limit=req.limit, tags=req.tags, skip_tags=req.skip_tags, dry_run=req.dry_run, diff=req.diff, parallel=req.parallel)
        return {
            "job_id": job.id,
            "status": job.status,
            "summary": job.summary(),
            "results": [r.result.to_dict() for r in job.results],
        }

    @app.get("/api/playbooks")
    def api_playbooks():
        base = Path("playbooks")
        if not base.exists():
            base = Path(__file__).parent.parent.parent / "playbooks"
        if not base.exists():
            return []
        return [{"name": p.stem, "path": str(p), "size": p.stat().st_size} for p in base.glob("*.yml")]

    # ── Audit
    @app.get("/api/audit")
    def api_audit(group: Optional[str] = None):
        inv = get_inv()
        hosts = inv.filter(group=group) if group else inv.entries
        findings = []
        for h in hosts:
            if h.auth.password == "changeme":
                findings.append({"host": h.name, "severity": "high", "check": "default password", "fix": "смените пароль, используйте ключи"})
            findings.append({"host": h.name, "severity": "medium", "check": "RouterOS updates", "fix": "7.14.2 → 7.15.3 available"})
            if not h.auth.api_ssl:
                findings.append({"host": h.name, "severity": "low", "check": "API without SSL", "fix": "включите api-ssl"})
        return {"hosts": len(hosts), "findings": findings, "scanned_at": datetime.now().isoformat()}

    # ── Legacy health
    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.2.0", "mode": "demo"}

    # ── Frontend
    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return HTMLResponse(DASHBOARD_HTML)

    @app.get("/api/docs/openapi.json", include_in_schema=False)
    def openapi_json():
        return app.openapi()

    return app

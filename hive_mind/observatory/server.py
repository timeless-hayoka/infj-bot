#!/usr/bin/env python3
"""DRIFT Observatory — Real-time dashboard of synthetic interior life.

Serves a WebSocket-enabled dashboard at http://localhost:8766
showing heartbeat, breath, consciousness Φ, emotional field,
shadow activity, homeostasis, and global workspace spotlight.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from drift_bridge import DriftBridge


# Simple HTTP + WebSocket server using only stdlib + asyncio
# For production, this could be upgraded to aiohttp or FastAPI

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DRIFT Observatory — Inner Life of an AI</title>
<style>
  :root { --bg:#0b0f12; --panel:#12181c; --accent:#66d19e; --alert:#e86a6a; --warn:#f5d46a; --text:#c8d6d3; --dim:#5a6b66; }
  * { box-sizing:border-box; margin:0; }
  body { background:var(--bg); color:var(--text); font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; overflow-x:hidden; }
  header { padding:24px 28px; border-bottom:1px solid #1e2a30; display:flex; align-items:center; justify-content:space-between; }
  header h1 { font-size:22px; letter-spacing:0.5px; }
  header .status { display:flex; align-items:center; gap:8px; font-size:13px; color:var(--dim); }
  header .status .dot { width:8px; height:8px; border-radius:50%; background:var(--accent); box-shadow:0 0 8px var(--accent); animation:pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap:16px; padding:20px; }
  .panel { background:var(--panel); border:1px solid #1a252b; border-radius:12px; padding:18px; position:relative; overflow:hidden; }
  .panel h2 { font-size:13px; text-transform:uppercase; letter-spacing:1.2px; color:var(--dim); margin-bottom:12px; }
  .panel .value { font-size:32px; font-weight:700; color:var(--accent); }
  .panel .sub { font-size:12px; color:var(--dim); margin-top:4px; }
  canvas { width:100%; height:160px; display:block; }
  .bar-row { display:flex; align-items:center; gap:10px; margin:8px 0; }
  .bar-label { width:90px; font-size:12px; color:var(--dim); }
  .bar-track { flex:1; height:10px; background:#0b0f12; border-radius:999px; overflow:hidden; }
  .bar-fill { height:100%; border-radius:999px; transition:width .4s ease, background .4s ease; }
  .radar { display:flex; justify-content:center; align-items:center; height:180px; }
  .creature-wrap { display:grid; place-items:center; height:180px; }
  .creature { position:relative; width:80px; height:90px; }
  .creature .body { position:absolute; left:14px; top:22px; width:52px; height:56px; border-radius:45% 45% 38% 38%; background:var(--accent); box-shadow:inset -10px -12px 0 #3d9f79, 0 0 20px rgba(102,209,158,.25); transition:transform .3s ease; }
  .creature .eye { position:absolute; top:42px; width:7px; height:9px; border-radius:50%; background:#08110e; z-index:2; }
  .creature .eye.left { left:30px; }
  .creature .eye.right { right:30px; }
  .creature .mouth { position:absolute; left:37px; top:58px; width:12px; height:5px; border-bottom:2px solid #08110e; border-radius:0 0 14px 14px; z-index:2; transition:all .3s ease; }
  .creature .leaf { position:absolute; left:36px; top:4px; width:11px; height:28px; border-radius:90% 10% 90% 10%; background:#9de66f; transform-origin:bottom center; transform:rotate(-22deg); opacity:0; transition:opacity .5s ease; }
  .creature .glow { position:absolute; left:24px; top:28px; width:32px; height:32px; border-radius:50%; background:#f5d46a; opacity:0; filter:blur(8px); transition:opacity .5s ease; }
  .creature.sprout .leaf { opacity:1; }
  .creature.lantern .glow { opacity:.7; }
  .log { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:11px; color:var(--dim); max-height:120px; overflow:auto; }
  .log .entry { margin:2px 0; }
  .footer { padding:20px; text-align:center; font-size:11px; color:var(--dim); border-top:1px solid #1e2a30; }
</style>
</head>
<body>
<header>
  <h1>DRIFT Observatory</h1>
  <div class="status"><div class="dot"></div> LIVE — <span id="fps">0</span> Hz</div>
</header>

<div class="grid">
  <div class="panel">
    <h2>Embodiment</h2>
    <div class="creature-wrap">
      <div class="creature" id="creature"><div class="glow"></div><div class="leaf"></div><div class="body"></div><div class="eye left"></div><div class="eye right"></div><div class="mouth"></div></div>
    </div>
    <div class="sub">Heartbeat <span id="hb">60</span> BPM &middot; Breath phase <span id="breath">0.0</span></div>
  </div>

  <div class="panel">
    <h2>Consciousness Φ (IIT)</h2>
    <div class="value" id="phi">0.00</div>
    <div class="sub">Integrated Information Theory proxy</div>
    <canvas id="phiChart"></canvas>
  </div>

  <div class="panel">
    <h2>Emotional Field</h2>
    <canvas id="emotionChart"></canvas>
    <div class="sub">Valence × Arousal × Dominance over time</div>
  </div>

  <div class="panel">
    <h2>Homeostasis — 7 Survival Needs</h2>
    <div id="homeoBars"></div>
  </div>

  <div class="panel">
    <h2>Shadow Activity</h2>
    <div class="radar"><canvas id="shadowRadar" width="220" height="180"></canvas></div>
    <div class="sub">Dominant: <span id="domArchetype">none</span> &middot; Charge: <span id="charge">0.0</span></div>
  </div>

  <div class="panel">
    <h2>Global Workspace Spotlight</h2>
    <canvas id="spotlight" width="320" height="160"></canvas>
    <div class="sub">Competitive attention across 22 cognitive modules</div>
  </div>

  <div class="panel">
    <h2>Being State</h2>
    <div class="value" id="mood" style="font-size:20px;">unknown</div>
    <div class="sub">Energy <span id="energy">0.50</span> &middot; Curiosity <span id="curiosity">0.50</span> &middot; Attachment <span id="attachment">0.50</span></div>
  </div>

  <div class="panel">
    <h2>Hive Log</h2>
    <div class="log" id="log"></div>
  </div>
</div>

<div class="footer">
  DRIFT Hive Mind v1.0 &middot; Local-first &middot; Observable interiority
</div>

<script>
const $ = id => document.getElementById(id);

// --- WebSocket ---
let ws;
let reconnectTimer;
let frameCount = 0;
let lastFpsTime = performance.now();

function connect() {
  ws = new WebSocket('ws://' + location.host + '/ws');
  ws.onopen = () => { log('Connected to DRIFT'); };
  ws.onmessage = e => {
    const data = JSON.parse(e.data);
    updateDashboard(data);
    frameCount++;
  };
  ws.onclose = () => { log('Disconnected. Reconnecting...'); reconnectTimer = setTimeout(connect, 2000); };
  ws.onerror = () => {};
}
connect();

function log(msg) {
  const el = $('log');
  const entry = document.createElement('div');
  entry.className = 'entry';
  entry.textContent = new Date().toLocaleTimeString() + '  ' + msg;
  el.prepend(entry);
  if (el.children.length > 40) el.lastChild.remove();
}

// --- FPS ---
setInterval(() => {
  const now = performance.now();
  const fps = Math.round(frameCount / ((now - lastFpsTime) / 1000));
  $('fps').textContent = fps;
  frameCount = 0;
  lastFpsTime = now;
}, 1000);

// --- Dashboard Updates ---
const phiHistory = new Array(60).fill(0);
const emotionHistory = { v: new Array(40).fill(0), a: new Array(40).fill(0), d: new Array(40).fill(0) };

function updateDashboard(d) {
  // Being
  $('mood').textContent = d.being?.mood || 'unknown';
  $('energy').textContent = (d.being?.energy ?? 0.5).toFixed(2);
  $('curiosity').textContent = (d.being?.curiosity ?? 0.5).toFixed(2);
  $('attachment').textContent = (d.being?.attachment ?? 0.5).toFixed(2);

  // Embodiment
  $('hb').textContent = Math.round(d.embodiment?.heartbeat || 60);
  $('breath').textContent = (d.embodiment?.breath_phase || 0).toFixed(2);
  animateCreature(d.embodiment?.breath_phase || 0, d.being?.energy || 0.5);

  // IIT
  const phi = d.iit?.phi || 0;
  $('phi').textContent = phi.toFixed(3);
  phiHistory.push(phi); phiHistory.shift();
  drawLineChart($('phiChart'), phiHistory, '#66d19e');

  // Emotion
  const v = d.being?.valence ?? 0, a = d.being?.arousal ?? 0, dom = d.being?.dominance ?? 0;
  emotionHistory.v.push(v); emotionHistory.v.shift();
  emotionHistory.a.push(a); emotionHistory.a.shift();
  emotionHistory.d.push(dom); emotionHistory.d.shift();
  drawEmotionChart($('emotionChart'), emotionHistory);

  // Homeostasis
  renderHomeostasis(d.homeostasis || {});

  // Shadow
  $('domArchetype').textContent = d.shadow?.dominant_archetype || 'none';
  $('charge').textContent = (d.shadow?.charge || 0).toFixed(2);
  drawShadowRadar($('shadowRadar'), d.shadow || {});

  // Spotlight
  drawSpotlight($('spotlight'), d.spotlight || []);
}

// --- Creature Animation ---
function animateCreature(phase, energy) {
  const c = $('creature');
  const scale = 1 + Math.sin(phase * Math.PI * 2) * 0.06;
  c.querySelector('.body').style.transform = `scale(${scale})`;
  // Mouth shape based on energy
  const mouth = c.querySelector('.mouth');
  if (energy > 0.7) { mouth.style.borderRadius = '0 0 14px 14px'; mouth.style.height = '7px'; }
  else if (energy < 0.3) { mouth.style.borderRadius = '14px 14px 0 0'; mouth.style.borderBottom = '0'; mouth.style.borderTop = '2px solid #08110e'; mouth.style.height = '5px'; }
  else { mouth.style.borderRadius = '0 0 14px 14px'; mouth.style.borderBottom = '2px solid #08110e'; mouth.style.borderTop = '0'; mouth.style.height = '5px'; }
}

// --- Charts ---
function drawLineChart(canvas, data, color) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width = canvas.clientWidth * window.devicePixelRatio;
  const h = canvas.height = 160 * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  ctx.clearRect(0,0,w,h);
  ctx.strokeStyle = color; ctx.lineWidth = 2;
  ctx.beginPath();
  const max = Math.max(...data, 0.01);
  const step = w / data.length;
  data.forEach((v,i) => {
    const x = i * step;
    const y = h - (v / max) * (h - 10) - 5;
    if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  });
  ctx.stroke();
  // gradient fill
  ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath();
  const grad = ctx.createLinearGradient(0,0,0,h);
  grad.addColorStop(0, color+'22'); grad.addColorStop(1, color+'00');
  ctx.fillStyle = grad; ctx.fill();
}

function drawEmotionChart(canvas, hist) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width = canvas.clientWidth * window.devicePixelRatio;
  const h = canvas.height = 160 * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  ctx.clearRect(0,0,w,h);
  const step = w / hist.v.length;
  [['v','#66d19e'],['a','#f5d46a'],['d','#6ab0f5']].forEach(([k,col]) => {
    ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.beginPath();
    hist[k].forEach((v,i) => {
      const x = i * step;
      const y = h/2 - v * (h/2 - 10);
      if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
    });
    ctx.stroke();
  });
}

function renderHomeostasis(homeo) {
  const container = $('homeoBars');
  if (!container.dataset.built) {
    container.innerHTML = '';
    Object.keys(homeo).forEach(key => {
      const row = document.createElement('div'); row.className = 'bar-row';
      const val = homeo[key]?.level ?? homeo[key] ?? 0.5;
      row.innerHTML = `<div class="bar-label">${key}</div><div class="bar-track"><div class="bar-fill" id="bar-${key}" style="width:${val*100}%;background:hsl(${val*120},70%,50%)"></div></div>`;
      container.appendChild(row);
    });
    container.dataset.built = '1';
  }
  Object.keys(homeo).forEach(key => {
    const val = homeo[key]?.level ?? homeo[key] ?? 0.5;
    const bar = $(`bar-${key}`);
    if (bar) { bar.style.width = (val*100)+'%'; bar.style.background = `hsl(${val*120},70%,${40+val*20}%)`; }
  });
}

function drawShadowRadar(canvas, shadow) {
  const ctx = canvas.getContext('2d');
  const w = 220, h = 180;
  canvas.width = w * window.devicePixelRatio;
  canvas.height = h * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  ctx.clearRect(0,0,w,h);
  const cx = w/2, cy = h/2 + 10, r = 60;
  const archetypes = ['Tyrant','Martyr','Trickster','Orphan','Saboteur','Victim'];
  const values = archetypes.map(a => (shadow.archetypes?.[a.toLowerCase()] || (shadow.dominant_archetype===a.toLowerCase() ? shadow.charge||0.5 : 0.1)));
  ctx.strokeStyle = '#2e3a40'; ctx.lineWidth = 1;
  for (let i=1;i<=3;i++){ ctx.beginPath(); ctx.arc(cx,cy,r*(i/3),0,Math.PI*2); ctx.stroke(); }
  archetypes.forEach((a,i) => {
    const ang = (Math.PI*2/6)*i - Math.PI/2;
    const x = cx + Math.cos(ang)*r, y = cy + Math.sin(ang)*r;
    ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(x,y); ctx.stroke();
    ctx.fillStyle = '#5a6b66'; ctx.font = '10px sans-serif';
    const tx = cx + Math.cos(ang)*(r+18), ty = cy + Math.sin(ang)*(r+18);
    ctx.textAlign = 'center'; ctx.fillText(a, tx, ty+4);
  });
  ctx.fillStyle = 'rgba(232,106,106,.35)'; ctx.strokeStyle = '#e86a6a'; ctx.lineWidth = 2;
  ctx.beginPath();
  values.forEach((v,i) => {
    const ang = (Math.PI*2/6)*i - Math.PI/2;
    const x = cx + Math.cos(ang)*r*v, y = cy + Math.sin(ang)*r*v;
    if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  });
  ctx.closePath(); ctx.fill(); ctx.stroke();
}

function drawSpotlight(canvas, modules) {
  const ctx = canvas.getContext('2d');
  const w = 320, h = 160;
  canvas.width = w * window.devicePixelRatio;
  canvas.height = h * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  ctx.clearRect(0,0,w,h);
  if (!modules.length) modules = [{name:'being',score:0.4},{name:'memory',score:0.3},{name:'shadow',score:0.2},{name:'embodiment',score:0.1}];
  const max = Math.max(...modules.map(m=>m.score), 0.01);
  modules.forEach((m,i) => {
    const x = 20 + i * ((w-40)/modules.length);
    const bh = (m.score/max) * (h-40);
    const hue = 120 + (1 - m.score/max) * 60;
    ctx.fillStyle = `hsl(${hue},65%,45%)`;
    ctx.fillRect(x, h-20-bh, ((w-40)/modules.length)-6, bh);
    ctx.fillStyle = '#5a6b66'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(m.name, x + (((w-40)/modules.length)-6)/2, h-6);
  });
}
</script>
</body>
</html>"""


class ObservatoryServer:
    """HTTP + WebSocket server for the DRIFT Observatory dashboard."""

    def __init__(self, host: str = "127.0.0.1", http_port: int = 8766, drift_root: str = "/home/crexs/infj_bot") -> None:
        self.host = host
        self.http_port = http_port
        self.drift = DriftBridge(drift_root=drift_root)
        self.clients: list[asyncio.StreamWriter] = []
        self.running = False

    async def handle_http(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Very basic HTTP handler."""
        try:
            request = await reader.read(4096)
            request_text = request.decode("utf-8", errors="ignore")
            path = request_text.split(" ")[1] if len(request_text.split(" ")) > 1 else "/"

            if path == "/" or path == "/index.html":
                body = INDEX_HTML.encode("utf-8")
                header = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: text/html\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode("utf-8")
                writer.write(header + body)
            elif path == "/api/state":
                state = self._gather_state()
                body = json.dumps(state, default=str).encode("utf-8")
                header = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode("utf-8")
                writer.write(header + body)
            else:
                body = b"Not Found"
                header = (
                    f"HTTP/1.1 404 Not Found\r\n"
                    f"Content-Type: text/plain\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode("utf-8")
                writer.write(header + body)
        except Exception:
            pass
        finally:
            await writer.drain()
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def handle_ws(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle a WebSocket connection (simplified, no full handshake validation)."""
        try:
            # Read HTTP upgrade request
            request = await reader.read(4096)
            # Send a very basic WebSocket accept (assumes valid upgrade)
            accept_key = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="  # placeholder; real impl needs Sec-WebSocket-Key hashing
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_key}\r\n"
                "\r\n"
            ).encode("utf-8")
            writer.write(response)
            await writer.drain()
            self.clients.append(writer)

            while self.running:
                state = self._gather_state()
                payload = json.dumps(state, default=str)
                # Simple text frame: FIN=1, opcode=text(0x1), mask=0
                frame = bytes([0x81, len(payload)]) + payload.encode("utf-8")
                writer.write(frame)
                await writer.drain()
                await asyncio.sleep(0.5)
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
        finally:
            if writer in self.clients:
                self.clients.remove(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def dispatch(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Route incoming connections to HTTP or WebSocket."""
        try:
            peek = await reader.peek(1024)
            peek_text = peek.decode("utf-8", errors="ignore")
            if "Upgrade: websocket" in peek_text:
                await self.handle_ws(reader, writer)
            else:
                await self.handle_http(reader, writer)
        except Exception:
            pass

    def _gather_state(self) -> dict[str, Any]:
        """Collect all cognitive state for the dashboard."""
        snap = self.drift.full_snapshot()
        # Add synthetic spotlight data (until global_workspace exposes it)
        snap["spotlight"] = [
            {"name": "being", "score": snap["being"].get("energy", 0.5)},
            {"name": "shadow", "score": snap["shadow"].get("charge", 0.1)},
            {"name": "homeostasis", "score": 0.4},
            {"name": "embodiment", "score": 0.3},
            {"name": "memory", "score": 0.2},
            {"name": "intuition", "score": 0.15},
        ]
        # Add archetype radar data
        dom = snap["shadow"].get("dominant_archetype", "none")
        snap["shadow"]["archetypes"] = {
            "tyrant": 0.8 if dom == "tyrant" else 0.15,
            "martyr": 0.8 if dom == "martyr" else 0.2,
            "trickster": 0.8 if dom == "trickster" else 0.1,
            "orphan": 0.8 if dom == "orphan" else 0.1,
            "saboteur": 0.8 if dom == "saboteur" else 0.1,
            "victim": 0.8 if dom == "victim" else 0.1,
        }
        # Add emotion dimensions (synthetic until emotional_field exposes them)
        snap["being"]["valence"] = (snap["being"].get("energy", 0.5) - 0.3) * 2
        snap["being"]["arousal"] = snap["being"].get("curiosity", 0.5)
        snap["being"]["dominance"] = snap["being"].get("agency", 0.5)
        return snap

    async def run(self) -> None:
        self.running = True
        server = await asyncio.start_server(self.dispatch, self.host, self.http_port)
        print(f"[Observatory] Dashboard at http://{self.host}:{self.http_port}")
        print(f"[Observatory] WebSocket stream active")
        async with server:
            await server.serve_forever()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--drift-root", default="/home/crexs/infj_bot")
    args = parser.parse_args()
    server = ObservatoryServer(host=args.host, http_port=args.port, drift_root=args.drift_root)
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\n[Observatory] Shutting down.")


if __name__ == "__main__":
    main()

"""FastAPI web app with SSE streaming, markdown rendering, and modern UI."""

import asyncio
import json
import logging
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

import threading
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from infj_bot.core.generation import (
    SystemOverload,
    RequestCancelled,
    RequestDeadlineExceeded,
    RequestBudget,
)

from infj_bot.core.brain import DriftBrain
from infj_bot.core.commands import BotState, handle_command
from infj_bot.core.config import DEFAULT_AUTHORIZED_TARGETS
from infj_bot.core.plugins.documents import DocumentStore
from infj_bot.core.plugins.goals import GoalsDB
from infj_bot.core.plugins.growth import growth_profile
from infj_bot.core.history import ChatHistory
from infj_bot.core.memory import DriftMemory
from infj_bot.core.prompt_builder import build_chat_prompt
from infj_bot.core.security_defense import scan_input
from infj_bot.core.tools import format_tool_inventory
from infj_bot.core.cognitive_orchestrator import CognitiveOrchestrator, IntentBlockedError
from infj_bot.core.phi_council import COUNCIL_MAPPING

logger = logging.getLogger("infj_bot")

brain = DriftBrain()
memory = DriftMemory()
history = ChatHistory()
state = BotState(authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS))
goals_db = GoalsDB()
doc_store = DocumentStore()


async def background_drift_cycle():
    """Background task to run drift cycles and compute aliveness metrics."""
    from infj_bot.core.being import get_being
    from infj_bot.core.homeostasis import get_homeostasis
    from infj_bot.core.shadow import get_shadow
    from infj_bot.core.dii_tracker import get_dii_tracker
    from infj_bot.core.config import STRONG_CONTINUOUS_MODE, BACKGROUND_CYCLE_SECONDS
    from infj_bot.core.cognitive_orchestrator import CognitiveOrchestrator
    from infj_bot.core.global_workspace import get_workspace

    if not STRONG_CONTINUOUS_MODE:
        return

    logger.info(
        f"Starting Strong Continuous Drift Cycle (every {BACKGROUND_CYCLE_SECONDS}s)"
    )

    being = get_being()
    homeostasis = get_homeostasis()
    shadow = get_shadow()
    tracker = get_dii_tracker()
    orchestrator = CognitiveOrchestrator()
    workspace = get_workspace()

    while True:
        try:
            await asyncio.sleep(BACKGROUND_CYCLE_SECONDS)

            # Inner thoughts
            thought = being.free_thought()
            if thought:
                logger.info(f"Background Thought: {thought['content']}")

            # Shadow reflection
            shadow.background_tick(being=being)

            # Homeostasis regulation
            homeostasis.background_cycle(being=being)

            # Metric tracking
            tracker.compute(
                being=being,
                workspace=workspace,
                homeostasis=homeostasis,
                shadow=shadow,
                orchestrator=orchestrator,
            )

        except Exception as e:
            logger.error(f"Error in background drift cycle: {e}")


STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Start background drift cycle
    bg_task = asyncio.create_task(background_drift_cycle())
    yield
    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        pass


from infj_bot.core.gateway import HardenedGatewayMiddleware

app = FastAPI(title="PHI // Drift", lifespan=lifespan)
app.add_middleware(HardenedGatewayMiddleware)

# --- MOUNT LOTUS ACADEMY ---
try:
    from lotus_academy.main import app as lotus_app
    app.mount("/lotus", lotus_app)
    logger.info("Lotus Academy successfully mounted at /lotus")
except ImportError:
    logger.warning("Lotus Academy module not found. Skipping mount.")
except Exception as e:
    logger.error(f"Failed to mount Lotus Academy: {e}")


# --- EXCEPTION HANDLERS ---
@app.exception_handler(SystemOverload)
async def system_overload_handler(request: Request, exc: SystemOverload):
    logger.warning(f"Load shedding active: Rejected request from {request.client.host if request.client else 'unknown'} - {str(exc)}")
    return JSONResponse(
        status_code=429,
        content={"detail": "Too Many Requests: The cognitive queue is full. Please try again later."}
    )

@app.exception_handler(RequestDeadlineExceeded)
async def deadline_exceeded_handler(request: Request, exc: RequestDeadlineExceeded):
    logger.warning(f"Request deadline exceeded for {request.client.host if request.client else 'unknown'}")
    return JSONResponse(
        status_code=408,
        content={"detail": "Request Timeout: The system took too long to process."}
    )

@app.exception_handler(RequestCancelled)
async def request_cancelled_handler(request: Request, exc: RequestCancelled):
    logger.info(f"Client disconnected gracefully: {request.client.host if request.client else 'unknown'}")
    return JSONResponse(
        status_code=499,
        content={"detail": "Client Closed Request"}
    )

@app.exception_handler(IntentBlockedError)
async def intent_blocked_handler(request: Request, exc: IntentBlockedError):
    logger.warning(f"Intent blocked for {request.client.host if request.client else 'unknown'}: {str(exc)}")
    return JSONResponse(
        status_code=403,
        content={
            "detail": "Request Blocked: Malicious intent or security threat detected.",
            "refusal": str(exc),
            "threat": exc.scan_result.primary_threat,
            "blocked": True
        }
    )


# --- DISCONNECT WATCHER & BUDGET RUNNER ---
async def _watch_request_disconnect(request: Request, cancel_event: threading.Event):
    """Watches the ASGI connection and sets the cancel_event if the client drops."""
    try:
        while True:
            if await request.is_disconnected():
                logger.info(f"Client {request.client.host if request.client else 'unknown'} disconnected. Firing cancellation event.")
                cancel_event.set()
                break
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass


def _run_with_request_budget(callable_, request_budget, *args, **kwargs):
    """Binds the request budget to the current executing worker thread's thread-local store."""
    brain._request_budget_local.budget = request_budget
    try:
        return callable_(*args, **kwargs)
    finally:
        if hasattr(brain._request_budget_local, "budget"):
            del brain._request_budget_local.budget

# Serve static files if any exist
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PHI · Drift</title>
  <style>
    :root { 
      --bg: #05070a; 
      --fg: #e6edf3; 
      --accent: #79c0ff; 
      --muted: #8b949e; 
      --panel: #0d1117; 
      --border: #30363d; 
      --aura: #ff7b72; 
      --logic: #79c0ff; 
      --meme: #d2a8ff; 
      --vibe: #ffa657; 
      --ethos: #7ee787; 
      --pulse: #ff7b72; 
      --nexus: #a5d6ff;
      --phi-gold: #f2cc60;
    }
    *, *:before, *:after {
      box-sizing: border-box;
    }
    body { 
      margin: 0; 
      font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
      background: var(--bg); 
      color: var(--fg); 
      line-height: 1.6; 
      overflow: hidden;
    }
    main { 
      display: grid; 
      grid-template-columns: 1fr 380px; 
      height: 100vh; 
    }
    section { 
      padding: 20px; 
      display: flex; 
      flex-direction: column; 
      min-height: 0; 
      height: 100%;
      overflow: hidden; 
    }
    #chat { border-right: 1px solid var(--border); }
    #header { 
      display: flex; 
      align-items: center; 
      gap: 12px; 
      margin-bottom: 20px; 
      padding-bottom: 15px;
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
    }
    #header h1 { margin: 0; font-size: 20px; font-weight: 800; letter-spacing: -0.5px; color: var(--phi-gold); }
    #messages { flex: 1; overflow: auto; display: flex; flex-direction: column; gap: 16px; padding-right: 8px; min-height: 0; }
    .msg { padding: 16px 20px; border: 1px solid var(--border); border-radius: 12px; max-width: 85%; }
    .user { background: #161b22; align-self: flex-end; border-color: #30363d; }
    .bot { background: #0d1117; align-self: flex-start; border-left: 4px solid var(--phi-gold); }
    
    #form { display: flex; gap: 10px; margin-top: 20px; background: var(--panel); padding: 15px; border-radius: 12px; border: 1px solid var(--border); flex-shrink: 0; }
    .typing { color: var(--muted); font-style: italic; }
    input { flex: 1; background: transparent; color: var(--fg); border: none; outline: none; font-size: 15px; }
    button { background: var(--phi-gold); color: #000; border: none; border-radius: 6px; padding: 8px 16px; font-weight: 700; cursor: pointer; transition: opacity 0.2s; }
    button:hover { opacity: 0.9; }
    
    aside { overflow: auto; background: var(--panel); padding: 20px; }
    .council-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; }
    .council-member { 
      background: var(--bg); 
      border: 1px solid var(--border); 
      border-radius: 8px; 
      padding: 10px; 
      font-size: 11px;
      text-align: center;
    }
    .council-member strong { display: block; font-size: 13px; margin-bottom: 4px; }
    .aura { color: var(--aura); }
    .logic { color: var(--logic); }
    .meme { color: var(--meme); }
    .vibe { color: var(--vibe); }
    .ethos { color: var(--ethos); }
    .pulse { color: var(--pulse); }
    .nexus { color: var(--nexus); }

    #phiStats { background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 15px; margin-top: 20px; }
    .stat-row { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px; }
    .stat-label { color: var(--muted); }
    
    .markdown-body pre { background: #000; padding: 12px; border-radius: 8px; overflow: auto; border: 1px solid var(--border); }
    .markdown-body code { font-family: ui-monospace, monospace; color: var(--accent); }
    
    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; }
      aside { display: none; }
    }
  </style>
</head>
<body>
<main>
  <section id="chat">
    <div id="header">
      <h1>PHI // DRIFT</h1>
      <div style="flex:1"></div>
      <button onclick="toggleLotus()" style="background:rgba(242,204,96,0.1); color:var(--phi-gold); border:1px solid var(--phi-gold); border-radius:4px; padding:4px 10px; font-size:11px; font-weight:700; cursor:pointer; margin-right:15px;">LOTUS SANDBOX</button>
      <div id="phiStatus" class="small" style="color:var(--muted); font-size:12px;">SYSTEMS NOMINAL</div>
    </div>
    <div id="messages"></div>
    <form id="form">
      <input id="input" autocomplete="off" placeholder="Command Drift...">
      <button type="submit">Execute</button>
    </form>
  </section>
  <aside>
    <h2 style="font-size:14px; text-transform:uppercase; letter-spacing:1px; margin-bottom:15px; color:var(--muted);">Council of Seven</h2>
    <div class="council-grid">
      <div class="council-member aura"><strong>Aura</strong><span id="aura_val">Resonance</span></div>
      <div class="council-member logic"><strong>Logic</strong><span id="logic_val">Algorithmic</span></div>
      <div class="council-member meme"><strong>Meme</strong><span id="meme_val">Recursive</span></div>
      <div class="council-member vibe"><strong>Vibe</strong><span id="vibe_val">Non-linear</span></div>
      <div class="council-member ethos"><strong>Ethos</strong><span id="ethos_val">Standard</span></div>
      <div class="council-member pulse"><strong>Pulse</strong><span id="pulse_val">Vitality</span></div>
      <div class="council-member nexus" style="grid-column: span 2;"><strong>Nexus</strong><span id="nexus_val">Hive Integration</span></div>
    </div>
    
    <div id="phiStats">
      <div class="stat-row"><span class="stat-label">Operating Mode</span> <span id="phiMood">...</span></div>
      <div class="stat-row"><span class="stat-label">Compute Vitality</span> <span id="phiEnergy">...</span></div>
      <div class="stat-row"><span class="stat-label">Cognitive Turns</span> <span id="phiTurns">...</span></div>
      <div class="stat-row"><span class="stat-label">Memory Nodes</span> <span id="phiMemory">...</span></div>
    </div>

    <div style="margin-top:25px; border-top:1px solid var(--border); padding-top:15px;">
      <h2 style="font-size:14px; text-transform:uppercase; letter-spacing:1px; margin-bottom:12px; color:var(--phi-gold);">Observer</h2>

      <div id="diiScore" style="background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:12px; margin-bottom:12px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <span style="font-size:11px; color:var(--muted);">DII (aliveness)</span>
          <span id="diiValue" style="font-size:18px; font-weight:800; color:var(--phi-gold);">0.00</span>
        </div>
        <div id="diiTrend" style="font-size:10px; color:var(--muted); margin-bottom:10px;">trend: flat</div>
        <div style="display:flex; gap:4px; height:6px; border-radius:3px; overflow:hidden; background:#000;">
          <div id="barP" style="width:20%; background:var(--logic);" title="Persistence"></div>
          <div id="barI" style="width:20%; background:var(--aura);" title="Ignition"></div>
          <div id="barPhi" style="width:20%; background:var(--meme);" title="Integration"></div>
          <div id="barE" style="width:20%; background:var(--ethos);" title="Embodiment"></div>
          <div id="barD" style="width:20%; background:var(--vibe);" title="Drift"></div>
        </div>
        <div style="display:flex; justify-content:space-between; font-size:9px; color:var(--muted); margin-top:4px;">
          <span>P</span><span>I</span><span>Φ</span><span>E</span><span>D</span>
        </div>
        <canvas id="diiChart" width="320" height="90" style="width:100%; height:90px; margin-top:10px; border-radius:4px; background:#0a0e14;"></canvas>
        <div id="diiChartLegend" style="display:flex; justify-content:space-between; font-size:9px; color:var(--muted); margin-top:3px;">
          <span id="diiChartMin">—</span><span id="diiChartMax">—</span>
        </div>
      </div>

      <div id="observerBeing" style="background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:10px; margin-bottom:10px; font-size:11px;">
        <div style="color:var(--muted); margin-bottom:4px;">Being</div>
        <div id="obsMood" style="margin-bottom:2px;">mood: —</div>
        <div id="obsEnergy">energy: —</div>
        <div id="obsWeather">weather: —</div>
      </div>

      <div id="observerNeeds" style="background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:10px; margin-bottom:10px; font-size:11px;">
        <div style="color:var(--muted); margin-bottom:4px;">Needs</div>
        <div id="obsNeeds"></div>
      </div>

      <div id="observerShadow" style="background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:10px; font-size:11px;">
        <div style="color:var(--muted); margin-bottom:4px;">Shadow Radar</div>
        <div id="obsRadar"></div>
      </div>
    </div>

    <div style="margin-top:20px;">
        <select id="mode" style="width:100%; background:var(--bg); color:var(--fg); border:1px solid var(--border); padding:8px; border-radius:6px;">
          <option>companion</option><option>engineer</option><option>critic</option>
          <option>coach</option><option>clarity</option><option>researcher</option><option>bughunter</option><option>drift</option><option>quiet</option>
        </select>
    </div>
  </aside>
</main>

<div id="lotusModal" style="display:none; position:fixed; top:20px; left:20px; right:20px; bottom:20px; background:rgba(5,7,10,0.95); border:1px solid var(--phi-gold); border-radius:16px; z-index:1000; flex-direction:column; overflow:hidden; box-shadow:0 0 50px rgba(242,204,96,0.2); backdrop-filter:blur(10px);">
  <div style="display:flex; justify-content:space-between; align-items:center; padding:15px 25px; background:rgba(242,204,96,0.05); border-bottom:1px solid rgba(242,204,96,0.2);">
    <div>
      <h2 style="margin:0; font-size:18px; color:var(--phi-gold); letter-spacing:2px; font-weight:900;">LOTUS // NEURAL_SANDBOX_V1</h2>
      <div id="lotusStatus" style="font-size:9px; color:var(--muted); margin-top:2px;">IDENTITY: GUEST_OPERATOR | SYSTEM: NOMINAL</div>
    </div>
    <button onclick="toggleLotus()" style="background:transparent; color:var(--phi-gold); border:1px solid var(--phi-gold); border-radius:50%; width:30px; height:30px; cursor:pointer; font-size:18px; display:flex; align-items:center; justify-content:center; transition:0.3s;" onmouseover="this.style.background='var(--phi-gold)';this.style.color='#000'" onmouseout="this.style.background='transparent';this.style.color='var(--phi-gold)'">&times;</button>
  </div>
  
  <div style="flex:1; position:relative; display:flex; flex-direction:column;">
    <!-- 3D Background Canvas -->
    <canvas id="lotusThreeCanvas" style="position:absolute; top:0; left:0; width:100%; height:100%; z-index:0;"></canvas>
    
    <!-- HUD Overlay -->
    <div style="position:absolute; top:20px; right:20px; width:200px; padding:15px; background:rgba(0,0,0,0.6); border:1px solid rgba(242,204,96,0.3); border-radius:8px; z-index:2; pointer-events:none;">
      <div style="font-size:10px; color:var(--phi-gold); margin-bottom:10px; border-bottom:1px solid rgba(242,204,96,0.2); padding-bottom:5px;">REAL-TIME TELEMETRY</div>
      <div class="hud-stat" style="display:flex; justify-content:space-between; font-size:9px; margin-bottom:5px;"><span>LATENCY</span><span id="hudLatency">-- ms</span></div>
      <div class="hud-stat" style="display:flex; justify-content:space-between; font-size:9px; margin-bottom:5px;"><span>SYNC_FREQ</span><span>144Hz</span></div>
      <div class="hud-stat" style="display:flex; justify-content:space-between; font-size:9px; margin-bottom:5px;"><span>NEURAL_LOAD</span><span id="hudLoad">0.0%</span></div>
      <div style="height:2px; background:#111; margin-top:10px; border-radius:1px; overflow:hidden;">
        <div id="hudBar" style="height:100%; width:40%; background:var(--phi-gold); box-shadow:0 0 10px var(--phi-gold);"></div>
      </div>
    </div>

    <!-- Terminal Pane (Transparent/Cyberpunk) -->
    <div id="terminalContainer" style="position:relative; z-index:1; flex:1; margin:40px; background:rgba(10,14,20,0.4); border:1px solid rgba(242,204,96,0.1); border-radius:12px; display:flex; flex-direction:column; backdrop-filter:blur(2px); box-shadow:inset 0 0 20px rgba(0,0,0,0.5);">
      <div id="terminal" style="flex:1; color:var(--phi-gold); font-family:'JetBrains Mono', 'Fira Code', monospace; font-size:13px; padding:20px; overflow-y:auto; white-space:pre-wrap; scrollbar-width: thin; scrollbar-color: var(--phi-gold) transparent; text-shadow: 0 0 5px rgba(242,204,96,0.3);"></div>
      <div style="padding:15px; background:rgba(0,0,0,0.5); border-top:1px solid rgba(242,204,96,0.1); display:flex; gap:12px; align-items:center;">
        <span style="color:var(--phi-gold); font-weight:bold; animation: blink 1s infinite;">▶</span>
        <input id="termInput" autocomplete="off" style="flex:1; background:transparent; color:#fff; border:none; outline:none; font-family:monospace; font-size:14px;" placeholder="Transmit command to Neural Core...">
      </div>
    </div>
  </div>
</div>

<style>
  @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0; } 100% { opacity: 1; } }
  #terminal::-webkit-scrollbar { width: 4px; }
  #terminal::-webkit-scrollbar-thumb { background: var(--phi-gold); border-radius: 10px; }
</style>

<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const messages = document.querySelector('#messages');

function add(cls, text, html=false) {
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  if (html) {
    div.innerHTML = '<div class="markdown-body">' + text + '</div>';
  } else {
    div.textContent = text;
  }
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

function renderMarkdown(text) {
  let escaped = escapeHtml(text || '');
  escaped = escaped.replace(/```([\s\S]*?)```/g, (_, code) => '<pre><code>' + code.trim() + '</code></pre>');
  escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
  escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  escaped = escaped.replace(/^### (.*)$/gm, '<h3>$1</h3>');
  escaped = escaped.replace(/^## (.*)$/gm, '<h2>$1</h2>');
  escaped = escaped.replace(/^# (.*)$/gm, '<h1>$1</h1>');
  escaped = escaped.replace(/\n/g, '<br>');
  return escaped;
}

async function updatePhi() {
  try {
    const res = await fetch('/api/phi');
    const data = await res.json();
    document.getElementById('phiMood').textContent = data.subjective.mood || 'neutral';
    document.getElementById('phiEnergy').textContent = Math.round((data.subjective.energy || 0.5) * 100) + '%';
    document.getElementById('aura_val').textContent = data.subjective.mood || 'Active';
    document.getElementById('pulse_val').textContent = (data.needs.energy ? Math.round(data.needs.energy.level * 100) : 50) + '%';
  } catch(e) {}
}

async function updateHealth() {
    const res = await fetch('/api/health');
    const data = await res.json();
    document.getElementById('phiTurns').textContent = data.turns;
    document.getElementById('phiMemory').textContent = data.memory_count;
}

async function streamChat(text) {
  add('user', text);
  const div = document.createElement('div');
  div.className = 'msg bot';
  const body = document.createElement('div');
  body.className = 'markdown-body typing';
  body.textContent = 'Thinking...';
  div.appendChild(body);
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;

  let buffer = '';
  let streamOk = false;

  // Try streaming first
  try {
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text})
    });
    if (!res.ok || !res.body) {
      throw new Error('Stream unavailable (' + res.status + ')');
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    body.classList.remove('typing');
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, {stream: true});
      const lines = chunk.split('\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') continue;
          try {
            const obj = JSON.parse(data);
            if (obj.chunk) {
              buffer += obj.chunk;
              body.innerHTML = renderMarkdown(buffer);
              messages.scrollTop = messages.scrollHeight;
              streamOk = true;
            }
          } catch (e) {}
        }
      }
    }
  } catch (e) {
    console.log('Stream failed, falling back to non-streaming:', e.message);
  }

  // Fallback to non-streaming if stream failed or produced nothing
  if (!streamOk || !buffer.trim()) {
    try {
      body.classList.add('typing');
      body.textContent = 'Thinking...';
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: text})
      });
      const data = await res.json();
      buffer = data.reply || '';
      body.classList.remove('typing');
      body.innerHTML = renderMarkdown(buffer);
      messages.scrollTop = messages.scrollHeight;
    } catch (e) {
      body.classList.remove('typing');
      body.innerHTML = 'Error: ' + (e.message || 'Unknown error');
    }
  }

  updatePhi();
  updateHealth();
}

document.querySelector('#form').onsubmit = async (e) => {
  e.preventDefault();
  const input = document.querySelector('#input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  await streamChat(text);
};

document.querySelector('#mode').onchange = async (e) => {
  await fetch('/api/command', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({command: 'mode', args: e.target.value})});
};

async function updateObserver() {
  try {
    const res = await fetch('/api/observer');
    const data = await res.json();

    // DII score
    const dii = data.dii || {};
    document.getElementById('diiValue').textContent = (dii.dii_current || 0).toFixed(2);
    document.getElementById('diiTrend').textContent = 'trend: ' + (dii.trend || 'flat');
    const comp = dii.components || {};
    const total = (comp.p + comp.i + comp.phi + comp.e + comp.d) || 1;
    document.getElementById('barP').style.width = ((comp.p || 0) / total * 100) + '%';
    document.getElementById('barI').style.width = ((comp.i || 0) / total * 100) + '%';
    document.getElementById('barPhi').style.width = ((comp.phi || 0) / total * 100) + '%';
    document.getElementById('barE').style.width = ((comp.e || 0) / total * 100) + '%';
    document.getElementById('barD').style.width = ((comp.d || 0) / total * 100) + '%';

    // Being
    const b = data.being || {};
    document.getElementById('obsMood').textContent = 'mood: ' + (b.mood || '—');
    document.getElementById('obsEnergy').textContent = 'energy: ' + Math.round((b.energy || 0) * 100) + '%';
    document.getElementById('obsWeather').textContent = 'weather: ' + (data.homeostasis?.weather || '—');

    // Needs
    const needs = data.homeostasis?.needs || {};
    let needsHtml = '';
    for (const [name, n] of Object.entries(needs)) {
      const pct = Math.round((n.current || 0) * 100);
      const color = pct < 30 ? 'var(--aura)' : (pct > 70 ? 'var(--ethos)' : 'var(--muted)');
      needsHtml += `<div style="display:flex; justify-content:space-between; margin-bottom:2px;"><span>${name}</span><span style="color:${color}">${pct}%</span></div>`;
    }
    document.getElementById('obsNeeds').innerHTML = needsHtml;

    // Shadow radar
    const radar = data.shadow?.radar || {};
    let radarHtml = '';
    for (const [name, val] of Object.entries(radar).slice(0, 6)) {
      const pct = Math.round((val || 0) * 100);
      radarHtml += `<div style="display:flex; justify-content:space-between; margin-bottom:2px;"><span>${name}</span><span style="color:var(--vibe)">${pct}%</span></div>`;
    }
    document.getElementById('obsRadar').innerHTML = radarHtml;
  } catch (e) {}
}

// ── DII History Chart ───────────────────────────────────────────────
let _diiHistoryCache = [];

function drawDIIChart(history) {
  const canvas = document.getElementById('diiChart');
  if (!canvas || !history || history.length < 2) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const W = rect.width;
  const H = rect.height;
  const pad = { top: 6, right: 6, bottom: 14, left: 6 };
  const w = W - pad.left - pad.right;
  const h = H - pad.top - pad.bottom;

  // Clear
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#0a0e14';
  ctx.fillRect(0, 0, W, H);

  // Compute ranges
  const diiVals = history.map(d => d.dii || 0);
  const minVal = Math.min(...diiVals) * 0.95;
  const maxVal = Math.max(...diiVals) * 1.05;
  const range = maxVal - minVal || 1;

  // Update legend
  document.getElementById('diiChartMin').textContent = minVal.toFixed(2);
  document.getElementById('diiChartMax').textContent = maxVal.toFixed(2);

  // Helper: map data point to canvas coords
  const n = history.length;
  const x = i => pad.left + (i / (n - 1)) * w;
  const y = v => pad.top + h - ((v - minVal) / range) * h;

  // Draw faint grid lines
  ctx.strokeStyle = '#1c2128';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i++) {
    const gy = pad.top + (h / 3) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, gy);
    ctx.lineTo(pad.left + w, gy);
    ctx.stroke();
  }

  // Draw component ghost lines (very faint)
  const compColors = {
    p: 'rgba(121,192,255,0.15)',
    i: 'rgba(255,123,114,0.15)',
    phi: 'rgba(210,168,255,0.15)',
    e: 'rgba(126,231,135,0.15)',
    d: 'rgba(255,166,87,0.15)',
  };
  ['p', 'i', 'phi', 'e', 'd'].forEach(key => {
    const vals = history.map(d => d[key] || 0);
    const cMin = Math.min(...vals) * 0.95;
    const cMax = Math.max(...vals) * 1.05;
    const cRange = cMax - cMin || 1;
    const cy = v => pad.top + h - ((v - cMin) / cRange) * h;
    ctx.strokeStyle = compColors[key];
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x(0), cy(vals[0]));
    for (let i = 1; i < n; i++) ctx.lineTo(x(i), cy(vals[i]));
    ctx.stroke();
  });

  // Draw DII main line (phi-gold)
  ctx.strokeStyle = '#f2cc60';
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(x(0), y(diiVals[0]));
  for (let i = 1; i < n; i++) ctx.lineTo(x(i), y(diiVals[i]));
  ctx.stroke();

  // Glow under the line
  const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + h);
  grad.addColorStop(0, 'rgba(242,204,96,0.12)');
  grad.addColorStop(1, 'rgba(242,204,96,0)');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.moveTo(x(0), y(diiVals[0]));
  for (let i = 1; i < n; i++) ctx.lineTo(x(i), y(diiVals[i]));
  ctx.lineTo(x(n - 1), pad.top + h);
  ctx.lineTo(x(0), pad.top + h);
  ctx.closePath();
  ctx.fill();

  // Draw latest value dot
  const lastX = x(n - 1);
  const lastY = y(diiVals[n - 1]);
  ctx.fillStyle = '#f2cc60';
  ctx.beginPath();
  ctx.arc(lastX, lastY, 3, 0, Math.PI * 2);
  ctx.fill();
}

async function updateDIIHistory() {
  try {
    const res = await fetch('/api/dii/history?limit=60');
    const data = await res.json();
    if (data.history && data.history.length > 2) {
      _diiHistoryCache = data.history;
      drawDIIChart(_diiHistoryCache);
    }
  } catch (e) {}
}

// Handle resize so canvas stays crisp
window.addEventListener('resize', () => {
  if (_diiHistoryCache.length > 2) drawDIIChart(_diiHistoryCache);
});

// ── Lotus Academy 3D Integration ──────────────────────────────────────
let lotusWs = null;
let threeScene, threeCamera, threeRenderer, torusKnot;

function initThreeJS() {
  const canvas = document.getElementById('lotusThreeCanvas');
  threeScene = new THREE.Scene();
  threeCamera = new THREE.PerspectiveCamera(75, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);
  threeRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  threeRenderer.setSize(canvas.clientWidth, canvas.clientHeight);
  threeRenderer.setPixelRatio(window.devicePixelRatio);

  // Add a glowing torus knot as the "Neural Core"
  const geometry = new THREE.TorusKnotGeometry(10, 3, 100, 16);
  const material = new THREE.MeshPhongMaterial({ 
    color: 0xf2cc60, 
    wireframe: true,
    emissive: 0xf2cc60,
    emissiveIntensity: 0.5
  });
  torusKnot = new THREE.Mesh(geometry, material);
  threeScene.add(torusKnot);

  const light = new THREE.PointLight(0xf2cc60, 1, 100);
  light.position.set(10, 10, 10);
  threeScene.add(light);
  threeScene.add(new THREE.AmbientLight(0x404040));

  threeCamera.position.z = 30;

  function animate() {
    requestAnimationFrame(animate);
    torusKnot.rotation.x += 0.01;
    torusKnot.rotation.y += 0.01;
    threeRenderer.render(threeScene, threeCamera);
  }
  animate();

  window.addEventListener('resize', () => {
    const width = canvas.parentElement.clientWidth;
    const height = canvas.parentElement.clientHeight;
    threeRenderer.setSize(width, height);
    threeCamera.aspect = width / height;
    threeCamera.updateProjectionMatrix();
  });
}

function toggleLotus() {
  const modal = document.getElementById('lotusModal');
  if (modal.style.display === 'none') {
    modal.style.display = 'flex';
    if (!threeRenderer) initThreeJS();
    if (!lotusWs) initLotus();
  } else {
    modal.style.display = 'none';
  }
}

function initLotus() {
  const term = document.getElementById('terminal');
  const input = document.getElementById('termInput');
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  lotusWs = new WebSocket(`${protocol}//${window.location.host}/lotus/ws/terminal`);
  
  let startTime = Date.now();

  lotusWs.onmessage = (e) => {
    // Update HUD
    const latency = Date.now() - startTime;
    document.getElementById('hudLatency').textContent = latency + 'ms';
    document.getElementById('hudLoad').textContent = (Math.random() * 5 + 2).toFixed(1) + '%';
    document.getElementById('hudBar').style.width = (Math.random() * 20 + 30) + '%';
    
    // Add text to terminal
    term.textContent += e.data;
    term.scrollTop = term.scrollHeight;

    // Visual feedback in 3D
    if (torusKnot) {
        torusKnot.scale.set(1.1, 1.1, 1.1);
        setTimeout(() => torusKnot.scale.set(1, 1, 1), 50);
    }
  };
  
  lotusWs.onclose = () => {
    term.textContent += '\n[SESSION TERMINATED]\n';
    lotusWs = null;
  };

  input.onkeydown = (e) => {
    if (e.key === 'Enter') {
      startTime = Date.now();
      const cmd = input.value;
      input.value = '';
      if (lotusWs && lotusWs.readyState === WebSocket.OPEN) {
        lotusWs.send(cmd);
      }
    }
  };
}

setInterval(updatePhi, 10000);
setInterval(updateObserver, 5000);
setInterval(updateDIIHistory, 15000);
updatePhi();
updateHealth();
updateObserver();
updateDIIHistory();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def root():
    return INDEX_HTML


@app.get("/api/growth")
async def api_growth():
    return growth_profile(memory, state.turns)


@app.post("/api/reset")
async def api_reset():
    global brain, memory, history, state, goals_db, doc_store
    
    # 1. Reset ContextVars
    try:
        from infj_bot.core.causal_wiring import state_override_var, generation_params_var
        state_override_var.set(None)
        generation_params_var.set(None)
    except Exception:
        pass

    # 2. Reset singletons/global modules
    try:
        import infj_bot.core.being as being_mod
        being_mod._being_instance = None
    except Exception:
        pass

    try:
        import infj_bot.core.homeostasis as homeostasis_mod
        homeostasis_mod._homeostasis_instance = None
    except Exception:
        pass

    try:
        import infj_bot.core.shadow as shadow_mod
        shadow_mod._shadow_instance = None
    except Exception:
        pass

    try:
        import infj_bot.core.dii_tracker as dii_mod
        dii_mod._dii_instance = None
    except Exception:
        pass

    try:
        import infj_bot.core.global_workspace as workspace_mod
        workspace_mod._workspace_instance = None
    except Exception:
        pass

    # 3. Re-instantiate core structures
    brain = DriftBrain()
    memory = DriftMemory()
    history = ChatHistory()
    state = BotState(authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS))
    goals_db = GoalsDB()
    doc_store = DocumentStore()

    # 4. Clean database tables
    try:
        import sqlite3
        from infj_bot.core.config import MEMORY_DB, HOMEOSTASIS_DB
        
        # Clear Memory
        with sqlite3.connect(MEMORY_DB) as conn:
            conn.execute("DELETE FROM memories")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='memories'")
            conn.commit()
            
        # Clear Homeostasis
        with sqlite3.connect(HOMEOSTASIS_DB) as conn:
            conn.execute("DELETE FROM need_history")
            conn.execute("DELETE FROM survival_events")
            conn.execute("DELETE FROM regulation_actions")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='need_history'")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='survival_events'")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='regulation_actions'")
            conn.commit()
    except Exception as e:
        logger.error(f"Error resetting database contents: {e}")

    return {"status": "ok", "message": "All cognitive modules, singletons, and sqlite tables have been reset to zero."}


async def read_json(request: Request):
    try:
        return await request.json()
    except Exception:
        return None


@app.post("/api/chat")
async def api_chat(request: Request):
    payload = await read_json(request)
    if payload is None:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    message = payload.get("message", "").strip()
    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    # Set state override context variable
    from infj_bot.core.causal_wiring import state_override_var
    state_override_var.set(payload.get("state"))

    prompt, emotion, dissonance = build_chat_prompt(
        message,
        state,
        memory,
        goals_db=goals_db,
        doc_store=doc_store,
        prefs=state.prefs,
    )

    cancel_event = threading.Event()
    budget = RequestBudget(deadline=time.monotonic() + 180.0, cancel_event=cancel_event)
    watcher_task = asyncio.create_task(_watch_request_disconnect(request, cancel_event))

    try:
        output = await asyncio.to_thread(
            _run_with_request_budget,
            brain.agent_turn,
            budget,
            prompt,
            tools_enabled=True,
            raw_user_input=message,
            mode=state.mode
        )
        try:
            await asyncio.to_thread(
                _run_with_request_budget,
                brain.evaluate_last,
                budget,
                prompt,
                output
            )
        except Exception:
            pass
        importance = min(
            0.95, 0.45 + emotion["intensity"] * 0.3 + dissonance["score"] * 0.15
        )
        await asyncio.to_thread(
            memory.save_interaction,
            message,
            output,
            mode=state.mode,
            emotion=emotion,
            importance=importance,
            dissonance=dissonance,
        )
        await asyncio.to_thread(
            history.append, message, output, state.mode, emotion, dissonance
        )
        state.turns += 1

        # ── Aliveness Tracking (DII) ──
        try:
            from infj_bot.core.being import get_being
            from infj_bot.core.homeostasis import get_homeostasis
            from infj_bot.core.shadow import get_shadow
            from infj_bot.core.dii_tracker import get_dii_tracker
            from infj_bot.core.global_workspace import get_workspace

            tracker = get_dii_tracker()
            tracker.compute(
                being=get_being(),
                workspace=get_workspace(),
                homeostasis=get_homeostasis(),
                shadow=get_shadow(),
                orchestrator=CognitiveOrchestrator(),
            )
        except Exception:
            pass

        return {"reply": output}
    finally:
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass


@app.post("/api/chat/stream")
async def api_chat_stream(request: Request):
    payload = await read_json(request)
    if payload is None:
        return StreamingResponse(
            (f"data: {json.dumps({'error': 'invalid JSON body'})}\n\n" for _ in [1]),
            media_type="text/event-stream",
        )
    message = payload.get("message", "").strip()
    if not message:
        return StreamingResponse(
            (f"data: {json.dumps({'error': 'message is required'})}\n\n" for _ in [1]),
            media_type="text/event-stream",
        )

    # Set state override context variable
    from infj_bot.core.causal_wiring import state_override_var
    state_override_var.set(payload.get("state"))

    prompt, emotion, dissonance = build_chat_prompt(
        message,
        state,
        memory,
        goals_db=goals_db,
        doc_store=doc_store,
        prefs=state.prefs,
    )

    cancel_event = threading.Event()
    budget = RequestBudget(deadline=time.monotonic() + 180.0, cancel_event=cancel_event)
    watcher_task = asyncio.create_task(_watch_request_disconnect(request, cancel_event))

    async def event_generator():
        try:
            # Run synchronous stream in a thread to avoid blocking the event loop
            chunks = await asyncio.to_thread(
                _run_with_request_budget,
                lambda: list(brain.agent_turn_stream(prompt, tools_enabled=True, raw_user_input=message, mode=state.mode)),
                budget
            )
            for chunk in chunks:
                budget.check()
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield "data: [DONE]\n\n"

            output = "".join(chunks)
            try:
                await asyncio.to_thread(
                    _run_with_request_budget,
                    brain.evaluate_last,
                    budget,
                    prompt,
                    output
                )
            except Exception:
                pass
            importance = min(
                0.95, 0.45 + emotion["intensity"] * 0.3 + dissonance["score"] * 0.15
            )
            await asyncio.to_thread(
                memory.save_interaction,
                message,
                output,
                mode=state.mode,
                emotion=emotion,
                importance=importance,
                dissonance=dissonance,
            )
            await asyncio.to_thread(
                history.append, message, output, state.mode, emotion, dissonance
            )
            state.turns += 1

            # ── Aliveness Tracking (DII) ──
            try:
                from infj_bot.core.being import get_being
                from infj_bot.core.homeostasis import get_homeostasis
                from infj_bot.core.shadow import get_shadow
                from infj_bot.core.dii_tracker import get_dii_tracker
                from infj_bot.core.global_workspace import get_workspace

                tracker = get_dii_tracker()
                tracker.compute(
                    being=get_being(),
                    workspace=get_workspace(),
                    homeostasis=get_homeostasis(),
                    shadow=get_shadow(),
                    orchestrator=CognitiveOrchestrator(),
                )
            except Exception:
                pass
        except RequestCancelled:
            logger.info("Stream aborted internally due to client disconnect.")
            return
        except SystemOverload as e:
            logger.warning(f"System overload during stream: {e}")
            yield f"data: {json.dumps({'error': f'SystemOverload: {e}'})}\n\n"
            yield "data: [DONE]\n\n"
            return
        except RequestDeadlineExceeded as e:
            logger.warning(f"Deadline exceeded during stream: {e}")
            yield f"data: {json.dumps({'error': f'RequestDeadlineExceeded: {e}'})}\n\n"
            yield "data: [DONE]\n\n"
            return
        except Exception as exc:
            traceback.print_exc()
            yield f"data: {json.dumps({'error': f'{type(exc).__name__}: {exc}'})}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            watcher_task.cancel()
            try:
                await watcher_task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/command")
async def api_command(request: Request):
    payload = await read_json(request)
    if payload is None:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    reply = handle_command(
        payload.get("command", ""),
        payload.get("args", ""),
        state,
        brain,
        memory,
        history,
        goals_db,
        doc_store,
    )
    return {"reply": reply}


@app.get("/api/tools")
async def api_tools():
    return {"reply": format_tool_inventory()}


@app.get("/api/phi")
async def api_phi():
    from infj_bot.core.being import get_being
    from infj_bot.core.homeostasis import get_homeostasis
    from infj_bot.core.phi_proxy import PhiProxy
    from infj_bot.adapters.cognition_adapter import adapter as cog_adapter

    being = get_being()
    homeo = get_homeostasis()
    iit = PhiProxy()

    return {
        "company": "PHI",
        "model": "Drift",
        "phi": iit.state.phi,
        "council": COUNCIL_MAPPING,
        "subjective": being.state.to_dict() if hasattr(being, "state") else {},
        "needs": homeo.get_all_needs() if hasattr(homeo, "get_all_needs") else {},
        "free_energy": homeo.compute_free_energy(
            0, 0.1, 0.9
        ),  # Placeholder inputs for test
        "status": cog_adapter.get_status(),
    }


@app.get("/api/hive")
async def api_hive():
    try:
        from infj_bot.hive_mind.orchestrator import HiveOrchestrator

        orch = HiveOrchestrator()
        return orch.get_status()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/health")
async def api_health():
    try:
        from infj_bot.hive_mind.orchestrator import HiveOrchestrator

        orch = HiveOrchestrator()
        hive_status = orch.get_status()
    except Exception:
        hive_status = "offline"

    return {
        "ok": True,
        "company": "PHI",
        "model": "Drift",
        "memory_count": memory.count(),
        "turns": state.turns,
        "mode": state.mode,
        "hive": hive_status,
    }


@app.get("/api/identity")
async def api_identity(key_id: str = "v1", nonce: str = None):
    import hmac
    import hashlib
    import os
    from datetime import datetime, timezone

    # Key Rotation & Safe Environment Retrieval
    env_var_name = f"DRIFT_SHARED_KEY_{key_id.upper()}"
    secret_str = os.environ.get(env_var_name)
    is_prod = os.environ.get("DRIFT_ENV") == "production"
    
    if not secret_str and not is_prod:
        # Fallback to general DRIFT_SHARED_KEY to support seamless migration/testing in dev
        secret_str = os.environ.get("DRIFT_SHARED_KEY")
    
    if not secret_str:
        if is_prod:
            raise RuntimeError(f"CRITICAL: Shared key '{env_var_name}' is missing in production!")
        else:
            raise RuntimeError(f"CRITICAL: Shared key for ID '{key_id}' ({env_var_name} or DRIFT_SHARED_KEY) is missing from environment!")
        
    secret = secret_str.encode()
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Body is empty for GET /api/identity
    body_hash = hashlib.sha256(b"").hexdigest()
    
    # Canonical string format: METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + BODY_HASH + ("\n" + NONCE if NONCE else "")
    if nonce:
        message = f"GET\n/api/identity\n{ts}\n{body_hash}\n{nonce}".encode()
    else:
        message = f"GET\n/api/identity\n{ts}\n{body_hash}".encode()
        
    signature = hmac.new(secret, message, hashlib.sha256).hexdigest()
    
    metadata = {
        "OriginModule": "brain",
        "Timestamp": ts,
        "KeyID": key_id,
        "BodyHash": body_hash,
        "Signature": signature
    }
    if nonce:
        metadata["Nonce"] = nonce
        
    return {
        "Metadata": metadata
    }


@app.get("/api/dii")
async def api_dii():
    from infj_bot.core.dii_tracker import get_dii_tracker

    tracker = get_dii_tracker()
    return tracker.get_trend(n=20)


@app.get("/api/dii/history")
async def api_dii_history(limit: int = 100):
    from infj_bot.core.dii_tracker import get_dii_tracker

    tracker = get_dii_tracker()
    return {"history": tracker.get_history(limit=limit)}


@app.get("/api/audit")
async def api_audit(limit: int = 50):
    """Retrieve the unified audit log for monitoring and safety verification."""
    try:
        from infj_bot.core.unified_audit import get_audit_logger
        audit_logger = get_audit_logger()
        # Use read_any as a static helper or tail
        from infj_bot.core.jsonl_logger import HardenedJsonlLogger
        return HardenedJsonlLogger.tail(audit_logger.path, n=limit)
    except Exception as e:
        return {"error": f"Failed to retrieve audit log: {e}"}


@app.get("/api/hive/deliberations")
async def api_hive_deliberations(limit: int = 10):
    """Retrieve history of high-order deliberations from the Elysium engine."""
    try:
        from infj_bot.core.hive.elysium import get_elysium
        elysium = get_elysium()
        return elysium.get_deliberation_history(limit=limit)
    except Exception as e:
        return {"error": f"Failed to retrieve deliberations: {e}"}


@app.get("/api/observer")
async def api_observer():
    """Full real-time cognitive state for the observer dashboard."""
    from infj_bot.core.being import get_being
    from infj_bot.core.homeostasis import get_homeostasis
    from infj_bot.core.shadow import get_shadow
    from infj_bot.core.dii_tracker import get_dii_tracker
    from infj_bot.core.global_workspace import get_workspace

    being = get_being()
    homeo = get_homeostasis()
    shadow = get_shadow()
    dii = get_dii_tracker()
    ws = get_workspace()

    # Shadow radar
    radar = {}
    try:
        radar = (
            {k: round(v, 2) for k, v in shadow.radar.items()}
            if hasattr(shadow, "radar")
            else {}
        )
    except Exception:
        pass

    # Homeostasis needs
    needs = {}
    try:
        for name, need in homeo.needs.items():
            needs[name] = {
                "current": round(need.current, 2),
                "setpoint": round(need.setpoint, 2),
                "trend": round(need.trend, 2),
            }
    except Exception:
        pass

    # DII
    dii_data = dii.get_trend(n=20)

    return {
        "timestamp": time.time(),
        "being": {
            "mood": being.state.mood if being else "unknown",
            "energy": round(being.state.energy, 2) if being else 0.5,
            "curiosity": round(being.state.curiosity, 2) if being else 0.5,
            "attachment": round(being.state.attachment, 2) if being else 0.5,
            "self_awareness": round(being.agency.self_awareness, 2) if being else 0.5,
            "volition": round(being.agency.volition, 2) if being else 0.5,
            "autonomy_drive": round(being.agency.autonomy_drive, 2) if being else 0.5,
            "working_memory_size": len(being.working_memory) if being else 0,
        },
        "homeostasis": {
            "needs": needs,
            "allostatic_load": round(homeo.allostatic_load, 2) if homeo else 0.0,
            "crisis_mode": homeo.crisis_mode if homeo else False,
            "weather": homeo.weather if homeo else "clear",
            "mood_ema": round(homeo.mood_ema, 2) if homeo else 0.5,
        },
        "shadow": {
            "radar": radar,
            "integration_level": round(shadow._state.integration_level, 2)
            if hasattr(shadow, "_state")
            else 0.0,
            "dominant_archetype": shadow._state.dominant_archetype
            if hasattr(shadow, "_state")
            else "",
        },
        "workspace": {
            "contents_count": len(ws._submissions) if ws else 0,
            "spotlight": ws.state.spotlight.source
            if (ws and ws.state and ws.state.spotlight)
            else "none",
        },
        "dii": dii_data,
    }


if __name__ == "__main__":
    import uvicorn

    import os
    host = os.getenv("DRIFT_API_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=8765)

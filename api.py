"""FastAPI web app with SSE streaming, markdown rendering, and modern UI."""

import asyncio
import json
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from brain import DriftBrain
from commands import BotState, handle_command
from config import DEFAULT_AUTHORIZED_TARGETS
from documents import DocumentStore
from goals import GoalsDB
from growth import growth_profile
from history import ChatHistory
from memory import DriftMemory
from prompt_builder import build_chat_prompt
from tools import format_tool_inventory
from cognitive_orchestrator import CognitiveOrchestrator
from infj_bot.core.phi_council import COUNCIL_MAPPING

brain = DriftBrain()
memory = DriftMemory()
history = ChatHistory()
state = BotState(authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS))
goals_db = GoalsDB()
doc_store = DocumentStore()


STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="PHI // Drift", lifespan=lifespan)

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
    section { padding: 20px; display: flex; flex-direction: column; }
    #chat { border-right: 1px solid var(--border); }
    #header { 
      display: flex; 
      align-items: center; 
      gap: 12px; 
      margin-bottom: 20px; 
      padding-bottom: 15px;
      border-bottom: 1px solid var(--border);
    }
    #header h1 { margin: 0; font-size: 20px; font-weight: 800; letter-spacing: -0.5px; color: var(--phi-gold); }
    #messages { flex: 1; overflow: auto; display: flex; flex-direction: column; gap: 16px; padding-right: 8px; }
    .msg { padding: 16px 20px; border: 1px solid var(--border); border-radius: 12px; max-width: 85%; }
    .user { background: #161b22; align-self: flex-end; border-color: #30363d; }
    .bot { background: #0d1117; align-self: flex-start; border-left: 4px solid var(--phi-gold); }
    
    #form { display: flex; gap: 10px; margin-top: 20px; background: var(--panel); padding: 15px; border-radius: 12px; border: 1px solid var(--border); }
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

    <div style="margin-top:20px;">
        <select id="mode" style="width:100%; background:var(--bg); color:var(--fg); border:1px solid var(--border); padding:8px; border-radius:6px;">
          <option>companion</option><option>engineer</option><option>critic</option>
          <option>coach</option><option>clarity</option><option>researcher</option><option>bughunter</option><option>drift</option><option>quiet</option>
        </select>
    </div>
  </aside>
</main>

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
  body.className = 'markdown-body';
  div.appendChild(body);
  messages.appendChild(div);
  
  let buffer = '';
  try {
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text})
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
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
            }
          } catch (e) {}
        }
      }
    }
  } catch (e) { body.innerHTML = 'Error: ' + e.message; }
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

setInterval(updatePhi, 10000);
updatePhi();
updateHealth();
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
    prompt, emotion, dissonance = build_chat_prompt(
        message,
        state,
        memory,
        goals_db=goals_db,
        doc_store=doc_store,
        prefs=state.prefs,
    )
    output = await asyncio.to_thread(brain.agent_turn, prompt, tools_enabled=True)
    try:
        await asyncio.to_thread(brain.evaluate_last, prompt, output)
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
    return {"reply": output}


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

    prompt, emotion, dissonance = build_chat_prompt(
        message,
        state,
        memory,
        goals_db=goals_db,
        doc_store=doc_store,
        prefs=state.prefs,
    )

    async def event_generator():
        try:
            # Run synchronous stream in a thread to avoid blocking the event loop
            chunks = await asyncio.to_thread(
                lambda: list(brain.agent_turn_stream(prompt, tools_enabled=True))
            )
            for chunk in chunks:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield "data: [DONE]\n\n"

            output = "".join(chunks)
            try:
                await asyncio.to_thread(brain.evaluate_last, prompt, output)
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
        except Exception as exc:
            traceback.print_exc()
            yield f"data: {json.dumps({'error': f'{type(exc).__name__}: {exc}'})}\n\n"
            yield "data: [DONE]\n\n"

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
    from infj_bot.adapters.cognition_adapter import adapter as cog_adapter
    
    being = get_being()
    homeo = get_homeostasis()
    
    return {
        "company": "PHI",
        "model": "Drift",
        "council": COUNCIL_MAPPING,
        "subjective": being.state.to_dict() if hasattr(being, "state") else {},
        "needs": homeo.get_all_needs() if hasattr(homeo, "get_all_needs") else {},
        "free_energy": homeo.compute_free_energy(0, 0.1, 0.9), # Placeholder inputs for test
        "status": cog_adapter.get_status()
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

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8765)
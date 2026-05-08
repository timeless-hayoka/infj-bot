"""FastAPI web app with SSE streaming, markdown rendering, and modern UI."""
import asyncio
import json
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from brain import InfjBrain
from commands import BotState, handle_command
from config import DEFAULT_AUTHORIZED_TARGETS
from documents import DocumentStore
from goals import GoalsDB
from growth import growth_profile
from history import ChatHistory
from memory import InfjMemory
from prompt_builder import build_chat_prompt
from tools import format_tool_inventory

brain = InfjBrain()
memory = InfjMemory()
history = ChatHistory()
state = BotState(authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS))
goals_db = GoalsDB()
doc_store = DocumentStore()


STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="INFJ Bot", lifespan=lifespan)

# Serve static files if any exist
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>INFJ Bot</title>
  <style>
    :root { --bg: #0d1117; --fg: #c9d1d9; --accent: #58a6ff; --muted: #8b949e; --panel: #161b22; --border: #30363d; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; background: var(--bg); color: var(--fg); line-height: 1.5; }
    main { display: grid; grid-template-columns: 1fr 340px; min-height: 100vh; }
    section { padding: 18px; }
    #chat { display: flex; flex-direction: column; gap: 12px; }
    #messages { height: calc(100vh - 130px); overflow: auto; display: flex; flex-direction: column; gap: 14px; }
    .msg { padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; }
    .user { background: #161b22; }
    .bot { background: #13211d; }
    .bot .markdown-body { background: transparent !important; color: var(--fg); }
    .markdown-body pre { overflow:auto; padding:10px; border:1px solid var(--border); border-radius:8px; background:#0d1117; }
    .markdown-body code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    form { display: flex; gap: 8px; }
    input, select, button, textarea { background: var(--panel); color: var(--fg); border: 1px solid var(--border); border-radius: 8px; padding: 10px; font-size: 14px; }
    input { flex: 1; }
    button { cursor: pointer; background: #238636; border-color: #238636; color: #fff; font-weight: 600; }
    button:hover { background: #2ea043; }
    aside { border-left: 1px solid var(--border); background: var(--panel); }
    .panel { margin-bottom: 18px; }
    .small { color: var(--muted); font-size: 12px; }
    #growthCard { border: 1px solid var(--border); border-radius: 10px; padding: 14px; background: #0d1117; }
    #growthAvatar { height: 120px; display: grid; place-items: center; border: 1px solid var(--border); border-radius: 10px; background: radial-gradient(circle at 50% 35%, #25443a, #0d1117 64%); overflow: hidden; }
    .creature { --scale: 1; position: relative; width: 64px; height: 72px; transform: scale(var(--scale)); transition: transform 180ms ease; }
    .creature .body { position: absolute; left: 10px; top: 18px; width: 44px; height: 46px; border-radius: 45% 45% 38% 38%; background: #66d19e; box-shadow: inset -8px -10px 0 #3d9f79; }
    .creature .eye { position: absolute; top: 34px; width: 6px; height: 8px; border-radius: 50%; background: #08110e; z-index: 2; }
    .creature .eye.left { left: 24px; }
    .creature .eye.right { right: 24px; }
    .creature .mouth { position: absolute; left: 29px; top: 47px; width: 10px; height: 5px; border-bottom: 2px solid #08110e; border-radius: 0 0 12px 12px; z-index: 2; }
    .creature .leaf { position: absolute; left: 28px; top: 3px; width: 10px; height: 24px; border-radius: 90% 10% 90% 10%; background: #9de66f; transform-origin: bottom center; transform: rotate(-22deg); opacity: 0; }
    .creature .glow { position: absolute; left: 18px; top: 22px; width: 28px; height: 28px; border-radius: 50%; background: #f5d46a; opacity: 0; filter: blur(6px); }
    .creature .star { position: absolute; width: 5px; height: 5px; border-radius: 50%; background: #d7f7ff; opacity: 0; }
    .creature .star.one { left: 6px; top: 12px; }
    .creature .star.two { right: 4px; top: 8px; }
    .creature .star.three { right: 12px; bottom: 12px; }
    .creature.spark .body { width: 24px; height: 24px; left: 20px; top: 28px; border-radius: 50%; }
    .creature.seed .body { width: 34px; height: 34px; left: 15px; top: 28px; border-radius: 50% 50% 42% 42%; }
    .creature.sprout .leaf, .creature.bloom .leaf, .creature.lantern .leaf, .creature.constellation .leaf { opacity: 1; }
    .creature.bloom .leaf { transform: rotate(-32deg) scale(1.15); }
    .creature.lantern .glow, .creature.constellation .glow { opacity: 0.7; }
    .creature.constellation .star { opacity: 1; }
    #growthStage { margin-top: 10px; font-weight: 700; }
    #growthBar { height: 8px; background: #1a252b; border-radius: 999px; overflow: hidden; margin: 8px 0; }
    #growthFill { height: 100%; width: 0%; background: #64d69b; transition: width 160ms ease; }
    #growthStats { margin: 8px 0 0; }
    .streaming .cursor::after { content: "\u258c"; animation: blink 1s step-end infinite; }
    @keyframes blink { 50% { opacity: 0; } }
    @media (max-width: 800px) { main { grid-template-columns: 1fr; } aside { border-left: 0; border-top: 1px solid var(--border); } }
  </style>
</head>
<body>
<main>
  <section id="chat">
    <div id="messages"></div>
    <form id="form">
      <input id="input" autocomplete="off" placeholder="Talk to the INFJ bot...">
      <button type="submit">Send</button>
      <button type="button" id="streamBtn" title="Toggle streaming">SSE</button>
    </form>
  </section>
  <aside>
    <section>
      <div class="panel">
        <div id="growthCard">
          <div id="growthAvatar"><div id="growthCreature" class="creature spark"><div class="glow"></div><div class="leaf"></div><div class="body"></div><div class="eye left"></div><div class="eye right"></div><div class="mouth"></div><div class="star one"></div><div class="star two"></div><div class="star three"></div></div></div>
          <div id="growthStage">Growth stage</div>
          <div id="growthBar"><div id="growthFill"></div></div>
          <div id="growthDesc" class="small"></div>
          <pre id="growthStats" class="small"></pre>
        </div>
      </div>
      <div class="panel">
        <label>Mode</label><br>
        <select id="mode">
          <option>companion</option><option>engineer</option><option>critic</option>
          <option>coach</option><option>clarity</option><option>researcher</option><option>bughunter</option><option>drift</option><option>quiet</option>
        </select>
      </div>
      <div class="panel">
        <button id="status">Status</button>
        <button id="reflect">Reflect</button>
        <pre id="side" class="small"></pre>
      </div>
      <div class="panel">
        <textarea id="query" rows="3" style="width:100%" placeholder="Search memory"></textarea>
        <button id="search">Search</button>
      </div>
    </section>
  </aside>
</main>
<script>
const messages = document.querySelector('#messages');
let streaming = true;

document.getElementById('streamBtn').onclick = () => {
  streaming = !streaming;
  document.getElementById('streamBtn').style.background = streaming ? '#238636' : '#30363d';
};

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
  escaped = escaped.replace(/```([\\s\\S]*?)```/g, (_, code) => '<pre><code>' + code.trim() + '</code></pre>');
  escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
  escaped = escaped.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
  escaped = escaped.replace(/^### (.*)$/gm, '<h3>$1</h3>');
  escaped = escaped.replace(/^## (.*)$/gm, '<h2>$1</h2>');
  escaped = escaped.replace(/^# (.*)$/gm, '<h1>$1</h1>');
  escaped = escaped.replace(/\\n/g, '<br>');
  return escaped;
}

function addStreaming() {
  const div = document.createElement('div');
  div.className = 'msg bot streaming';
  const body = document.createElement('div');
  body.className = 'markdown-body';
  const cursor = document.createElement('span');
  cursor.className = 'cursor';
  body.appendChild(cursor);
  div.appendChild(body);
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return { div, body, cursor };
}

async function post(path, body={}) {
  const res = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  return await res.json();
}

async function refreshGrowth() {
  const res = await fetch('/api/growth');
  const data = await res.json();
  const creature = document.querySelector('#growthCreature');
  creature.className = 'creature ' + data.avatar;
  creature.style.setProperty('--scale', data.size || 1);
  document.querySelector('#growthStage').textContent = data.stage + ' - ' + data.points + ' pts';
  document.querySelector('#growthFill').style.width = Math.round(data.progress * 100) + '%';
  document.querySelector('#growthDesc').textContent = data.description;
  document.querySelector('#growthStats').textContent =
    'memories: ' + data.stats.total_memories +
    '\\nchats: ' + data.stats.interactions +
    '\\nconcepts: ' + data.stats.concepts +
    '\\nreflections: ' + data.stats.reflections;
}

async function streamChat(text) {
  add('user', text);
  const { body, cursor } = addStreaming();
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
      const lines = chunk.split('\\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') continue;
          try {
            const obj = JSON.parse(data);
            if (obj.chunk) {
              buffer += obj.chunk;
              cursor.remove();
              body.innerHTML = renderMarkdown(buffer);
              body.appendChild(cursor);
              messages.scrollTop = messages.scrollHeight;
            }
          } catch (e) {
            // ignore parse errors
          }
        }
      }
    }
  } catch (e) {
    body.innerHTML = '<em>Error: ' + e.message + '</em>';
  }
  cursor.remove();
  refreshGrowth();
}

async function regularChat(text) {
  add('user', text);
  const data = await post('/api/chat', {message: text});
  const reply = data.reply || data.error;
  add('bot', renderMarkdown(reply), true);
  refreshGrowth();
}

document.querySelector('#form').onsubmit = async (e) => {
  e.preventDefault();
  const input = document.querySelector('#input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  if (streaming) {
    await streamChat(text);
  } else {
    await regularChat(text);
  }
};

document.querySelector('#mode').onchange = async (e) => {
  const data = await post('/api/command', {command: 'mode', args: e.target.value});
  document.querySelector('#side').textContent = data.reply;
};
document.querySelector('#status').onclick = async () => {
  const data = await post('/api/command', {command: 'status', args: ''});
  document.querySelector('#side').textContent = data.reply;
};
document.querySelector('#reflect').onclick = async () => {
  const data = await post('/api/command', {command: 'reflect', args: ''});
  document.querySelector('#side').textContent = data.reply;
  refreshGrowth();
};
document.querySelector('#search').onclick = async () => {
  const data = await post('/api/command', {command: 'memory', args: document.querySelector('#query').value});
  document.querySelector('#side').textContent = data.reply;
};
refreshGrowth();
</script>
</body>
</html>"""


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
    prompt, emotion, dissonance = build_chat_prompt(message, state, memory, goals_db=goals_db, doc_store=doc_store, prefs=state.prefs)
    output = await asyncio.to_thread(brain.agent_turn, prompt, tools_enabled=True)
    try:
        await asyncio.to_thread(brain.evaluate_last, prompt, output)
    except Exception:
        pass
    importance = min(0.95, 0.45 + emotion["intensity"] * 0.3 + dissonance["score"] * 0.15)
    await asyncio.to_thread(
        memory.save_interaction,
        message,
        output,
        mode=state.mode,
        emotion=emotion,
        importance=importance,
        dissonance=dissonance,
    )
    await asyncio.to_thread(history.append, message, output, state.mode, emotion, dissonance)
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

    prompt, emotion, dissonance = build_chat_prompt(message, state, memory, goals_db=goals_db, doc_store=doc_store, prefs=state.prefs)

    async def event_generator():
        try:
            # Run synchronous stream in a thread to avoid blocking the event loop
            chunks = await asyncio.to_thread(lambda: list(brain.agent_turn_stream(prompt, tools_enabled=True)))
            for chunk in chunks:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield "data: [DONE]\n\n"

            output = "".join(chunks)
            try:
                await asyncio.to_thread(brain.evaluate_last, prompt, output)
            except Exception:
                pass
            importance = min(0.95, 0.45 + emotion["intensity"] * 0.3 + dissonance["score"] * 0.15)
            await asyncio.to_thread(
                memory.save_interaction,
                message,
                output,
                mode=state.mode,
                emotion=emotion,
                importance=importance,
                dissonance=dissonance,
            )
            await asyncio.to_thread(history.append, message, output, state.mode, emotion, dissonance)
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


@app.get("/api/health")
async def api_health():
    return {
        "ok": True,
        "memory_count": memory.count(),
        "turns": state.turns,
        "mode": state.mode,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)

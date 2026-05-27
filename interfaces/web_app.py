from gevent import monkey

monkey.patch_all()

import json
import time
from pathlib import Path

import gevent
from flask import Flask, request, jsonify, render_template_string
from flask_socketio import SocketIO, emit
import threading
from infj_bot.core.cognitive_orchestrator import CognitiveOrchestrator

# Observatory integration — hive_mind is an external symlinked dependency
try:
    import sys as _sys

    _hive_path = str(Path(__file__).resolve().parent / "hive_mind")
    if _hive_path not in _sys.path:
        _sys.path.insert(0, _hive_path)
    from drift_bridge import DriftBridge as _DriftBridge

    _obs_drift = _DriftBridge()
    _OBSERVATORY_ENABLED = True
except Exception:
    _OBSERVATORY_ENABLED = False

from infj_bot.core.brain import DriftBrain
from infj_bot.core.commands import BotState, handle_command
from infj_bot.core.plugins.growth import growth_profile
from infj_bot.core.history import ChatHistory
from infj_bot.core.memory import DriftMemory
from infj_bot.core.plugins.goals import GoalsDB
from infj_bot.core.config import DATA_DIR, DEFAULT_AUTHORIZED_TARGETS

STATE_ROOT = DATA_DIR
from infj_bot.core.plugins.documents import DocumentStore
from infj_bot.core.prompt_builder import build_chat_prompt


brain = DriftBrain()
memory = DriftMemory()
history = ChatHistory()
state = BotState(authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS))
goals_db = GoalsDB()
doc_store = DocumentStore()
_MAX_PAYLOAD = 1_048_576  # 1 MB


INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DRIFT // DASHBOARD</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600;700&display=swap');
    
    :root {
        --bg-deep: #050505;
        --bg-surface: #111111;
        --accent-orange: #FF5500;
        --accent-white: #FFFFFF;
        --text-muted: #A0A0A0;
        --border-dim: #222;
    }

    body { 
        margin: 0; 
        font-family: 'Rajdhani', sans-serif; 
        background: var(--bg-deep); 
        color: var(--accent-white); 
        overflow: hidden;
    }

    main { 
        display: grid; 
        grid-template-columns: 1fr 340px; 
        height: 100vh; 
    }

    section#chat { 
        display: flex; 
        flex-direction: column; 
        padding: 20px;
        background-image: radial-gradient(circle at 50% 50%, #0a0a0a 0%, #050505 100%);
    }

    header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
        border-bottom: 1px solid var(--border-dim);
        padding-bottom: 10px;
    }

    header h1 {
        font-family: 'Orbitron', sans-serif;
        font-size: 1.2rem;
        letter-spacing: 2px;
        margin: 0;
        color: var(--accent-orange);
    }

    #messages { 
        flex: 1; 
        overflow-y: auto; 
        display: flex; 
        flex-direction: column; 
        gap: 15px; 
        padding-right: 10px;
        scrollbar-width: thin;
        scrollbar-color: var(--accent-orange) var(--bg-deep);
    }

    .msg { 
        padding: 12px 16px; 
        border-radius: 2px; 
        max-width: 85%;
        line-height: 1.5;
        position: relative;
    }

    .user { 
        align-self: flex-end; 
        background: var(--bg-surface); 
        border: 1px solid #444; 
        color: var(--accent-white);
    }

    .bot { 
        align-self: flex-start; 
        background: rgba(255, 85, 0, 0.05); 
        border: 1px solid var(--accent-orange); 
        color: var(--accent-white);
        border-left-width: 4px;
    }

    form#form { 
        display: flex; 
        gap: 10px; 
        margin-top: 20px;
        background: var(--bg-surface);
        padding: 5px;
        border: 1px solid var(--border-dim);
    }

    input#input { 
        flex: 1; 
        background: transparent; 
        border: none; 
        color: var(--accent-white); 
        padding: 12px; 
        font-family: 'Rajdhani', sans-serif;
        font-size: 1rem;
    }

    input#input:focus { outline: none; }

    button { 
        background: var(--accent-orange); 
        color: var(--bg-deep); 
        border: none; 
        padding: 0 25px; 
        font-family: 'Orbitron', sans-serif; 
        font-weight: 700; 
        cursor: pointer;
        text-transform: uppercase;
        font-size: 0.8rem;
        transition: all 0.2s;
    }

    button:hover { background: var(--accent-white); }

    aside { 
        background: var(--bg-surface); 
        border-left: 1px solid var(--border-dim); 
        padding: 20px;
        overflow-y: auto;
        scrollbar-width: none;
    }

    .panel { 
        margin-bottom: 25px; 
        border: 1px solid var(--border-dim);
        padding: 15px;
        position: relative;
    }

    .panel::after {
        content: '';
        position: absolute;
        top: 0; left: 0; width: 10px; height: 10px;
        border-top: 2px solid var(--accent-orange);
        border-left: 2px solid var(--accent-orange);
    }

    .panel label {
        font-family: 'Orbitron', sans-serif;
        font-size: 0.7rem;
        color: var(--accent-orange);
        text-transform: uppercase;
        letter-spacing: 1px;
        display: block;
        margin-bottom: 10px;
    }

    select, textarea, input.side-input {
        width: 100%;
        background: #0a0a0a;
        border: 1px solid var(--border-dim);
        color: var(--accent-white);
        padding: 8px;
        font-family: 'Rajdhani', sans-serif;
        margin-bottom: 10px;
        box-sizing: border-box;
    }

    #growthCard { 
        text-align: center;
    }

    #growthAvatar { 
        height: 120px; 
        display: flex; 
        justify-content: center; 
        align-items: center; 
        background: #0a0a0a; 
        border: 1px solid var(--border-dim);
        margin-bottom: 15px;
        position: relative;
    }

    #growthBar { 
        height: 4px; 
        background: #222; 
        margin: 10px 0; 
        position: relative;
    }

    #growthFill { 
        height: 100%; 
        width: 0%; 
        background: var(--accent-orange); 
        box-shadow: 0 0 10px var(--accent-orange);
        transition: width 0.5s ease; 
    }

    #growthStage { 
        font-family: 'Orbitron', sans-serif;
        font-weight: 700; 
        color: var(--accent-white);
        font-size: 0.9rem;
    }

    .small { 
        color: var(--text-muted); 
        font-size: 0.8rem; 
        white-space: pre-wrap;
    }

    .obs-link {
        display: block;
        text-align: center;
        padding: 12px;
        background: var(--accent-orange);
        color: var(--bg-deep);
        font-family: 'Orbitron', sans-serif;
        font-weight: 700;
        text-decoration: none;
        font-size: 0.8rem;
        letter-spacing: 1px;
        transition: all 0.2s;
    }

    .obs-link:hover { background: var(--accent-white); }

    /* Creature Styles (adapted for orange theme) */
    .creature { --scale: 1; position: relative; width: 64px; height: 72px; transform: scale(var(--scale)); }
    .creature .body { position: absolute; left: 10px; top: 18px; width: 44px; height: 46px; border-radius: 45% 45% 38% 38%; background: var(--accent-orange); box-shadow: inset -8px -10px 0 #cc4400; }
    .creature .eye { position: absolute; top: 34px; width: 6px; height: 8px; border-radius: 50%; background: #000; z-index: 2; }
    .creature .eye.left { left: 24px; }
    .creature .eye.right { right: 24px; }
    .creature .mouth { position: absolute; left: 29px; top: 47px; width: 10px; height: 5px; border-bottom: 2px solid #000; border-radius: 0 0 12px 12px; z-index: 2; }
    .creature .leaf { position: absolute; left: 28px; top: 3px; width: 10px; height: 24px; border-radius: 90% 10% 90% 10%; background: #fff; transform-origin: bottom center; transform: rotate(-22deg); opacity: 0; }
    .creature .glow { position: absolute; left: 18px; top: 22px; width: 28px; height: 28px; border-radius: 50%; background: #fff; opacity: 0; filter: blur(6px); }
  </style>
</head>
<body>
<main>
  <section id="chat">
    <header>
      <h1>DRIFT // NEURAL INTERFACE</h1>
      <div class="small" id="connection-status">ONLINE // SESSION ACTIVE</div>
    </header>
    <div id="messages"></div>
    <form id="form">
      <input id="input" autocomplete="off" placeholder="TRANSMIT MESSAGE...">
      <button>SEND</button>
    </form>
  </section>
  <aside>
    <div class="panel" id="growthCard">
      <label>Biological Growth</label>
      <div id="growthAvatar">
        <div id="growthCreature" class="creature spark">
            <div class="glow"></div><div class="leaf"></div><div class="body"></div><div class="eye left"></div><div class="eye right"></div><div class="mouth"></div>
        </div>
      </div>
      <div id="growthStage">INITIALIZING...</div>
      <div id="growthBar"><div id="growthFill"></div></div>
      <div id="growthDesc" class="small"></div>
      <pre id="growthStats" class="small" style="text-align:left; margin-top:10px;"></pre>
    </div>

    <div class="panel">
      <label>Cognitive Mode</label>
      <select id="mode">
        <option>companion</option><option>engineer</option><option>critic</option>
        <option>coach</option><option>clarity</option><option>researcher</option><option>bughunter</option><option>quiet</option>
      </select>
      <div style="display:flex; gap:5px;">
        <button id="status" style="flex:1; padding:8px 0;">STATUS</button>
        <button id="reflect" style="flex:1; padding:8px 0;">REFLECT</button>
      </div>
      <pre id="side" class="small" style="margin-top:10px;"></pre>
    </div>

    <div class="panel">
      <label>Memory Retrieval</label>
      <textarea id="query" rows="2" placeholder="QUERY PARAMETERS..."></textarea>
      <button id="search" style="width:100%; padding:8px 0;">SEARCH</button>
    </div>

    <div class="panel" style="border:none; padding:0; display:flex; flex-direction:column; gap:8px;">
      <a href="/observatory" target="_blank" class="obs-link">OPEN OBSERVATORY</a>
      <a href="/glyph" target="_blank" class="obs-link" style="background:#111; color:var(--accent-orange); border:1px solid var(--accent-orange);">GLYPH SYSTEM</a>
    </div>
  </aside>
</main>
<script>
const messages = document.querySelector('#messages');
function add(cls, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  div.textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
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
  document.querySelector('#growthStage').textContent = data.stage.toUpperCase() + ' [' + data.points + ' XP]';
  document.querySelector('#growthFill').style.width = Math.round(data.progress * 100) + '%';
  document.querySelector('#growthDesc').textContent = data.description;
  document.querySelector('#growthStats').textContent =
    'MEMORIES: ' + data.stats.total_memories +
    '\\nCHATS: ' + data.stats.interactions +
    '\\nCONCEPTS: ' + data.stats.concepts +
    '\\nREFLECTIONS: ' + data.stats.reflections;
}
document.querySelector('#form').onsubmit = async (e) => {
  e.preventDefault();
  const input = document.querySelector('#input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  add('user', text);
  const data = await post('/api/chat', {message: text});
  add('bot', data.reply || data.error);
  refreshGrowth();
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


def chat_reply(message):
    prompt, emotion, dissonance = build_chat_prompt(
        message,
        state,
        memory,
        goals_db=goals_db,
        doc_store=doc_store,
        prefs=state.prefs,
    )
    output = brain.agent_turn(prompt, tools_enabled=True)
    try:
        brain.evaluate_last(prompt, output)
    except Exception:
        pass
    importance = min(
        0.95, 0.45 + emotion["intensity"] * 0.3 + dissonance["score"] * 0.15
    )
    memory.save_interaction(
        message,
        output,
        mode=state.mode,
        emotion=emotion,
        importance=importance,
        dissonance=dissonance,
    )
    history.append(message, output, state.mode, emotion, dissonance)
    state.turns += 1
    return output


app = Flask(__name__)
app.config["SECRET_KEY"] = "drift-secret-key"

socketio = SocketIO(
    app, async_mode="gevent", cors_allowed_origins="*", websocket_compression=True
)

broadcast_interval = 0.35
total_bytes_raw = 0
total_bytes_compressed = 0
cognitive_orchestrator = CognitiveOrchestrator()

# Sandbox / Trial Management
trial_sessions = {}  # {session_id: start_time}


def is_trial_active(session_id):
    if not session_id or session_id not in trial_sessions:
        return False
    # 30 minute limit (1800 seconds)
    if time.time() - trial_sessions[session_id] > 1800:
        return False
    return True


@app.route("/trial")
def start_trial():
    import uuid

    session_id = str(uuid.uuid4())
    trial_sessions[session_id] = time.time()
    # Simple hack to inject the session into the frontend
    trial_html = INDEX_HTML.replace(
        "document.querySelector('#form').onsubmit",
        f"const DRIFT_SESSION_ID = '{session_id}';\n"
        + "document.querySelector('#form').onsubmit",
    ).replace(
        "async function post(path, body={}) {",
        "async function post(path, body={}) {\n  if(typeof DRIFT_SESSION_ID !== 'undefined') body.session_id = DRIFT_SESSION_ID;",
    )
    return trial_html


def broadcast_observatory_state():
    global broadcast_interval, total_bytes_raw, total_bytes_compressed
    while True:
        try:
            delta = cognitive_orchestrator.get_delta_state()
            if len(delta) > 1:
                raw_size = len(json.dumps(delta))
                total_bytes_raw += raw_size
                total_bytes_compressed += int(raw_size * 0.3)
                delta["network_stats"] = {
                    "raw_kb": round(total_bytes_raw / 1024, 2),
                    "comp_kb": round(total_bytes_compressed / 1024, 2),
                    "interval_ms": int(broadcast_interval * 1000),
                }
                socketio.emit("observatory_delta", delta)
        except Exception:
            pass
        gevent.sleep(broadcast_interval)


threading.Thread(target=broadcast_observatory_state, daemon=True).start()


@socketio.on("latency_ping")
def handle_latency_ping(data):
    emit(
        "latency_pong",
        {"server_time": time.time(), "client_timestamp": data.get("timestamp")},
    )


@socketio.on("auto_adjust_rate")
def handle_adjust_rate(data):
    global broadcast_interval
    target_interval = data.get("interval", 0.35)
    broadcast_interval = max(0.2, min(target_interval, 1.5))


@app.route("/")
def index():
    return INDEX_HTML


@app.route("/api/growth", methods=["GET"])
def get_growth():
    return jsonify(growth_profile(memory, state.turns))


@app.route("/api/tags", methods=["GET"])
def ollama_tags():
    return jsonify(
        {
            "models": [
                {
                    "name": "infj_bot:latest",
                    "model": "infj_bot:latest",
                    "modified_at": "2023-11-04T14:56:49.277302595-07:00",
                    "size": 7323310500,
                    "digest": "9f438cb9cd581fc025612d27f7c1a6669ff83a8bb0ed86c94fcf4c5440555697",
                }
            ]
        }
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    payload = request.json

    # Check for trial session
    session_id = payload.get("session_id")
    if session_id and not is_trial_active(session_id):
        return jsonify(
            {"error": "Trial session expired. Please start a new session at /trial"}
        ), 403

    # Check if this is an Ollama-style request (from Reins)
    if "messages" in payload:
        messages = payload.get("messages", [])
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
        if not user_message:
            return jsonify({"error": "No user message found"}), 400

        reply_text = chat_reply(user_message)

        return jsonify(
            {
                "model": payload.get("model", "infj_bot:latest"),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                "message": {"role": "assistant", "content": reply_text},
                "done": True,
            }
        )

    # Standard INFJ Bot UI request
    message = payload.get("message", "")
    if isinstance(message, str):
        message = message.strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    return jsonify({"reply": chat_reply(message)})


@app.route("/v1/chat/completions", methods=["POST", "OPTIONS"])
def openai_chat_completions():
    if request.method == "OPTIONS":
        return "", 200

    payload = request.json
    messages = payload.get("messages", [])

    # Extract the last user message
    user_message = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    if not user_message:
        return jsonify({"error": "No user message found"}), 400

    # Get reply from infj_bot
    reply_text = chat_reply(user_message)

    # Format as OpenAI response
    import uuid

    response = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.get("model", "infj_bot"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    return jsonify(response)


@app.route("/api/command", methods=["POST"])
def api_command():
    payload = request.json
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
    return jsonify({"reply": reply})


@app.route("/api/email", methods=["POST"])
def api_email():
    # Email sending is not implemented; no send_email backend available.
    return jsonify(
        {
            "sent": False,
            "error": "Email sending not implemented (no backend configured).",
        }
    ), 501


@app.route("/observatory")
def observatory():
    try:
        path = Path(__file__).resolve().parent / "templates" / "observatory.html"
        if not path.exists():
            path = Path("/home/crexs/templates/observatory.html")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return render_template_string(content)
    except Exception as e:
        return str(e), 500


@app.route("/glyph")
@app.route("/phi-glyph")
def glyph():
    try:
        path = Path(__file__).resolve().parent / "templates" / "phi_glyph_system.html"
        if not path.exists():
            path = Path("/home/crexs/Downloads/PHI Glyph System.html")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return render_template_string(content)
    except Exception as e:
        return str(e), 500


def main():
    import os

    print("🚀 DRIFT Web App: Gevent + Compression + Delta Logic Active")
    port = int(os.getenv("PORT", 7860))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()

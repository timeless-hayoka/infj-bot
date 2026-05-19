from gevent import monkey
monkey.patch_all()

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import traceback

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
    from observatory.server import INDEX_HTML as _OBS_HTML, gather_state as _obs_gather
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
from infj_bot.core.config import DEFAULT_AUTHORIZED_TARGETS
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
  <title>INFJ Bot</title>
  <style>
    body { margin: 0; font-family: system-ui, sans-serif; background: #101418; color: #ecf2f0; }
    main { display: grid; grid-template-columns: 1fr 320px; min-height: 100vh; }
    section { padding: 18px; }
    #chat { display: flex; flex-direction: column; gap: 12px; }
    #messages { height: calc(100vh - 120px); overflow: auto; display: flex; flex-direction: column; gap: 10px; }
    .msg { padding: 10px 12px; border: 1px solid #2e3a40; border-radius: 8px; white-space: pre-wrap; }
    .user { background: #18232b; }
    .bot { background: #13211d; }
    form { display: flex; gap: 8px; }
    input, select, button, textarea { background: #151b20; color: #ecf2f0; border: 1px solid #334047; border-radius: 6px; padding: 9px; }
    input { flex: 1; }
    button { cursor: pointer; }
    aside { border-left: 1px solid #2e3a40; background: #0c1013; }
    .panel { margin-bottom: 16px; }
    .small { color: #9fb0ad; font-size: 13px; }
    #growthCard { border: 1px solid #2e3a40; border-radius: 8px; padding: 12px; background: #101820; }
    #growthAvatar { height: 112px; display: grid; place-items: center; border: 1px solid #31434a; border-radius: 8px; background: radial-gradient(circle at 50% 35%, #25443a, #101820 64%); overflow: hidden; }
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
    @media (max-width: 760px) { main { grid-template-columns: 1fr; } aside { border-left: 0; border-top: 1px solid #2e3a40; } }
  </style>
</head>
<body>
<main>
  <section id="chat">
    <div id="messages"></div>
    <form id="form">
      <input id="input" autocomplete="off" placeholder="Talk to the INFJ bot...">
      <button>Send</button>
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
          <option>coach</option><option>clarity</option><option>researcher</option><option>bughunter</option><option>quiet</option>
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
      <div class="panel">
        <label>Email</label><br>
        <input id="emailTo" placeholder="to" style="width:100%;margin-bottom:6px;">
        <input id="emailSubject" placeholder="subject" style="width:100%;margin-bottom:6px;">
        <textarea id="emailBody" rows="3" style="width:100%" placeholder="body"></textarea>
        <button id="sendEmail">Send</button>
        <pre id="emailResult" class="small"></pre>
      </div>
      <div class="panel">
        <a href="/observatory" target="_blank" style="display:block;text-align:center;padding:8px;background:#101820;border:1px solid #2e3a40;border-radius:6px;color:#66d19e;text-decoration:none;font-size:13px;">&#128302; Observatory — Watch DRIFT think</a>
      </div>
    </section>
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
  document.querySelector('#growthStage').textContent = data.stage + ' - ' + data.points + ' pts';
  document.querySelector('#growthFill').style.width = Math.round(data.progress * 100) + '%';
  document.querySelector('#growthDesc').textContent = data.description;
  document.querySelector('#growthStats').textContent =
    'memories: ' + data.stats.total_memories +
    '\nchats: ' + data.stats.interactions +
    '\nconcepts: ' + data.stats.concepts +
    '\nreflections: ' + data.stats.reflections;
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
document.querySelector('#sendEmail').onclick = async () => {
  const data = await post('/api/email', {
    to: document.querySelector('#emailTo').value,
    subject: document.querySelector('#emailSubject').value,
    body: document.querySelector('#emailBody').value
  });
  document.querySelector('#emailResult').textContent = data.sent ? 'Sent.' : 'Error: ' + (data.error || 'unknown');
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
app.config['SECRET_KEY'] = 'drift-secret-key'

socketio = SocketIO(
    app,
    async_mode='gevent', 
    cors_allowed_origins="*",
    websocket_compression=True
)

broadcast_interval = 0.35 
total_bytes_raw = 0
total_bytes_compressed = 0
cognitive_orchestrator = CognitiveOrchestrator()

# Sandbox / Trial Management
trial_sessions = {} # {session_id: start_time}

def is_trial_active(session_id):
    if not session_id or session_id not in trial_sessions:
        return False
    # 30 minute limit (1800 seconds)
    if time.time() - trial_sessions[session_id] > 1800:
        return False
    return True

@app.route('/trial')
def start_trial():
    import uuid
    session_id = str(uuid.uuid4())
    trial_sessions[session_id] = time.time()
    # Simple hack to inject the session into the frontend
    trial_html = INDEX_HTML.replace(
        "document.querySelector('#form').onsubmit",
        f"const DRIFT_SESSION_ID = '{session_id}';\n" +
        "document.querySelector('#form').onsubmit"
    ).replace(
        "async function post(path, body={}) {",
        "async function post(path, body={}) {\n  if(typeof DRIFT_SESSION_ID !== 'undefined') body.session_id = DRIFT_SESSION_ID;"
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
                delta['network_stats'] = {
                    'raw_kb': round(total_bytes_raw / 1024, 2),
                    'comp_kb': round(total_bytes_compressed / 1024, 2),
                    'interval_ms': int(broadcast_interval * 1000)
                }
                socketio.emit('observatory_delta', delta)
        except Exception as e:
            pass
        gevent.sleep(broadcast_interval)

threading.Thread(target=broadcast_observatory_state, daemon=True).start()

@socketio.on('latency_ping')
def handle_latency_ping(data):
    emit('latency_pong', {
        'server_time': time.time(),
        'client_timestamp': data.get('timestamp')
    })

@socketio.on('auto_adjust_rate')
def handle_adjust_rate(data):
    global broadcast_interval
    target_interval = data.get('interval', 0.35)
    broadcast_interval = max(0.2, min(target_interval, 1.5))

@app.route('/')
def index():
    return INDEX_HTML

@app.route('/api/growth', methods=['GET'])
def get_growth():
    return jsonify(growth_profile(memory, state.turns))

@app.route('/api/tags', methods=['GET'])
def ollama_tags():
    return jsonify({
        "models": [
            {
                "name": "infj_bot:latest",
                "model": "infj_bot:latest",
                "modified_at": "2023-11-04T14:56:49.277302595-07:00",
                "size": 7323310500,
                "digest": "9f438cb9cd581fc025612d27f7c1a6669ff83a8bb0ed86c94fcf4c5440555697"
            }
        ]
    })

@app.route('/api/chat', methods=['POST'])
def api_chat():
    payload = request.json
    
    # Check for trial session
    session_id = payload.get("session_id")
    if session_id and not is_trial_active(session_id):
        return jsonify({"error": "Trial session expired. Please start a new session at /trial"}), 403

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
        
        return jsonify({
            "model": payload.get("model", "infj_bot:latest"),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "message": {
                "role": "assistant",
                "content": reply_text
            },
            "done": True
        })
        
    # Standard INFJ Bot UI request
    message = payload.get("message", "")
    if isinstance(message, str):
        message = message.strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    return jsonify({"reply": chat_reply(message)})

@app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
def openai_chat_completions():
    if request.method == 'OPTIONS':
        return '', 200
        
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
                "message": {
                    "role": "assistant",
                    "content": reply_text
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }
    return jsonify(response)

@app.route('/api/command', methods=['POST'])
def api_command():
    payload = request.json
    reply = handle_command(
        payload.get("command", ""),
        payload.get("args", ""),
        state, brain, memory, history, goals_db, doc_store
    )
    return jsonify({"reply": reply})

@app.route('/api/email', methods=['POST'])
def api_email():
    # Email sending is not implemented; no send_email backend available.
    payload = request.json
    return jsonify({
        "sent": False,
        "error": "Email sending not implemented (no backend configured)."
    }), 501

@app.route('/observatory')
def observatory():
    try:
        with open("/home/crexs/templates/observatory.html", "r") as f:
            content = f.read()
        return render_template_string(content)
    except Exception as e:
        return str(e), 500

def main():
    print("🚀 DRIFT Web App: Gevent + Compression + Delta Logic Active")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()

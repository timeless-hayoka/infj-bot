import json
import sys as _sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path as _Path
import traceback

# Observatory integration — add hive_mind to path
_hive_path = str(_Path(__file__).resolve().parent / "hive_mind")
if _hive_path not in _sys.path:
    _sys.path.insert(0, _hive_path)
try:
    from observatory.server import INDEX_HTML as _OBS_HTML, gather_state as _obs_gather
    from drift_bridge import DriftBridge as _DriftBridge

    _obs_drift = _DriftBridge()
    _OBSERVATORY_ENABLED = True
except Exception:
    _OBSERVATORY_ENABLED = False

from brain import InfjBrain
from commands import BotState, handle_command
from growth import growth_profile
from history import ChatHistory
from memory import InfjMemory
from goals import GoalsDB
from config import DEFAULT_AUTHORIZED_TARGETS
from documents import DocumentStore
from prompt_builder import build_chat_prompt


brain = InfjBrain()
memory = InfjMemory()
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


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, content_type, body):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _json(self, payload, status=200):
        self._send(status, "application/json", json.dumps(payload))

    def do_GET(self):
        if self.path == "/":
            self._send(200, "text/html", INDEX_HTML)
        elif self.path == "/api/growth":
            self._json(growth_profile(memory, state.turns))
        elif self.path in ("/observatory", "/observatory/"):
            if not _OBSERVATORY_ENABLED:
                self._json({"error": "Observatory unavailable"}, 503)
                return
            self._send(200, "text/html; charset=utf-8", _OBS_HTML)
        elif self.path == "/observatory/api/state":
            if not _OBSERVATORY_ENABLED:
                self._json({"error": "Observatory unavailable"}, 503)
                return
            snap = _obs_gather(_obs_drift)
            self._send(200, "application/json", json.dumps(snap, default=str))
        elif self.path == "/observatory/api/stream":
            if not _OBSERVATORY_ENABLED:
                self._json({"error": "Observatory unavailable"}, 503)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                while True:
                    snap = _obs_gather(_obs_drift)
                    payload = json.dumps(snap, default=str)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self._json({"error": "not found"}, 404)

    def do_HEAD(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > _MAX_PAYLOAD:
                self._json({"error": "payload too large"}, 413)
                return
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/chat":
                message = payload.get("message", "").strip()
                if not message:
                    self._json({"error": "message is required"}, 400)
                    return
                self._json({"reply": chat_reply(message)})
            elif self.path == "/api/command":
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
                self._json({"reply": reply})
            elif self.path == "/api/email":
                from emailer import send_email

                result = send_email(
                    to=payload.get("to", ""),
                    subject=payload.get("subject", ""),
                    body=payload.get("body", ""),
                    html_body=payload.get("html_body"),
                )
                if result.get("ok"):
                    self._json({"sent": True})
                else:
                    self._json({"sent": False, "error": result.get("error")}, 500)
            else:
                self._json({"error": "not found"}, 404)
        except json.JSONDecodeError:
            self._json({"error": "invalid JSON"}, 400)
        except Exception as exc:
            traceback.print_exc()
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("INFJ bot web UI: http://127.0.0.1:8765")
    server.serve_forever()


if __name__ == "__main__":
    main()

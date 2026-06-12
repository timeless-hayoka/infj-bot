from gevent import monkey

monkey.patch_all()

import json
import time
from pathlib import Path

import gevent
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import threading
from drift.core.cognitive_orchestrator import CognitiveOrchestrator

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

from drift.core.brain import DriftBrain
from drift.core.commands import BotState, handle_command
from drift.core.plugins.growth import growth_profile
from drift.core.history import ChatHistory
from drift.core.memory import DriftMemory
from drift.core.plugins.goals import GoalsDB
from drift.core.config import DATA_DIR, DEFAULT_AUTHORIZED_TARGETS

STATE_ROOT = DATA_DIR
from drift.core.plugins.documents import DocumentStore
from drift.core.prompt_builder import build_chat_prompt


from drift.core.plugins.preferences import PreferenceStore
from drift.core.plugins.scheduler import TaskScheduler
from drift.core.plugins.self_eval import SelfEvaluator
from drift.core.gen_cache import DiskGenCache

SESSIONS_DIR = STATE_ROOT / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

sessions = {}
sessions_lock = threading.Lock()

class SessionResources:
    def __init__(self, session_id: str):
        self.session_id = session_id
        if session_id == "global":
            self.session_dir = STATE_ROOT / "global_session"
        else:
            self.session_dir = SESSIONS_DIR / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. State (isolated PreferenceStore and TaskScheduler)
        self.state = BotState(
            authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS),
            prefs=PreferenceStore(db_path=self.session_dir / "preferences.db"),
            scheduler=TaskScheduler(db_path=self.session_dir / "scheduler.db")
        )
        
        # 2. Memory
        self.memory = DriftMemory(
            persist_directory=str(self.session_dir / "memory")
        )
        
        # 3. Document Store
        self.doc_store = DocumentStore(
            persist_directory=str(self.session_dir / "chroma_db")
        )
        
        # 4. Goals DB
        self.goals_db = GoalsDB(
            db_path=self.session_dir / "goals.db"
        )
        
        # 5. History
        self.history = ChatHistory(
            path=self.session_dir / "history.jsonl"
        )
        
        # 6. Brain (with custom evaluator and disk cache)
        evaluator = SelfEvaluator(db_path=self.session_dir / "self_eval.db")
        try:
            disk_cache = DiskGenCache(
                path=self.session_dir / "drift_gen_cache.sqlite3"
            )
        except Exception:
            disk_cache = None
        self.brain = DriftBrain(evaluator=evaluator, disk_cache=disk_cache)
        
        self.last_accessed = time.time()
        
    def close(self):
        # Close disk cache connection to release file descriptors
        if hasattr(self.brain, "_disk_cache") and self.brain._disk_cache:
            try:
                self.brain._disk_cache.close()
            except Exception:
                pass


def get_session(session_id: str = None) -> SessionResources:
    if not session_id:
        session_id = "global"
    with sessions_lock:
        if session_id not in sessions:
            sessions[session_id] = SessionResources(session_id)
        else:
            sessions[session_id].last_accessed = time.time()
        return sessions[session_id]


def get_request_session_id():
    """Extracts session_id from JSON payload or cookie fallback."""
    session_id = None
    if request.is_json:
        try:
            payload = request.json or {}
            session_id = payload.get("session_id")
        except Exception:
            pass
    if not session_id:
        session_id = request.cookies.get("drift_session_id")
    return session_id


def prune_and_cleanup_sessions():
    """Prunes inactive in-memory sessions and cleans up old disk folders."""
    while True:
        try:
            now = time.time()
            # 1. Prune in-memory sessions (30 mins inactivity)
            with sessions_lock:
                inactive_keys = []
                for sid, sres in sessions.items():
                    if sid == "global":
                        continue
                    if now - sres.last_accessed > 1800:  # 30 mins
                        inactive_keys.append(sid)
                for sid in inactive_keys:
                    print(f"Pruning in-memory session: {sid}")
                    sres = sessions.pop(sid)
                    sres.close()
            
            # 2. Cleanup old session folders on disk (not accessed for over 7 days)
            if SESSIONS_DIR.exists():
                import shutil
                for p in SESSIONS_DIR.iterdir():
                    if p.is_dir():
                        with sessions_lock:
                            is_loaded = p.name in sessions
                        if not is_loaded:
                            try:
                                mtime = p.stat().st_mtime
                                for filepath in p.rglob("*"):
                                    if filepath.is_file():
                                        mtime = max(mtime, filepath.stat().st_mtime)
                                if now - mtime > 7 * 86400:
                                    print(f"Deleting expired session folder on disk: {p.name}")
                                    shutil.rmtree(p, ignore_errors=True)
                            except Exception:
                                pass
        except Exception as e:
            print(f"Error in pruning sessions: {e}")
        gevent.sleep(300)


def background_cognitive_loop():
    """Background loop to tick homeostasis, shadow, and embodiment for the active sessions."""
    from drift.core.being import get_being
    from drift.core.homeostasis import get_homeostasis
    from drift.core.shadow import get_shadow
    from drift.core.dii_tracker import get_dii_tracker
    from drift.core.global_workspace import get_workspace
    
    being = get_being()
    homeostasis = get_homeostasis()
    shadow = get_shadow()
    tracker = get_dii_tracker()
    workspace = get_workspace()
    
    while True:
        try:
            # Update embodiment / heartbeat / breath with some dynamic variations
            embodiment_plugin = cognitive_orchestrator.arch.get_plugin("embodiment")
            embodiment = embodiment_plugin.instance if embodiment_plugin else None
            if embodiment:
                import random
                bpm = getattr(embodiment, "heartbeat_bpm", 72)
                bpm += random.uniform(-1.5, 1.5)
                bpm = max(60, min(100, bpm))
                setattr(embodiment, "heartbeat_bpm", bpm)
                
                phase = getattr(embodiment, "breath_phase", "exhale")
                depth = getattr(embodiment, "breath_depth", 0.65)
                depth += random.uniform(-0.05, 0.05)
                depth = max(0.3, min(0.95, depth))
                setattr(embodiment, "breath_depth", depth)
                
                if random.random() < 0.2:
                    setattr(embodiment, "breath_phase", "inhale" if phase == "exhale" else "exhale")

            # Let homeostasis and shadow run their background cycles
            if hasattr(shadow, "background_tick"):
                shadow.background_tick(being=being)
            if hasattr(homeostasis, "background_cycle"):
                homeostasis.background_cycle(being=being)
                
            # Compute tracker metrics
            if hasattr(tracker, "compute"):
                tracker.compute(
                    being=being,
                    workspace=workspace,
                    homeostasis=homeostasis,
                    shadow=shadow,
                    orchestrator=cognitive_orchestrator,
                )
        except Exception as e:
            print(f"Error in background cognitive cycle: {e}")
        gevent.sleep(4.0)


_MAX_PAYLOAD = 1_048_576  # 1 MB


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DRIFT // CHROMATIC CORE</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=Rajdhani:wght@300;400;500;600;700&family=Fira+Code:wght@300;400;500&display=swap');
    
    :root {
        --c-blue: #00A3FF;
        --c-violet: #8F00FF;
        --c-red: #FF003D;
        --c-yellow: #FFD600;
        --bg-black: #030303;
        --glass: rgba(255, 255, 255, 0.03);
        --glass-border: rgba(255, 255, 255, 0.08);
        --text: #F0F0F0;
        --text-dim: #888;
    }

    * { box-sizing: border-box; }

    body { 
        margin: 0; 
        font-family: 'Rajdhani', sans-serif; 
        background: var(--bg-black); 
        color: var(--text); 
        overflow: hidden; 
        height: 100vh;
        /* Flowing Background */
        background: linear-gradient(-45deg, #001A33, #1A0033, #330008, #332B00);
        background-size: 400% 400%;
        animation: gradientFlow 15s ease infinite;
    }

    @keyframes gradientFlow {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    /* Overall Shine Overlay */
    body::after {
        content: '';
        position: absolute;
        top: -50%; left: -50%; width: 200%; height: 200%;
        background: linear-gradient(45deg, transparent 45%, rgba(255,255,255,0.03) 50%, transparent 55%);
        transform: rotate(30deg);
        animation: shineSweep 10s linear infinite;
        pointer-events: none;
        z-index: 100;
    }

    @keyframes shineSweep {
        0% { transform: translateX(-100%) rotate(30deg); }
        100% { transform: translateX(100%) rotate(30deg); }
    }

    main { 
        display: grid; 
        grid-template-columns: 1fr 380px; 
        height: 100vh; 
        padding: 20px;
        gap: 20px;
        position: relative;
        z-index: 10;
    }

    /* --- GLASS PANELS --- */
    .panel {
        background: var(--glass);
        backdrop-filter: blur(15px);
        -webkit-backdrop-filter: blur(15px);
        border: 1px solid var(--glass-border);
        border-radius: 12px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.8);
        display: flex;
        flex-direction: column;
        overflow: hidden;
        position: relative;
    }

    /* Chromatic Border Glow */
    .panel::before {
        content: '';
        position: absolute;
        inset: 0;
        border-radius: 12px;
        padding: 1px;
        background: linear-gradient(90deg, var(--c-blue), var(--c-violet), var(--c-red), var(--c-yellow));
        -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
        -webkit-mask-composite: xor;
        mask-composite: exclude;
        opacity: 0.3;
    }

    /* --- CHAT AREA --- */
    section#chat {
        padding: 30px;
    }

    header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 25px;
        padding-bottom: 15px;
        border-bottom: 1px solid var(--glass-border);
    }

    header h1 {
        font-family: 'Orbitron', sans-serif;
        font-size: 1.2rem;
        font-weight: 800;
        margin: 0;
        background: linear-gradient(90deg, var(--c-blue), var(--c-violet), var(--c-red), var(--c-yellow));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: 4px;
    }

    #messages { 
        flex: 1; 
        overflow-y: auto; 
        display: flex; 
        flex-direction: column; 
        gap: 20px; 
        padding-right: 15px;
        scroll-behavior: smooth;
    }

    #messages::-webkit-scrollbar { width: 4px; }
    #messages::-webkit-scrollbar-thumb { 
        background: linear-gradient(var(--c-blue), var(--c-violet));
        border-radius: 10px;
    }

    .msg { 
        padding: 16px 20px; 
        border-radius: 8px; 
        max-width: 80%;
        line-height: 1.6;
        font-size: 1rem;
        position: relative;
        animation: msgAppear 0.3s ease-out;
    }

    @keyframes msgAppear {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    .user { 
        align-self: flex-end; 
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: #fff;
    }

    .bot { 
        align-self: flex-start; 
        background: rgba(0, 163, 255, 0.03);
        border: 1px solid rgba(0, 163, 255, 0.2);
        box-shadow: 0 0 20px rgba(0, 163, 255, 0.05);
    }

    .bot-tag {
        font-family: 'Orbitron', sans-serif;
        font-size: 0.55rem;
        color: var(--c-blue);
        letter-spacing: 2px;
        margin-bottom: 8px;
        display: block;
        opacity: 0.8;
    }

    .input-area {
        margin-top: 25px;
    }

    form#form { 
        display: flex; 
        background: rgba(0, 0, 0, 0.3);
        border: 1px solid var(--glass-border);
        border-radius: 8px;
        padding: 5px;
        transition: all 0.3s;
    }

    form#form:focus-within {
        border-color: var(--c-blue);
        box-shadow: 0 0 15px rgba(0, 163, 255, 0.2);
    }

    input#input { 
        flex: 1; 
        background: transparent; 
        border: none; 
        color: #fff; 
        padding: 12px 15px; 
        font-family: 'Rajdhani', sans-serif;
        font-size: 1.1rem;
    }

    input#input:focus { outline: none; }

    button#send-btn { 
        background: linear-gradient(90deg, var(--c-blue), var(--c-violet));
        color: #fff; 
        border: none; 
        padding: 0 25px; 
        font-family: 'Orbitron', sans-serif; 
        font-weight: 700; 
        border-radius: 6px;
        cursor: pointer;
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 1px;
        transition: all 0.3s;
    }

    button#send-btn:hover { 
        filter: brightness(1.2);
        transform: scale(1.02);
    }

    /* --- SIDEBAR --- */
    aside {
        display: flex;
        flex-direction: column;
        gap: 20px;
    }

    .side-panel {
        flex: 1;
        padding: 24px;
        display: flex;
        flex-direction: column;
    }

    .label {
        font-family: 'Orbitron', sans-serif;
        font-size: 0.65rem;
        color: var(--text-dim);
        text-transform: uppercase;
        letter-spacing: 3px;
        margin-bottom: 20px;
        display: block;
    }

    /* Mood Visage (The Face) */
    #visageFrame {
        height: 200px;
        display: flex;
        justify-content: center;
        align-items: center;
        position: relative;
        margin-bottom: 20px;
    }

    .visage-orb {
        width: 120px; height: 120px;
        border-radius: 50%;
        position: relative;
        background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.1), transparent);
        box-shadow: inset 0 0 40px rgba(0,0,0,0.5);
        transition: all 1s ease;
    }

    .face {
        position: absolute;
        inset: 0;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        gap: 15px;
    }

    .eyes {
        display: flex;
        gap: 30px;
    }

    .eye {
        width: 12px; height: 12px;
        background: #fff;
        border-radius: 50%;
        box-shadow: 0 0 15px #fff;
        transition: all 0.5s ease;
    }

    .mouth {
        width: 40px; height: 4px;
        background: rgba(255,255,255,0.3);
        border-radius: 2px;
        transition: all 0.5s ease;
    }

    /* Stats Grid */
    .stats-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 15px;
        font-family: 'Fira Code', monospace;
        font-size: 0.65rem;
        color: var(--text-dim);
    }

    .stat-val { color: #fff; font-weight: 600; }

    .control-group {
        margin-top: auto;
        display: flex;
        flex-direction: column;
        gap: 10px;
    }

    select, textarea {
        width: 100%;
        background: rgba(0,0,0,0.4);
        border: 1px solid var(--glass-border);
        color: #fff;
        padding: 10px;
        border-radius: 6px;
        font-family: 'Rajdhani', sans-serif;
    }

    .btn-action {
        background: var(--glass);
        border: 1px solid var(--glass-border);
        color: #fff;
        padding: 10px;
        border-radius: 6px;
        font-family: 'Orbitron', sans-serif;
        font-size: 0.6rem;
        cursor: pointer;
        transition: all 0.2s;
    }

    .btn-action:hover {
        background: rgba(255,255,255,0.05);
        border-color: var(--c-blue);
    }

    #sysLog {
        font-family: 'Fira Code', monospace;
        font-size: 0.6rem;
        color: var(--c-blue);
        margin-top: 10px;
        opacity: 0.6;
    }

    @media (max-width: 1000px) {
        main { grid-template-columns: 1fr; }
        aside { display: none; }
    }
  </style>
</head>
<body>
<main>
  <section id="chat" class="panel">
    <header>
      <h1>DRIFT // NEURAL</h1>
      <div style="font-family:'Orbitron', sans-serif; font-size:0.6rem; color:var(--c-cyan);">CORE_STABILITY: NOMINAL</div>
    </header>

    <div id="messages">
        <!-- Messages Injected Here -->
    </div>

    <div class="input-area">
        <form id="form">
          <input id="input" autocomplete="off" placeholder="TRANSMIT TO COGNITIVE CORE..." autofocus>
          <button id="send-btn">SEND</button>
        </form>
    </div>
  </section>

  <aside>
    <div class="side-panel panel">
      <span class="label">NEURAL VISAGE</span>
      <div id="visageFrame">
          <div class="visage-orb" id="visageOrb">
              <div class="face">
                  <div class="eyes">
                      <div class="eye" id="eyeL"></div>
                      <div class="eye" id="eyeR"></div>
                  </div>
                  <div class="mouth" id="visageMouth"></div>
              </div>
          </div>
      </div>
      <div id="stageName" style="font-family:'Orbitron', sans-serif; font-weight:700; text-align:center; color:var(--c-blue); letter-spacing:2px; margin-bottom:5px;">INITIALIZING...</div>
      <div id="stageDesc" style="font-size:0.75rem; color:var(--text-dim); text-align:center; margin-bottom:20px;">Synchronizing with being state...</div>
      
      <div class="stats-grid">
          <div>MEMS: <span class="stat-val" id="stat-mems">0</span></div>
          <div>LEVEL: <span class="stat-val" id="stat-pts">0</span></div>
      </div>

      <div class="control-group">
          <label class="label" style="margin-bottom:10px;">COGNITIVE_MODE</label>
          <select id="modeSelect">
              <option>companion</option><option>engineer</option><option>critic</option>
              <option>coach</option><option>clarity</option><option>researcher</option>
          </select>
          <div style="display:flex; gap:8px;">
              <button id="statusBtn" class="btn-action" style="flex:1;">STATUS</button>
              <button id="reflectBtn" class="btn-action" style="flex:1;">REFLECT</button>
          </div>
          <div id="sysLog">Awaiting signal...</div>
      </div>
    </div>
    
    <div class="link-group">
        <a href="/observatory" target="_blank" class="btn-action" style="text-align:center; padding:15px; border-color:var(--c-violet); color:var(--c-violet);">OPEN_OBSERVATORY</a>
    </div>
  </aside>
</main>

<script>
const msgContainer = document.querySelector('#messages');
const visageOrb = document.querySelector('#visageOrb');
const eyeL = document.querySelector('#eyeL');
const eyeR = document.querySelector('#eyeR');
const mouth = document.querySelector('#visageMouth');

// Chat Scroll Fix
function scrollToBottom() {
    msgContainer.scrollTop = msgContainer.scrollHeight;
}

function addMsg(cls, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  if(cls === 'bot') {
      const tag = document.createElement('span');
      tag.className = 'bot-tag';
      tag.textContent = 'DRIFT // RESPONSE';
      div.appendChild(tag);
  }
  const content = document.createElement('div');
  content.textContent = text;
  div.appendChild(content);
  msgContainer.appendChild(div);
  
  // Force scroll after brief delay to ensure layout
  setTimeout(scrollToBottom, 50);
}

async function post(path, body={}) {
  const res = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  return await res.json();
}

// Mood Mapping to Visuals
const MOOD_MAP = {
    'curious': { color: 'var(--c-blue)', eyeScale: 1.2, mouthW: '30px', mouthH: '10px', mouthR: '50% 50% 0 0' },
    'playful': { color: 'var(--c-yellow)', eyeScale: 1.1, mouthW: '40px', mouthH: '15px', mouthR: '0 0 50% 50%' },
    'hopeful': { color: 'var(--c-blue)', eyeScale: 1.0, mouthW: '35px', mouthH: '8px', mouthR: '0 0 40% 40%' },
    'tired':   { color: '#555', eyeScale: 0.6, mouthW: '20px', mouthH: '2px', mouthR: '0' },
    'quiet':   { color: 'var(--c-violet)', eyeScale: 0.8, mouthW: '15px', mouthH: '2px', mouthR: '0' },
    'neutral': { color: '#888', eyeScale: 1.0, mouthW: '30px', mouthH: '3px', mouthR: '0' },
    'excited': { color: 'var(--c-red)', eyeScale: 1.3, mouthW: '45px', mouthH: '20px', mouthR: '0 0 50% 50%' },
    'contemplative': { color: 'var(--c-violet)', eyeScale: 0.9, mouthW: '25px', mouthH: '3px', mouthR: '5px' }
};

function updateVisage(mood) {
    const config = MOOD_MAP[mood] || MOOD_MAP['neutral'];
    visageOrb.style.boxShadow = `0 0 50px ${config.color}, inset 0 0 30px ${config.color}`;
    visageOrb.style.borderColor = config.color;
    
    eyeL.style.transform = `scale(${config.eyeScale})`;
    eyeR.style.transform = `scale(${config.eyeScale})`;
    eyeL.style.background = config.color;
    eyeR.style.background = config.color;
    eyeL.style.boxShadow = `0 0 15px ${config.color}`;
    eyeR.style.boxShadow = `0 0 15px ${config.color}`;
    
    mouth.style.width = config.mouthW;
    mouth.style.height = config.mouthH;
    mouth.style.borderRadius = config.mouthR;
    mouth.style.background = config.color;
    mouth.style.boxShadow = `0 0 10px ${config.color}`;
}

async function refresh() {
  const res = await fetch('/api/growth');
  const data = await res.json();
  
  document.querySelector('#stageName').textContent = data.stage;
  document.querySelector('#stageDesc').textContent = data.description;
  document.querySelector('#stat-mems').textContent = data.stats.total_memories;
  document.querySelector('#stat-pts').textContent = data.points;
  
  updateVisage(data.mood);
}

document.querySelector('#form').onsubmit = async (e) => {
  e.preventDefault();
  const input = document.querySelector('#input');
  const btn = document.querySelector('#send-btn');
  const text = input.value.trim();
  if (!text || btn.disabled) return;
  
  input.value = '';
  btn.disabled = true;
  btn.textContent = '...';
  addMsg('user', text);
  
  try {
    const data = await post('/api/chat', {message: text});
    if (data.reply) addMsg('bot', data.reply);
    else if (data.error) addMsg('bot', 'SIGNAL_INTERRUPTED: ' + data.error);
  } catch (err) {
    addMsg('bot', 'CONNECTION_ERROR: Core unresponsive.');
  } finally {
    btn.disabled = false;
    btn.textContent = 'SEND';
    refresh();
  }
};

document.querySelector('#modeSelect').onchange = async (e) => {
    const data = await post('/api/command', {command: 'mode', args: e.target.value});
    document.querySelector('#sysLog').textContent = data.reply;
};

document.querySelector('#statusBtn').onclick = async () => {
    const data = await post('/api/command', {command: 'status', args: ''});
    document.querySelector('#sysLog').textContent = data.reply;
};

document.querySelector('#reflectBtn').onclick = async () => {
    document.querySelector('#sysLog').textContent = "CONSULTING_INNER_VOICE...";
    const data = await post('/api/command', {command: 'reflect', args: ''});
    document.querySelector('#sysLog').textContent = data.reply;
    refresh();
};

// Periodic Refresh
setInterval(refresh, 5000);
refresh();

// Handle window resize scroll fix
window.addEventListener('resize', scrollToBottom);
</script>
</body>
</html>
"""


def chat_reply(message, session_res: SessionResources):
    prompt, emotion, dissonance = build_chat_prompt(
        message,
        session_res.state,
        session_res.memory,
        goals_db=session_res.goals_db,
        doc_store=session_res.doc_store,
        prefs=session_res.state.prefs,
    )
    output = session_res.brain.agent_turn(prompt, tools_enabled=True, raw_user_input=message)
    try:
        session_res.brain.evaluate_last(prompt, output)
    except Exception:
        pass
    importance = min(
        0.95, 0.45 + emotion["intensity"] * 0.3 + dissonance["score"] * 0.15
    )
    session_res.memory.save_interaction(
        message,
        output,
        mode=session_res.state.mode,
        emotion=emotion,
        importance=importance,
        dissonance=dissonance,
    )
    session_res.history.append(message, output, session_res.state.mode, emotion, dissonance)
    session_res.state.turns += 1
    return output


app = Flask(__name__)
import secrets
import os
app.config["SECRET_KEY"] = os.environ.get("DRIFT_SECRET_KEY", secrets.token_hex(32))

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


@app.route("/api/v1/system/governor-metrics", methods=["GET"])
def governor_metrics():
    session_id = get_request_session_id() or "global"
    session_res = get_session(session_id)
    brain = session_res.brain
    gov = getattr(brain, "_governor", None)
    if gov is None:
        return jsonify({
            "status": "error",
            "detail": "RateGovernor not initialized. Call self.init_governor() in DriftBrain.__init__."
        }), 503
    return jsonify({"status": "online", **gov.metrics_report()})


@app.route("/expo")
def start_expo():
    """Alias for /trial — clean URL for sharing demo sessions."""
    return start_trial()


@app.route("/trial")
def start_trial():
    import uuid
    from flask import make_response

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
    resp = make_response(trial_html)
    resp.set_cookie("drift_session_id", session_id, max_age=1800, httponly=True, samesite="Lax")
    return resp


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
    from flask import make_response
    session_id = request.cookies.get("drift_session_id")
    had_cookie = True
    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())
        had_cookie = False
    
    # Inject session_id into JS
    html = INDEX_HTML.replace(
        "document.querySelector('#form').onsubmit",
        f"const DRIFT_SESSION_ID = '{session_id}';\n"
        + "document.querySelector('#form').onsubmit",
    ).replace(
        "async function post(path, body={}) {",
        "async function post(path, body={}) {\n  if(typeof DRIFT_SESSION_ID !== 'undefined') body.session_id = DRIFT_SESSION_ID;",
    )
    
    resp = make_response(html)
    if not had_cookie:
        resp.set_cookie("drift_session_id", session_id, max_age=30*86400, httponly=True, samesite="Lax")
    return resp


@app.route("/api/growth", methods=["GET"])
def get_growth():
    session_id = get_request_session_id()
    session_res = get_session(session_id)
    return jsonify(growth_profile(session_res.memory, session_res.state.turns))


@app.route("/api/tags", methods=["GET"])
def ollama_tags():
    return jsonify(
        {
            "models": [
                {
                    "name": "drift:latest",
                    "model": "drift:latest",
                    "modified_at": "2023-11-04T14:56:49.277302595-07:00",
                    "size": 7323310500,
                    "digest": "9f438cb9cd581fc025612d27f7c1a6669ff83a8bb0ed86c94fcf4c5440555697",
                }
            ]
        }
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    payload = request.json or {}
    session_id = get_request_session_id()

    # Check for trial session
    if session_id and session_id in trial_sessions:
        if not is_trial_active(session_id):
            return jsonify(
                {"error": "Trial session expired. Please start a new session at /trial"}
            ), 403

    session_res = get_session(session_id)

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

        reply_text = chat_reply(user_message, session_res)

        return jsonify(
            {
                "model": payload.get("model", "drift:latest"),
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
    return jsonify({"reply": chat_reply(message, session_res)})


@app.route("/v1/chat/completions", methods=["POST", "OPTIONS"])
def openai_chat_completions():
    if request.method == "OPTIONS":
        return "", 200

    payload = request.json or {}
    session_id = get_request_session_id()

    # Check for trial session expiration
    if session_id and session_id in trial_sessions:
        if not is_trial_active(session_id):
            return jsonify(
                {"error": "Trial session expired. Please start a new session at /trial"}
            ), 403

    session_res = get_session(session_id)
    
    messages = payload.get("messages", [])

    # Extract the last user message
    user_message = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    if not user_message:
        return jsonify({"error": "No user message found"}), 400

    # Get reply from drift
    reply_text = chat_reply(user_message, session_res)

    # Format as OpenAI response
    import uuid

    response = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.get("model", "drift"),
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
    payload = request.json or {}
    session_id = get_request_session_id()
    session_res = get_session(session_id)
    
    reply = handle_command(
        payload.get("command", ""),
        payload.get("args", ""),
        session_res.state,
        session_res.brain,
        session_res.memory,
        session_res.history,
        session_res.goals_db,
        session_res.doc_store,
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
        from flask import make_response
        resp = make_response(content)
        resp.headers["Content-Type"] = "text/html"
        return resp
    except Exception:
        app.logger.exception("observatory render failed")
        return "Internal server error", 500


@app.route("/glyph")
@app.route("/phi-glyph")
def glyph():
    try:
        path = Path(__file__).resolve().parent / "templates" / "phi_glyph_system.html"
        if not path.exists():
            path = Path("/home/crexs/Downloads/PHI Glyph System.html")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        from flask import make_response
        resp = make_response(content)
        resp.headers["Content-Type"] = "text/html"
        return resp
    except Exception:
        app.logger.exception("glyph render failed")
        return "Internal server error", 500


def main():
    import os

    print("🚀 DRIFT Web App: Gevent + Compression + Delta Logic Active")
    
    # Spawn background greenlets for cognitive and session management
    gevent.spawn(background_cognitive_loop)
    gevent.spawn(prune_and_cleanup_sessions)
    
    port = int(os.getenv("PORT", 7860))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()

import os
import json
import hashlib
import subprocess
import sys
import signal
import time
import threading
import sqlite3
from functools import wraps
from flask import (Flask, request, redirect, url_for, render_template_string,
                   session, flash, send_from_directory, jsonify)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'ethbd-change-this-secret-key-2025')

# ---- Railway/Render-এ persistent disk থাকলে এখানে পাথ দিতে হবে ----
# উদাহরণ: Railway → /data, Render → /var/data
DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
LOGS_FOLDER = os.path.join(DATA_DIR, 'logs')
DB_PATH = os.path.join(DATA_DIR, 'ethbd.db')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

running_processes = {}
lock = threading.Lock()


# ================= database =================
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT NOT NULL,
        created  REAL NOT NULL
    );
    """)
    conn.commit()
    conn.close()


init_db()


# ================= helpers =================
def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if 'user' not in session:
            flash('Please login first.', 'error')
            return redirect(url_for('login'))
        return f(*a, **kw)
    return wrapper


def safe_filename(name):
    name = os.path.basename(name)
    return ''.join(c for c in name if c.isalnum() or c in '._- ')[:120] or 'file.py'


def get_log_path(user, filename):
    return os.path.join(LOGS_FOLDER, f"{user}__{safe_filename(filename)}.log")


def is_running(user, filename):
    with lock:
        proc = running_processes.get(user, {}).get(filename)
        if proc is None:
            return False
        if proc.poll() is not None:
            del running_processes[user][filename]
            return False
        return True


def start_process(user, filename):
    user_dir = os.path.join(UPLOAD_FOLDER, user)
    filepath = os.path.join(user_dir, filename)
    if not os.path.exists(filepath):
        return False, "File not found."

    if is_running(user, filename):
        stop_process(user, filename)

    log_path = get_log_path(user, filename)
    open(log_path, 'w').close()

    log_f = open(log_path, 'a', buffering=1, encoding='utf-8', errors='replace')
    log_f.write(f"🚀 [{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting: {filename}\n")
    log_f.write("─" * 50 + "\n")
    log_f.flush()

    # Render/Railway/Linux-এ preexec_fn কাজ করে, Windows-এ না
    kwargs = {}
    if os.name != 'nt':
        kwargs['preexec_fn'] = os.setsid

    try:
        proc = subprocess.Popen(
            [sys.executable, '-u', filepath],
            stdout=log_f,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            cwd=user_dir,
            env={**os.environ, 'PYTHONUNBUFFERED': '1'},
            **kwargs
        )
    except Exception as e:
        log_f.write(f"\n❌ Failed: {e}\n")
        log_f.close()
        return False, str(e)

    with lock:
        running_processes.setdefault(user, {})[filename] = proc

    def monitor():
        proc.wait()
        try:
            log_f.write(f"\n{'─' * 50}\n")
            log_f.write(f"✅ [{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                        f"Exited with code {proc.returncode}.\n")
            log_f.flush()
            log_f.close()
        except Exception:
            pass
        with lock:
            running_processes.get(user, {}).pop(filename, None)

    threading.Thread(target=monitor, daemon=True).start()
    return True, "Started."


def stop_process(user, filename):
    with lock:
        proc = running_processes.get(user, {}).get(filename)
    if proc is None or proc.poll() is not None:
        return False, "Not running."
    try:
        if os.name != 'nt':
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        else:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name != 'nt':
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                proc.kill()
        with lock:
            running_processes.get(user, {}).pop(filename, None)
        return True, "Stopped."
    except Exception as e:
        return False, str(e)


def auto_start_all():
    conn = get_db()
    rows = conn.execute("SELECT username FROM users").fetchall()
    conn.close()
    for row in rows:
        username = row['username']
        user_dir = os.path.join(UPLOAD_FOLDER, username)
        if not os.path.isdir(user_dir):
            continue
        for fname in os.listdir(user_dir):
            if fname.endswith('.py'):
                try:
                    start_process(username, fname)
                    print(f"   ▶ {username}/{fname}")
                except Exception as e:
                    print(f"   ⚠ {username}/{fname}: {e}")


# ================= base template =================
BASE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}ETHBD Hosting{% endblock %}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root{--bg:#0a0a0f;--card:#13131a;--card-hover:#1a1a24;--border:#26262f;
    --text:#e6e6ee;--muted:#8b8b9a;--accent:#7c5cff;--accent-hover:#6b4bff;
    --success:#22c55e;--error:#ef4444;--radius:12px;}
  *{box-sizing:border-box;margin:0;padding:0;}
  html,body{background:var(--bg);color:var(--text);
    font-family:'Inter',-apple-system,sans-serif;min-height:100vh;
    -webkit-font-smoothing:antialiased;}
  body{background:
      radial-gradient(circle at 20% 0%, rgba(124,92,255,.15), transparent 40%),
      radial-gradient(circle at 80% 100%, rgba(124,92,255,.10), transparent 40%),
      var(--bg);
    padding:16px;padding-bottom:60px;}
  .container{max-width:900px;margin:0 auto;}
  header{display:flex;justify-content:space-between;align-items:center;
    padding:14px 18px;background:rgba(19,19,26,.7);border:1px solid var(--border);
    border-radius:var(--radius);backdrop-filter:blur(12px);margin-bottom:24px;}
  .logo{font-weight:700;font-size:1.1rem;
    background:linear-gradient(90deg,#7c5cff,#b794ff);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;}
  nav a{color:var(--muted);text-decoration:none;margin-left:16px;
    font-size:.9rem;transition:color .2s;}
  nav a:hover{color:var(--text);}
  h1,h2,h3{letter-spacing:-.02em;font-weight:700;}
  h1{font-size:1.8rem;margin-bottom:8px;}
  h2{font-size:1.3rem;margin-bottom:16px;}
  p{color:var(--muted);line-height:1.6;}
  .card{background:var(--card);border:1px solid var(--border);
    border-radius:var(--radius);padding:24px;margin-bottom:20px;}
  label{display:block;font-size:.85rem;color:var(--muted);
    margin-bottom:6px;font-weight:500;}
  input[type=text],input[type=password],input[type=file]{
    width:100%;background:#0e0e14;border:1px solid var(--border);
    color:var(--text);padding:12px 14px;border-radius:10px;
    font-size:1rem;margin-bottom:16px;font-family:inherit;}
  input[type=file]{padding:10px;}
  input:focus{outline:none;border-color:var(--accent);
    box-shadow:0 0 0 3px rgba(124,92,255,.15);}
  .btn{display:inline-flex;align-items:center;justify-content:center;
    gap:8px;background:var(--accent);color:#fff;border:none;
    padding:12px 22px;border-radius:10px;font-size:.95rem;
    font-weight:600;cursor:pointer;font-family:inherit;width:100%;
    text-decoration:none;transition:background .2s,transform .1s;}
  .btn:hover{background:var(--accent-hover);}
  .btn:active{transform:scale(.98);}
  .btn:disabled{opacity:.55;cursor:not-allowed;}
  .btn-sm{width:auto;padding:8px 14px;font-size:.85rem;}
  .btn-ghost{background:transparent;border:1px solid var(--border);
    color:var(--text);}
  .btn-ghost:hover{background:var(--card-hover);}
  .btn-run{background:linear-gradient(90deg,#22c55e,#16a34a);}
  .btn-stop{background:linear-gradient(90deg,#ef4444,#dc2626);}
  .flash{padding:12px 16px;border-radius:10px;margin-bottom:16px;
    font-size:.9rem;border:1px solid;}
  .flash.success{background:rgba(34,197,94,.1);color:#86efac;
    border-color:rgba(34,197,94,.3);}
  .flash.error{background:rgba(239,68,68,.1);color:#fca5a5;
    border-color:rgba(239,68,68,.3);}
  .file-item{background:#0e0e14;border:1px solid var(--border);
    border-radius:10px;margin-bottom:14px;overflow:hidden;}
  .file-item.running{border-color:rgba(34,197,94,.35);}
  .file-header{display:flex;justify-content:space-between;align-items:center;
    gap:12px;padding:12px 14px;flex-wrap:wrap;}
  .file-name{font-family:'JetBrains Mono',monospace;font-size:.88rem;
    color:var(--text);word-break:break-all;flex:1;min-width:150px;
    display:flex;align-items:center;gap:8px;}
  .status-dot{width:9px;height:9px;border-radius:50%;background:#555;
    display:inline-block;flex-shrink:0;}
  .status-dot.running{background:#22c55e;
    box-shadow:0 0 10px rgba(34,197,94,.9);animation:pulse 1.4s infinite;}
  @keyframes pulse{0%,100%{opacity:1;}50%{opacity:.4;}}
  .file-actions{display:flex;gap:8px;flex-wrap:wrap;}
  .output-wrap{padding:0 14px 14px;}
  .output-box{background:#06060a;border:1px solid var(--border);
    border-radius:10px;padding:14px;
    font-family:'JetBrains Mono',monospace;font-size:.78rem;
    white-space:pre-wrap;word-break:break-word;
    height:300px;overflow-y:auto;color:#c9d1d9;line-height:1.55;}
  .output-box.error{color:#fca5a5;border-color:rgba(239,68,68,.4);}
  .output-head{display:flex;justify-content:space-between;align-items:center;
    padding:8px 0 6px;font-size:.72rem;color:var(--muted);
    text-transform:uppercase;letter-spacing:.08em;}
  .spinner{width:11px;height:11px;border:2px solid rgba(124,92,255,.25);
    border-top-color:#7c5cff;border-radius:50%;
    animation:spin .7s linear infinite;display:inline-block;
    vertical-align:middle;margin-right:6px;}
  @keyframes spin{to{transform:rotate(360deg);}}
  .center{text-align:center;}
  .hero{text-align:center;padding:32px 8px;}
  .hero h1{font-size:2rem;margin-bottom:12px;}
  .hero p{max-width:520px;margin:0 auto 24px;}
  .auth-link{color:var(--accent);text-decoration:none;font-weight:600;}
  .muted{color:var(--muted);font-size:.85rem;}
  .badge{display:inline-block;padding:3px 9px;border-radius:20px;
    font-size:.7rem;background:rgba(124,92,255,.15);color:#b794ff;
    border:1px solid rgba(124,92,255,.3);margin-left:6px;}
  @media (max-width:520px){
    h1{font-size:1.5rem;}.hero h1{font-size:1.6rem;}
    .card{padding:18px;}
    header{padding:12px 14px;}
    nav a{margin-left:12px;font-size:.82rem;}
    .file-header{flex-direction:column;align-items:stretch;}
    .file-actions{justify-content:stretch;}
    .file-actions .btn{flex:1;}
    .output-box{height:240px;font-size:.72rem;}
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo">⚡ ETHBD Hosting</div>
    <nav>
      {% if session.user %}
        <a href="{{ url_for('dashboard') }}">Dashboard</a>
        <a href="{{ url_for('logout') }}">Logout</a>
      {% else %}
        <a href="{{ url_for('login') }}">Login</a>
        <a href="{{ url_for('register') }}">Register</a>
      {% endif %}
    </nav>
  </header>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, msg in messages %}
      <div class="flash {{ category }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}
  {% block content %}{% endblock %}
</div>
</body>
</html>
"""

INDEX_PAGE = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="card hero">
  <h1>Host &amp; Run Python <span class="badge">24/7</span></h1>
  <p>Upload a Python file — it auto-starts instantly and runs 24/7. Watch live output. Works great on mobile.</p>
  <div style="display:flex;gap:10px;max-width:340px;margin:0 auto;">
    <a href="{{ url_for('register') }}" class="btn">Get Started</a>
    <a href="{{ url_for('login') }}" class="btn btn-ghost">Login</a>
  </div>
</div>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Welcome — ETHBD")

REGISTER_PAGE = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="card" style="max-width:420px;margin:0 auto;">
  <h2>Create Account 🚀</h2>
  <p class="muted" style="margin-bottom:20px;">Register once, start hosting 24/7.</p>
  <form method="post">
    <label>Username</label>
    <input type="text" name="username" placeholder="Username" required>
    <label>Password</label>
    <input type="password" name="password" placeholder="Password" required>
    <button class="btn" type="submit">Register</button>
  </form>
  <p class="muted center" style="margin-top:16px;">
    Already have an account? <a class="auth-link" href="{{ url_for('login') }}">Login</a>
  </p>
</div>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Register — ETHBD")

LOGIN_PAGE = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="card" style="max-width:420px;margin:0 auto;">
  <h2>Welcome Back 👋</h2>
  <p class="muted" style="margin-bottom:20px;">Login to access your files.</p>
  <form method="post">
    <label>Username</label>
    <input type="text" name="username" placeholder="Username" required>
    <label>Password</label>
    <input type="password" name="password" placeholder="Password" required>
    <button class="btn" type="submit">Login</button>
  </form>
  <p class="muted center" style="margin-top:16px;">
    No account? <a class="auth-link" href="{{ url_for('register') }}">Register</a>
  </p>
</div>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Login — ETHBD")

DASHBOARD_PAGE = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="card">
  <h2>Hello, {{ user }} 👋</h2>
  <p class="muted">Upload a <b>.py</b> file — it auto-starts and runs 24/7 until you press Stop.</p>
</div>

<div class="card">
  <h2>📤 Upload &amp; Auto-Run</h2>
  <form action="{{ url_for('upload_file') }}" method="post" enctype="multipart/form-data">
    <label>Choose a Python file (.py)</label>
    <input type="file" name="file" accept=".py" required>
    <button class="btn" type="submit">Upload &amp; Run</button>
  </form>
</div>

<div class="card">
  <h2>📂 Your Files ({{ files|length }})</h2>
  {% if files %}
    {% for file in files %}
      {% set running = file in running %}
      <div class="file-item {{ 'running' if running else '' }}"
           data-file="{{ file }}" data-running="{{ '1' if running else '0' }}">
        <div class="file-header">
          <div class="file-name">
            <span class="status-dot {{ 'running' if running else '' }}"></span>
            📄 {{ file }}
          </div>
          <div class="file-actions">
            <a href="{{ url_for('download_file', filename=file) }}"
               class="btn btn-ghost btn-sm">Download</a>
            {% if file.endswith('.py') %}
              <button class="btn btn-run btn-sm run-btn"
                      onclick="startFile('{{ file }}', this)"
                      {% if running %}style="display:none"{% endif %}>▶ Run</button>
              <button class="btn btn-stop btn-sm stop-btn"
                      onclick="stopFile('{{ file }}', this)"
                      {% if not running %}style="display:none"{% endif %}>■ Stop</button>
            {% endif %}
          </div>
        </div>
        <div class="output-wrap" style="display:none;">
          <div class="output-head">
            <span><span class="spinner"></span>Loading output...</span>
            <span class="muted"></span>
          </div>
          <div class="output-box"></div>
        </div>
      </div>
    {% endfor %}
  {% else %}
    <p class="muted">No files yet. Upload one above ☝️</p>
  {% endif %}
</div>

<script>
const pollers = {}, lastLog = {}, loading = {};

function escapeHtml(s){
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;',
    '>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function getItem(f){
  return document.querySelector('.file-item[data-file="'+CSS.escape(f)+'"]');
}

async function startFile(f, btn){
  btn.disabled = true; btn.textContent = '⏳ Starting...';
  try{
    const r = await fetch('/start/'+encodeURIComponent(f), {method:'POST'});
    const d = await r.json();
    if(d.ok){
      const item = getItem(f);
      item.dataset.running = '1';
      item.classList.add('running');
      item.querySelector('.status-dot').classList.add('running');
      item.querySelector('.run-btn').style.display = 'none';
      item.querySelector('.stop-btn').style.display = '';
      item.querySelector('.output-wrap').style.display = 'block';
      loading[f] = true;
      startPolling(f);
    } else alert('Error: ' + (d.error || 'unknown'));
  }catch(e){ alert(e); }
  finally{ btn.disabled = false; btn.textContent = '▶ Run'; }
}

async function stopFile(f, btn){
  btn.disabled = true; btn.textContent = '⏳ Stopping...';
  try{
    await fetch('/stop/'+encodeURIComponent(f), {method:'POST'});
    const item = getItem(f);
    item.dataset.running = '0';
    item.classList.remove('running');
    item.querySelector('.status-dot').classList.remove('running');
    item.querySelector('.run-btn').style.display = '';
    item.querySelector('.stop-btn').style.display = 'none';
    stopPolling(f); fetchLog(f);
  }catch(e){ alert(e); }
  finally{ btn.disabled = false; btn.textContent = '■ Stop'; }
}

async function fetchLog(f){
  try{
    const r = await fetch('/log/'+encodeURIComponent(f));
    const d = await r.json();
    const item = getItem(f);
    const head = item.querySelector('.output-head span:first-child');
    const timeEl = item.querySelector('.output-head span:last-child');
    const box = item.querySelector('.output-box');
    const log = d.log || '';
    const isRun = item.dataset.running === '1';

    if(loading[f] && log.length > 0) loading[f] = false;

    if(loading[f]) head.innerHTML = '<span class="spinner"></span>Loading output...';
    else if(isRun) head.innerHTML = '<span style="color:#22c55e">● Live Output</span>';
    else head.innerHTML = 'Final Output';
    timeEl.textContent = new Date().toLocaleTimeString();

    const hasError = /Traceback|Error:|Exception|❌/i.test(log);

    if(lastLog[f] !== log){
      lastLog[f] = log;
      const wasBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
      box.innerHTML = log ? escapeHtml(log)
        : '<span style="color:#555">Waiting for output...</span>';
      box.classList.toggle('error', hasError);
      if(wasBottom) box.scrollTop = box.scrollHeight;
    }
  }catch(e){}
}

function startPolling(f){
  if(pollers[f]) return;
  fetchLog(f);
  pollers[f] = setInterval(async () => {
    const item = getItem(f);
    if(!item){ clearInterval(pollers[f]); delete pollers[f]; return; }
    await fetchLog(f);
    try{
      const r = await fetch('/status/'+encodeURIComponent(f));
      const s = await r.json();
      if(!s.running && item.dataset.running === '1'){
        item.dataset.running = '0';
        item.classList.remove('running');
        item.querySelector('.status-dot').classList.remove('running');
        item.querySelector('.run-btn').style.display = '';
        item.querySelector('.stop-btn').style.display = 'none';
        clearInterval(pollers[f]); delete pollers[f];
        fetchLog(f);
      }
    }catch(e){}
  }, 1500);
}
function stopPolling(f){ if(pollers[f]){ clearInterval(pollers[f]); delete pollers[f]; } }

document.querySelectorAll('.file-item').forEach(item => {
  const w = item.querySelector('.output-wrap');
  if(w) w.style.display = 'block';
  startPolling(item.dataset.file);
});
window.addEventListener('beforeunload', () => {
  Object.values(pollers).forEach(clearInterval);
});
</script>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Dashboard — ETHBD")


# ================= routes =================
@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template_string(INDEX_PAGE)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form.get('username', '').strip()
        p = request.form.get('password', '')
        if not u or not p:
            flash('Username and password required.', 'error')
            return redirect(url_for('register'))
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (username, password, created) VALUES (?,?,?)",
                         (u, hash_password(p), time.time()))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            flash('Username already taken.', 'error')
            return redirect(url_for('register'))
        conn.close()
        os.makedirs(os.path.join(UPLOAD_FOLDER, u), exist_ok=True)
        session['user'] = u
        flash('Account created! 🎉', 'success')
        return redirect(url_for('dashboard'))
    return render_template_string(REGISTER_PAGE)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username', '').strip()
        p = request.form.get('password', '')
        conn = get_db()
        row = conn.execute("SELECT password FROM users WHERE username=?",
                           (u,)).fetchone()
        conn.close()
        if row and row['password'] == hash_password(p):
            session['user'] = u
            flash('Logged in! ✅', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template_string(LOGIN_PAGE)


@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('Logged out.', 'success')
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    user = session['user']
    user_dir = os.path.join(UPLOAD_FOLDER, user)
    os.makedirs(user_dir, exist_ok=True)
    files = sorted(os.listdir(user_dir))
    running = [f for f in files if is_running(user, f)]
    return render_template_string(DASHBOARD_PAGE,
                                  user=user, files=files, running=running)


@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    user = session['user']
    user_dir = os.path.join(UPLOAD_FOLDER, user)
    os.makedirs(user_dir, exist_ok=True)
    if 'file' in request.files:
        f = request.files['file']
        if f.filename:
            fname = safe_filename(f.filename)
            f.save(os.path.join(user_dir, fname))
            flash(f'Uploaded "{fname}" ✅', 'success')
            if fname.endswith('.py'):
                ok, msg = start_process(user, fname)
                if ok:
                    flash(f'Auto-started "{fname}" 🚀', 'success')
                else:
                    flash(f'Auto-start failed: {msg}', 'error')
    return redirect(url_for('dashboard'))


@app.route('/start/<filename>', methods=['POST'])
@login_required
def start_file(filename):
    user = session['user']
    filename = safe_filename(filename)
    if not filename.endswith('.py'):
        return jsonify({'ok': False, 'error': 'Only .py files.'})
    if is_running(user, filename):
        return jsonify({'ok': True})
    ok, msg = start_process(user, filename)
    return jsonify({'ok': ok, 'error': None if ok else msg})


@app.route('/stop/<filename>', methods=['POST'])
@login_required
def stop_file(filename):
    user = session['user']
    filename = safe_filename(filename)
    ok, msg = stop_process(user, filename)
    return jsonify({'ok': ok, 'msg': msg})


@app.route('/status/<filename>')
@login_required
def status_file(filename):
    user = session['user']
    return jsonify({'running': is_running(user, safe_filename(filename))})


@app.route('/log/<filename>')
@login_required
def log_file(filename):
    user = session['user']
    filename = safe_filename(filename)
    log_path = get_log_path(user, filename)
    if not os.path.exists(log_path):
        return jsonify({'log': ''})
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            data = f.read()
        if len(data) > 100_000:
            data = '...[truncated]...\n' + data[-100_000:]
        return jsonify({'log': data})
    except Exception as e:
        return jsonify({'log': '', 'error': str(e)})


@app.route('/files/<path:filename>')
@login_required
def download_file(filename):
    user = session['user']
    return send_from_directory(os.path.join(UPLOAD_FOLDER, user), filename)


# ---- auto-start on app boot (gunicorn-এর সাথে কাজ করে) ----
try:
    auto_start_all()
except Exception as e:
    print(f"Auto-start error: {e}")


if __name__ == '__main__':
    try:
        from pyngrok import ngrok
        url = ngrok.connect(5000).public_url
        print(f"\n🌍 {url}\n")
    except Exception:
        print("\n⚠ http://localhost:5000\n")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
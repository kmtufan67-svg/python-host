import os
import json
import hashlib
import subprocess
import sys
import signal
import time
import threading
from functools import wraps
from flask import (Flask, request, redirect, url_for, render_template_string,
                   session, flash, send_from_directory, jsonify)

app = Flask(__name__)
app.secret_key = 'ethbd-change-this-secret-key-2025'

UPLOAD_FOLDER = 'uploads'
USERS_FILE = 'users.json'
LOGS_FOLDER = 'logs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024

# চলমান প্রসেস ট্র্যাকিং: {username: {filename: Popen object}}
running_processes = {}
lock = threading.Lock()


# ---------------- helpers ----------------
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, 'r') as f:
        return json.load(f)


def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)


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


def get_log_path(user, filename):
    return os.path.join(LOGS_FOLDER, f"{user}__{filename}.log")


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
    """ব্যাকগ্রাউন্ডে ফাইল রান শুরু করে, লগ ফাইলে আউটপুট লেখে"""
    user_dir = os.path.join(UPLOAD_FOLDER, user)
    filepath = os.path.join(user_dir, filename)
    if not os.path.exists(filepath):
        return False, "File not found."

    log_path = get_log_path(user, filename)

    # পুরনো লগ মুছে ফেলি
    open(log_path, 'w').close()

    # Python unbuffered mode (-u) -> লাইভ আউটপুট পাব
    log_f = open(log_path, 'a', buffering=1)
    log_f.write(f"🚀 [{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting {filename}...\n\n")
    log_f.flush()

    try:
        proc = subprocess.Popen(
            [sys.executable, '-u', filepath],
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=user_dir,
            preexec_fn=os.setsid,   # আলাদা process group -> পুরো ট্রি kill করা যাবে
        )
    except Exception as e:
        log_f.write(f"\n❌ Failed to start: {e}\n")
        log_f.close()
        return False, str(e)

    with lock:
        running_processes.setdefault(user, {})[filename] = proc

    # মনিটর থ্রেড -> প্রসেস শেষ হলে লগে লেখে
    def monitor():
        proc.wait()
        try:
            log_f.write(f"\n\n✅ [{time.strftime('%Y-%m-%d %H:%M:%S')}] Process exited "
                        f"with code {proc.returncode}.\n")
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
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        with lock:
            running_processes.get(user, {}).pop(filename, None)
        return True, "Stopped."
    except Exception as e:
        return False, str(e)


# ---------------- base layout ----------------
BASE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}ETHBD Hosting{% endblock %}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#0a0a0f; --card:#13131a; --card-hover:#1a1a24; --border:#26262f;
    --text:#e6e6ee; --muted:#8b8b9a; --accent:#7c5cff; --accent-hover:#6b4bff;
    --success:#22c55e; --error:#ef4444; --radius:12px;
  }
  *{box-sizing:border-box;margin:0;padding:0;}
  html,body{background:var(--bg);color:var(--text);
    font-family:'Inter',-apple-system,sans-serif;min-height:100vh;
    -webkit-font-smoothing:antialiased;}
  body{
    background:
      radial-gradient(circle at 20% 0%, rgba(124,92,255,.15), transparent 40%),
      radial-gradient(circle at 80% 100%, rgba(124,92,255,.10), transparent 40%),
      var(--bg);
    padding:16px;padding-bottom:60px;
  }
  .container{max-width:900px;margin:0 auto;}
  header{display:flex;justify-content:space-between;align-items:center;
    padding:14px 18px;background:rgba(19,19,26,.7);border:1px solid var(--border);
    border-radius:var(--radius);backdrop-filter:blur(12px);margin-bottom:24px;}
  .logo{font-weight:700;font-size:1.1rem;
    background:linear-gradient(90deg,#7c5cff,#b794ff);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
    letter-spacing:-.02em;}
  nav a{color:var(--muted);text-decoration:none;margin-left:16px;
    font-size:.9rem;transition:color .2s;}
  nav a:hover{color:var(--text);}
  h1,h2,h3{letter-spacing:-.02em;font-weight:700;}
  h1{font-size:1.8rem;margin-bottom:8px;}
  h2{font-size:1.3rem;margin-bottom:16px;}
  p{color:var(--muted);line-height:1.6;}
  .card{background:var(--card);border:1px solid var(--border);
    border-radius:var(--radius);padding:24px;margin-bottom:20px;
    transition:border-color .2s;}
  .card:hover{border-color:#33333f;}
  label{display:block;font-size:.85rem;color:var(--muted);
    margin-bottom:6px;font-weight:500;}
  input[type=text],input[type=password],input[type=file]{
    width:100%;background:#0e0e14;border:1px solid var(--border);
    color:var(--text);padding:12px 14px;border-radius:10px;
    font-size:1rem;margin-bottom:16px;font-family:inherit;
    transition:border-color .2s;}
  input[type=file]{padding:10px;}
  input:focus{outline:none;border-color:var(--accent);
    box-shadow:0 0 0 3px rgba(124,92,255,.15);}
  .btn{display:inline-flex;align-items:center;justify-content:center;
    gap:8px;background:var(--accent);color:#fff;border:none;
    padding:12px 22px;border-radius:10px;font-size:.95rem;
    font-weight:600;cursor:pointer;transition:background .2s,transform .1s;
    font-family:inherit;width:100%;text-decoration:none;}
  .btn:hover{background:var(--accent-hover);}
  .btn:active{transform:scale(.98);}
  .btn:disabled{opacity:.6;cursor:not-allowed;}
  .btn-sm{width:auto;padding:8px 14px;font-size:.85rem;}
  .btn-ghost{background:transparent;border:1px solid var(--border);
    color:var(--text);}
  .btn-ghost:hover{background:var(--card-hover);border-color:#3a3a48;}
  .btn-run{background:linear-gradient(90deg,#22c55e,#16a34a);}
  .btn-run:hover{background:linear-gradient(90deg,#16a34a,#15803d);}
  .btn-stop{background:linear-gradient(90deg,#ef4444,#dc2626);}
  .btn-stop:hover{background:linear-gradient(90deg,#dc2626,#b91c1c);}
  .flash{padding:12px 16px;border-radius:10px;margin-bottom:16px;
    font-size:.9rem;border:1px solid;}
  .flash.success{background:rgba(34,197,94,.1);color:#86efac;
    border-color:rgba(34,197,94,.3);}
  .flash.error{background:rgba(239,68,68,.1);color:#fca5a5;
    border-color:rgba(239,68,68,.3);}
  .file-item{display:flex;justify-content:space-between;align-items:center;
    gap:12px;padding:12px 14px;background:#0e0e14;border:1px solid var(--border);
    border-radius:10px;margin-bottom:10px;flex-wrap:wrap;}
  .file-name{font-family:'JetBrains Mono',monospace;font-size:.88rem;
    color:var(--text);word-break:break-all;flex:1;min-width:150px;
    display:flex;align-items:center;gap:8px;}
  .status-dot{width:8px;height:8px;border-radius:50%;background:#555;
    display:inline-block;flex-shrink:0;}
  .status-dot.running{background:#22c55e;
    box-shadow:0 0 8px rgba(34,197,94,.8);
    animation:pulse 1.5s infinite;}
  @keyframes pulse{0%,100%{opacity:1;}50%{opacity:.4;}}
  .file-actions{display:flex;gap:8px;flex-wrap:wrap;}
  .output-box{background:#08080c;border:1px solid var(--border);
    border-radius:10px;padding:14px;margin-top:12px;
    font-family:'JetBrains Mono',monospace;font-size:.8rem;
    white-space:pre-wrap;word-break:break-word;max-height:340px;
    overflow-y:auto;color:#c9d1d9;width:100%;}
  .output-box.error{color:#fca5a5;border-color:rgba(239,68,68,.3);}
  .output-box .label{color:var(--muted);font-size:.7rem;
    text-transform:uppercase;letter-spacing:.08em;display:block;
    margin-bottom:6px;}
  .center{text-align:center;}
  .hero{text-align:center;padding:32px 8px;}
  .hero h1{font-size:2rem;margin-bottom:12px;}
  .hero p{max-width:500px;margin:0 auto 24px;}
  .auth-link{color:var(--accent);text-decoration:none;font-weight:600;}
  .auth-link:hover{text-decoration:underline;}
  .muted{color:var(--muted);font-size:.85rem;}
  .badge{display:inline-block;padding:3px 9px;border-radius:20px;
    font-size:.7rem;background:rgba(124,92,255,.15);color:#b794ff;
    border:1px solid rgba(124,92,255,.3);margin-left:6px;}
  @media (max-width:520px){
    h1{font-size:1.5rem;}
    .hero h1{font-size:1.6rem;}
    .card{padding:18px;}
    header{padding:12px 14px;}
    nav a{margin-left:12px;font-size:.82rem;}
    .file-item{flex-direction:column;align-items:stretch;}
    .file-actions{justify-content:stretch;}
    .file-actions .btn{flex:1;}
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


# ---------------- pages ----------------
INDEX_PAGE = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="card hero">
  <h1>Host &amp; Run Python <span class="badge">Premium</span></h1>
  <p>Upload Python files, run them forever in the background, watch live output. Works great on mobile.</p>
  <div style="display:flex;gap:10px;max-width:340px;margin:0 auto;">
    <a href="{{ url_for('register') }}" class="btn">Get Started</a>
    <a href="{{ url_for('login') }}" class="btn btn-ghost">Login</a>
  </div>
</div>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Welcome — ETHBD Hosting")


REGISTER_PAGE = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="card" style="max-width:420px;margin:0 auto;">
  <h2>Create Account 🚀</h2>
  <p class="muted" style="margin-bottom:20px;">Register once and start hosting your Python files.</p>
  <form method="post">
    <label>Username</label>
    <input type="text" name="username" placeholder="Choose a username" required autocomplete="username">
    <label>Password</label>
    <input type="password" name="password" placeholder="Choose a password" required autocomplete="new-password">
    <button class="btn" type="submit">Register</button>
  </form>
  <p class="muted center" style="margin-top:16px;">
    Already have an account? <a class="auth-link" href="{{ url_for('login') }}">Login</a>
  </p>
</div>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Register — ETHBD Hosting")


LOGIN_PAGE = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="card" style="max-width:420px;margin:0 auto;">
  <h2>Welcome Back 👋</h2>
  <p class="muted" style="margin-bottom:20px;">Login to access your hosted files.</p>
  <form method="post">
    <label>Username</label>
    <input type="text" name="username" placeholder="Your username" required autocomplete="username">
    <label>Password</label>
    <input type="password" name="password" placeholder="Your password" required autocomplete="current-password">
    <button class="btn" type="submit">Login</button>
  </form>
  <p class="muted center" style="margin-top:16px;">
    No account? <a class="auth-link" href="{{ url_for('register') }}">Register</a>
  </p>
</div>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Login — ETHBD Hosting")


DASHBOARD_PAGE = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="card">
  <h2>Hello, {{ user }} 👋</h2>
  <p class="muted">Upload, run, and manage your Python files. Processes run forever until you stop them.</p>
</div>

<div class="card">
  <h2>📤 Upload File</h2>
  <form action="{{ url_for('upload_file') }}" method="post" enctype="multipart/form-data">
    <label>Choose a file (max 20MB)</label>
    <input type="file" name="file" required>
    <button class="btn" type="submit">Upload</button>
  </form>
</div>

<div class="card">
  <h2>📂 Your Files ({{ files|length }})</h2>
  {% if files %}
    {% for file in files %}
      {% set running = file in running %}
      <div class="file-item" data-file="{{ file }}" data-running="{{ '1' if running else '0' }}">
        <div class="file-name">
          <span class="status-dot {{ 'running' if running else '' }}"></span>
          📄 {{ file }}
        </div>
        <div class="file-actions">
          <a href="{{ url_for('download_file', filename=file) }}" class="btn btn-ghost btn-sm">Download</a>
          {% if file.endswith('.py') %}
            <button class="btn btn-run btn-sm run-btn" onclick="startFile('{{ file }}', this)"
                    {% if running %}style="display:none"{% endif %}>▶ Run</button>
            <button class="btn btn-stop btn-sm stop-btn" onclick="stopFile('{{ file }}', this)"
                    {% if not running %}style="display:none"{% endif %}>■ Stop</button>
            <button class="btn btn-ghost btn-sm" onclick="toggleLog('{{ file }}', this)">📜 Log</button>
          {% endif %}
        </div>
        <div class="output-box" style="display:none;">
          <span class="label">Loading...</span>
        </div>
      </div>
    {% endfor %}
  {% else %}
    <p class="muted">No files uploaded yet. Upload your first file above ☝️</p>
  {% endif %}
</div>

<script>
const pollers = {};

function escapeHtml(s){
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function getItem(filename){
  return document.querySelector('.file-item[data-file="' + CSS.escape(filename) + '"]');
}

async function startFile(filename, btn){
  btn.disabled = true; btn.textContent = '⏳ Starting...';
  try{
    const res = await fetch('/start/' + encodeURIComponent(filename), {method:'POST'});
    const data = await res.json();
    if(data.ok){
      const item = getItem(filename);
      item.dataset.running = '1';
      item.querySelector('.status-dot').classList.add('running');
      item.querySelector('.run-btn').style.display = 'none';
      item.querySelector('.stop-btn').style.display = '';
      const box = item.querySelector('.output-box');
      box.style.display = 'block';
      startPolling(filename);
    } else {
      alert('Error: ' + (data.error || 'unknown'));
    }
  }catch(e){ alert('Error: ' + e); }
  finally{ btn.disabled = false; btn.textContent = '▶ Run'; }
}

async function stopFile(filename, btn){
  btn.disabled = true; btn.textContent = '⏳ Stopping...';
  try{
    const res = await fetch('/stop/' + encodeURIComponent(filename), {method:'POST'});
    const data = await res.json();
    const item = getItem(filename);
    item.dataset.running = '0';
    item.querySelector('.status-dot').classList.remove('running');
    item.querySelector('.run-btn').style.display = '';
    item.querySelector('.stop-btn').style.display = 'none';
  }catch(e){ alert('Error: ' + e); }
  finally{ btn.disabled = false; btn.textContent = '■ Stop'; }
}

async function fetchLog(filename){
  try{
    const res = await fetch('/log/' + encodeURIComponent(filename));
    const data = await res.json();
    const item = getItem(filename);
    const box = item.querySelector('.output-box');
    const wasBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    box.innerHTML = '<span class="label">Live Output' +
      (item.dataset.running === '1' ? ' ● Running' : '') + '</span>' +
      (data.log ? escapeHtml(data.log) : '<span style="color:#555">(no output yet)</span>');
    if(wasBottom) box.scrollTop = box.scrollHeight;
  }catch(e){}
}

function startPolling(filename){
  if(pollers[filename]) return;
  fetchLog(filename);
  pollers[filename] = setInterval(async () => {
    const item = getItem(filename);
    if(!item) { clearInterval(pollers[filename]); delete pollers[filename]; return; }
    if(item.dataset.running !== '1' && item.querySelector('.output-box').style.display === 'none'){
      clearInterval(pollers[filename]); delete pollers[filename]; return;
    }
    await fetchLog(filename);
    // স্টেটাস চেক
    try{
      const r = await fetch('/status/' + encodeURIComponent(filename));
      const s = await r.json();
      if(!s.running && item.dataset.running === '1'){
        item.dataset.running = '0';
        item.querySelector('.status-dot').classList.remove('running');
        item.querySelector('.run-btn').style.display = '';
        item.querySelector('.stop-btn').style.display = 'none';
      }
    }catch(e){}
  }, 1500);
}

function toggleLog(filename, btn){
  const item = getItem(filename);
  const box = item.querySelector('.output-box');
  if(box.style.display === 'none'){
    box.style.display = 'block';
    startPolling(filename);
  } else {
    box.style.display = 'none';
  }
}

// পেজ লোডে চলমান সব ফাইলের পোলিং শুরু
document.querySelectorAll('.file-item[data-running="1"]').forEach(item => {
  item.querySelector('.output-box').style.display = 'block';
  startPolling(item.dataset.file);
});

// পেজ বন্ধ হলে পোলিং বন্ধ
window.addEventListener('beforeunload', () => {
  Object.values(pollers).forEach(clearInterval);
});
</script>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Dashboard — ETHBD Hosting")


# ---------------- routes ----------------
@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template_string(INDEX_PAGE)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('Username and password required.', 'error')
            return redirect(url_for('register'))
        users = load_users()
        if username in users:
            flash('Username already taken.', 'error')
            return redirect(url_for('register'))
        users[username] = {'password': hash_password(password)}
        save_users(users)
        os.makedirs(os.path.join(UPLOAD_FOLDER, username), exist_ok=True)
        session['user'] = username
        flash('Account created successfully! 🎉', 'success')
        return redirect(url_for('dashboard'))
    return render_template_string(REGISTER_PAGE)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        users = load_users()
        if username in users and users[username]['password'] == hash_password(password):
            session['user'] = username
            flash('Logged in successfully! ✅', 'success')
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
    files = os.listdir(user_dir)
    running = [f for f in files if is_running(user, f)]
    return render_template_string(DASHBOARD_PAGE, user=user, files=files, running=running)


@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    user = session['user']
    user_dir = os.path.join(UPLOAD_FOLDER, user)
    os.makedirs(user_dir, exist_ok=True)
    if 'file' in request.files:
        file = request.files['file']
        if file.filename:
            file.save(os.path.join(user_dir, file.filename))
            flash(f'File "{file.filename}" uploaded ✅', 'success')
    return redirect(url_for('dashboard'))


@app.route('/start/<filename>', methods=['POST'])
@login_required
def start_file(filename):
    user = session['user']
    if not filename.endswith('.py'):
        return jsonify({'ok': False, 'error': 'Only .py files can be executed.'})
    if is_running(user, filename):
        return jsonify({'ok': True, 'msg': 'Already running.'})
    ok, msg = start_process(user, filename)
    return jsonify({'ok': ok, 'error': None if ok else msg})


@app.route('/stop/<filename>', methods=['POST'])
@login_required
def stop_file(filename):
    user = session['user']
    ok, msg = stop_process(user, filename)
    return jsonify({'ok': ok, 'msg': msg})


@app.route('/status/<filename>')
@login_required
def status_file(filename):
    user = session['user']
    return jsonify({'running': is_running(user, filename)})


@app.route('/log/<filename>')
@login_required
def log_file(filename):
    user = session['user']
    # path traversal protection
    if '/' in filename or '\\' in filename or '..' in filename:
        return jsonify({'log': '', 'error': 'Invalid filename'})
    log_path = get_log_path(user, filename)
    if not os.path.exists(log_path):
        return jsonify({'log': ''})
    try:
        with open(log_path, 'r', errors='replace') as f:
            data = f.read()
        # শেষ 50KB দেখাই (বড় লগে ব্রাউজার যেন আটকে না যায়)
        if len(data) > 50_000:
            data = '...[truncated]...\n' + data[-50_000:]
        return jsonify({'log': data})
    except Exception as e:
        return jsonify({'log': '', 'error': str(e)})


@app.route('/files/<path:filename>')
@login_required
def download_file(filename):
    user = session['user']
    return send_from_directory(os.path.join(UPLOAD_FOLDER, user), filename)


# ---------------- run ----------------
if __name__ == '__main__':
    try:
        from pyngrok import ngrok
        public_url = ngrok.connect(5000).public_url
        print(f"\n🌍 Public URL: {public_url}\n")
    except Exception as e:
        print(f"\n⚠ ngrok চালু হয়নি ({e}). লোকাল: http://localhost:5000\n")

    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
# ============================================================
# 🔮 AUTO PACKAGE INSTALLER (Termux Magic Code)
# Automatically installs missing packages — no errors
# ============================================================
import subprocess
import sys
import importlib

REQUIRED_PACKAGES = {
    "flask": "flask",
    "requests": "requests",
    "pyngrok": "pyngrok",
}

def _install_package(pip_name):
    try:
        print(f"📦 Installing missing package: {pip_name} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--disable-pip-version-check", pip_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        print(f"✅ Installed: {pip_name}")
        return True
    except Exception as e:
        print(f"⚠️ Could not install {pip_name}: {e}")
        return False

def _ensure_all_packages():
    for module_name, pip_name in REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(module_name)
        except ImportError:
            _install_package(pip_name)

_ensure_all_packages()
# ============================================================

import os
import io
import re
import json
import time
import signal
import sqlite3
import hashlib
import secrets
import threading
import subprocess as _sp
import sys
import random
import shutil
import requests
from functools import wraps
from flask import (Flask, request, redirect, url_for, render_template_string,
                   session, flash, send_from_directory, jsonify, send_file)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
LOGS_FOLDER = os.path.join(DATA_DIR, 'logs')
DB_PATH = os.path.join(DATA_DIR, 'ethbd.db')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

ADMIN_USER = os.environ.get('ADMIN_USER', 'M1NX')

# ============ TELEGRAM CONTACT ============
TELEGRAM_HANDLE = "M1NXGAMINGVIP1"
TELEGRAM_URL = f"https://t.me/{TELEGRAM_HANDLE}"

# ============ AI CONFIG ============
AI_API_KEY = os.environ.get('AI_API_KEY', "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")
AI_API_URL = "https://api.groq.com/openai/v1/chat/completions"
AI_MODEL   = "llama-3.3-70b-versatile"

# ============ ADS (default 3 ads) ============
ADS_JSON = os.environ.get('ADS_JSON', json.dumps([
    {
        "text": "🚀 <b>ETHBD Hosting</b> — Host your Python bot 24/7, absolutely free!",
        "url": "https://example.com"
    },
    {
        "text": "⚡ <b>Need a VPS?</b> Get 50% off your first month with code <code>ETHBD50</code>",
        "url": "https://example.com/vps"
    },
    {
        "text": "💎 <b>Upgrade to Pro</b> — Unlimited files, priority support, custom domains!",
        "url": "https://example.com/pro"
    }
]))

running_processes = {}
lock = threading.Lock()


# ==================== DATABASE ====================
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        username  TEXT PRIMARY KEY,
        password  TEXT NOT NULL,
        created   REAL NOT NULL,
        last_login REAL,
        is_admin  INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS files (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        username  TEXT NOT NULL,
        filename  TEXT NOT NULL,
        size      INTEGER,
        uploaded  REAL,
        UNIQUE(username, filename)
    );
    CREATE TABLE IF NOT EXISTS activity (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        username  TEXT,
        action    TEXT,
        detail    TEXT,
        ts        REAL
    );
    """)
    conn.commit()
    conn.close()


init_db()


# ==================== HELPERS ====================
def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()


def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if 'user' not in session:
            flash('Please login first.', 'error')
            return redirect(url_for('login'))
        return f(*a, **kw)
    return w


def admin_required(f):
    @wraps(f)
    def w(*a, **kw):
        if 'user' not in session:
            return redirect(url_for('admin_login'))
        conn = get_db()
        row = conn.execute("SELECT is_admin FROM users WHERE username=?",
                           (session['user'],)).fetchone()
        conn.close()
        if not row or not row['is_admin']:
            flash('Admin access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*a, **kw)
    return w


def safe_filename(name):
    name = os.path.basename(name)
    return ''.join(c for c in name if c.isalnum() or c in '._- ')[:120] or 'file.py'


def get_log_path(user, filename):
    return os.path.join(LOGS_FOLDER, f"{user}__{safe_filename(filename)}.log")


def log_activity(user, action, detail=''):
    try:
        conn = get_db()
        conn.execute("INSERT INTO activity (username, action, detail, ts) VALUES (?,?,?,?)",
                     (user, action, detail, time.time()))
        conn.commit()
        conn.close()
    except Exception:
        pass


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

    kwargs = {}
    if os.name != 'nt':
        kwargs['preexec_fn'] = os.setsid

    try:
        proc = _sp.Popen(
            [sys.executable, '-u', filepath],
            stdout=log_f, stderr=_sp.STDOUT, stdin=_sp.DEVNULL,
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
            log_f.write(f"✅ Exited with code {proc.returncode}.\n")
            log_f.flush(); log_f.close()
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
        except _sp.TimeoutExpired:
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
        u = row['username']
        d = os.path.join(UPLOAD_FOLDER, u)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.endswith('.py'):
                try:
                    start_process(u, f)
                    print(f"   ▴ {u}/{f}")
                except Exception as e:
                    print(f"   ⚠ {u}/{f}: {e}")


def detect_error(log):
    if not log:
        return False
    patterns = [
        r'Traceback \(most recent call last\)',
        r'^\s*\w*(Error|Exception)\s*:',
        r'SyntaxError',
        r'IndentationError',
        r'ModuleNotFoundError',
        r'ImportError',
        r'NameError',
        r'TypeError',
        r'ValueError',
        r'ZeroDivisionError',
        r'KeyError',
        r'IndexError',
        r'AttributeError',
        r'FileNotFoundError',
        r'❌',
    ]
    return any(re.search(p, log, re.MULTILINE | re.IGNORECASE) for p in patterns)


# ==================== AI ERROR FIX ====================
AI_SYSTEM_PROMPT = """You are an expert Python debugger.
The user gives you Python source code and its runtime error output.
Your job:
1. Fix the code so it runs without errors.
2. Keep the original intent and behavior.
3. Return ONLY a JSON object with keys:
   - "explanation": short English explanation of what was wrong and what you fixed (max 2 sentences).
   - "fixed_code": the entire corrected Python code as a string.
Do NOT wrap the response in markdown fences. Return pure JSON only."""


def ai_fix_code(code, error_output):
    start = time.time()
    if not AI_API_KEY:
        time.sleep(1.5)
        return demo_fix(code, error_output), \
               "Demo fix (no AI key configured). Added basic guards.", \
               time.time() - start

    user_msg = f"CODE:\n```python\n{code}\n```\n\nERROR:\n```\n{error_output}\n```\n\nReturn JSON."
    try:
        r = requests.post(
            AI_API_URL,
            headers={'Authorization': f'Bearer {AI_API_KEY}',
                     'Content-Type': 'application/json'},
            json={
                'model': AI_MODEL,
                'messages': [
                    {'role': 'system', 'content': AI_SYSTEM_PROMPT},
                    {'role': 'user', 'content': user_msg}
                ],
                'temperature': 0.2,
            },
            timeout=60
        )
        r.raise_for_status()
        content = r.json()['choices'][0]['message']['content'].strip()
        content = re.sub(r'^```(?:json)?|```$', '', content, flags=re.MULTILINE).strip()
        data = json.loads(content)
        return data.get('fixed_code', code), \
               data.get('explanation', 'AI fix applied.'), \
               time.time() - start
    except Exception as e:
        return code, f"AI fix failed: {e}", time.time() - start


def demo_fix(code, error_output):
    fixed = code
    if 'NameError' in error_output:
        m = re.search(r"name '(\w+)' is not defined", error_output)
        if m:
            name = m.group(1)
            if name == 'random':
                fixed = "import random\n" + fixed
            elif name == 'time':
                fixed = "import time\n" + fixed
            elif name == 'os':
                fixed = "import os\n" + fixed
            elif name == 'sys':
                fixed = "import sys\n" + fixed
            elif name == 'math':
                fixed = "import math\n" + fixed
    if 'ZeroDivisionError' in error_output:
        fixed = re.sub(r'(\w+)\s*/\s*(\w+)',
                       r'(\1 / \2 if \2 != 0 else 0)', fixed)
    fixed = re.sub(r'^(\s*)print\s+([^\(].*)$',
                   r'\1print(\2)', fixed, flags=re.MULTILINE)
    return fixed


# ==================== HTML BASE ====================
BASE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}ETHBD Hosting{% endblock %}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root{--bg:#0a0a0f;--card:#13131a;--card-hover:#1a1a24;--border:#26262f;
    --text:#e6e6ee;--muted:#8b8b9a;--accent:#7c5cff;--accent-hover:#6b4bff;
    --success:#22c55e;--error:#ef4444;--warn:#f59e0b;--radius:12px;}
  *{box-sizing:border-box;margin:0;padding:0;}
  html,body{background:var(--bg);color:var(--text);
    font-family:'Inter',-apple-system,sans-serif;min-height:100vh;
    -webkit-font-smoothing:antialiased;}
  body{background:
      radial-gradient(circle at 20% 0%, rgba(124,92,255,.15), transparent 40%),
      radial-gradient(circle at 80% 100%, rgba(124,92,255,.10), transparent 40%),
      var(--bg);padding:16px;padding-bottom:100px;}
  .container{max-width:1100px;margin:0 auto;}
  header{display:flex;justify-content:space-between;align-items:center;
    padding:14px 18px;background:rgba(19,19,26,.75);border:1px solid var(--border);
    border-radius:var(--radius);backdrop-filter:blur(12px);margin-bottom:24px;
    position:sticky;top:8px;z-index:100;}
  .logo{font-weight:800;font-size:1.05rem;
    background:linear-gradient(90deg,#7c5cff,#b794ff);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
    text-decoration:none;display:flex;align-items:center;gap:6px;}
  .nav-wrap{display:flex;align-items:center;gap:12px;}
  .nav-toggle{background:transparent;border:1px solid var(--border);
    color:var(--text);width:38px;height:38px;border-radius:10px;
    cursor:pointer;font-size:1.1rem;display:none;}
  .nav-links{display:flex;align-items:center;gap:4px;}
  .nav-links a{color:var(--muted);text-decoration:none;padding:8px 12px;
    font-size:.88rem;border-radius:8px;transition:all .2s;white-space:nowrap;}
  .nav-links a:hover{color:var(--text);background:var(--card-hover);}
  .nav-links a.active{color:#fff;background:rgba(124,92,255,.15);}
  h1,h2,h3{letter-spacing:-.02em;font-weight:700;}
  h1{font-size:1.8rem;margin-bottom:8px;}
  h2{font-size:1.25rem;margin-bottom:16px;}
  p{color:var(--muted);line-height:1.6;}
  .card{background:var(--card);border:1px solid var(--border);
    border-radius:var(--radius);padding:24px;margin-bottom:20px;}
  label{display:block;font-size:.85rem;color:var(--muted);
    margin-bottom:6px;font-weight:500;}
  input[type=text],input[type=password],input[type=file],textarea,select{
    width:100%;background:#0e0e14;border:1px solid var(--border);
    color:var(--text);padding:12px 14px;border-radius:10px;
    font-size:1rem;margin-bottom:16px;font-family:inherit;
    transition:border-color .2s;}
  textarea{font-family:'JetBrains Mono',monospace;font-size:.85rem;
    min-height:300px;resize:vertical;line-height:1.5;}
  input:focus,textarea:focus,select:focus{outline:none;
    border-color:var(--accent);box-shadow:0 0 0 3px rgba(124,92,255,.15);}
  .btn{display:inline-flex;align-items:center;justify-content:center;
    gap:8px;background:var(--accent);color:#fff;border:none;
    padding:12px 22px;border-radius:10px;font-size:.95rem;
    font-weight:600;cursor:pointer;font-family:inherit;text-decoration:none;
    transition:all .2s;}
  .btn:hover{background:var(--accent-hover);}
  .btn:active{transform:scale(.98);}
  .btn:disabled{opacity:.55;cursor:not-allowed;}
  .btn-block{width:100%;}
  .btn-sm{padding:8px 14px;font-size:.82rem;}
  .btn-ghost{background:transparent;border:1px solid var(--border);color:var(--text);}
  .btn-ghost:hover{background:var(--card-hover);}
  .btn-run{background:linear-gradient(90deg,#22c55e,#16a34a);}
  .btn-stop{background:linear-gradient(90deg,#ef4444,#dc2626);}
  .btn-danger{background:linear-gradient(90deg,#dc2626,#b91c1c);}
  .btn-fix{background:linear-gradient(90deg,#f59e0b,#d97706);}
  .flash{padding:12px 16px;border-radius:10px;margin-bottom:16px;
    font-size:.9rem;border:1px solid;}
  .flash.success{background:rgba(34,197,94,.1);color:#86efac;border-color:rgba(34,197,94,.3);}
  .flash.error{background:rgba(239,68,68,.1);color:#fca5a5;border-color:rgba(239,68,68,.3);}
  .file-item{background:#0e0e14;border:1px solid var(--border);
    border-radius:10px;margin-bottom:14px;overflow:hidden;}
  .file-item.running{border-color:rgba(34,197,94,.35);}
  .file-item.has-error{border-color:rgba(239,68,68,.5);}
  .file-header{display:flex;justify-content:space-between;align-items:center;
    gap:12px;padding:12px 14px;flex-wrap:wrap;}
  .file-name{font-family:'JetBrains Mono',monospace;font-size:.88rem;
    flex:1;min-width:150px;display:flex;align-items:center;gap:8px;word-break:break-all;}
  .status-dot{width:9px;height:9px;border-radius:50%;background:#555;
    display:inline-block;flex-shrink:0;}
  .status-dot.running{background:#22c55e;
    box-shadow:0 0 10px rgba(34,197,94,.9);animation:pulse 1.4s infinite;}
  .status-dot.error{background:#ef4444;box-shadow:0 0 10px rgba(239,68,68,.9);}
  @keyframes pulse{0%,100%{opacity:1;}50%{opacity:.4;}}
  .file-actions{display:flex;gap:8px;flex-wrap:wrap;}
  .output-wrap{padding:0 14px 14px;}
  .output-box{background:#06060a;border:1px solid var(--border);
    border-radius:10px;padding:14px;font-family:'JetBrains Mono',monospace;
    font-size:.78rem;white-space:pre-wrap;word-break:break-word;
    max-height:340px;overflow-y:auto;color:#c9d1d9;line-height:1.55;}
  .output-box.error{color:#fca5a5;border-color:rgba(239,68,68,.4);}
  .output-head{display:flex;justify-content:space-between;align-items:center;
    padding:8px 0 6px;font-size:.72rem;color:var(--muted);
    text-transform:uppercase;letter-spacing:.08em;flex-wrap:wrap;gap:8px;}
  .spinner{width:11px;height:11px;border:2px solid rgba(124,92,255,.25);
    border-top-color:#7c5cff;border-radius:50%;
    animation:spin .7s linear infinite;display:inline-block;
    vertical-align:middle;margin-right:6px;}
  @keyframes spin{to{transform:rotate(360deg);}}

  /* ============ PREMIUM AD BOX ============ */
  .ad-box{
    background:linear-gradient(135deg,rgba(124,92,255,.18),rgba(183,148,255,.06));
    border:1px solid rgba(124,92,255,.35);
    border-radius:14px;
    padding:16px 20px;
    margin-bottom:20px;
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:14px;
    flex-wrap:wrap;
    position:relative;
    overflow:hidden;
    box-shadow:0 4px 24px rgba(124,92,255,.12);
    animation:adGlow 3s ease-in-out infinite;
  }
  .ad-box::before{
    content:'';
    position:absolute;
    top:-50%;left:-50%;
    width:200%;height:200%;
    background:linear-gradient(45deg,transparent 30%,rgba(183,148,255,.08) 50%,transparent 70%);
    animation:adShine 4s linear infinite;
    pointer-events:none;
  }
  @keyframes adShine{0%{transform:translateX(-100%);}100%{transform:translateX(100%);}}
  @keyframes adGlow{
    0%,100%{box-shadow:0 4px 24px rgba(124,92,255,.12);}
    50%{box-shadow:0 4px 32px rgba(124,92,255,.25);}
  }
  .ad-box .ad-label{
    font-size:.65rem;
    color:#b794ff;
    text-transform:uppercase;
    letter-spacing:.15em;
    font-weight:700;
    margin-bottom:4px;
  }
  .ad-box .ad-content{
    flex:1;
    font-size:.92rem;
    color:#e6e6ee;
    line-height:1.5;
  }
  .ad-box .ad-content b{color:#b794ff;}
  .ad-box .ad-content code{
    background:rgba(124,92,255,.2);
    color:#b794ff;
    padding:1px 6px;
    border-radius:4px;
    font-size:.85em;
  }
  .ad-box a{
    color:#fff;
    font-weight:700;
    text-decoration:none;
    padding:8px 16px;
    background:linear-gradient(90deg,#7c5cff,#b794ff);
    border-radius:8px;
    font-size:.82rem;
    transition:all .2s;
    white-space:nowrap;
  }
  .ad-box a:hover{
    transform:translateX(3px);
    box-shadow:0 4px 16px rgba(124,92,255,.5);
  }

  /* ============ PREMIUM FIX PANEL ============ */
  .fix-panel{
    margin-top:14px;
    padding:16px;
    background:linear-gradient(135deg,rgba(245,158,11,.12),rgba(245,158,11,.04));
    border:1px solid rgba(245,158,11,.4);
    border-radius:12px;
    position:relative;
    overflow:hidden;
    animation:fixPulse 2s ease-in-out infinite;
  }
  @keyframes fixPulse{
    0%,100%{border-color:rgba(245,158,11,.4);}
    50%{border-color:rgba(245,158,11,.7);}
  }
  .fix-panel h4{
    font-size:.95rem;
    color:#fbbf24;
    margin-bottom:8px;
    display:flex;
    align-items:center;
    gap:8px;
    font-weight:700;
  }
  .fix-panel h4::before{
    content:'🤖';
    font-size:1.1rem;
    animation:botBounce 1.5s ease-in-out infinite;
  }
  @keyframes botBounce{
    0%,100%{transform:translateY(0);}
    50%{transform:translateY(-3px);}
  }
  .fix-progress{
    height:8px;
    background:rgba(255,255,255,.1);
    border-radius:8px;
    overflow:hidden;
    margin:12px 0;
    position:relative;
  }
  .fix-progress-bar{
    height:100%;
    background:linear-gradient(90deg,#f59e0b,#fbbf24,#f59e0b);
    background-size:200% 100%;
    width:0%;
    transition:width .4s;
    border-radius:8px;
    animation:progressShine 1.5s linear infinite;
  }
  @keyframes progressShine{
    0%{background-position:200% 0;}
    100%{background-position:-200% 0;}
  }
  .fix-status{
    margin-top:10px;
    text-align:center;
    font-size:.85rem;
    color:#fbbf24;
    min-height:20px;
  }

  .center{text-align:center;}
  .hero{text-align:center;padding:36px 8px;}
  .hero h1{font-size:2.2rem;margin-bottom:14px;}
  .hero p{max-width:560px;margin:0 auto 24px;}
  .auth-link{color:var(--accent);text-decoration:none;font-weight:600;}
  .auth-link:hover{text-decoration:underline;}
  .muted{color:var(--muted);font-size:.85rem;}
  .badge{display:inline-block;padding:3px 9px;border-radius:20px;
    font-size:.7rem;background:rgba(124,92,255,.15);color:#b794ff;
    border:1px solid rgba(124,92,255,.3);margin-left:6px;}
  .badge.admin{background:rgba(239,68,68,.15);color:#fca5a5;
    border-color:rgba(239,68,68,.3);}
  .stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
    gap:12px;margin-bottom:20px;}
  .stat{background:#0e0e14;border:1px solid var(--border);
    border-radius:10px;padding:16px;text-align:center;}
  .stat .num{font-size:1.6rem;font-weight:700;color:#b794ff;}
  .stat .lbl{font-size:.75rem;color:var(--muted);
    text-transform:uppercase;letter-spacing:.06em;margin-top:4px;}
  table{width:100%;border-collapse:collapse;font-size:.85rem;}
  th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--border);}
  th{color:var(--muted);font-weight:600;font-size:.75rem;
    text-transform:uppercase;letter-spacing:.06em;}
  tr:hover td{background:rgba(124,92,255,.04);}
  code{font-family:'JetBrains Mono',monospace;font-size:.85em;
    background:rgba(255,255,255,.06);padding:2px 6px;border-radius:4px;
    color:#b794ff;}
  pre{background:#06060a;border:1px solid var(--border);border-radius:10px;
    padding:14px;font-family:'JetBrains Mono',monospace;font-size:.8rem;
    overflow-x:auto;color:#c9d1d9;line-height:1.5;margin-bottom:12px;}
  .sidebar{position:fixed;top:0;right:-320px;width:320px;height:100%;
    background:var(--card);border-left:1px solid var(--border);
    padding:20px;overflow-y:auto;transition:right .3s;z-index:999;
    box-shadow:-10px 0 40px rgba(0,0,0,.5);}
  .sidebar.open{right:0;}
  .sidebar-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);
    opacity:0;pointer-events:none;transition:opacity .3s;z-index:998;}
  .sidebar-overlay.open{opacity:1;pointer-events:auto;}
  .sidebar h3{font-size:.78rem;color:var(--muted);
    text-transform:uppercase;letter-spacing:.08em;margin-bottom:12px;}
  .side-link{display:block;padding:12px 14px;background:#0e0e14;
    border:1px solid var(--border);border-radius:10px;margin-bottom:10px;
    color:var(--text);text-decoration:none;font-size:.88rem;
    transition:all .2s;cursor:pointer;}
  .side-link:hover{background:var(--card-hover);border-color:var(--accent);
    transform:translateX(-4px);}
  .side-link .desc{color:var(--muted);font-size:.75rem;margin-top:4px;}

  /* ============ TELEGRAM CONTACT BUTTON ============ */
  .tg-contact {
    position: fixed;
    bottom: 22px;
    right: 22px;
    z-index: 900;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 18px 12px 14px;
    background: linear-gradient(135deg, #229ED9, #1c8ac0);
    color: #fff;
    text-decoration: none;
    font-weight: 700;
    font-size: .9rem;
    border-radius: 50px;
    box-shadow: 0 8px 24px rgba(34, 158, 217, .45);
    transition: all .25s ease;
    animation: tgFloat 2.8s ease-in-out infinite;
  }
  .tg-contact:hover {
    transform: translateY(-3px) scale(1.04);
    box-shadow: 0 12px 30px rgba(34, 158, 217, .65);
    background: linear-gradient(135deg, #2ab0ee, #229ED9);
    color: #fff;
  }
  .tg-contact svg {
    width: 22px;
    height: 22px;
    flex-shrink: 0;
    filter: drop-shadow(0 0 6px rgba(255,255,255,.4));
  }
  @keyframes tgFloat {
    0%, 100% { transform: translateY(0); }
    50%      { transform: translateY(-6px); }
  }

  @media (max-width:768px){
    .nav-toggle{display:flex;align-items:center;justify-content:center;}
    .nav-links{display:none;position:absolute;top:100%;left:0;right:0;
      background:var(--card);border:1px solid var(--border);
      border-radius:10px;padding:8px;margin-top:8px;flex-direction:column;
      align-items:stretch;gap:2px;box-shadow:0 10px 40px rgba(0,0,0,.5);}
    .nav-links.open{display:flex;}
    .nav-links a{padding:12px;text-align:left;}
    header{position:relative;}
    .sidebar{width:88%;right:-100%;}
  }
  @media (max-width:520px){
    h1{font-size:1.5rem;}.hero h1{font-size:1.6rem;}
    .card{padding:18px;}
    .file-header{flex-direction:column;align-items:stretch;}
    .file-actions{justify-content:stretch;}
    .file-actions .btn{flex:1;min-width:0;}
    .output-box{font-size:.72rem;}
    .stats-grid{grid-template-columns:repeat(2,1fr);}
    table{font-size:.75rem;}
    th,td{padding:8px 6px;}
    .tg-contact {
      padding: 10px 14px 10px 12px;
      font-size: .82rem;
      bottom: 16px;
      right: 16px;
    }
    .tg-contact svg { width: 20px; height: 20px; }
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <a href="{{ url_for('index') }}" class="logo">⚡ ETHBD Hosting</a>
    <div class="nav-wrap">
      <button class="nav-toggle" onclick="toggleNav()">☰</button>
      <nav class="nav-links" id="navLinks">
        {% if session.user %}
          <a href="{{ url_for('dashboard') }}">Dashboard</a>
          <a href="{{ url_for('settings') }}">Settings</a>
          {% if session.is_admin %}<a href="{{ url_for('admin_panel') }}">Admin</a>{% endif %}
          <a href="{{ url_for('logout') }}">Logout</a>
        {% else %}
          <a href="{{ url_for('login') }}">Login</a>
          <a href="{{ url_for('register') }}">Register</a>
        {% endif %}
      </nav>
    </div>
  </header>

  {% if ad %}
  <div class="ad-box">
    <div style="flex:1;">
      <div class="ad-label">✨ Sponsored</div>
      <div class="ad-content">{{ ad.text|safe }}</div>
    </div>
    {% if ad.url %}<a href="{{ ad.url }}" target="_blank">Visit →</a>{% endif %}
  </div>
  {% endif %}

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for c, m in messages %}
      <div class="flash {{ c }}">{{ m }}</div>
    {% endfor %}
  {% endwith %}

  {% block content %}{% endblock %}
</div>

<!-- ============ TELEGRAM CONTACT FLOATING BUTTON ============ -->
<a href="https://t.me/M1NXGAMINGVIP1" target="_blank" rel="noopener"
   class="tg-contact" title="Contact on Telegram">
  <svg viewBox="0 0 240 240" xmlns="http://www.w3.org/2000/svg">
    <circle cx="120" cy="120" r="120" fill="#fff" opacity=".15"/>
    <path fill="#fff" d="M98 175c-3.8 0-3.1-1.4-4.4-5l-11-36 85-50c4-2.5 7.7-1.1 4.7 1.6l-72 65-3.3 20.4c-.5 1.8-1.4 3.5-3.2 3.5z"/>
    <path fill="#fff" opacity=".8" d="M98 175c2 0 2.9-.9 4-2l11-11-15-9-2 19c-.5 1.7.8 3 2 3z"/>
    <path fill="#fff" d="M113 153l57 42c6.5 3.6 11.2 1.7 12.8-6l23-108c2.4-9.5-3.6-13.7-9.7-10.6L48 128c-9.3 3.7-9.2 9-.6 11.3l39 12 90-57c4.2-2.6 8-1.2 4.9 1.6L113 153z"/>
  </svg>
  <span>Contact: @M1NXGAMINGVIP1</span>
</a>

<!-- Sidebar for Python Code Logic -->
<div class="sidebar-overlay" id="overlay" onclick="closeSidebar()"></div>
<div class="sidebar" id="sidebar">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
    <h2 style="font-size:1.1rem;">🐍 Python Guide</h2>
    <button class="btn btn-ghost btn-sm" onclick="closeSidebar()">✕</button>
  </div>
  <h3>Code Logic Examples</h3>
  <div class="side-link" onclick="showLogic('hello')">
    Hello World
    <div class="desc">The simplest possible program</div>
  </div>
  <div class="side-link" onclick="showLogic('bot')">
    Telegram Bot
    <div class="desc">24/7 running bot</div>
  </div>
  <div class="side-link" onclick="showLogic('flask')">
    Flask Web Server
    <div class="desc">Build your own API</div>
  </div>
  <div class="side-link" onclick="showLogic('scraper')">
    Web Scraper
    <div class="desc">Fetch data from websites</div>
  </div>
  <div class="side-link" onclick="showLogic('loop')">
    Infinite Loop Task
    <div class="desc">Do work every second</div>
  </div>
</div>

<script>
function toggleNav(){
  document.getElementById('navLinks').classList.toggle('open');
}
function openSidebar(){
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('overlay').classList.add('open');
}
function closeSidebar(){
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('overlay').classList.remove('open');
}
const LOGICS = {
  hello: `# Hello World - simplest
print("Hello from ETHBD Hosting! 🚀")
print("This runs 24/7 on the server.")`,
  bot: `# Telegram Bot - 24/7 running
# pip install python-telegram-bot
from telegram.ext import Application, CommandHandler

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

async def start(update, context):
    await update.message.reply_text("👋 Hello! Bot is alive 24/7.")

async def ping(update, context):
    await update.message.reply_text("🏓 Pong!")

app = Application.builder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ping", ping))

print("🤖 Bot running...")
app.run_polling()`,
  flask: `# Flask API Server
from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "ok", "msg": "API running"})

@app.route('/time')
def t():
    import datetime
    return jsonify({"time": str(datetime.datetime.now())})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)`,
  scraper: `# Simple Web Scraper
import requests
from time import sleep

while True:
    try:
        r = requests.get("https://api.github.com", timeout=10)
        print(f"✅ Status: {r.status_code}, Size: {len(r.text)} bytes")
    except Exception as e:
        print(f"❌ Error: {e}")
    sleep(60)`,
  loop: `# Infinite Loop Task
import time
from datetime import datetime

count = 0
while True:
    count += 1
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Tick #{count}")
    time.sleep(5)`
};
function showLogic(key){
  const code = LOGICS[key];
  if(!code) return;
  const blob = new Blob([code], {type:'text/plain'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = key + '.py';
  a.click();
  alert('✅ Downloaded ' + key + '.py\\n\\nUpload it in your dashboard to run 24/7!');
}
</script>
{% block scripts %}{% endblock %}
</body>
</html>
"""


def get_random_ad():
    try:
        ads = json.loads(ADS_JSON)
        if ads:
            return random.choice(ads)
    except Exception:
        pass
    return {
        'text': '🚀 <b>Your ad here!</b> Contact admin to promote your product.',
        'url': ''
    }


@app.context_processor
def inject_globals():
    return {
        'ad': get_random_ad(),
        'session': dict(session),
    }


# ==================== PAGES ====================
INDEX_PAGE = BASE.replace("{% block content %}{% endblock %}", r"""
{% block content %}
<div class="card hero">
  <h1>Host &amp; Run Python <span class="badge">24/7</span></h1>
  <p>Upload Python code — it auto-runs instantly, forever. Live logs, auto error fixing, mobile-first. Free forever.</p>
  <div style="display:flex;gap:10px;max-width:360px;margin:0 auto;flex-wrap:wrap;">
    <a href="{{ url_for('register') }}" class="btn" style="flex:1;">Get Started</a>
    <a href="{{ url_for('login') }}" class="btn btn-ghost" style="flex:1;">Login</a>
  </div>
</div>

<div class="card">
  <h2>✨ Features</h2>
  <p style="margin-bottom:8px;">▸ <b>Auto-run</b> — upload &amp; forget, runs forever</p>
  <p style="margin-bottom:8px;">📜 <b>Live logs</b> — see output in real time</p>
  <p style="margin-bottom:8px;">🔧 <b>Auto error fix</b> — AI corrects bugs instantly</p>
  <p style="margin-bottom:8px;">📱 <b>Mobile-first</b> — perfect on phone</p>
  <p>🐍 <b>Code templates</b> — click the sidebar for ready-made scripts</p>
</div>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Welcome — ETHBD Hosting")


REGISTER_PAGE = BASE.replace("{% block content %}{% endblock %}", r"""
{% block content %}
<div class="card" style="max-width:460px;margin:0 auto;position:relative;overflow:hidden;">
  <div style="position:absolute;top:-50px;right:-50px;width:150px;height:150px;
    background:radial-gradient(circle,rgba(124,92,255,.25),transparent 70%);
    border-radius:50%;pointer-events:none;"></div>
  <div style="position:absolute;bottom:-60px;left:-60px;width:180px;height:180px;
    background:radial-gradient(circle,rgba(183,148,255,.15),transparent 70%);
    border-radius:50%;pointer-events:none;"></div>

  <div class="center" style="margin-bottom:28px;position:relative;">
    <div style="font-size:3rem;filter:drop-shadow(0 0 20px rgba(124,92,255,.5));">🚀</div>
    <h2 style="margin-top:14px;font-size:1.5rem;
      background:linear-gradient(90deg,#fff,#b794ff);
      -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
      Create Account
    </h2>
    <p class="muted" style="margin-top:6px;">Register once — host Python 24/7 free</p>
  </div>

  <form method="post" id="regForm" style="position:relative;">
    <label>👤 Username</label>
    <input type="text" name="username" id="regUser" placeholder="choose a username"
           pattern="[a-zA-Z0-9_]{3,30}" required
           title="3-30 chars: letters, numbers, underscore"
           oninput="checkUser(this.value)">

    <label>🔒 Password</label>
    <input type="password" name="password" id="regPass" placeholder="min 6 characters"
           minlength="6" required oninput="checkStrength(this.value)">

    <div style="height:6px;background:rgba(255,255,255,.08);border-radius:6px;
      overflow:hidden;margin:-10px 0 14px;">
      <div id="strengthBar" style="height:100%;width:0%;transition:all .3s;
        border-radius:6px;background:#ef4444;"></div>
    </div>
    <p id="strengthText" class="muted" style="font-size:.75rem;margin-top:-10px;
      margin-bottom:14px;"></p>

    <label>🔐 Confirm Password</label>
    <input type="password" id="regPass2" placeholder="repeat password" required
           oninput="checkMatch()">
    <p id="matchText" class="muted" style="font-size:.75rem;margin-top:-10px;
      margin-bottom:14px;"></p>

    <button class="btn btn-block" type="submit" id="regBtn">
      ✨ Create Free Account
    </button>
  </form>

  <div style="display:flex;align-items:center;gap:10px;margin:18px 0;">
    <div style="flex:1;height:1px;background:var(--border);"></div>
    <span class="muted" style="font-size:.75rem;">OR</span>
    <div style="flex:1;height:1px;background:var(--border);"></div>
  </div>

  <p class="muted center" style="font-size:.9rem;">
    Already have an account?
    <a class="auth-link" href="{{ url_for('login') }}">Login →</a>
  </p>

  <div style="margin-top:20px;padding:12px;background:rgba(124,92,255,.06);
    border:1px solid rgba(124,92,255,.2);border-radius:10px;">
    <p class="muted" style="font-size:.75rem;line-height:1.6;">
      ✅ Free forever &nbsp;·&nbsp; ✅ Unlimited files &nbsp;·&nbsp; ✅ AI auto-fix<br>
      ✅ 24/7 uptime &nbsp;·&nbsp; ✅ Live logs &nbsp;·&nbsp; ✅ No credit card
    </p>
  </div>
</div>

<script>
function checkUser(v){
  const el = document.getElementById('regUser');
  if(v.length === 0){ el.style.borderColor = ''; return; }
  if(/^[a-zA-Z0-9_]{3,30}$/.test(v)) el.style.borderColor = '#22c55e';
  else el.style.borderColor = '#ef4444';
}
function checkStrength(p){
  const bar = document.getElementById('strengthBar');
  const txt = document.getElementById('strengthText');
  let s = 0;
  if(p.length >= 6) s++;
  if(p.length >= 10) s++;
  if(/[A-Z]/.test(p)) s++;
  if(/[0-9]/.test(p)) s++;
  if(/[^A-Za-z0-9]/.test(p)) s++;
  const map = [
    {w:'0%', c:'#ef4444', t:''},
    {w:'25%', c:'#ef4444', t:'Weak password'},
    {w:'45%', c:'#f59e0b', t:'Fair password'},
    {w:'65%', c:'#f59e0b', t:'Good password'},
    {w:'85%', c:'#22c55e', t:'Strong password'},
    {w:'100%', c:'#22c55e', t:'💪 Very strong!'}
  ];
  const m = map[Math.min(s, 5)];
  bar.style.width = m.w;
  bar.style.background = m.c;
  txt.textContent = m.t;
  txt.style.color = m.c;
}
function checkMatch(){
  const p1 = document.getElementById('regPass').value;
  const p2 = document.getElementById('regPass2').value;
  const el = document.getElementById('regPass2');
  const txt = document.getElementById('matchText');
  if(!p2){ el.style.borderColor = ''; txt.textContent = ''; return; }
  if(p1 === p2){
    el.style.borderColor = '#22c55e';
    txt.textContent = '✅ Passwords match';
    txt.style.color = '#22c55e';
  } else {
    el.style.borderColor = '#ef4444';
    txt.textContent = '❌ Passwords do not match';
    txt.style.color = '#ef4444';
  }
}
document.getElementById('regForm').addEventListener('submit', function(e){
  const p1 = document.getElementById('regPass').value;
  const p2 = document.getElementById('regPass2').value;
  if(p1 !== p2){
    e.preventDefault();
    alert('❌ Passwords do not match!');
    return;
  }
  const btn = document.getElementById('regBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Creating account...';
});
</script>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Register — ETHBD Hosting")


LOGIN_PAGE = BASE.replace("{% block content %}{% endblock %}", r"""
{% block content %}
<div class="card" style="max-width:420px;margin:0 auto;">
  <div class="center" style="margin-bottom:24px;">
    <div style="font-size:2.5rem;">👋</div>
    <h2 style="margin-top:12px;">Welcome Back</h2>
    <p class="muted">Login to your dashboard</p>
  </div>
  <form method="post">
    <label>Username</label>
    <input type="text" name="username" placeholder="username" required autocomplete="username">
    <label>Password</label>
    <input type="password" name="password" placeholder="password" required autocomplete="current-password">
    <button class="btn btn-block" type="submit">Login</button>
  </form>
  <p class="muted center" style="margin-top:18px;">
    No account? <a class="auth-link" href="{{ url_for('register') }}">Register</a>
  </p>
</div>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Login — ETHBD Hosting")


DASHBOARD_PAGE = BASE.replace("{% block content %}{% endblock %}", r"""
{% block content %}
<div class="card">
  <h2>Hello, {{ user }} 👋</h2>
  <p class="muted">Upload a <b>.py</b> file → runs 24/7. Auto-fix triggers on errors.</p>
  <button class="btn btn-ghost btn-sm" style="margin-top:12px;" onclick="openSidebar()">🐍 Browse Code Templates</button>
</div>

<div class="card">
  <h2>📤 Upload &amp; Auto-Run</h2>
  <form action="{{ url_for('upload_file') }}" method="post" enctype="multipart/form-data">
    <label>Choose a Python file (.py)</label>
    <input type="file" name="file" accept=".py" required>
    <button class="btn btn-block" type="submit">Upload &amp; Run</button>
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
              <button class="btn btn-ghost btn-sm" onclick="editFile('{{ file }}')">✎ Edit</button>
            {% endif %}
          </div>
        </div>
        <div class="output-wrap" style="display:none;">
          <div class="output-head">
            <span><span class="spinner"></span>Loading output...</span>
            <span class="muted"></span>
          </div>
          <div class="output-box"></div>
          <div class="fix-panel" style="display:none;">
            <h4>⚠ Error detected</h4>
            <p class="muted" style="margin-bottom:10px;">AI can fix this automatically.</p>
            <button class="btn btn-fix btn-block fix-btn">🔧 Fix Error with AI</button>
            <div class="fix-progress" style="display:none;">
              <div class="fix-progress-bar"></div>
            </div>
            <p class="muted fix-status" style="margin-top:8px;text-align:center;"></p>
          </div>
        </div>
      </div>
    {% endfor %}
  {% else %}
    <p class="muted">No files yet. Upload one above ☝️</p>
  {% endif %}
</div>

<!-- Editor Modal -->
<div class="sidebar-overlay" id="editorOverlay" onclick="closeEditor()"></div>
<div class="sidebar" id="editorSidebar" style="width:min(640px,95%);">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
    <h2 style="font-size:1.1rem;">✎ Editing: <span id="editName"></span></h2>
    <button class="btn btn-ghost btn-sm" onclick="closeEditor()">✕</button>
  </div>
  <textarea id="editCode" spellcheck="false"></textarea>
  <button class="btn btn-block" onclick="saveFile()" style="margin-top:12px;">💾 Save &amp; Restart</button>
  <p class="muted center" style="margin-top:8px;font-size:.78rem;">
    Saving will restart the running process.
  </p>
</div>

<script>
const pollers = {}, lastLog = {}, loading = {}, errState = {};

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
      errState[f] = false;
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

function detectErrorJS(log){
  if(!log) return false;
  return /Traceback \(most recent call last\)|\b\w*(Error|Exception)\s*:|SyntaxError|IndentationError|ModuleNotFoundError|ImportError|NameError|TypeError|ValueError|ZeroDivisionError|KeyError|IndexError|AttributeError|FileNotFoundError|❌/i.test(log);
}

async function fetchLog(f){
  try{
    const r = await fetch('/log/'+encodeURIComponent(f));
    const d = await r.json();
    const item = getItem(f);
    if(!item) return;
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

    const hasErr = d.has_error || detectErrorJS(log);

    if(lastLog[f] !== log){
      lastLog[f] = log;
      const wasBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
      box.innerHTML = log ? escapeHtml(log)
        : '<span style="color:#555">Waiting for output...</span>';
      box.classList.toggle('error', hasErr);
      if(wasBottom) box.scrollTop = box.scrollHeight;
    }

    const fixPanel = item.querySelector('.fix-panel');
    if(hasErr){
      if(fixPanel.style.display !== 'block'){
        fixPanel.style.display = 'block';
        item.classList.add('has-error');
        item.querySelector('.status-dot').classList.add('error');
        bindFixButton(f, item);
      }
      errState[f] = true;
    } else {
      if(fixPanel.style.display === 'block'){
        fixPanel.style.display = 'none';
        item.classList.remove('has-error');
        item.querySelector('.status-dot').classList.remove('error');
      }
      errState[f] = false;
    }
  }catch(e){ console.warn('log fetch error', e); }
}

function bindFixButton(f, item){
  const btn = item.querySelector('.fix-btn');
  if(!btn) return;
  const newBtn = btn.cloneNode(true);
  btn.parentNode.replaceChild(newBtn, btn);
  newBtn.addEventListener('click', () => autoFix(f, item));
}

async function autoFix(f, item){
  const btn = item.querySelector('.fix-btn');
  const progWrap = item.querySelector('.fix-progress');
  const prog = item.querySelector('.fix-progress-bar');
  const status = item.querySelector('.fix-status');

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>AI is analyzing...';
  progWrap.style.display = 'block';
  status.textContent = 'Analyzing error...';

  let p = 5;
  prog.style.width = p + '%';
  const ticker = setInterval(() => {
    p = Math.min(p + Math.random() * 8, 90);
    prog.style.width = p + '%';
  }, 400);

  const t0 = Date.now();
  const timeTicker = setInterval(() => {
    const s = ((Date.now() - t0) / 1000).toFixed(1);
    status.textContent = `Fixing... ${s}s elapsed`;
  }, 200);

  try{
    const r = await fetch('/fix/'+encodeURIComponent(f), {method:'POST'});
    const d = await r.json();
    clearInterval(ticker); clearInterval(timeTicker);
    prog.style.width = '100%';

    if(d.ok){
      status.innerHTML = `✅ <b>Fixed in ${d.elapsed.toFixed(1)}s</b><br>${escapeHtml(d.explanation)}`;
      setTimeout(() => {
        item.querySelector('.fix-panel').style.display = 'none';
        errState[f] = false;
        item.classList.remove('has-error');
        item.querySelector('.status-dot').classList.remove('error');
      }, 3000);
      setTimeout(() => startFile(f, item.querySelector('.run-btn')), 500);
    } else {
      status.innerHTML = '❌ ' + escapeHtml(d.error || 'Fix failed');
      btn.disabled = false;
      btn.innerHTML = '🔧 Try Again';
    }
  }catch(e){
    clearInterval(ticker); clearInterval(timeTicker);
    status.textContent = '❌ ' + e;
    btn.disabled = false;
    btn.innerHTML = '🔧 Try Again';
  }
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

async function editFile(f){
  const r = await fetch('/get-code/'+encodeURIComponent(f));
  const d = await r.json();
  document.getElementById('editName').textContent = f;
  document.getElementById('editCode').value = d.code || '';
  document.getElementById('editorSidebar').classList.add('open');
  document.getElementById('editorOverlay').classList.add('open');
  document.getElementById('editorSidebar').dataset.file = f;
}
function closeEditor(){
  document.getElementById('editorSidebar').classList.remove('open');
  document.getElementById('editorOverlay').classList.remove('open');
}
async function saveFile(){
  const f = document.getElementById('editorSidebar').dataset.file;
  const code = document.getElementById('editCode').value;
  const r = await fetch('/save-code/'+encodeURIComponent(f), {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({code})
  });
  const d = await r.json();
  if(d.ok){
    closeEditor();
    setTimeout(() => location.reload(), 300);
  } else alert('Save failed: ' + d.error);
}

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
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Dashboard — ETHBD Hosting")


SETTINGS_PAGE = BASE.replace("{% block content %}{% endblock %}", r"""
{% block content %}
<div class="card" style="max-width:500px;margin:0 auto;">
  <h2>⚙ Account Settings</h2>
  <p class="muted" style="margin-bottom:20px;">Logged in as <b>{{ user }}</b></p>

  <h3 style="font-size:1rem;margin:20px 0 10px;">Change Password</h3>
  <form method="post" action="{{ url_for('change_password') }}">
    <label>Current Password</label>
    <input type="password" name="old_password" required>
    <label>New Password</label>
    <input type="password" name="new_password" minlength="6" required>
    <button class="btn btn-block" type="submit">Update Password</button>
  </form>
</div>

<div class="card" style="max-width:500px;margin:0 auto;border-color:rgba(239,68,68,.3);">
  <h2 style="color:#fca5a5;">⚠ Danger Zone</h2>
  <p class="muted" style="margin-bottom:16px;">Deleting your account removes all your files permanently. This cannot be undone.</p>
  <form method="post" action="{{ url_for('delete_account') }}"
        onsubmit="return confirm('Are you SURE? This will delete your account and all files forever.');">
    <label>Type your username to confirm: <code>{{ user }}</code></label>
    <input type="text" name="confirm_username" placeholder="{{ user }}" required>
    <label>Password</label>
    <input type="password" name="password" required>
    <button class="btn btn-danger btn-block" type="submit">Delete My Account</button>
  </form>
</div>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Settings — ETHBD Hosting")


ADMIN_LOGIN_PAGE = BASE.replace("{% block content %}{% endblock %}", r"""
{% block content %}
<div class="card" style="max-width:420px;margin:0 auto;border-color:rgba(239,68,68,.4);">
  <div class="center" style="margin-bottom:24px;">
    <div style="font-size:2.5rem;">🛡</div>
    <h2 style="margin-top:12px;">Admin Access</h2>
    <p class="muted">Restricted area</p>
  </div>
  <form method="post">
    <label>Admin Username</label>
    <input type="text" name="username" required>
    <label>Admin Password</label>
    <input type="password" name="password" required>
    <button class="btn btn-danger btn-block" type="submit">Enter Admin Panel</button>
  </form>
  <p class="muted center" style="margin-top:16px;">
    <a class="auth-link" href="{{ url_for('login') }}">← Normal Login</a>
  </p>
</div>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Admin Login")


ADMIN_PAGE = BASE.replace("{% block content %}{% endblock %}", r"""
{% block content %}
<div class="card" style="border-color:rgba(239,68,68,.4);">
  <h2 style="color:#fca5a5;">🛡 Admin Panel</h2>
  <p class="muted">Full overview of users, files, and activity.</p>
</div>

<div class="stats-grid">
  <div class="stat"><div class="num">{{ stats.users }}</div><div class="lbl">Users</div></div>
  <div class="stat"><div class="num">{{ stats.files }}</div><div class="lbl">Files</div></div>
  <div class="stat"><div class="num">{{ stats.running }}</div><div class="lbl">Running</div></div>
  <div class="stat"><div class="num">{{ stats.size_kb }}KB</div><div class="lbl">Total Size</div></div>
</div>

<div class="card">
  <h2>👥 Users</h2>
  <div style="overflow-x:auto;">
    <table>
      <thead><tr>
        <th>Username</th><th>Files</th><th>Running</th><th>Joined</th><th>Actions</th>
      </tr></thead>
      <tbody>
        {% for u in users %}
        <tr>
          <td><code>{{ u.username }}</code>
            {% if u.is_admin %}<span class="badge admin">admin</span>{% endif %}
          </td>
          <td>{{ u.file_count }}</td>
          <td>{{ u.running_count }}</td>
          <td class="muted">{{ u.created_str }}</td>
          <td>
            <a class="btn btn-ghost btn-sm"
               href="{{ url_for('admin_user_detail', username=u.username) }}">View</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<div class="card">
  <h2>📋 Recent Activity</h2>
  <div style="overflow-x:auto;">
    <table>
      <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Detail</th></tr></thead>
      <tbody>
        {% for a in activity %}
        <tr>
          <td class="muted">{{ a.ts_str }}</td>
          <td><code>{{ a.username }}</code></td>
          <td>{{ a.action }}</td>
          <td class="muted">{{ a.detail }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<div class="card">
  <h2>💾 Backup</h2>
  <p class="muted" style="margin-bottom:12px;">Download all users, files metadata, and logs.</p>
  <a class="btn btn-ghost" href="{{ url_for('admin_backup') }}">⬇ Download Backup (JSON)</a>
</div>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "Admin Panel")


ADMIN_USER_PAGE = BASE.replace("{% block content %}{% endblock %}", r"""
{% block content %}
<div class="card">
  <h2>👤 {{ target_user }}</h2>
  <p class="muted">
    Joined: {{ joined }} · Files: {{ files|length }} · Running: {{ running_count }}
  </p>
  <a class="btn btn-ghost btn-sm" style="margin-top:12px;" href="{{ url_for('admin_panel') }}">← Back</a>
</div>

<div class="card">
  <h2>📂 Files</h2>
  {% if files %}
    <div style="overflow-x:auto;">
      <table>
        <thead><tr><th>Name</th><th>Size</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>
          {% for f in files %}
          <tr>
            <td><code>{{ f.name }}</code></td>
            <td class="muted">{{ f.size }} B</td>
            <td>
              {% if f.running %}<span style="color:#22c55e;">● Running</span>
              {% else %}<span class="muted">○ Stopped</span>{% endif %}
            </td>
            <td>
              <a class="btn btn-ghost btn-sm"
                 href="{{ url_for('admin_download', username=target_user, filename=f.name) }}">Download</a>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  {% else %}
    <p class="muted">No files.</p>
  {% endif %}
</div>
{% endblock %}
""").replace("{% block title %}ETHBD Hosting{% endblock %}", "User Detail — Admin")


# ==================== ROUTES ====================
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
        if not re.match(r'^[a-zA-Z0-9_]{3,30}$', u):
            flash('Username: 3-30 chars, letters/numbers/underscore only.', 'error')
            return redirect(url_for('register'))
        if len(p) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('register'))
        conn = get_db()
        try:
            is_admin = 1 if u == ADMIN_USER else 0
            conn.execute(
                "INSERT INTO users (username,password,created,last_login,is_admin) VALUES (?,?,?,?,?)",
                (u, hash_password(p), time.time(), time.time(), is_admin))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            flash('Username already taken.', 'error')
            return redirect(url_for('register'))
        conn.close()
        os.makedirs(os.path.join(UPLOAD_FOLDER, u), exist_ok=True)
        session['user'] = u
        session['is_admin'] = (u == ADMIN_USER)
        log_activity(u, 'register', 'New account')
        flash('Account created! 🎉', 'success')
        return redirect(url_for('dashboard'))
    return render_template_string(REGISTER_PAGE)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username', '').strip()
        p = request.form.get('password', '')
        conn = get_db()
        row = conn.execute("SELECT password,is_admin FROM users WHERE username=?",
                           (u,)).fetchone()
        if row and row['password'] == hash_password(p):
            conn.execute("UPDATE users SET last_login=? WHERE username=?",
                         (time.time(), u))
            conn.commit(); conn.close()
            session['user'] = u
            session['is_admin'] = bool(row['is_admin'])
            log_activity(u, 'login', '')
            flash('Logged in! ✅', 'success')
            return redirect(url_for('dashboard'))
        conn.close()
        flash('Invalid username or password.', 'error')
    return render_template_string(LOGIN_PAGE)


@app.route('/logout')
def logout():
    if 'user' in session:
        log_activity(session['user'], 'logout', '')
    session.clear()
    flash('Logged out.', 'success')
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    u = session['user']
    d = os.path.join(UPLOAD_FOLDER, u)
    os.makedirs(d, exist_ok=True)
    files = sorted(os.listdir(d))
    running = [f for f in files if is_running(u, f)]
    return render_template_string(DASHBOARD_PAGE, user=u, files=files, running=running)


@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    u = session['user']
    d = os.path.join(UPLOAD_FOLDER, u)
    os.makedirs(d, exist_ok=True)
    if 'file' in request.files:
        f = request.files['file']
        if f.filename:
            fname = safe_filename(f.filename)
            path = os.path.join(d, fname)
            f.save(path)
            conn = get_db()
            conn.execute("""INSERT OR REPLACE INTO files
                (username,filename,size,uploaded) VALUES (?,?,?,?)""",
                (u, fname, os.path.getsize(path), time.time()))
            conn.commit(); conn.close()
            log_activity(u, 'upload', fname)
            flash(f'Uploaded "{fname}" ✅', 'success')
            if fname.endswith('.py'):
                ok, msg = start_process(u, fname)
                if ok:
                    flash(f'Auto-started "{fname}" 🚀', 'success')
                else:
                    flash(f'Auto-start failed: {msg}', 'error')
    return redirect(url_for('dashboard'))


@app.route('/start/<filename>', methods=['POST'])
@login_required
def start_file(filename):
    u = session['user']
    filename = safe_filename(filename)
    if not filename.endswith('.py'):
        return jsonify({'ok': False, 'error': 'Only .py files.'})
    if is_running(u, filename):
        return jsonify({'ok': True})
    ok, msg = start_process(u, filename)
    if ok: log_activity(u, 'start', filename)
    return jsonify({'ok': ok, 'error': None if ok else msg})


@app.route('/stop/<filename>', methods=['POST'])
@login_required
def stop_file(filename):
    u = session['user']
    filename = safe_filename(filename)
    ok, msg = stop_process(u, filename)
    if ok: log_activity(u, 'stop', filename)
    return jsonify({'ok': ok, 'msg': msg})


@app.route('/status/<filename>')
@login_required
def status_file(filename):
    return jsonify({'running': is_running(session['user'], safe_filename(filename))})


@app.route('/log/<filename>')
@login_required
def log_file(filename):
    u = session['user']
    filename = safe_filename(filename)
    log_path = get_log_path(u, filename)
    if not os.path.exists(log_path):
        return jsonify({'log': '', 'has_error': False})
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            data = f.read()
        if len(data) > 100_000:
            data = '...[truncated]...\n' + data[-100_000:]
        return jsonify({
            'log': data,
            'has_error': detect_error(data)
        })
    except Exception as e:
        return jsonify({'log': '', 'has_error': False, 'error': str(e)})


@app.route('/get-code/<filename>')
@login_required
def get_code(filename):
    u = session['user']
    filename = safe_filename(filename)
    path = os.path.join(UPLOAD_FOLDER, u, filename)
    if not os.path.exists(path):
        return jsonify({'code': '', 'error': 'Not found'})
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return jsonify({'code': f.read()})
    except Exception as e:
        return jsonify({'code': '', 'error': str(e)})


@app.route('/save-code/<filename>', methods=['POST'])
@login_required
def save_code(filename):
    u = session['user']
    filename = safe_filename(filename)
    data = request.get_json() or {}
    code = data.get('code', '')
    path = os.path.join(UPLOAD_FOLDER, u, filename)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(code)
        log_activity(u, 'edit', filename)
        if is_running(u, filename):
            stop_process(u, filename)
            time.sleep(0.5)
        if filename.endswith('.py'):
            start_process(u, filename)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/fix/<filename>', methods=['POST'])
@login_required
def fix_file(filename):
    u = session['user']
    filename = safe_filename(filename)
    path = os.path.join(UPLOAD_FOLDER, u, filename)
    if not os.path.exists(path):
        return jsonify({'ok': False, 'error': 'File not found'})

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            code = f.read()
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

    log_path = get_log_path(u, filename)
    error_output = ''
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            error_output = f.read()[-4000:]

    if not detect_error(error_output):
        return jsonify({'ok': False, 'error': 'No error detected.'})

    fixed, explanation, elapsed = ai_fix_code(code, error_output)

    try:
        with open(path + '.bak', 'w', encoding='utf-8') as f:
            f.write(code)
    except Exception:
        pass

    with open(path, 'w', encoding='utf-8') as f:
        f.write(fixed)

    log_activity(u, 'ai-fix', filename)

    if is_running(u, filename):
        stop_process(u, filename)
        time.sleep(0.3)
    start_process(u, filename)

    return jsonify({'ok': True, 'explanation': explanation,
                    'elapsed': round(elapsed, 1)})


@app.route('/settings')
@login_required
def settings():
    return render_template_string(SETTINGS_PAGE, user=session['user'])


@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    u = session['user']
    old = request.form.get('old_password', '')
    new = request.form.get('new_password', '')
    conn = get_db()
    row = conn.execute("SELECT password FROM users WHERE username=?", (u,)).fetchone()
    if not row or row['password'] != hash_password(old):
        conn.close()
        flash('Current password is wrong.', 'error')
        return redirect(url_for('settings'))
    if len(new) < 6:
        conn.close()
        flash('New password too short.', 'error')
        return redirect(url_for('settings'))
    conn.execute("UPDATE users SET password=? WHERE username=?",
                 (hash_password(new), u))
    conn.commit(); conn.close()
    log_activity(u, 'password-change', '')
    flash('Password updated ✅', 'success')
    return redirect(url_for('settings'))


@app.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    u = session['user']
    confirm = request.form.get('confirm_username', '')
    pwd = request.form.get('password', '')
    if confirm != u:
        flash('Username confirmation does not match.', 'error')
        return redirect(url_for('settings'))
    conn = get_db()
    row = conn.execute("SELECT password FROM users WHERE username=?", (u,)).fetchone()
    if not row or row['password'] != hash_password(pwd):
        conn.close()
        flash('Password is wrong.', 'error')
        return redirect(url_for('settings'))
    with lock:
        for fname in list(running_processes.get(u, {}).keys()):
            stop_process(u, fname)
    udir = os.path.join(UPLOAD_FOLDER, u)
    if os.path.isdir(udir):
        shutil.rmtree(udir, ignore_errors=True)
    for f in os.listdir(LOGS_FOLDER):
        if f.startswith(u + '__'):
            try: os.remove(os.path.join(LOGS_FOLDER, f))
            except OSError: pass
    conn.execute("DELETE FROM users WHERE username=?", (u,))
    conn.execute("DELETE FROM files WHERE username=?", (u,))
    conn.commit(); conn.close()
    log_activity(u, 'delete-account', '')
    session.clear()
    flash('Account deleted. Goodbye 👋', 'success')
    return redirect(url_for('index'))


@app.route('/files/<path:filename>')
@login_required
def download_file(filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER, session['user']), filename)


# ==================== ADMIN ====================
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        u = request.form.get('username', '').strip()
        p = request.form.get('password', '')
        conn = get_db()
        row = conn.execute(
            "SELECT password,is_admin FROM users WHERE username=?",
            (u,)).fetchone()
        conn.close()
        if row and row['password'] == hash_password(p) and row['is_admin']:
            session['user'] = u
            session['is_admin'] = True
            log_activity(u, 'admin-login', '')
            flash('Welcome, admin 🛡', 'success')
            return redirect(url_for('admin_panel'))
        flash('Invalid admin credentials.', 'error')
    return render_template_string(ADMIN_LOGIN_PAGE)


@app.route('/admin/panel')
@admin_required
def admin_panel():
    conn = get_db()
    user_rows = conn.execute("SELECT * FROM users ORDER BY created DESC").fetchall()
    activity_rows = conn.execute(
        "SELECT * FROM activity ORDER BY ts DESC LIMIT 50").fetchall()
    total_files = conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()['c']
    total_size = conn.execute("SELECT COALESCE(SUM(size),0) AS s FROM files").fetchone()['s']
    conn.close()

    users = []
    total_running = 0
    for r in user_rows:
        u = r['username']
        udir = os.path.join(UPLOAD_FOLDER, u)
        fc = len(os.listdir(udir)) if os.path.isdir(udir) else 0
        rc = sum(1 for f in (os.listdir(udir) if os.path.isdir(udir) else [])
                 if is_running(u, f))
        total_running += rc
        users.append({
            'username': u,
            'is_admin': r['is_admin'],
            'file_count': fc,
            'running_count': rc,
            'created_str': time.strftime('%Y-%m-%d', time.localtime(r['created']))
        })

    activity = [{
        'username': a['username'],
        'action': a['action'],
        'detail': a['detail'],
        'ts_str': time.strftime('%m-%d %H:%M', time.localtime(a['ts']))
    } for a in activity_rows]

    stats = {
        'users': len(users),
        'files': total_files,
        'running': total_running,
        'size_kb': round(total_size / 1024, 1)
    }

    return render_template_string(ADMIN_PAGE, users=users,
                                  activity=activity, stats=stats)


@app.route('/admin/user/<username>')
@admin_required
def admin_user_detail(username):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if not row:
        flash('User not found.', 'error')
        return redirect(url_for('admin_panel'))

    udir = os.path.join(UPLOAD_FOLDER, username)
    files = []
    if os.path.isdir(udir):
        for f in sorted(os.listdir(udir)):
            fp = os.path.join(udir, f)
            files.append({
                'name': f,
                'size': os.path.getsize(fp),
                'running': is_running(username, f)
            })
    running_count = sum(1 for f in files if f['running'])
    return render_template_string(
        ADMIN_USER_PAGE,
        target_user=username,
        joined=time.strftime('%Y-%m-%d %H:%M', time.localtime(row['created'])),
        files=files,
        running_count=running_count)


@app.route('/admin/download/<username>/<filename>')
@admin_required
def admin_download(username, filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER, username),
                               safe_filename(filename))


@app.route('/admin/backup')
@admin_required
def admin_backup():
    conn = get_db()
    users = [dict(r) for r in conn.execute("SELECT * FROM users").fetchall()]
    files = [dict(r) for r in conn.execute("SELECT * FROM files").fetchall()]
    act = [dict(r) for r in conn.execute(
        "SELECT * FROM activity ORDER BY ts DESC LIMIT 500").fetchall()]
    conn.close()
    data = {'exported': time.time(), 'users': users,
            'files': files, 'activity': act}
    buf = io.BytesIO(json.dumps(data, indent=2).encode())
    return send_file(buf, mimetype='application/json', as_attachment=True,
                     download_name=f'ethbd-backup-{int(time.time())}.json')


# ==================== BOOT ====================
try:
    auto_start_all()
except Exception as e:
    print(f"Auto-start error: {e}")


if __name__ == '__main__':
    try:
        from pyngrok import ngrok
        print(f"\n🌐 {ngrok.connect(5000).public_url}\n")
    except Exception:
        print("\n⚠ http://localhost:5000\n")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
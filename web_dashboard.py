import discord
from flask import Flask, render_template_string, request, redirect, session, jsonify
import threading
import asyncio
import psutil
import os
import json
import logging
from datetime import datetime

# --- Configuration ---
PASSWORD = "401444"
SECRET_KEY = os.urandom(24)
DATA_FILE = "data.json"

# --- Flask App Setup ---
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Disable Flask default logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Global variables
bot_instance = None
system_logs = []

def log_action(action):
    """บันทึก Log การทำงาน"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {action}"
    system_logs.insert(0, log_entry)
    if len(system_logs) > 50:
        system_logs.pop()

def get_bot_stats():
    """ดึงข้อมูลสถานะบอท"""
    if not bot_instance or not bot_instance.is_ready():
        return None
    
    process = psutil.Process(os.getpid())
    ram_usage = process.memory_info().rss / 1024 / 1024 # MB
    ping = round(bot_instance.latency * 1000)
    
    data_size = 0
    if os.path.exists(DATA_FILE):
        data_size = os.path.getsize(DATA_FILE) / 1024 # KB

    return {
        "ram": f"{ram_usage:.2f} MB",
        "ping": f"{ping} ms",
        "data_size": f"{data_size:.2f} KB",
        "guild_count": len(bot_instance.guilds),
        "user_count": sum(g.member_count for g in bot_instance.guilds),
        "is_online": True
    }

# --- HTML Template (Cyberpunk V2) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NETRUNNER CONTROL_PANEL // V.2.0.77</title>
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --yellow: #fcee0a;
            --cyan: #00f0ff;
            --red: #ff003c;
            --black: #050505;
            --dark-gray: #121212;
            --text: #e0e0e0;
        }
        * { box-sizing: border-box; }
        body {
            background-color: var(--black);
            color: var(--text);
            font-family: 'Rajdhani', sans-serif;
            margin: 0;
            padding: 0;
            overflow-x: hidden;
        }
        
        /* --- Cyberpunk Background & Animation --- */
        .cyber-bg {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1;
            background: 
                linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), 
                linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06));
            background-size: 100% 2px, 3px 100%;
            pointer-events: none;
        }
        .scanline {
            width: 100%; height: 100px; z-index: 10;
            background: linear-gradient(0deg, rgba(0,0,0,0) 0%, rgba(0, 240, 255, 0.2) 50%, rgba(0,0,0,0) 100%);
            opacity: 0.1;
            position: absolute; bottom: 100%;
            animation: scanline 10s linear infinite;
            pointer-events: none;
        }
        @keyframes scanline {
            0% { bottom: 100%; } 80% { bottom: 100%; } 100% { bottom: -100px; }
        }

        /* --- Login Screen Animation --- */
        .login-wrapper {
            height: 100vh; display: flex; justify-content: center; align-items: center; flex-direction: column;
            background: radial-gradient(circle at center, #1a1a1a 0%, #000 100%);
            position: relative;
        }
        .login-box {
            border: 2px solid var(--cyan);
            padding: 40px;
            background: rgba(0, 0, 0, 0.8);
            box-shadow: 0 0 20px rgba(0, 240, 255, 0.2);
            text-align: center;
            position: relative;
            clip-path: polygon(0 0, 100% 0, 100% 85%, 90% 100%, 0 100%);
        }
        .login-box::before {
            content: "SECURITY_CHECK";
            position: absolute; top: -10px; left: 20px;
            background: var(--black); color: var(--cyan);
            padding: 0 10px; font-weight: bold; border: 1px solid var(--cyan);
        }
        
        .blink-text { animation: blink 1s infinite; color: var(--red); font-weight: bold; }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.2; } 100% { opacity: 1; } }

        .glitch-title {
            font-size: 3rem; margin-bottom: 20px; color: var(--yellow);
            text-shadow: 2px 2px var(--red);
            position: relative;
        }

        /* --- Dashboard Layout --- */
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; position: relative; z-index: 1; }
        
        .dashboard-grid { display: grid; grid-template-columns: 280px 1fr 300px; gap: 20px; margin-top: 30px; }
        
        .panel {
            background: rgba(15, 15, 15, 0.9);
            border: 1px solid var(--text);
            border-left: 4px solid var(--yellow);
            padding: 20px; margin-bottom: 20px;
            box-shadow: 5px 5px 0px rgba(0,0,0,0.5);
        }
        .panel h2 {
            border-bottom: 2px solid var(--cyan); padding-bottom: 5px;
            color: var(--cyan); margin-top: 0; text-transform: uppercase; letter-spacing: 2px;
        }

        /* --- Scrollable Server List --- */
        .scrollable-list {
            max-height: 500px;
            overflow-y: auto;
            padding-right: 10px;
        }
        /* Custom Scrollbar */
        .scrollable-list::-webkit-scrollbar { width: 8px; }
        .scrollable-list::-webkit-scrollbar-track { background: var(--black); }
        .scrollable-list::-webkit-scrollbar-thumb { background: var(--cyan); border-radius: 4px; }
        .scrollable-list::-webkit-scrollbar-thumb:hover { background: var(--yellow); }

        .server-card {
            background: rgba(30, 30, 30, 0.4);
            border-left: 2px solid var(--red);
            padding: 10px 15px; margin-bottom: 10px;
            display: flex; justify-content: space-between; align-items: center;
            transition: 0.3s;
        }
        .server-card:hover { background: rgba(255, 0, 60, 0.1); border-left: 4px solid var(--yellow); }
        .server-info h3 { margin: 0; color: var(--text); font-size: 1.1rem; }
        
        /* --- Inputs & Buttons --- */
        .cyber-input {
            background: var(--black); border: 1px solid var(--cyan); color: var(--yellow);
            padding: 10px; font-family: 'Rajdhani'; width: 100%; outline: none;
            font-size: 1.1rem; text-align: center;
        }
        .cyber-input:focus { box-shadow: 0 0 10px var(--cyan); }
        
        .cyber-btn {
            background: var(--yellow); color: var(--black); border: none; padding: 10px 20px;
            font-weight: bold; cursor: pointer; text-transform: uppercase;
            clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
            transition: 0.2s; font-family: 'Rajdhani';
        }
        .cyber-btn:hover { background: var(--cyan); color: black; transform: scale(1.05); }
        .cyber-btn.danger { background: var(--red); color: white; }
        
        .tiny-btn {
            background: transparent; border: 1px solid var(--text); color: var(--text);
            padding: 2px 8px; cursor: pointer; font-size: 0.8rem; margin-left: 3px;
            text-transform: uppercase;
        }
        .tiny-btn:hover { background: var(--cyan); color: black; border-color: var(--cyan); }

        /* --- Stats & Logs --- */
        .stat-item { display: flex; justify-content: space-between; margin-bottom: 8px; border-bottom: 1px dotted var(--gray); }
        .stat-val { color: var(--yellow); font-family: monospace; }
        
        .log-console {
            background: #050505; color: #0f0; font-family: monospace; height: 350px;
            overflow-y: scroll; padding: 10px; border: 1px solid var(--gray); font-size: 0.85rem;
        }
        .log-entry { margin-bottom: 4px; border-bottom: 1px solid #111; word-wrap: break-word; }

        .owner-item {
            display: flex; justify-content: space-between; align-items: center;
            background: rgba(0,255,255,0.05); padding: 5px; margin-bottom: 5px; border-left: 2px solid var(--cyan);
        }

        /* --- Status Badge --- */
        .status-badge {
            padding: 5px 15px; font-weight: bold; text-transform: uppercase; border: 1px solid;
            display: inline-block;
        }
        .online { border-color: #0f0; color: #0f0; box-shadow: 0 0 5px #0f0; text-shadow: 0 0 5px #0f0; }
        .offline { border-color: #f00; color: #f00; box-shadow: 0 0 5px #f00; text-shadow: 0 0 5px #f00; }

        @media (max-width: 1000px) { .dashboard-grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>

<div class="cyber-bg"></div>
<div class="scanline"></div>

{% if not session.get('auth') %}
    <!-- LOGIN SCREEN -->
    <div class="login-wrapper">
        <div class="login-box">
            <h1 class="glitch-title">NETRUNNER<br>ACCESS</h1>
            <p class="blink-text" style="margin-bottom: 30px;">>> AUTHENTICATION REQUIRED <<</p>
            <!-- Form submits to root '/' -->
            <form method="POST" action="/">
                <input type="password" name="passcode" class="cyber-input" placeholder="ENTER 6-DIGIT CODE" maxlength="6" autofocus required 
                       style="font-size: 2rem; letter-spacing: 5px; width: 250px; margin-bottom: 20px;">
                <br>
                <button type="submit" class="cyber-btn" style="width: 100%; font-size: 1.2rem;">DECRYPT & ENTER</button>
            </form>
            {% if error %} 
                <p style="color: var(--red); margin-top: 20px; font-weight: bold; border: 1px solid var(--red); padding: 5px;">
                    ⚠️ ACCESS DENIED: INVALID TOKEN
                </p> 
            {% endif %}
        </div>
        <div style="position: absolute; bottom: 20px; color: var(--gray); font-size: 0.8rem;">
            SYSTEM V.2.0.77 // SECURE CONNECTION
        </div>
    </div>

{% else %}
    <!-- DASHBOARD -->
    <div class="container">
        <header style="display:flex; justify-content:space-between; align-items:center; border-bottom: 2px solid var(--yellow); padding-bottom: 20px; margin-bottom: 20px; background: rgba(0,0,0,0.5); padding: 20px;">
            <div>
                <h1 style="margin:0; font-size: 2.5rem; color: var(--yellow); text-shadow: 2px 2px 0px var(--red);">CONTROL_PANEL</h1>
                <small style="color: var(--cyan); letter-spacing: 1px;">TARGET: {{ bot_name }}</small>
            </div>
            <div>
                <span class="status-badge {{ 'online' if bot_status else 'offline' }}">{{ 'SYSTEM ONLINE' if bot_status else 'SYSTEM OFFLINE' }}</span>
                <a href="/logout" class="tiny-btn" style="margin-left: 20px; border-color: var(--red); color: var(--red);">DISCONNECT</a>
            </div>
        </header>

        <div class="dashboard-grid">
            <!-- LEFT: STATS & CONTROLS -->
            <div class="sidebar">
                <div class="panel">
                    <h2>SYSTEM_STATS</h2>
                    <div id="stats-container">
                        <div class="stat-item"><span>MEMORY</span><span class="stat-val" id="ram">...</span></div>
                        <div class="stat-item"><span>LATENCY</span><span class="stat-val" id="ping">...</span></div>
                        <div class="stat-item"><span>DATABASE</span><span class="stat-val" id="data">...</span></div>
                        <div class="stat-item"><span>GUILDS</span><span class="stat-val" id="guilds">...</span></div>
                    </div>
                </div>

                <div class="panel">
                    <h2>MAIN_FRAME</h2>
                    <form action="/bot_action" method="POST">
                        <input type="hidden" name="action" value="shutdown">
                        <button type="submit" class="cyber-btn danger" style="width:100%;" onclick="return confirm('WARNING: CRITICAL ACTION. CONFIRM SHUTDOWN?')">❌ KILL PROCESS</button>
                    </form>
                </div>

                <div class="panel">
                    <h2>ADMIN_LIST</h2>
                    <form action="/manage_owner" method="POST" style="display:flex; gap:5px; margin-bottom: 10px;">
                        <input type="text" name="user_id" placeholder="USER ID ONLY" pattern="\d+" title="กรุณากรอกตัวเลขเท่านั้น" class="cyber-input" style="text-align:left; font-size:0.9rem;" required>
                        <button name="op" value="add" class="tiny-btn" style="color:lime; border-color:lime;">ADD</button>
                    </form>
                    <div style="max-height: 200px; overflow-y: auto;">
                        {% for owner in owners %}
                        <div class="owner-item">
                            <div>
                                <span style="color:var(--yellow); display:block; font-weight:bold;">{{ owner.name }}</span>
                                <small style="color:var(--gray); font-family:monospace;">ID: {{ owner.id }}</small>
                            </div>
                            <form action="/manage_owner" method="POST" style="margin:0;">
                                <input type="hidden" name="user_id" value="{{ owner.id }}">
                                <button name="op" value="del" class="tiny-btn" style="color:red; border:none;">X</button>
                            </form>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>

            <!-- CENTER: SERVER LIST -->
            <div class="main-content">
                <div class="panel" style="border-left-color: var(--cyan);">
                    <div style="display:flex; justify-content:space-between; align-items:center; border-bottom: 2px solid var(--cyan); margin-bottom: 15px; padding-bottom:5px;">
                        <h2 style="border:none; margin:0; padding:0;">NETWORK_NODES</h2>
                        <small style="color:var(--text);">TOTAL: {{ servers|length }}</small>
                    </div>
                    
                    <div class="scrollable-list">
                        {% for guild in servers %}
                        <div class="server-card">
                            <div class="server-info">
                                <h3>{{ guild.name }}</h3>
                                <small style="font-family:monospace; color:var(--cyan);">ID: {{ guild.id }}</small> | 
                                <small style="color:var(--yellow);">Users: {{ guild.member_count }}</small><br>
                                <small style="color:var(--gray);">Owner: {{ guild.owner }}</small>
                            </div>
                            <div class="server-actions">
                                <form action="/server_action" method="POST" target="_blank" style="display:inline;">
                                    <input type="hidden" name="guild_id" value="{{ guild.id }}">
                                    <input type="hidden" name="action" value="invite">
                                    <button type="submit" class="tiny-btn">LINK</button>
                                </form>
                                <form action="/server_action" method="POST" style="display:inline;">
                                    <input type="hidden" name="guild_id" value="{{ guild.id }}">
                                    <input type="hidden" name="action" value="delete_data">
                                    <button type="submit" class="tiny-btn" style="color:orange;" onclick="return confirm('WIPE DATA for this server?')">WIPE</button>
                                </form>
                                <form action="/server_action" method="POST" style="display:inline;">
                                    <input type="hidden" name="guild_id" value="{{ guild.id }}">
                                    <input type="hidden" name="action" value="leave">
                                    <button type="submit" class="tiny-btn" style="color:red;" onclick="return confirm('DISCONNECT from server?')">EXIT</button>
                                </form>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>

            <!-- RIGHT: LOGS -->
            <div class="right-bar">
                <div class="panel">
                    <h2>EVENT_LOGS</h2>
                    <div class="log-console" id="log-display">
                        {% for log in logs %}
                            <div class="log-entry">> {{ log }}</div>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function updateStats() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    if(data.error) return;
                    document.getElementById('ram').innerText = data.ram;
                    document.getElementById('ping').innerText = data.ping;
                    document.getElementById('data').innerText = data.data_size;
                    document.getElementById('guilds').innerText = data.guild_count;
                })
                .catch(err => console.log('Stats error:', err));
        }
        // Initial call and Auto-refresh every 60s
        updateStats();
        setInterval(updateStats, 60000); 
    </script>
{% endif %}

</body>
</html>
"""

# --- Routes ---

@app.route('/', methods=['GET', 'POST'])
def login():
    error = False
    if request.method == 'POST':
        if request.form.get('passcode') == PASSWORD:
            session['auth'] = True
            log_action("Admin logged in via Web Interface.")
            return redirect('/dashboard')
        else:
            error = True
            log_action("Failed login attempt (Wrong Passcode).")
    
    return render_template_string(HTML_TEMPLATE, error=error)

@app.route('/dashboard')
def dashboard():
    if not session.get('auth'): return redirect('/')
    
    servers = []
    bot_name = "System Offline"
    bot_status = False
    owners_list = []

    # Get Owners Info
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                owner_ids = data.get('owners', [])
                
                # Fetch usernames if bot is ready
                if bot_instance and bot_instance.is_ready():
                    for uid in owner_ids:
                        user = bot_instance.get_user(uid)
                        name = user.name if user else "Unknown User"
                        owners_list.append({"id": uid, "name": name})
                else:
                    # Fallback if bot offline
                    owners_list = [{"id": uid, "name": "Fetching..."} for uid in owner_ids]
        except: pass

    if bot_instance and bot_instance.is_ready():
        bot_name = bot_instance.user.name
        bot_status = True
        for guild in bot_instance.guilds:
            servers.append({
                "id": guild.id,
                "name": guild.name,
                "member_count": guild.member_count,
                "owner": str(guild.owner)
            })
    
    return render_template_string(HTML_TEMPLATE, 
                                  bot_name=bot_name, 
                                  bot_status=bot_status, 
                                  servers=servers,
                                  owners=owners_list,
                                  logs=system_logs)

@app.route('/logout')
def logout():
    session.pop('auth', None)
    return redirect('/')

@app.route('/api/stats')
def api_stats():
    if not session.get('auth'): return jsonify({"error": "Unauthorized"}), 401
    stats = get_bot_stats()
    if stats: return jsonify(stats)
    return jsonify({"error": "Bot Offline"}), 503

async def create_or_get_invite(guild):
    try:
        invites = await guild.invites()
        for invite in invites:
            return invite.url, f"{invite.inviter} (Existing)"
        
        if guild.text_channels:
            invite = await guild.text_channels[0].create_invite(max_age=300)
            return invite.url, f"{bot_instance.user.name} (New)"
    except Exception as e:
        return "#", f"Error: {e}"
    return "#", "No channels found"

@app.route('/server_action', methods=['POST'])
def server_action():
    if not session.get('auth'): return redirect('/')
    
    guild_id = int(request.form.get('guild_id'))
    action = request.form.get('action')
    guild = bot_instance.get_guild(guild_id)
    
    if action == 'leave':
        if guild:
            asyncio.run_coroutine_threadsafe(guild.leave(), bot_instance.loop)
            log_action(f"Left server: {guild.name} ({guild.id})")
        return redirect('/dashboard')

    elif action == 'delete_data':
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            sid = str(guild_id)
            if "guilds" in data and sid in data["guilds"]:
                del data["guilds"][sid]
                # Optional: Delete active auctions/tickets related to this guild if needed
                
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                log_action(f"Wiped data for server ID: {guild_id}")
            else:
                log_action(f"No data found to wipe for server ID: {guild_id}")
        except Exception as e:
            log_action(f"Data Wipe Error: {e}")
        return redirect('/dashboard')

    elif action == 'invite':
        if guild:
            future = asyncio.run_coroutine_threadsafe(create_or_get_invite(guild), bot_instance.loop)
            try:
                invite_url, creator = future.result(timeout=5)
                # Redirect script
                return f"""
                <style>body{{background:black; color:#0f0; font-family:monospace; display:flex; justify-content:center; align-items:center; height:100vh;}}</style>
                <div>
                    <h1>>> CONNECTION ESTABLISHED</h1>
                    <p>Redirecting to target node...</p>
                    <p>Link Source: {creator}</p>
                </div>
                <script>setTimeout(function(){{ window.location.href='{invite_url}'; }}, 1500);</script>
                """
            except Exception as e:
                return f"Error creating invite: {e}"
        return "Guild not found"
        
    return redirect('/dashboard')

@app.route('/manage_owner', methods=['POST'])
def manage_owner():
    if not session.get('auth'): return redirect('/')
    user_id = request.form.get('user_id')
    op = request.form.get('op')
    
    # Validation: Ensure it's digits
    if not user_id or not user_id.isdigit(): 
        log_action("Invalid User ID format entered.")
        return redirect('/dashboard')
    
    user_id = int(user_id)

    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if 'owners' not in data: data['owners'] = []
        
        if op == 'add':
            if user_id not in data['owners']:
                data['owners'].append(user_id)
                log_action(f"Added new owner ID: {user_id}")
        elif op == 'del':
            if user_id in data['owners']:
                data['owners'].remove(user_id)
                log_action(f"Removed owner ID: {user_id}")
        
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
            
    except Exception as e:
        log_action(f"Owner config error: {e}")

    return redirect('/dashboard')

@app.route('/bot_action', methods=['POST'])
def bot_action():
    if not session.get('auth'): return redirect('/')
    action = request.form.get('action')
    if action == 'shutdown':
        log_action("⚠️ SYSTEM SHUTDOWN INITIATED BY ADMIN.")
        if bot_instance:
            asyncio.run_coroutine_threadsafe(bot_instance.close(), bot_instance.loop)
        os._exit(0)
    return redirect('/dashboard')

def run_flask(bot):
    global bot_instance
    bot_instance = bot
    app.run(host='0.0.0.0', port=8080)

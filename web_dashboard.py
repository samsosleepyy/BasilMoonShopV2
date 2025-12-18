import discord
from flask import Flask, render_template_string, request, redirect, session, jsonify, url_for
import threading
import asyncio
import psutil
import os
import time
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

# Global variables to store bot reference and logs
bot_instance = None
system_logs = []

def log_action(action):
    """บันทึก Log การทำงาน"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {action}"
    system_logs.insert(0, log_entry) # Add to top
    if len(system_logs) > 50: # Keep last 50 logs
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

# --- HTML Template (Cyberpunk Style) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NETRUNNER CONTROL_PANEL // V.2.0.77</title>
    <link href="[https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&display=swap](https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&display=swap)" rel="stylesheet">
    <style>
        :root {
            --yellow: #fcee0a;
            --cyan: #00f0ff;
            --red: #ff003c;
            --black: #050505;
            --gray: #1a1a1a;
            --text: #e0e0e0;
        }
        
        * { box-sizing: border-box; }
        
        body {
            background-color: var(--black);
            color: var(--text);
            font-family: 'Rajdhani', sans-serif;
            margin: 0;
            padding: 0;
            background-image: 
                linear-gradient(rgba(5, 5, 5, 0.9), rgba(5, 5, 5, 0.9)),
                url('[https://media.giphy.com/media/uYe2emzTECyHu/giphy.gif](https://media.giphy.com/media/uYe2emzTECyHu/giphy.gif)'); /* Optional BG */
            background-size: cover;
            overflow-x: hidden;
        }

        /* --- Glitch Effect Class --- */
        .glitch {
            position: relative;
            color: var(--yellow);
        }
        .glitch::before, .glitch::after {
            content: attr(data-text);
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }
        .glitch::before {
            left: 2px;
            text-shadow: -1px 0 var(--red);
            clip: rect(24px, 550px, 90px, 0);
            animation: glitch-anim-2 3s infinite linear alternate-reverse;
        }
        .glitch::after {
            left: -2px;
            text-shadow: -1px 0 var(--cyan);
            clip: rect(85px, 550px, 140px, 0);
            animation: glitch-anim 2.5s infinite linear alternate-reverse;
        }

        @keyframes glitch-anim {
            0% { clip: rect(10px, 9999px, 30px, 0); }
            20% { clip: rect(80px, 9999px, 100px, 0); }
            100% { clip: rect(0, 9999px, 20px, 0); }
        }
        @keyframes glitch-anim-2 {
            0% { clip: rect(60px, 9999px, 90px, 0); }
            20% { clip: rect(10px, 9999px, 50px, 0); }
            100% { clip: rect(30px, 9999px, 70px, 0); }
        }

        /* --- Layout --- */
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        /* --- Login Screen --- */
        .login-wrapper {
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }
        .cyber-input {
            background: var(--black);
            border: 2px solid var(--cyan);
            color: var(--yellow);
            padding: 15px;
            font-size: 1.5rem;
            font-family: 'Rajdhani';
            text-align: center;
            width: 300px;
            outline: none;
            box-shadow: 0 0 10px var(--cyan);
            clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
        }
        .cyber-btn {
            background: var(--yellow);
            color: var(--black);
            border: none;
            padding: 10px 30px;
            font-size: 1.2rem;
            font-weight: bold;
            font-family: 'Rajdhani';
            margin-top: 20px;
            cursor: pointer;
            clip-path: polygon(20px 0, 100% 0, 100% calc(100% - 20px), calc(100% - 20px) 100%, 0 100%, 0 20px);
            transition: all 0.3s;
        }
        .cyber-btn:hover {
            background: var(--cyan);
            box-shadow: 5px 5px 0px var(--red);
            transform: translate(-2px, -2px);
        }
        .cyber-btn.danger { background: var(--red); color: white; }
        .cyber-btn.danger:hover { background: darkred; }

        /* --- Dashboard Grid --- */
        .dashboard-grid {
            display: grid;
            grid-template-columns: 250px 1fr 300px;
            gap: 20px;
            margin-top: 30px;
        }
        
        .panel {
            background: rgba(10, 10, 10, 0.8);
            border: 1px solid var(--gray);
            border-left: 4px solid var(--yellow);
            padding: 20px;
            margin-bottom: 20px;
            position: relative;
        }
        .panel::before {
            content: "SYSTEM_MODULE";
            position: absolute;
            top: -10px;
            right: 10px;
            background: var(--yellow);
            color: var(--black);
            padding: 2px 5px;
            font-size: 0.8rem;
            font-weight: bold;
        }

        h2 { border-bottom: 2px solid var(--red); padding-bottom: 5px; color: var(--cyan); text-transform: uppercase; }

        /* --- Stats Box --- */
        .stat-item {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            border-bottom: 1px dashed var(--gray);
            padding-bottom: 5px;
        }
        .stat-val { color: var(--yellow); font-weight: bold; }

        /* --- Server List --- */
        .server-card {
            background: rgba(30,30,30,0.6);
            border: 1px solid var(--cyan);
            padding: 15px;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .server-info h3 { margin: 0; color: var(--yellow); }
        .server-actions { display: flex; gap: 10px; }
        .tiny-btn {
            background: transparent;
            border: 1px solid var(--text);
            color: var(--text);
            padding: 5px 10px;
            cursor: pointer;
            font-size: 0.9rem;
        }
        .tiny-btn:hover { background: var(--cyan); color: var(--black); }

        /* --- Logs --- */
        .log-console {
            background: black;
            color: lime;
            font-family: monospace;
            height: 300px;
            overflow-y: scroll;
            padding: 10px;
            border: 1px solid var(--gray);
            font-size: 0.9rem;
        }
        .log-entry { margin-bottom: 5px; border-bottom: 1px solid #111; }

        /* --- Toggle Switch --- */
        .status-badge {
            padding: 5px 15px;
            font-weight: bold;
            text-transform: uppercase;
        }
        .online { background: #0f0; color: black; box-shadow: 0 0 10px #0f0; }
        .offline { background: #f00; color: white; box-shadow: 0 0 10px #f00; }

        /* --- Responsive --- */
        @media (max-width: 1000px) {
            .dashboard-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>

{% if not session.get('auth') %}
    <!-- LOGIN SCREEN -->
    <div class="login-wrapper">
        <h1 class="glitch" data-text="ACCESS CONTROL">ACCESS CONTROL</h1>
        <form method="POST" action="/login">
            <input type="password" name="passcode" class="cyber-input" placeholder="ENTER PASSCODE" maxlength="6" autofocus required>
            <br>
            <button type="submit" class="cyber-btn">AUTHENTICATE</button>
        </form>
        {% if error %}
            <p style="color: var(--red); margin-top: 20px;">>> ACCESS DENIED: INVALID PASSCODE</p>
        {% endif %}
    </div>

{% else %}
    <!-- DASHBOARD -->
    <div class="container">
        <header style="display:flex; justify-content:space-between; align-items:center; border-bottom: 2px solid var(--yellow); padding-bottom: 20px; margin-bottom: 20px;">
            <div>
                <h1 class="glitch" data-text="NETRUNNER_DASHBOARD" style="margin:0; font-size: 2.5rem;">NETRUNNER_DASHBOARD</h1>
                <small style="color: var(--cyan);">CONNECTED TO: {{ bot_name }}</small>
            </div>
            <div>
                <span class="status-badge {{ 'online' if bot_status else 'offline' }}">
                    {{ 'SYSTEM ONLINE' if bot_status else 'SYSTEM OFFLINE' }}
                </span>
                <a href="/logout" class="tiny-btn" style="margin-left: 20px;">LOGOUT</a>
            </div>
        </header>

        <div class="dashboard-grid">
            <!-- LEFT PANEL: STATS & CONTROLS -->
            <div class="sidebar">
                <div class="panel">
                    <h2>SYSTEM STATUS</h2>
                    <div id="stats-container">
                        <div class="stat-item"><span>RAM USAGE</span><span class="stat-val" id="ram">Loading...</span></div>
                        <div class="stat-item"><span>PING</span><span class="stat-val" id="ping">Loading...</span></div>
                        <div class="stat-item"><span>DATA SIZE</span><span class="stat-val" id="data">Loading...</span></div>
                        <div class="stat-item"><span>SERVERS</span><span class="stat-val" id="guilds">Loading...</span></div>
                    </div>
                    <small style="color:var(--gray);">*Updates every 1 hour (Auto)</small>
                </div>

                <div class="panel">
                    <h2>MAIN CONTROL</h2>
                    <form action="/bot_action" method="POST">
                        <input type="hidden" name="action" value="shutdown">
                        <button type="submit" class="cyber-btn danger" style="width:100%;" onclick="return confirm('WARNING: This will shutdown the bot process. The website might go down too.')">SHUTDOWN BOT</button>
                    </form>
                </div>

                <div class="panel">
                    <h2>MANAGE OWNERS</h2>
                    <form action="/manage_owner" method="POST" style="display:flex; gap:5px;">
                        <input type="text" name="user_id" placeholder="User ID" style="background:black; border:1px solid var(--cyan); color:white; width: 70%;">
                        <button name="op" value="add" class="tiny-btn" style="color:lime;">+</button>
                        <button name="op" value="del" class="tiny-btn" style="color:red;">-</button>
                    </form>
                    <div style="margin-top:10px;">
                        <strong>Current Owners:</strong><br>
                        <div id="owner-list" style="font-size:0.8rem; color:var(--yellow);">
                            {% for owner in owners %}
                                > {{ owner }}<br>
                            {% endfor %}
                        </div>
                    </div>
                </div>
            </div>

            <!-- CENTER PANEL: SERVER LIST -->
            <div class="main-content">
                <div class="panel" style="border-left-color: var(--cyan);">
                    <h2>CONNECTED SERVERS</h2>
                    {% for guild in servers %}
                    <div class="server-card">
                        <div class="server-info">
                            <h3>{{ guild.name }}</h3>
                            <small>ID: {{ guild.id }} | Members: {{ guild.member_count }}</small><br>
                            <small style="color:var(--gray);">Owner: {{ guild.owner }}</small>
                        </div>
                        <div class="server-actions">
                            <form action="/server_action" method="POST" target="_blank" style="display:inline;">
                                <input type="hidden" name="guild_id" value="{{ guild.id }}">
                                <input type="hidden" name="action" value="invite">
                                <button type="submit" class="tiny-btn">GENERATE LINK</button>
                            </form>
                            
                            <form action="/server_action" method="POST" style="display:inline;">
                                <input type="hidden" name="guild_id" value="{{ guild.id }}">
                                <input type="hidden" name="action" value="delete_data">
                                <button type="submit" class="tiny-btn" style="border-color:orange; color:orange;" onclick="return confirm('Confirm DELETE DATA for this server?')">DEL DATA</button>
                            </form>

                            <form action="/server_action" method="POST" style="display:inline;">
                                <input type="hidden" name="guild_id" value="{{ guild.id }}">
                                <input type="hidden" name="action" value="leave">
                                <button type="submit" class="tiny-btn" style="border-color:red; color:red;" onclick="return confirm('Confirm LEAVE server?')">LEAVE</button>
                            </form>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>

            <!-- RIGHT PANEL: LOGS -->
            <div class="right-bar">
                <div class="panel">
                    <h2>SYSTEM LOGS</h2>
                    <div class="log-console" id="log-display">
                        {% for log in logs %}
                            <div class="log-entry">{{ log }}</div>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Auto Update Stats (Every 1 Hour = 3600000ms, but for demo let's do 60s, user asked 1hr)
        // User requested "update every 1 hr", I will set interval to 3600 * 1000
        
        function updateStats() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    if(data.error) return;
                    document.getElementById('ram').innerText = data.ram;
                    document.getElementById('ping').innerText = data.ping;
                    document.getElementById('data').innerText = data.data_size;
                    document.getElementById('guilds').innerText = data.guild_count;
                });
        }

        // Update immediately on load
        updateStats();
        // Update every 1 hour as requested
        setInterval(updateStats, 3600000); 
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
            log_action("Admin logged in via Web.")
            return redirect('/dashboard')
        else:
            error = True
            log_action("Failed login attempt.")
    
    return render_template_string(HTML_TEMPLATE, error=error)

@app.route('/dashboard')
def dashboard():
    if not session.get('auth'): return redirect('/')
    
    # Gather Data
    servers = []
    bot_name = "System Offline"
    bot_status = False
    current_owners = []

    # Load Owners from JSON
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Assuming data structure from previous cogs...
                # We need a root 'owners' list or fallback to config
                # Since we don't have exact owner structure, I'll assume standard list
                current_owners = data.get('owners', [])
                if not current_owners and 'guilds' in data: # Try to find admins in guilds if structure is nested
                     pass # Complex structure, leave empty or customize based on your data.json
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
                                  owners=current_owners,
                                  logs=system_logs)

@app.route('/logout')
def logout():
    session.pop('auth', None)
    return redirect('/')

@app.route('/api/stats')
def api_stats():
    if not session.get('auth'): return jsonify({"error": "Unauthorized"}), 401
    stats = get_bot_stats()
    if stats:
        return jsonify(stats)
    return jsonify({"error": "Bot Offline"}), 503

@app.route('/server_action', methods=['POST'])
def server_action():
    if not session.get('auth'): return redirect('/')
    
    guild_id = int(request.form.get('guild_id'))
    action = request.form.get('action')
    
    guild = bot_instance.get_guild(guild_id)
    
    if action == 'leave':
        if guild:
            asyncio.run_coroutine_threadsafe(guild.leave(), bot_instance.loop)
            log_action(f"Left server: {guild.name}")
        return redirect('/dashboard')

    elif action == 'delete_data':
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Logic to delete data for specific guild
            # Assuming structure data['guilds'][str(guild_id)] based on previous cogs
            sid = str(guild_id)
            if "guilds" in data and sid in data["guilds"]:
                del data["guilds"][sid]
                # Also clean active auctions/tickets if linked by channel ID (Complex, skipping for safety)
                
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                log_action(f"Deleted data for server ID: {guild_id}")
            else:
                log_action(f"No data found for server ID: {guild_id}")
        except Exception as e:
            log_action(f"Error deleting data: {e}")
        return redirect('/dashboard')

    elif action == 'invite':
        if guild:
            # Run async function in bot loop and wait for result is tricky in Flask
            # We will fire and forget or use a future, but for redirecting to link

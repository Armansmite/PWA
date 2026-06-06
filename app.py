import os
import json
import pickle
import base64
from flask import Flask, request, jsonify

app = Flask(__name__)

settings_data = {
    "total_duration": 7,
    "fade_duration": 2,
    "max_quote_len": 50,
    "slots": ["05:30", "11:30", "17:30", "23:30"],
    "base_tags": "shorts, quotes, motivation, wisdom",
    "description_extra": "💡 Quote of the day | Motivational quotes | Motivational speech | Motivational video | Understanding politics",
    "category_id": "22"
}
credentials = None
log_messages = []

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

# ---------- FIX: Return the HTML directly ----------
@app.route('/')
def index():
    return DASHBOARD_HTML

@app.route('/frontend')
def frontend():
    return DASHBOARD_HTML

# ---------- API routes (unchanged) ----------
@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    global settings_data
    if request.method == 'POST':
        settings_data = request.get_json()
        return jsonify({'status': 'ok'})
    return jsonify(settings_data)

@app.route('/api/log', methods=['GET', 'POST'])
def handle_log():
    global log_messages
    if request.method == 'POST':
        msg = request.get_json().get('message', '')
        log_messages.append(msg)
        if len(log_messages) > 200:
            log_messages.pop(0)
        return jsonify({'status': 'ok'})
    return jsonify(log_messages)

@app.route('/api/auth/upload_client_secret', methods=['POST'])
def upload_client_secret():
    return jsonify({'error': 'Auth not implemented on server. Use the Colab notebook for authentication.'}), 501

@app.route('/api/auth/authenticate', methods=['POST'])
def authenticate():
    return jsonify({'error': 'Auth not implemented on server.'}), 501

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    global credentials
    if not credentials:
        return jsonify({'status': 'none'})
    return jsonify({'status': 'valid' if credentials.valid else 'invalid'})

@app.route('/api/export', methods=['GET'])
def export_config():
    global settings_data, credentials
    creds_bytes = pickle.dumps(credentials) if credentials else b''
    return jsonify({
        'settings': settings_data,
        'credentials_b64': base64.b64encode(creds_bytes).decode('utf-8')
    })

@app.route('/api/import', methods=['POST'])
def import_config():
    global settings_data, credentials
    data = request.get_json()
    if 'settings' in data:
        settings_data = data['settings']
    if 'credentials_b64' in data:
        creds_bytes = base64.b64decode(data['credentials_b64'])
        credentials = pickle.loads(creds_bytes)
    return jsonify({'status': 'imported', 'settings': settings_data})

# ---------- Dashboard HTML (same as before, just assign to DASHBOARD_HTML) ----------
DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>YouTube Shorts Bot</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  :root {
    --bg: #0a0a1a;
    --surface: rgba(20, 20, 40, 0.7);
    --blur: blur(20px);
    --primary: #7c5dfa;
    --primary-hover: #6a4cf0;
    --accent: #00d4aa;
    --danger: #ff4d6a;
    --text: #eaeaea;
    --muted: #a0a0b0;
    --border-radius: 16px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: linear-gradient(135deg, #0a0a1a 0%, #1a0a2e 100%);
    font-family: 'Inter', sans-serif;
    color: var(--text);
    display: flex;
    justify-content: center;
    padding: 20px;
    min-height: 100vh;
    align-items: center;
  }
  .container {
    width: 100%;
    max-width: 960px;
    background: var(--surface);
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    border-radius: 28px;
    padding: 30px;
    box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
    border: 1px solid rgba(255,255,255,0.08);
  }
  h1 {
    text-align: center;
    font-weight: 700;
    font-size: 2.2rem;
    margin-bottom: 5px;
    background: linear-gradient(135deg, #7c5dfa, #00d4aa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .tabs {
    display: flex;
    gap: 8px;
    background: rgba(255,255,255,0.04);
    padding: 6px;
    border-radius: 14px;
    margin: 25px 0;
  }
  .tab {
    flex: 1;
    padding: 12px;
    text-align: center;
    cursor: pointer;
    border-radius: 10px;
    font-weight: 500;
    transition: all 0.3s;
    color: var(--muted);
  }
  .tab.active { background: var(--primary); color: white; box-shadow: 0 8px 20px -8px var(--primary); }
  .tab:not(.active):hover { background: rgba(255,255,255,0.06); color: white; }
  .panel {
    background: rgba(255,255,255,0.02);
    border-radius: var(--border-radius);
    padding: 25px;
    border: 1px solid rgba(255,255,255,0.05);
    display: none;
    animation: fade 0.3s ease;
  }
  .panel.active { display: block; }
  @keyframes fade { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  .card {
    background: rgba(255,255,255,0.03);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
  }
  .row { display: flex; gap: 20px; flex-wrap: wrap; }
  .col { flex: 1; min-width: 180px; }
  label {
    display: block;
    margin-bottom: 6px;
    font-weight: 500;
    color: var(--muted);
    font-size: 0.9rem;
  }
  input, textarea, button {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 10px;
    color: white;
    padding: 12px 16px;
    font-size: 0.95rem;
    width: 100%;
    transition: 0.2s;
    outline: none;
  }
  input:focus, textarea:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(124,93,250,0.2); }
  button {
    background: var(--primary);
    border: none;
    cursor: pointer;
    font-weight: 600;
    letter-spacing: 0.5px;
    transition: all 0.3s;
    box-shadow: 0 4px 15px rgba(124,93,250,0.3);
  }
  button:hover { background: var(--primary-hover); transform: translateY(-2px); box-shadow: 0 8px 25px rgba(124,93,250,0.4); }
  .log-box {
    background: rgba(0,0,0,0.3);
    border-radius: 12px;
    padding: 18px;
    height: 300px;
    overflow-y: auto;
    font-family: 'Fira Code', monospace;
    font-size: 0.85rem;
    white-space: pre-wrap;
    line-height: 1.6;
    border: 1px solid rgba(255,255,255,0.05);
  }
  .status-badge {
    display: inline-block;
    padding: 5px 14px;
    border-radius: 20px;
    font-weight: 600;
    font-size: 0.8rem;
  }
  .badge-green { background: #00c853; color: white; }
  .badge-yellow { background: #ffd600; color: black; }
  .badge-red { background: #ff1744; color: white; }
  .inline { display: flex; gap: 10px; align-items: center; }
  .mt-1 { margin-top: 12px; }
  .mt-2 { margin-top: 24px; }
  .time-slot-row {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-bottom: 8px;
  }
  .time-slot-row input { width: 120px; }
  .time-slot-row button {
    background: rgba(255,77,106,0.2);
    border: 1px solid rgba(255,77,106,0.3);
    padding: 8px 12px;
    font-size: 0.9rem;
    box-shadow: none;
    width: auto;
  }
  .time-slot-row button:hover { background: var(--danger); }
  .add-btn {
    background: var(--accent) !important;
    box-shadow: 0 4px 15px rgba(0,212,170,0.3) !important;
    margin-top: 10px;
  }
  .add-btn:hover { background: #00e6b0 !important; }
</style>
</head>
<body>
<div class="container">
  <h1>🎬 YouTube Shorts Bot</h1>
  <div class="tabs">
    <div class="tab active" onclick="switchTab('settings')">⚙️ Settings</div>
    <div class="tab" onclick="switchTab('log')">📋 Log</div>
  </div>

  <div id="panel-settings" class="panel active">
    <div class="card">
      <h3>⏱️ Video</h3>
      <div class="row">
        <div class="col">
          <label>Duration (seconds)</label>
          <input type="number" id="total_duration" value="7" min="5" max="15">
        </div>
        <div class="col">
          <label>Fade-in (seconds)</label>
          <input type="number" id="fade_duration" value="2" min="0.5" max="3" step="0.1">
        </div>
        <div class="col">
          <label>Max quote length</label>
          <input type="number" id="max_quote_len" value="50" min="30" max="100">
        </div>
      </div>
    </div>

    <div class="card">
      <h3>📅 Upload Slots (UTC)</h3>
      <div id="slotsContainer"></div>
      <button type="button" class="add-btn" onclick="addSlot()">+ Add Slot</button>
    </div>

    <div class="card">
      <h3>🏷️ Tags & Description</h3>
      <label>Base Tags (comma separated)</label>
      <input type="text" id="base_tags" value="shorts, quotes, motivation, wisdom">
      <label class="mt-1">Extra Description Line</label>
      <textarea id="description_extra" rows="2">💡 Quote of the day | Motivational quotes | Motivational speech | Motivational video | Understanding politics</textarea>
      <label class="mt-1">Category ID</label>
      <input type="text" id="category_id" value="22">
    </div>
    <button type="button" onclick="saveSettings()">💾 Save Settings</button>
    <p class="mt-1" style="color:var(--muted); font-size:0.85rem;">These settings will be used when you run the Colab notebook.</p>
  </div>

  <div id="panel-log" class="panel">
    <div class="log-box" id="logBox"></div>
    <button type="button" onclick="refreshLog()" class="mt-1">🔄 Refresh Log</button>
  </div>
</div>

<script>
  let timeSlots = ["05:30", "11:30", "17:30", "23:30"];

  function renderSlots() {
    const container = document.getElementById('slotsContainer');
    container.innerHTML = timeSlots.map((slot, index) => `
      <div class="time-slot-row">
        <input type="time" value="${slot}" onchange="updateSlot(${index}, this.value)">
        <button type="button" onclick="removeSlot(${index})" style="width:auto;">✕</button>
      </div>
    `).join('');
  }

  function addSlot() { timeSlots.push("12:00"); renderSlots(); }
  function removeSlot(index) { if (timeSlots.length <= 1) return; timeSlots.splice(index, 1); renderSlots(); }
  function updateSlot(index, value) { timeSlots[index] = value; }
  renderSlots();

  function switchTab(tab) {
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById('panel-' + tab).classList.add('active');
    event.target.classList.add('active');
  }

  function saveSettings() {
    const settings = {
      total_duration: parseFloat(document.getElementById('total_duration').value),
      fade_duration: parseFloat(document.getElementById('fade_duration').value),
      max_quote_len: parseInt(document.getElementById('max_quote_len').value),
      slots: timeSlots,
      base_tags: document.getElementById('base_tags').value,
      description_extra: document.getElementById('description_extra').value,
      category_id: document.getElementById('category_id').value
    };
    fetch('/api/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(settings)
    }).then(() => alert('Settings saved!'));
  }

  function refreshLog() {
    fetch('/api/log')
      .then(r => r.json())
      .then(lines => {
        document.getElementById('logBox').textContent = lines.join('\n');
      });
  }
  refreshLog();
  setInterval(refreshLog, 5000);
</script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

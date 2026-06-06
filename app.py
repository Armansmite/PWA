import os
import json
import pickle
import base64
import io
from flask import Flask, request, jsonify, send_file

# For OAuth (google-auth)
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

app = Flask(__name__)

# ---------- In‑memory storage (persistent for the lifetime of the server) ----------
settings_data = {
    "total_duration": 7,
    "fade_duration": 2,
    "max_quote_len": 50,
    "slots": ["05:30", "11:30", "17:30", "23:30"],
    "base_tags": "shorts, quotes, motivation, wisdom",
    "description_extra": "💡 Quote of the day | Motivational quotes | Motivational speech | Motivational video | Understanding politics",
    "category_id": "22"
}

token_bytes = None            # raw bytes of token.pickle
quote_bytes = None            # raw bytes of quote.txt
images_zip = None             # ZIP file of images/
music_zip = None              # ZIP file of music/
log_messages = []
oauth_flow = None             # holds the InstalledAppFlow during auth

# ---------- CORS ----------
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

# ---------- FRONTEND ----------
@app.route('/')
def index():
    return FULL_DASHBOARD_HTML

# ---------- SETTINGS API ----------
@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    global settings_data
    if request.method == 'POST':
        settings_data = request.get_json()
        return jsonify({'status': 'ok'})
    return jsonify(settings_data)

# ---------- AUTH ----------
@app.route('/api/auth/upload_client_secret', methods=['POST'])
def upload_client_secret():
    global oauth_flow
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    filepath = '/tmp/client_secret.json'
    file.save(filepath)
    try:
        flow = InstalledAppFlow.from_client_secrets_file(filepath, [
            'https://www.googleapis.com/auth/youtube.upload',
            'https://www.googleapis.com/auth/youtube.readonly'
        ])
        flow.redirect_uri = 'http://localhost:8080'
        auth_url, _ = flow.authorization_url(prompt='consent')
        oauth_flow = flow
        return jsonify({'auth_url': auth_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/authenticate', methods=['POST'])
def authenticate():
    global token_bytes, oauth_flow
    raw = request.get_json().get('code', '')
    if 'code=' in raw:
        raw = raw.split('code=')[1].split('&')[0]
    if not oauth_flow:
        return jsonify({'error': 'No client_secret uploaded yet'}), 400
    try:
        oauth_flow.fetch_token(code=raw)
        creds = oauth_flow.credentials
        # Test credentials
        service = build('youtube', 'v3', credentials=creds)
        service.channels().list(part='id', mine=True).execute()
        # Save token
        token_bytes = pickle.dumps(creds)
        oauth_flow = None
        # Return config so user can download immediately
        config = {
            'settings': settings_data,
            'credentials_b64': base64.b64encode(token_bytes).decode('utf-8')
        }
        return jsonify({'status': 'authenticated', 'config': config})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    global token_bytes
    if not token_bytes:
        return jsonify({'status': 'none'})
    creds = pickle.loads(token_bytes)
    if creds.valid:
        return jsonify({'status': 'valid'})
    elif creds.expired and creds.refresh_token:
        return jsonify({'status': 'expired_refreshable'})
    else:
        return jsonify({'status': 'invalid'})

@app.route('/api/token')
def download_token():
    global token_bytes
    if not token_bytes:
        return jsonify({'error': 'No token uploaded'}), 404
    return send_file(io.BytesIO(token_bytes), mimetype='application/octet-stream',
                     as_attachment=True, download_name='token.pickle')

# ---------- FILE UPLOADS (optional, for overriding GitHub files) ----------
@app.route('/api/upload-quote', methods=['POST'])
def upload_quote():
    global quote_bytes
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    quote_bytes = file.read()
    return jsonify({'status': 'ok'})

@app.route('/api/upload-token', methods=['POST'])
def upload_token():
    global token_bytes
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    token_bytes = file.read()
    return jsonify({'status': 'ok'})

@app.route('/api/upload-images', methods=['POST'])
def upload_images():
    global images_zip
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    images_zip = file.read()
    return jsonify({'status': 'ok'})

@app.route('/api/upload-music', methods=['POST'])
def upload_music():
    global music_zip
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    music_zip = file.read()
    return jsonify({'status': 'ok'})

# ---------- EXPORT / IMPORT CONFIG ----------
@app.route('/api/export', methods=['GET'])
def export_config():
    global settings_data, token_bytes
    creds_b64 = base64.b64encode(token_bytes).decode() if token_bytes else ''
    return jsonify({
        'settings': settings_data,
        'credentials_b64': creds_b64
    })

@app.route('/api/import', methods=['POST'])
def import_config():
    global settings_data, token_bytes
    data = request.get_json()
    if 'settings' in data:
        settings_data = data['settings']
    if 'credentials_b64' in data:
        creds_b64 = data['credentials_b64']
        if creds_b64:
            token_bytes = base64.b64decode(creds_b64)
    return jsonify({'status': 'imported', 'settings': settings_data})

# ---------- LOGS ----------
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

# ---------- RUN BOT (stub – bot is run from Colab) ----------
@app.route('/api/run', methods=['POST'])
def run_bot():
    return jsonify({'status': 'Use the Colab notebook to run the bot.'})

# ---------- THE COMPLETE DASHBOARD HTML (V4 full UI) ----------
FULL_DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>YouTube Shorts Bot V4</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  /* Exactly the same glassmorphism CSS you had before, with all variables */
  /* I'll include the full CSS here for completeness */
  :root {
    --bg: #0a0a1a;
    --surface: rgba(20, 20, 40, 0.7);
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
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
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
  .tabs { display: flex; gap: 8px; background: rgba(255,255,255,0.04); padding: 6px; border-radius: 14px; margin: 25px 0; }
  .tab { flex: 1; padding: 12px; text-align: center; cursor: pointer; border-radius: 10px; font-weight: 500; transition: all 0.3s; color: var(--muted); }
  .tab.active { background: var(--primary); color: white; box-shadow: 0 8px 20px -8px var(--primary); }
  .tab:not(.active):hover { background: rgba(255,255,255,0.06); color: white; }
  .panel { background: rgba(255,255,255,0.02); border-radius: var(--border-radius); padding: 25px; border: 1px solid rgba(255,255,255,0.05); display: none; animation: fade 0.3s ease; }
  .panel.active { display: block; }
  @keyframes fade { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  .card { background: rgba(255,255,255,0.03); border-radius: 12px; padding: 20px; margin-bottom: 20px; }
  .row { display: flex; gap: 20px; flex-wrap: wrap; }
  .col { flex: 1; min-width: 180px; }
  label { display: block; margin-bottom: 6px; font-weight: 500; color: var(--muted); font-size: 0.9rem; }
  input, textarea, button { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; color: white; padding: 12px 16px; font-size: 0.95rem; width: 100%; transition: 0.2s; outline: none; }
  input:focus, textarea:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(124,93,250,0.2); }
  button { background: var(--primary); border: none; cursor: pointer; font-weight: 600; letter-spacing: 0.5px; transition: all 0.3s; box-shadow: 0 4px 15px rgba(124,93,250,0.3); }
  button:hover { background: var(--primary-hover); transform: translateY(-2px); box-shadow: 0 8px 25px rgba(124,93,250,0.4); }
  .log-box { background: rgba(0,0,0,0.3); border-radius: 12px; padding: 18px; height: 300px; overflow-y: auto; font-family: monospace; font-size: 0.85rem; white-space: pre-wrap; line-height: 1.6; border: 1px solid rgba(255,255,255,0.05); }
  .status-badge { display: inline-block; padding: 5px 14px; border-radius: 20px; font-weight: 600; font-size: 0.8rem; }
  .badge-green { background: #00c853; color: white; }
  .badge-yellow { background: #ffd600; color: black; }
  .badge-red { background: #ff1744; color: white; }
  .inline { display: flex; gap: 10px; align-items: center; }
  .mt-1 { margin-top: 12px; }
  .mt-2 { margin-top: 24px; }
  .time-slot-row { display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }
  .time-slot-row input { width: 120px; }
  .time-slot-row button { background: rgba(255,77,106,0.2); border: 1px solid rgba(255,77,106,0.3); padding: 8px 12px; font-size: 0.9rem; box-shadow: none; width: auto; }
  .time-slot-row button:hover { background: var(--danger); }
  .add-btn { background: var(--accent) !important; box-shadow: 0 4px 15px rgba(0,212,170,0.3) !important; margin-top: 10px; }
  .add-btn:hover { background: #00e6b0 !important; }
</style>
</head>
<body>
<div class="container">
  <h1>🎬 YouTube Shorts Bot V4</h1>
  <div class="tabs">
    <div class="tab active" onclick="switchTab('settings')">⚙️ Settings</div>
    <div class="tab" onclick="switchTab('auth')">🔐 Auth</div>
    <div class="tab" onclick="switchTab('run')">🚀 Run</div>
    <div class="tab" onclick="switchTab('export')">📦 Import/Export</div>
    <div class="tab" onclick="switchTab('files')">📁 Files</div>
    <div class="tab" onclick="switchTab('log')">📋 Log</div>
  </div>

  <!-- Settings Panel -->
  <div id="panel-settings" class="panel active">
    <div class="card">
      <h3>⏱️ Video</h3>
      <div class="row">
        <div class="col"><label>Duration (s)</label><input type="number" id="total_duration" value="7" min="5" max="15"></div>
        <div class="col"><label>Fade-in (s)</label><input type="number" id="fade_duration" value="2" min="0.5" max="3" step="0.1"></div>
        <div class="col"><label>Max quote length</label><input type="number" id="max_quote_len" value="50" min="30" max="100"></div>
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
  </div>

  <!-- Auth Panel -->
  <div id="panel-auth" class="panel">
    <div class="card">
      <h3>1. Upload client_secret.json</h3>
      <input type="file" id="client_secret_file" accept=".json">
      <button type="button" onclick="uploadClientSecret()">Upload</button>
      <span id="uploadStatus"></span>
    </div>
    <div class="card">
      <h3>2. Authorize</h3>
      <div class="inline mt-1">
        <input type="text" id="auth_url" readonly placeholder="URL will appear...">
        <button type="button" onclick="copyAuthUrl()">📋 Copy</button>
      </div>
      <div class="inline mt-1">
        <input type="text" id="auth_code" placeholder="Paste code or full redirect URL">
        <button type="button" onclick="authenticate()">🔑 Authenticate</button>
      </div>
      <span id="authStatus"></span>
    </div>
    <div class="card" id="downloadConfigCard" style="display:none;">
      <h3>✅ Done! Download your config file:</h3>
      <button type="button" onclick="downloadConfigAfterAuth()">📥 Download Config</button>
      <p class="mt-1" style="color:var(--muted);">Keep this file – you can re‑upload it later to skip steps 1 & 2.</p>
    </div>
    <div class="card">
      <h3>Token Status</h3>
      <div id="tokenStatus" class="status-badge badge-red">No token</div>
    </div>
  </div>

  <!-- Run Panel -->
  <div id="panel-run" class="panel">
    <p style="margin-bottom:20px;">The bot runs on Google Colab for free GPU. Click below to open the notebook.</p>
    <button type="button" onclick="window.open('https://colab.research.google.com/drive/1U505-nHazAkHB2VVRtqTxDjzrDG_hWTZ?authuser=1#scrollTo=56uU71i-4sup', '_blank')">Open Colab Notebook</button>
    <p class="mt-2" style="color:var(--muted); font-size:0.9rem;">After running the notebook, logs will appear in the "Log" tab here.</p>
  </div>

  <!-- Import/Export Panel -->
  <div id="panel-export" class="panel">
    <div class="card">
      <h3>Export Configuration</h3>
      <button type="button" onclick="exportConfig()">📥 Download Config File</button>
    </div>
    <div class="card mt-2">
      <h3>Import Configuration</h3>
      <input type="file" id="import_file" accept=".json">
      <button type="button" class="mt-1" onclick="importConfig()">📤 Restore Config</button>
      <span id="importStatus"></span>
    </div>
  </div>

  <!-- Files Panel -->
  <div id="panel-files" class="panel">
    <div class="card">
      <h3>📄 Quote File (quote.txt)</h3>
      <input type="file" id="quoteFile" accept=".txt">
      <button onclick="uploadFile('quote')" class="mt-1">Upload</button><span id="quoteStatus"></span>
    </div>
    <div class="card">
      <h3>🔐 YouTube Token (token.pickle)</h3>
      <input type="file" id="tokenFile" accept=".pickle,.pkl">
      <button onclick="uploadFile('token')" class="mt-1">Upload</button><span id="tokenStatus"></span>
    </div>
    <div class="card">
      <h3>🖼️ Images (ZIP)</h3>
      <input type="file" id="imagesFile" accept=".zip">
      <button onclick="uploadFile('images')" class="mt-1">Upload</button><span id="imagesStatus"></span>
    </div>
    <div class="card">
      <h3>🎵 Music (ZIP)</h3>
      <input type="file" id="musicFile" accept=".zip">
      <button onclick="uploadFile('music')" class="mt-1">Upload</button><span id="musicStatus"></span>
    </div>
  </div>

  <!-- Log Panel -->
  <div id="panel-log" class="panel">
    <div class="log-box" id="logBox"></div>
    <button type="button" onclick="refreshLog()" class="mt-1">🔄 Refresh Log</button>
  </div>
</div>

<script>
  // --- Time slots ---
  let timeSlots = ["05:30", "11:30", "17:30", "23:30"];
  function renderSlots() {
    const container = document.getElementById('slotsContainer');
    container.innerHTML = timeSlots.map((slot, i) => `
      <div class="time-slot-row">
        <input type="time" value="${slot}" onchange="updateSlot(${i}, this.value)">
        <button type="button" onclick="removeSlot(${i})" style="width:auto;">✕</button>
      </div>`).join('');
  }
  function addSlot() { timeSlots.push("12:00"); renderSlots(); }
  function removeSlot(i) { if (timeSlots.length<=1) return; timeSlots.splice(i,1); renderSlots(); }
  function updateSlot(i, v) { timeSlots[i] = v; }
  renderSlots();

  function switchTab(tab) {
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById('panel-'+tab).classList.add('active');
    event.target.classList.add('active');
  }

  // Settings
  function saveSettings() {
    const data = {
      total_duration: +document.getElementById('total_duration').value,
      fade_duration: +document.getElementById('fade_duration').value,
      max_quote_len: +document.getElementById('max_quote_len').value,
      slots: timeSlots,
      base_tags: document.getElementById('base_tags').value,
      description_extra: document.getElementById('description_extra').value,
      category_id: document.getElementById('category_id').value
    };
    fetch('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)})
      .then(() => alert('Settings saved!'));
  }

  // Auth
  function uploadClientSecret() {
    const file = document.getElementById('client_secret_file').files[0];
    if (!file) return alert('Choose a file');
    const fd = new FormData(); fd.append('file', file);
    fetch('/api/auth/upload_client_secret', {method:'POST', body:fd})
      .then(r => r.json())
      .then(d => {
        if (d.auth_url) {
          document.getElementById('auth_url').value = d.auth_url;
          document.getElementById('uploadStatus').innerHTML = '<span class="status-badge badge-green">✅ Ready</span>';
        } else {
          document.getElementById('uploadStatus').innerHTML = '<span class="status-badge badge-red">❌ '+d.error+'</span>';
        }
      });
  }
  function copyAuthUrl() {
    const inp = document.getElementById('auth_url'); inp.select(); document.execCommand('copy');
  }
  let latestConfig = null;
  function authenticate() {
    let code = document.getElementById('auth_code').value.trim();
    if (!code) return alert('Paste code first');
    fetch('/api/auth/authenticate', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({code})
    }).then(r => r.json()).then(d => {
      if (d.status==='authenticated') {
        document.getElementById('authStatus').innerHTML = '<span class="status-badge badge-green">✅ Authenticated</span>';
        latestConfig = d.config;
        document.getElementById('downloadConfigCard').style.display = 'block';
        updateTokenStatus();
      } else {
        document.getElementById('authStatus').innerHTML = '<span class="status-badge badge-red">❌ '+d.error+'</span>';
      }
    });
  }
  function downloadConfigAfterAuth() {
    if (!latestConfig) return;
    const blob = new Blob([JSON.stringify(latestConfig, null, 2)], {type:'application/json'});
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'shorts_bot_config.json'; a.click();
  }
  function updateTokenStatus() {
    fetch('/api/auth/status').then(r => r.json()).then(d => {
      const el = document.getElementById('tokenStatus');
      if (d.status==='valid') { el.className='status-badge badge-green'; el.textContent='Token valid'; }
      else if (d.status==='expired_refreshable') { el.className='status-badge badge-yellow'; el.textContent='Expired (refreshable)'; }
      else { el.className='status-badge badge-red'; el.textContent='No token'; }
    });
  }
  setInterval(updateTokenStatus, 30000); updateTokenStatus();

  // File uploads
  function uploadFile(type) {
    const map = { quote:'quoteFile', token:'tokenFile', images:'imagesFile', music:'musicFile' };
    const file = document.getElementById(map[type]).files[0];
    if (!file) return alert('Select a file');
    const fd = new FormData(); fd.append('file', file);
    fetch('/api/upload-'+type, {method:'POST', body:fd})
      .then(r => r.json())
      .then(d => {
        const span = document.getElementById(type+'Status');
        if (d.status==='ok') span.innerHTML = '<span class="status-badge badge-green">✅ Uploaded</span>';
        else span.innerHTML = '<span class="status-badge badge-red">❌ Error</span>';
      });
  }

  // Logs
  function refreshLog() {
    fetch('/api/log').then(r => r.json()).then(lines => {
      document.getElementById('logBox').textContent = lines.join('\n');
    });
  }
  refreshLog(); setInterval(refreshLog, 5000);

  // Export/Import
  function exportConfig() {
    fetch('/api/export').then(r => r.json()).then(d => {
      const blob = new Blob([JSON.stringify(d, null, 2)], {type:'application/json'});
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'shorts_bot_config.json'; a.click();
    });
  }
  function importConfig() {
    const file = document.getElementById('import_file').files[0];
    if (!file) return alert('Select a file');
    const reader = new FileReader();
    reader.onload = e => {
      try {
        const config = JSON.parse(e.target.result);
        fetch('/api/import', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(config)})
        .then(r => r.json()).then(d => {
          if (d.status==='imported') {
            document.getElementById('importStatus').innerHTML = '<span class="status-badge badge-green">✅ Config restored</span>';
            if (d.settings) {
              document.getElementById('total_duration').value = d.settings.total_duration;
              document.getElementById('fade_duration').value = d.settings.fade_duration;
              document.getElementById('max_quote_len').value = d.settings.max_quote_len;
              document.getElementById('base_tags').value = d.settings.base_tags;
              document.getElementById('description_extra').value = d.settings.description_extra;
              document.getElementById('category_id').value = d.settings.category_id;
              timeSlots = d.settings.slots; renderSlots();
            }
            updateTokenStatus();
          } else {
            document.getElementById('importStatus').innerHTML = '<span class="status-badge badge-red">❌ Failed</span>';
          }
        });
      } catch(ex) { alert('Invalid JSON file'); }
    };
    reader.readAsText(file);
  }
</script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

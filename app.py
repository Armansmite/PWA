import os, json, time, base64, io, urllib.request, ast
from flask import Flask, request, jsonify, send_file, Response
import requests as http_requests

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

# ---------- Load configs from GitHub ----------
CONFIGS_URL = "https://raw.githubusercontent.com/Armansmite/Youtube-quote/main/configs.json"
cached_configs = []

def load_configs():
    global cached_configs
    try:
        with urllib.request.urlopen(CONFIGS_URL) as resp:
            cached_configs = json.load(resp)
    except Exception:
        cached_configs = [{"id": "classic", "name": "Classic V1", "file": "classic.py",
                           "settings": {
                               "total_duration": {"default": 7, "type": "number", "min": 5, "max": 15, "label": "Duration (seconds)"},
                               "fade_duration": {"default": 2, "type": "number", "min": 0.5, "max": 3, "step": 0.1, "label": "Fade‑in (seconds)"},
                               "max_quote_len": {"default": 50, "type": "number", "min": 30, "max": 100, "label": "Max Quote Length"},
                               "min_quote_len": {"default": 0, "type": "number", "min": 0, "max": 200, "label": "Min Quote Length"}
                           }}]

load_configs()

# ---------- In‑memory storage ----------
settings_data = {
    "max_videos": 0,
    "slots": ["05:30", "11:30", "17:30", "23:30"],
    "base_tags": "shorts, quotes, motivation, wisdom",
    "description_extra": "💡 Quote of the day | Motivational quotes | Motivational speech | Motivational video | Understanding politics",
    "category_id": "22",
    "active_config": "classic",
    "config_settings": {}
}

token_json = None
quote_bytes = None
images_zip = None
music_zip = None
log_messages = []
oauth_flow = None
colab_connected = False
last_heartbeat = 0

# ---------- CORS ----------
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

# ---------- FRONTEND (separate file) ----------
@app.route('/')
def index():
    return send_file('dashboard.html')

# ---------- SETTINGS ----------
@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    global settings_data
    if request.method == 'POST':
        settings_data = request.get_json()
        return jsonify({'status': 'ok'})

    active = settings_data.get("active_config", "classic")
    saved_config = settings_data.get("config_settings", {}).get(active, {})
    return jsonify({
        **settings_data,
        "current_config_settings": saved_config
    })

# ---------- CONFIGS LIST ----------
@app.route('/api/configs')
def list_configs():
    return jsonify(cached_configs)

# ---------- DYNAMIC CONFIG SETTINGS WITH FALLBACK ----------
@app.route('/api/config-settings/<config_id>')
def config_settings(config_id):
    config_entry = next((c for c in cached_configs if c["id"] == config_id), None)
    if not config_entry:
        return jsonify({"error": "Config not found"}), 404

    # 1. Try to extract SETTINGS_DEF from the raw Python file on GitHub
    file_name = config_entry.get("file")
    raw_url = f"https://raw.githubusercontent.com/Armansmite/Youtube-quote/main/configs/{file_name}"
    try:
        resp = http_requests.get(raw_url, timeout=10)
        resp.raise_for_status()
        source = resp.text

        start = source.find("SETTINGS_DEF = {")
        if start != -1:
            brace_count = 0
            end = start + len("SETTINGS_DEF = ")
            for i in range(end, len(source)):
                if source[i] == '{':
                    brace_count += 1
                elif source[i] == '}':
                    if brace_count == 0:
                        end = i + 1
                        break
                    brace_count -= 1
            dict_str = source[end-1:i+1] if brace_count == 0 else ""
            if dict_str:
                settings_def = ast.literal_eval(dict_str)
                return jsonify(settings_def)
    except Exception:
        pass

    # 2. Fallback: use the "settings" field from configs.json
    fallback = config_entry.get("settings", {})
    if fallback:
        return jsonify(fallback)

    return jsonify({"error": "No settings definition available for this config."}), 500

# ---------- CONNECTION STATUS ----------
@app.route('/api/connect', methods=['POST'])
def connect():
    global colab_connected, last_heartbeat
    data = request.get_json() or {}
    colab_connected = data.get('connected', True)
    last_heartbeat = time.time()
    return jsonify({'status': 'ok'})

@app.route('/api/status')
def connection_status():
    alive = colab_connected and (time.time() - last_heartbeat < 90)
    return jsonify({'connected': alive})

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
    global token_json, oauth_flow
    raw = request.get_json().get('code', '')
    if 'code=' in raw:
        raw = raw.split('code=')[1].split('&')[0]
    if not oauth_flow:
        return jsonify({'error': 'No client_secret uploaded yet'}), 400
    try:
        oauth_flow.fetch_token(code=raw)
        creds = oauth_flow.credentials
        service = build('youtube', 'v3', credentials=creds)
        service.channels().list(part='id', mine=True).execute()
        token_json = creds.to_json()
        oauth_flow = None
        config = {
            'settings': settings_data,
            'credentials_json': token_json
        }
        return jsonify({'status': 'authenticated', 'config': config})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    global token_json
    if not token_json:
        return jsonify({'status': 'none'})
    creds = Credentials.from_authorized_user_info(json.loads(token_json))
    if creds.valid:
        return jsonify({'status': 'valid'})
    elif creds.expired and creds.refresh_token:
        return jsonify({'status': 'expired_refreshable'})
    else:
        return jsonify({'status': 'invalid'})

@app.route('/api/token')
def download_token():
    global token_json
    if not token_json:
        return jsonify({'error': 'No token uploaded'}), 404
    return Response(token_json, mimetype='application/json',
                    headers={'Content-Disposition': 'attachment; filename="token.json"'})

# ---------- FILE UPLOADS ----------
@app.route('/api/upload-quote', methods=['POST'])
def upload_quote():
    global quote_bytes
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    quote_bytes = request.files['file'].read()
    return jsonify({'status': 'ok'})

@app.route('/api/upload-token', methods=['POST'])
def upload_token():
    global token_json
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    token_json = request.files['file'].read().decode('utf-8')
    return jsonify({'status': 'ok'})

@app.route('/api/upload-images', methods=['POST'])
def upload_images():
    global images_zip
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    images_zip = request.files['file'].read()
    return jsonify({'status': 'ok'})

@app.route('/api/upload-music', methods=['POST'])
def upload_music():
    global music_zip
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    music_zip = request.files['file'].read()
    return jsonify({'status': 'ok'})

# ---------- EXPORT / IMPORT ----------
@app.route('/api/export', methods=['GET'])
def export_config():
    global settings_data, token_json
    return jsonify({
        'settings': settings_data,
        'credentials_json': token_json or ''
    })

@app.route('/api/import', methods=['POST'])
def import_config():
    global settings_data, token_json
    data = request.get_json()
    if 'settings' in data:
        settings_data = data['settings']
    if 'credentials_json' in data and data['credentials_json']:
        token_json = data['credentials_json']
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

# ---------- RUN BOT (GitHub Actions trigger) ----------
@app.route('/api/run', methods=['POST'])
def run_bot():
    gh_token = os.environ.get('GH_TOKEN')
    if not gh_token:
        return jsonify({'status': 'error', 'message': 'GH_TOKEN not configured on server'}), 500

    repo = "Armansmite/Youtube-quote"
    headers = {
        "Authorization": f"token {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "Content-Type": "application/json"
    }

    dispatch_data = {"event_type": "start_bot"}
    resp = http_requests.post(
        f"https://api.github.com/repos/{repo}/dispatches",
        json=dispatch_data,
        headers=headers
    )

    if resp.status_code == 204:
        return jsonify({'status': 'ok', 'message': 'GitHub Actions workflow triggered.'})
    else:
        return jsonify({'status': 'error', 'message': f'Failed: {resp.text}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

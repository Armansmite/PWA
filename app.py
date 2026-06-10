import os, json, time, base64, io, urllib.request, ast
from flask import Flask, request, jsonify, send_file, Response
import requests as http_requests
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
BOT_USER_ID = os.environ.get("BOT_USER_ID")
BOT_SECRET = os.environ.get("BOT_SECRET")

# ---------- Load configs from GitHub ----------
CONFIGS_URL = "https://raw.githubusercontent.com/Armansmite/Youtube-quote/main/configs.json"
cached_configs = []

def load_configs():
    global cached_configs
    try:
        with urllib.request.urlopen(CONFIGS_URL) as resp:
            cached_configs = json.load(resp)
    except Exception:
        cached_configs = [{
            "id": "classic", "name": "Classic V1", "file": "classic.py",
            "settings": {
                "total_duration": {"default": 7, "type": "number", "min": 5, "max": 15, "label": "Duration (seconds)"},
                "fade_duration": {"default": 2, "type": "number", "min": 0.5, "max": 3, "step": 0.1, "label": "Fade‑in (seconds)"},
                "max_quote_len": {"default": 50, "type": "number", "min": 30, "max": 100, "label": "Max Quote Length"},
                "min_quote_len": {"default": 0, "type": "number", "min": 0, "max": 200, "label": "Min Quote Length"}
            }
        }]

load_configs()

# ---------- CORS ----------
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Bot-Secret'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

# ---------- FRONTEND ----------
@app.route('/')
def index():
    if os.path.exists("dashboard.html"):
        return send_file("dashboard.html")
    return "<h2>dashboard.html not found</h2>"

# ---------- SUPABASE HELPERS ----------
def supabase_get(table, user_id):
    r = http_requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}?user_id=eq.{user_id}&select=*",
        headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    )
    if r.status_code == 200:
        rows = r.json()
        return rows[0] if rows else {}
    return None

def supabase_upsert(table, user_id, data):
    payload = {"user_id": user_id}
    payload.update(data)
    r = http_requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}?on_conflict=user_id",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        },
        json=payload
    )
    return r.status_code in (200, 201)

def supabase_delete(table, user_id):
    r = http_requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}?user_id=eq.{user_id}",
        headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    )
    return r.status_code in (200, 204)

# ---------- AUTH ----------
def get_user_id_for_request():
    if request.headers.get("X-Bot-Secret") == BOT_SECRET:
        return BOT_USER_ID
    auth = request.headers.get("Authorization", "").replace("Bearer ", "")
    if auth:
        r = http_requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {auth}"}
        )
        if r.status_code == 200:
            return r.json()["id"]
    return None

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.get_json()
    r = http_requests.post(
        f"{SUPABASE_URL}/auth/v1/signup",
        headers={"apikey": SUPABASE_SERVICE_KEY, "Content-Type": "application/json"},
        json={"email": data["email"], "password": data["password"]}
    )
    return jsonify(r.json()), r.status_code

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    r = http_requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": SUPABASE_SERVICE_KEY, "Content-Type": "application/json"},
        json={"email": data["email"], "password": data["password"]}
    )
    return jsonify(r.json()), r.status_code

# ---------- SETTINGS ----------
@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    user_id = get_user_id_for_request()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    if request.method == 'POST':
        settings = request.get_json()
        ok = supabase_upsert("user_settings", user_id, {"settings": settings})
        return jsonify({"status": "ok" if ok else "error"})

    row = supabase_get("user_settings", user_id)
    return jsonify(row.get("settings", {}))

# ---------- TOKEN (YouTube) ----------
@app.route('/api/token', methods=['GET', 'POST'])
def handle_token():
    user_id = get_user_id_for_request()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    if request.method == 'POST':
        token_json = request.get_json().get("token_json")
        if not token_json:
            return jsonify({"error": "Missing token_json"}), 400
        ok = supabase_upsert("user_token", user_id, {"token_json": token_json})
        return jsonify({"status": "ok" if ok else "error"})

    row = supabase_get("user_token", user_id)
    token = row.get("token_json") if row else None
    if token:
        return Response(token, mimetype='application/json',
                        headers={'Content-Disposition': 'attachment; filename="token.json"'})
    return jsonify({"error": "No token stored"}), 404

# ---------- DIRECT TOKEN FILE UPLOAD ----------
@app.route('/api/upload-token', methods=['POST'])
def upload_token():
    user_id = get_user_id_for_request()
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    token_str = file.read().decode('utf-8')
    ok = supabase_upsert("user_token", user_id, {"token_json": token_str})
    return jsonify({'status': 'ok' if ok else 'error'})

# ---------- OAUTH FLOW (YouTube) ----------
@app.route('/api/auth/upload_client_secret', methods=['POST'])
def upload_client_secret():
    user_id = get_user_id_for_request()
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    filepath = '/tmp/client_secret.json'
    file.save(filepath)

    # Store the client_secret content in Supabase so we can recreate the flow later
    with open(filepath, 'r') as f:
        secret_content = f.read()
    ok = supabase_upsert("user_oauth_state", user_id, {"client_secret": secret_content})
    if not ok:
        return jsonify({'error': 'Could not save state'}), 500

    try:
        flow = InstalledAppFlow.from_client_secrets_file(filepath, [
            'https://www.googleapis.com/auth/youtube.upload',
            'https://www.googleapis.com/auth/youtube.readonly'
        ])
        flow.redirect_uri = 'http://localhost:8080'
        auth_url, _ = flow.authorization_url(prompt='consent')
        return jsonify({'auth_url': auth_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/authenticate', methods=['POST'])
def authenticate():
    user_id = get_user_id_for_request()
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    # Retrieve stored client_secret from Supabase
    row = supabase_get("user_oauth_state", user_id)
    if not row or not row.get("client_secret"):
        return jsonify({'error': 'No client_secret uploaded. Please re‑upload.'}), 400

    # Recreate the flow from the stored secret
    with open('/tmp/restored_secret.json', 'w') as f:
        f.write(row["client_secret"])
    try:
        flow = InstalledAppFlow.from_client_secrets_file('/tmp/restored_secret.json', [
            'https://www.googleapis.com/auth/youtube.upload',
            'https://www.googleapis.com/auth/youtube.readonly'
        ])
        flow.redirect_uri = 'http://localhost:8080'

        raw = request.get_json().get('code', '')
        if 'code=' in raw:
            raw = raw.split('code=')[1].split('&')[0]
        flow.fetch_token(code=raw)
        creds = flow.credentials

        # Validate the token
        service = build('youtube', 'v3', credentials=creds)
        service.channels().list(part='id', mine=True).execute()
        token_json = creds.to_json()

        # Save token to Supabase
        ok = supabase_upsert("user_token", user_id, {"token_json": token_json})
        if not ok:
            return jsonify({'error': 'Could not save token'}), 500

        # Cleanup OAuth state
        supabase_delete("user_oauth_state", user_id)

        return jsonify({'status': 'authenticated', 'config': {'settings': {}, 'credentials_json': token_json}})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    user_id = get_user_id_for_request()
    if not user_id:
        return jsonify({'status': 'none'})
    row = supabase_get("user_token", user_id)
    if not row or not row.get("token_json"):
        return jsonify({'status': 'none'})
    creds = Credentials.from_authorized_user_info(json.loads(row["token_json"]))
    if creds.valid:
        return jsonify({'status': 'valid'})
    elif creds.expired and creds.refresh_token:
        return jsonify({'status': 'expired_refreshable'})
    else:
        return jsonify({'status': 'invalid'})

# ---------- CONFIGS LIST ----------
@app.route('/api/configs')
def list_configs():
    return jsonify(cached_configs)

# ---------- DYNAMIC CONFIG SETTINGS ----------
@app.route('/api/config-settings/<config_id>')
def config_settings(config_id):
    config_entry = next((c for c in cached_configs if c["id"] == config_id), None)
    if not config_entry:
        return jsonify({"error": "Config not found"}), 404
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
                if source[i] == '{': brace_count += 1
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
    fallback = config_entry.get("settings", {})
    if fallback:
        return jsonify(fallback)
    return jsonify({"error": "No settings definition available for this config."}), 500

# ---------- LOGS ----------
log_messages = []
@app.route('/api/log', methods=['GET', 'POST'])
def handle_log():
    global log_messages
    if request.method == 'POST':
        msg = request.get_json().get('message', '')
        log_messages.append(msg)
        if len(log_messages) > 200: log_messages.pop(0)
        return jsonify({'status': 'ok'})
    return jsonify(log_messages)

# ---------- RUN BOT ----------
@app.route('/api/run', methods=['POST'])
def run_bot():
    gh_token = os.environ.get('GH_TOKEN')
    if not gh_token:
        return jsonify({'status': 'error', 'message': 'GH_TOKEN not configured'}), 500
    repo = "Armansmite/Youtube-quote"
    headers = {
        "Authorization": f"token {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "Content-Type": "application/json"
    }
    dispatch_data = {"event_type": "start_bot"}
    resp = http_requests.post(f"https://api.github.com/repos/{repo}/dispatches", json=dispatch_data, headers=headers)
    if resp.status_code == 204:
        return jsonify({'status': 'ok', 'message': 'Workflow triggered.'})
    return jsonify({'status': 'error', 'message': resp.text}), 500

# ---------- RUN STATUS & CANCEL ----------
@app.route('/api/run-status')
def run_status():
    gh_token = os.environ.get('GH_TOKEN')
    if not gh_token: return jsonify({'running': False})
    repo = "Armansmite/Youtube-quote"
    headers = {
        "Authorization": f"token {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10"
    }
    url = f"https://api.github.com/repos/{repo}/actions/runs?event=repository_dispatch&branch=main"
    try:
        resp = http_requests.get(url, headers=headers)
        if resp.status_code == 200:
            runs = resp.json().get("workflow_runs", [])
            for run in runs:
                if run["status"] in ("in_progress", "queued"):
                    return jsonify({"running": True, "run_id": run["id"]})
        return jsonify({"running": False})
    except Exception:
        return jsonify({"running": False})

@app.route('/api/cancel', methods=['POST'])
def cancel_bot():
    gh_token = os.environ.get('GH_TOKEN')
    if not gh_token: return jsonify({'status': 'error', 'message': 'GH_TOKEN not configured'}), 500
    repo = "Armansmite/Youtube-quote"
    headers = {
        "Authorization": f"token {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10"
    }
    url = f"https://api.github.com/repos/{repo}/actions/runs?event=repository_dispatch&branch=main"
    try:
        resp = http_requests.get(url, headers=headers)
        if resp.status_code == 200:
            runs = resp.json().get("workflow_runs", [])
            for run in runs:
                if run["status"] in ("in_progress", "queued"):
                    run_id = run["id"]
                    cancel_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/cancel"
                    cr = http_requests.post(cancel_url, headers=headers)
                    if cr.status_code == 202:
                        return jsonify({'status': 'ok', 'message': 'Workflow cancelled.'})
                    else:
                        return jsonify({'status': 'error', 'message': cr.text}), 500
            return jsonify({'status': 'error', 'message': 'No running workflow found'}), 404
        else:
            return jsonify({'status': 'error', 'message': resp.text}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

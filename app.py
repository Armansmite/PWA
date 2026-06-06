import os, json, time, base64, io
from flask import Flask, request, jsonify, send_file

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

settings_data = {
    "total_duration": 7,
    "fade_duration": 2,
    "max_quote_len": 50,
    "max_videos": 0,
    "slots": ["05:30", "11:30", "17:30", "23:30"],
    "base_tags": "shorts, quotes, motivation, wisdom",
    "description_extra": "💡 Quote of the day | Motivational quotes | Motivational speech | Motivational video | Understanding politics",
    "category_id": "22"
}

token_json = None          # JSON string of credentials
quote_bytes = None
images_zip = None
music_zip = None
log_messages = []
oauth_flow = None

colab_connected = False
last_heartbeat = 0

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

@app.route('/')
def index():
    return DASHBOARD_HTML

# --- Settings ---
@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    global settings_data
    if request.method == 'POST':
        settings_data = request.get_json()
        return jsonify({'status': 'ok'})
    return jsonify(settings_data)

# --- Connection ---
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

# --- Auth (now uses JSON) ---
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
        token_json = creds.to_json()          # store as JSON
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

# --- File uploads ---
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

# --- Export/Import (now uses JSON) ---
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

# --- Logs ---
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

# --- Run stub ---
@app.route('/api/run', methods=['POST'])
def run_bot():
    return jsonify({'status': 'Use the Colab notebook to run the bot.'})

# --- The full HTML (same as before) ---
DASHBOARD_HTML = r""" ... """   # (copy the entire HTML from the previous answer)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

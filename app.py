import os
import json
import pickle
import base64
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# In-memory storage (Render free tier has ephemeral filesystem, but this is fine for a single user)
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

# CORS
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/frontend')
def frontend():
    return send_file('dashboard.html')

# API routes
@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    global settings_data
    if request.method == 'POST':
        settings_data = request.get_json()
        return jsonify({'status': 'ok'})
    return jsonify(settings_data)

@app.route('/api/auth/upload_client_secret', methods=['POST'])
def upload_client_secret():
    # Simplified – not needed for Colab, but keep for web UI
    return jsonify({'error': 'Not implemented on server'}), 501

@app.route('/api/auth/authenticate', methods=['POST'])
def authenticate():
    return jsonify({'error': 'Not implemented on server'}), 501

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

@app.route('/api/log', methods=['GET', 'POST'])
def handle_log():
    global log_messages
    if request.method == 'POST':
        msg = request.get_json().get('message', '')
        log_messages.append(msg)
        if len(log_messages) > 200:
            log_messages = log_messages[-200:]
        return jsonify({'status': 'ok'})
    return jsonify(log_messages)

@app.route('/api/run', methods=['POST'])
def run_bot():
    # The actual bot is run by Colab, not here
    return jsonify({'status': 'Use the Colab notebook to run the bot'})

# Serve static frontend files
# We'll include dashboard.html as a string (the same glassmorphism HTML)
# For Render, we need to put the HTML in a separate file dashboard.html
# We'll generate it in a moment

if __name__ == '__main__':
    # Ensure dashboard.html exists (we'll create it in the build step)
    if not os.path.exists('dashboard.html'):
        with open('dashboard.html', 'w') as f:
            f.write(open('dashboard_source.html').read())
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

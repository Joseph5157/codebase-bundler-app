import os
import tempfile
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, send_file, Response
from bundler import process_zip_file, process_directory

# Load environment variables from .env file if present
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max upload limit

# Automatically start Telegram Bot if token is provided
bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
if bot_token:
    # Ensure bot only starts once per Python process and avoids duplicate threads in Flask debug reloader
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or os.environ.get('WERKZEUG_RUN_MAIN') is None:
        import threading
        from bot import run_bot
        if not getattr(app, '_bot_started', False):
            app._bot_started = True
            print("Telegram Bot Token detected! Starting bot in background thread...")
            bot_thread = threading.Thread(target=run_bot, daemon=True)
            bot_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/bundle', methods=['POST'])
def bundle_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    uploaded_file = request.files['file']
    if uploaded_file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = uploaded_file.filename.lower()
    if not (filename.endswith('.zip') or filename.endswith('.tar') or filename.endswith('.gz')):
        return jsonify({'error': 'Please upload a .zip archive'}), 400

    custom_ignores_raw = request.form.get('custom_ignores', '')
    custom_ignores = [x.strip() for x in custom_ignores_raw.split(',') if x.strip()]

    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
        uploaded_file.save(tmp.name)
        tmp_path = tmp.name

    try:
        result = process_zip_file(tmp_path, custom_ignores=custom_ignores)
        return jsonify({
            'success': True,
            'file_count': result['file_count'],
            'total_lines': result['total_lines'],
            'total_bytes': result['total_bytes'],
            'text': result['text']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.route('/api/download', methods=['POST'])
def download_result():
    text = request.form.get('text', '')
    response = Response(
        text,
        mimetype="text/plain",
        headers={"Content-disposition": "attachment; filename=project_context.txt"}
    )
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port, debug=True)


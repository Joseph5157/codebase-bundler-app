import os
import tempfile
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, send_file, Response
from bundler import process_zip_file
from github_downloader import download_github_repo_zip
from store import save_bundle, get_bundle

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

@app.route('/copy/<bundle_id>')
def copy_bundle_view(bundle_id):
    bundle = get_bundle(bundle_id)
    if not bundle:
        return render_template('copy.html', error="Context bundle expired or not found. Please generate a new bundle."), 404
    return render_template('copy.html', bundle=bundle, bundle_id=bundle_id)

@app.route('/raw/<bundle_id>')
def raw_bundle_view(bundle_id):
    bundle = get_bundle(bundle_id)
    if not bundle:
        return "Context bundle expired or not found.", 404
    return Response(bundle['text'], mimetype="text/plain")

@app.route('/download/<bundle_id>')
def download_bundle_file(bundle_id):
    bundle = get_bundle(bundle_id)
    if not bundle:
        return "Context bundle expired or not found.", 404
    ext = ".xml" if bundle.get('active_format') == 'xml' else ".txt"
    return Response(
        bundle['text'],
        mimetype="text/plain",
        headers={"Content-disposition": f"attachment; filename=project_context{ext}"}
    )

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
        bundle_id = save_bundle(
            text=result['text'],
            file_count=result['file_count'],
            total_lines=result['total_lines'],
            total_bytes=result['total_bytes'],
            token_count=result['token_count'],
            redacted_count=result['redacted_count'],
            xml_text=result['xml_text'],
            markdown_text=result['markdown_text'],
            filename=uploaded_file.filename
        )
        return jsonify({
            'success': True,
            'bundle_id': bundle_id,
            'file_count': result['file_count'],
            'total_lines': result['total_lines'],
            'total_bytes': result['total_bytes'],
            'token_count': result['token_count'],
            'redacted_count': result['redacted_count'],
            'text': result['text'],
            'xml_text': result['xml_text'],
            'markdown_text': result['markdown_text']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.route('/api/bundle-github', methods=['POST'])
def bundle_github():
    data = request.get_json() or {}
    github_url = data.get('github_url', '').strip()
    custom_ignores = data.get('custom_ignores', [])

    if not github_url:
        return jsonify({'error': 'GitHub URL is required'}), 400

    try:
        tmp_zip, repo_filename = download_github_repo_zip(github_url)
        result = process_zip_file(tmp_zip, custom_ignores=custom_ignores)
        
        bundle_id = save_bundle(
            text=result['text'],
            file_count=result['file_count'],
            total_lines=result['total_lines'],
            total_bytes=result['total_bytes'],
            token_count=result['token_count'],
            redacted_count=result['redacted_count'],
            xml_text=result['xml_text'],
            markdown_text=result['markdown_text'],
            filename=repo_filename
        )

        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)

        return jsonify({
            'success': True,
            'bundle_id': bundle_id,
            'file_count': result['file_count'],
            'total_lines': result['total_lines'],
            'total_bytes': result['total_bytes'],
            'token_count': result['token_count'],
            'redacted_count': result['redacted_count'],
            'text': result['text'],
            'xml_text': result['xml_text'],
            'markdown_text': result['markdown_text']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

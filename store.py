import time
import uuid

BUNDLES = {}
MAX_BUNDLES = 150

def save_bundle(
    text: str,
    file_count: int,
    total_lines: int,
    total_bytes: int,
    token_count: int = 0,
    redacted_count: int = 0,
    xml_text: str = "",
    markdown_text: str = "",
    filename: str = "project.zip"
) -> str:
    now = time.time()
    if len(BUNDLES) >= MAX_BUNDLES:
        expired_keys = [k for k, v in BUNDLES.items() if now - v.get('created_at', 0) > 10800]
        for k in expired_keys:
            BUNDLES.pop(k, None)
        if len(BUNDLES) >= MAX_BUNDLES:
            for k in list(BUNDLES.keys())[:20]:
                BUNDLES.pop(k, None)

    bundle_id = uuid.uuid4().hex[:12]
    xml_content = xml_text or text
    md_content = markdown_text or text

    BUNDLES[bundle_id] = {
        'xml_text': xml_content,
        'markdown_text': md_content,
        'text': xml_content,
        'active_format': 'xml',
        'file_count': file_count,
        'total_lines': total_lines,
        'total_bytes': total_bytes,
        'token_count': token_count,
        'redacted_count': redacted_count,
        'filename': filename,
        'sent_message_ids': [],
        'created_at': now
    }
    return bundle_id

def get_bundle(bundle_id: str):
    return BUNDLES.get(bundle_id)

def add_sent_message(bundle_id: str, msg_id: int):
    bundle = BUNDLES.get(bundle_id)
    if bundle:
        if 'sent_message_ids' not in bundle:
            bundle['sent_message_ids'] = []
        if msg_id not in bundle['sent_message_ids']:
            bundle['sent_message_ids'].append(msg_id)

def toggle_bundle_format(bundle_id: str):
    bundle = BUNDLES.get(bundle_id)
    if not bundle:
        return None
    if bundle.get('active_format') == 'xml':
        bundle['active_format'] = 'markdown'
        bundle['text'] = bundle['markdown_text']
    else:
        bundle['active_format'] = 'xml'
        bundle['text'] = bundle['xml_text']
    return bundle

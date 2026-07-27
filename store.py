import time
import uuid

# In-memory bundle store
# Maps bundle_id -> {'text': str, 'file_count': int, 'total_lines': int, 'total_bytes': int, 'created_at': float}
BUNDLES = {}
MAX_BUNDLES = 150

def save_bundle(text: str, file_count: int, total_lines: int, total_bytes: int, filename: str = "project.zip") -> str:
    now = time.time()
    # Clean up old bundles (> 3 hours) or if max limit reached
    if len(BUNDLES) >= MAX_BUNDLES:
        expired_keys = [k for k, v in BUNDLES.items() if now - v.get('created_at', 0) > 10800]
        for k in expired_keys:
            BUNDLES.pop(k, None)
        if len(BUNDLES) >= MAX_BUNDLES:
            for k in list(BUNDLES.keys())[:20]:
                BUNDLES.pop(k, None)

    bundle_id = uuid.uuid4().hex[:12]
    BUNDLES[bundle_id] = {
        'text': text,
        'file_count': file_count,
        'total_lines': total_lines,
        'total_bytes': total_bytes,
        'filename': filename,
        'created_at': now
    }
    return bundle_id

def get_bundle(bundle_id: str):
    return BUNDLES.get(bundle_id)

import os
import zipfile
import tempfile
import shutil

IGNORE_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".idea", ".vscode"
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".pyc", ".pyo", ".pyd",
    ".db", ".sqlite", ".sqlite3",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac", ".ogg"
}

def is_binary_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext in BINARY_EXTENSIONS:
        return True
    
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return True
            try:
                chunk.decode("utf-8")
            except UnicodeDecodeError:
                return True
    except Exception:
        return True
    return False

def process_directory(root_dir, custom_ignores=None):
    """
    Recursively processes a directory and returns bundled text + stats.
    """
    ignore_set = set(IGNORE_DIRS)
    if custom_ignores:
        for item in custom_ignores:
            if item.strip():
                ignore_set.add(item.strip())

    entries = []
    file_count = 0
    total_lines = 0

    root_dir = os.path.abspath(root_dir)

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Ignore specified directories and hidden directories
        dirnames[:] = [
            d for d in dirnames
            if d not in ignore_set and not d.startswith(".")
        ]

        for filename in filenames:
            if filename.startswith("."):
                continue

            file_path = os.path.join(dirpath, filename)

            if is_binary_file(file_path):
                continue

            rel_path = os.path.relpath(file_path, root_dir).replace("\\", "/")

            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                lines = content.count("\n") + (1 if content else 0)
                total_lines += lines
                file_count += 1

                header = f"--- FILE: {rel_path} ---"
                entries.append(f"{header}\n{content}\n")
            except Exception as e:
                print(f"Warning: Could not read {rel_path}: {e}")

    bundled_text = "\n".join(entries)
    return {
        "text": bundled_text,
        "file_count": file_count,
        "total_lines": total_lines,
        "total_bytes": len(bundled_text.encode("utf-8"))
    }

def process_zip_file(zip_path, custom_ignores=None):
    """
    Extracts zip file into a temporary directory and bundles it.
    """
    temp_dir = tempfile.mkdtemp(prefix="bundler_")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        # Handle top-level single directory inside ZIP if present
        subitems = os.listdir(temp_dir)
        target_dir = temp_dir
        if len(subitems) == 1 and os.path.isdir(os.path.join(temp_dir, subitems[0])):
            target_dir = os.path.join(temp_dir, subitems[0])

        return process_directory(target_dir, custom_ignores)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

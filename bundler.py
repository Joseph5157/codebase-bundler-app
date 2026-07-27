import os
import re
import zipfile
import tempfile
import shutil
import pathspec
import tiktoken

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

# Regex patterns for masking sensitive keys/secrets
SECRET_PATTERNS = [
    (re.compile(r'sk-[a-zA-Z0-9]{32,}'), '[REDACTED API KEY]'),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'), '[REDACTED GITHUB TOKEN]'),
    (re.compile(r'gho_[a-zA-Z0-9]{36}'), '[REDACTED GITHUB OAUTH TOKEN]'),
    (re.compile(r'github_pat_[a-zA-Z0-9_]{22,}'), '[REDACTED GITHUB PAT]'),
    (re.compile(r'AKIA[0-9A-Z]{16}'), '[REDACTED AWS ACCESS KEY]'),
    (re.compile(r'xox[baprs]-[a-zA-Z0-9]{10,}'), '[REDACTED SLACK TOKEN]'),
    (re.compile(r'eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}'), '[REDACTED JWT TOKEN]'),
    (re.compile(r'(?i)\b(api[_-]?key|secret[_-]?key|password|db[_-]?pass|auth[_-]?token)\s*=\s*[\'"]?([^\'"\s#]+)[\'"]?'), r'\1=[REDACTED]'),
]

# Initialize tiktoken encoder
try:
    TOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:
    TOKEN_ENCODER = None

def count_tokens(text: str) -> int:
    if TOKEN_ENCODER:
        try:
            return len(TOKEN_ENCODER.encode(text, disallowed_special=()))
        except Exception:
            pass
    return len(text) // 4

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

def redact_secrets(text: str) -> (str, int):
    redacted_count = 0
    updated_text = text
    for pattern, replacement in SECRET_PATTERNS:
        matches = len(pattern.findall(updated_text))
        if matches > 0:
            redacted_count += matches
            updated_text = pattern.sub(replacement, updated_text)
    return updated_text, redacted_count

def load_gitignore_spec(root_dir):
    gitignore_path = os.path.join(root_dir, ".gitignore")
    if os.path.exists(gitignore_path):
        try:
            with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                spec = pathspec.PathSpec.from_lines("gitwildmatch", f)
                return spec
        except Exception as e:
            print(f"Warning: Could not parse .gitignore: {e}")
    return None

def generate_ascii_tree(root_dir, ignore_set, gitignore_spec):
    tree_lines = ["."]
    
    def _build_tree(dir_path, prefix=""):
        try:
            entries = sorted(os.listdir(dir_path))
        except Exception:
            return

        valid_entries = []
        for entry in entries:
            if entry.startswith(".") and entry not in {".env.example"}:
                continue
            if entry in ignore_set:
                continue

            full_path = os.path.join(dir_path, entry)
            rel_path = os.path.relpath(full_path, root_dir).replace("\\", "/")

            if gitignore_spec and gitignore_spec.match_file(rel_path):
                continue
            if os.path.isfile(full_path) and is_binary_file(full_path):
                continue

            valid_entries.append((entry, full_path))

        count = len(valid_entries)
        for i, (entry, full_path) in enumerate(valid_entries):
            is_last = (i == count - 1)
            connector = "└── " if is_last else "├── "
            tree_lines.append(f"{prefix}{connector}{entry}")
            
            if os.path.isdir(full_path):
                new_prefix = prefix + ("    " if is_last else "│   ")
                _build_tree(full_path, new_prefix)

    _build_tree(root_dir)
    return "\n".join(tree_lines)

def process_directory(root_dir, custom_ignores=None):
    ignore_set = set(IGNORE_DIRS)
    if custom_ignores:
        for item in custom_ignores:
            if item.strip():
                ignore_set.add(item.strip())

    root_dir = os.path.abspath(root_dir)
    gitignore_spec = load_gitignore_spec(root_dir)

    file_entries = []
    file_count = 0
    total_lines = 0
    total_redacted = 0

    # 1. Always Generate ASCII Directory Tree at top
    ascii_tree = generate_ascii_tree(root_dir, ignore_set, gitignore_spec)

    # 2. Process Files
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [
            d for d in dirnames
            if d not in ignore_set and not d.startswith(".")
        ]

        for filename in filenames:
            if filename.startswith(".") and filename not in {".env", ".env.example"}:
                continue

            file_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(file_path, root_dir).replace("\\", "/")

            if gitignore_spec and gitignore_spec.match_file(rel_path):
                continue

            if is_binary_file(file_path):
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    raw_content = f.read()

                clean_content, redacted_count = redact_secrets(raw_content)
                total_redacted += redacted_count

                lines = clean_content.count("\n") + (1 if clean_content else 0)
                total_lines += lines
                file_count += 1

                file_entries.append((rel_path, clean_content))
            except Exception as e:
                print(f"Warning: Could not read {rel_path}: {e}")

    # 3. Format Output in XML (DEFAULT)
    xml_parts = [
        "<repository>",
        "  <structure>",
        ascii_tree,
        "  </structure>",
        "  <files>"
    ]
    for path, content in file_entries:
        safe_content = content.replace("]]>", "]]&gt;")
        xml_parts.append(f'    <file path="{path}">\n      <![CDATA[\n{safe_content}\n      ]]>\n    </file>')
    xml_parts.append("  </files>")
    xml_parts.append("</repository>")

    xml_text = "\n".join(xml_parts)

    # 4. Format Output in Markdown
    md_parts = [
        "================================================================",
        "PROJECT STRUCTURE",
        "================================================================",
        ascii_tree,
        "",
        "================================================================",
        "FILE CONTENTS",
        "================================================================"
    ]
    for path, content in file_entries:
        md_parts.append(f"\n--- FILE: {path} ---\n{content}")

    markdown_text = "\n".join(md_parts)

    token_count = count_tokens(xml_text)

    return {
        "text": xml_text,  # Default to XML text
        "xml_text": xml_text,
        "markdown_text": markdown_text,
        "file_count": file_count,
        "total_lines": total_lines,
        "total_bytes": len(xml_text.encode("utf-8")),
        "token_count": token_count,
        "redacted_count": total_redacted,
        "ascii_tree": ascii_tree
    }

def process_zip_file(zip_path, custom_ignores=None):
    temp_dir = tempfile.mkdtemp(prefix="bundler_")
    real_temp_dir = os.path.realpath(temp_dir)
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.infolist():
                extracted_path = os.path.realpath(os.path.join(temp_dir, member.filename))
                if not (extracted_path == real_temp_dir or extracted_path.startswith(real_temp_dir + os.sep)):
                    raise ValueError(f"Security Alert: Malicious zip entry path detected '{member.filename}'")
                zip_ref.extract(member, temp_dir)

        subitems = os.listdir(temp_dir)
        target_dir = temp_dir
        if len(subitems) == 1 and os.path.isdir(os.path.join(temp_dir, subitems[0])):
            target_dir = os.path.join(temp_dir, subitems[0])

        return process_directory(target_dir, custom_ignores)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

from __future__ import annotations
import io, shutil, stat, tempfile, zipfile
from pathlib import Path, PurePosixPath

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_FILE_BYTES = 1 * 1024 * 1024
MAX_FILES = 5000
IGNORED_DIRS = {".git", ".hg", ".svn", "node_modules", "target", "dist", "build", ".venv", "venv", "env", "__pycache__", ".tox"}
IGNORED_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_dsa"}
IGNORED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt", ".der", ".sqlite", ".db", ".exe", ".dll", ".so", ".bin", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".zip", ".tar", ".gz", ".pdf"}

def safe_member_path(name: str) -> Path | None:
    if not name or "\\" in name:
        return None
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    return Path(*pure.parts)

def should_ignore(path: Path) -> bool:
    return bool(set(path.parts) & IGNORED_DIRS) or path.name.lower() in IGNORED_NAMES or path.suffix.lower() in IGNORED_SUFFIXES

def extract_repository(upload: bytes | bytearray | io.BufferedIOBase, destination: Path | None = None) -> Path:
    if hasattr(upload, "read"):
        upload = upload.read()
    data = bytes(upload)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB limit")
    target = destination or Path(tempfile.mkdtemp(prefix="repo-witness-"))
    target.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES:
                raise ValueError("ZIP contains too many files")
            kept = 0
            for info in infos:
                rel = safe_member_path(info.filename)
                if rel is None or should_ignore(rel) or info.is_dir():
                    continue
                if info.file_size > MAX_FILE_BYTES:
                    continue
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    continue
                out = (target / rel).resolve()
                if target.resolve() not in out.parents:
                    raise ValueError("ZIP path escapes extraction directory")
                out.parent.mkdir(parents=True, exist_ok=True)
                raw = archive.read(info)
                if len(raw) > MAX_FILE_BYTES or b"\x00" in raw:
                    continue
                out.write_bytes(raw)
                kept += 1
        if not kept:
            raise ValueError("No eligible text files found in repository")
        return target
    except Exception:
        if destination is None:
            shutil.rmtree(target, ignore_errors=True)
        raise


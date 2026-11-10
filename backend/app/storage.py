"""File-based client registry: DATA_DIR/clients/<client_id>/{client.json, files/<kind>.<ext>}"""
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import ALLOWED_EXTENSIONS, DATA_DIR, FILE_KINDS

CLIENTS_DIR = DATA_DIR / "clients"


def _client_dir(client_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", client_id):
        raise KeyError(client_id)
    return CLIENTS_DIR / client_id


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "client")[:40]


def _read(client_id: str) -> dict:
    p = _client_dir(client_id) / "client.json"
    if not p.exists():
        raise KeyError(client_id)
    return json.loads(p.read_text())


def _write(client_id: str, meta: dict) -> None:
    (_client_dir(client_id) / "client.json").write_text(json.dumps(meta, indent=2))


def file_path(client_id: str, kind: str) -> Path | None:
    d = _client_dir(client_id) / "files"
    for ext in ALLOWED_EXTENSIONS:
        p = d / f"{kind}{ext}"
        if p.exists():
            return p
    return None


def _public(client_id: str, meta: dict) -> dict:
    files = {}
    for kind in FILE_KINDS:
        p = file_path(client_id, kind)
        files[kind] = (
            {"filename": meta.get("filenames", {}).get(kind, p.name), "size": p.stat().st_size,
             "uploaded_at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}
            if p else None
        )
    return {
        "id": client_id,
        "name": meta["name"],
        "description": meta.get("description", ""),
        "notes": meta.get("notes", {}),
        "files": files,
        "ready": all(files.values()),
        "created_at": meta["created_at"],
    }


def list_clients() -> list[dict]:
    if not CLIENTS_DIR.exists():
        return []
    out = []
    for d in sorted(CLIENTS_DIR.iterdir()):
        if (d / "client.json").exists():
            out.append(_public(d.name, _read(d.name)))
    return sorted(out, key=lambda c: c["name"].lower())


def get_client(client_id: str) -> dict:
    return _public(client_id, _read(client_id))


def create_client(name: str, description: str = "") -> dict:
    client_id = f"{_slug(name)}-{uuid.uuid4().hex[:6]}"
    (_client_dir(client_id) / "files").mkdir(parents=True)
    meta = {"name": name.strip(), "description": description, "notes": {},
            "created_at": datetime.now(timezone.utc).isoformat()}
    _write(client_id, meta)
    return _public(client_id, meta)


def update_client(client_id: str, name=None, description=None, notes=None) -> dict:
    meta = _read(client_id)
    if name is not None:
        meta["name"] = name.strip()
    if description is not None:
        meta["description"] = description
    if notes is not None:
        meta["notes"] = {k: v for k, v in notes.items() if k in FILE_KINDS}
    _write(client_id, meta)
    return _public(client_id, meta)


def delete_client(client_id: str) -> None:
    _read(client_id)
    shutil.rmtree(_client_dir(client_id))


def save_file(client_id: str, kind: str, filename: str, fileobj) -> dict:
    meta = _read(client_id)
    if kind not in FILE_KINDS:
        raise ValueError(f"Unknown file kind '{kind}'")
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}")
    d = _client_dir(client_id) / "files"
    d.mkdir(exist_ok=True)
    old = file_path(client_id, kind)
    if old:
        old.unlink()
    with open(d / f"{kind}{ext}", "wb") as out:
        shutil.copyfileobj(fileobj, out)
    meta.setdefault("filenames", {})[kind] = filename
    _write(client_id, meta)
    return _public(client_id, meta)


def delete_file(client_id: str, kind: str) -> dict:
    meta = _read(client_id)
    p = file_path(client_id, kind)
    if p:
        p.unlink()
    meta.get("filenames", {}).pop(kind, None)
    _write(client_id, meta)
    return _public(client_id, meta)

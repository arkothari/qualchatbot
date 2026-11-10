"""File-based client registry: DATA_DIR/clients/<client_id>/{client.json, files/<kind>.<ext>}"""
import io
import json
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .config import ALLOWED_EXTENSIONS, DATA_DIR, FILE_KINDS

CLIENTS_DIR = DATA_DIR / "clients"
KEEP_VERSIONS = 5


class LoadRequired(Exception):
    """Replacing/removing existing files requires an open 'new data load'."""


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
        "loading": bool(meta.get("load")),
        "replaced": (meta.get("load") or {}).get("replaced", []),
        "load_snapshot": (meta.get("load") or {}).get("snapshot"),
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
    if old and not meta.get("load"):
        raise LoadRequired("Start a new data load before replacing existing files.")
    if old:
        old.unlink()
    with open(d / f"{kind}{ext}", "wb") as out:
        shutil.copyfileobj(fileobj, out)
    meta.setdefault("filenames", {})[kind] = filename
    load = meta.get("load")
    if load is not None:
        if kind not in load["replaced"]:
            load["replaced"].append(kind)
        if set(load["replaced"]) >= set(FILE_KINDS):  # all five refreshed -> load complete
            meta.pop("load")
    _write(client_id, meta)
    return _public(client_id, meta)


def delete_file(client_id: str, kind: str, force: bool = False) -> dict:
    meta = _read(client_id)
    p = file_path(client_id, kind)
    if p and not force and not meta.get("load"):
        raise LoadRequired("Start a new data load before removing existing files.")
    if p:
        p.unlink()
    meta.get("filenames", {}).pop(kind, None)
    _write(client_id, meta)
    return _public(client_id, meta)


# ---- versioning: zip snapshots of the 5 files + client.json, one per data load -------------
def _archive_dir(client_id: str) -> Path:
    return _client_dir(client_id) / "archive"


def snapshot(client_id: str) -> str | None:
    """Zip the current files + client.json. Keeps only the newest KEEP_VERSIONS. Returns the zip name."""
    d = _client_dir(client_id)
    files = [p for k in FILE_KINDS if (p := file_path(client_id, k))]
    if not files:
        return None
    arch = _archive_dir(client_id)
    arch.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    name, n = f"{stamp}.zip", 1
    while (arch / name).exists():
        name, n = f"{stamp}-{n}.zip", n + 1
    with zipfile.ZipFile(arch / name, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(d / "client.json", "client.json")
        for p in files:
            z.write(p, f"files/{p.name}")
    for old in sorted(arch.glob("*.zip"))[:-KEEP_VERSIONS]:
        old.unlink()
    return name


def start_load(client_id: str) -> dict:
    meta = _read(client_id)
    if not meta.get("load"):  # idempotent: an open load keeps its original snapshot
        name = snapshot(client_id)
        meta = _read(client_id)
        meta["load"] = {"started_at": datetime.now(timezone.utc).isoformat(), "replaced": [], "snapshot": name}
        _write(client_id, meta)
    return _public(client_id, meta)


def finish_load(client_id: str) -> dict:
    meta = _read(client_id)
    meta.pop("load", None)
    _write(client_id, meta)
    return _public(client_id, meta)


_ZIP_NAME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z(-\d+)?\.zip")


def list_versions(client_id: str) -> list[dict]:
    _read(client_id)
    arch = _archive_dir(client_id)
    out = []
    for p in sorted(arch.glob("*.zip"), reverse=True) if arch.exists() else []:
        out.append({"name": p.name, "size": p.stat().st_size,
                    "created_at": datetime.strptime(p.name[:20], "%Y-%m-%dT%H-%M-%SZ")
                    .replace(tzinfo=timezone.utc).isoformat()})
    return out


def version_path(client_id: str, name: str) -> Path:
    _read(client_id)
    if not _ZIP_NAME.fullmatch(name) or not (_archive_dir(client_id) / name).exists():
        raise KeyError(name)
    return _archive_dir(client_id) / name


def restore_version(client_id: str, name: str) -> dict:
    zbytes = version_path(client_id, name).read_bytes()  # read first: snapshot below may prune it
    snapshot(client_id)  # keep what's current so a restore can itself be undone
    d = _client_dir(client_id)
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        allowed = {"client.json"} | {f"files/{k}{e}" for k in FILE_KINDS for e in ALLOWED_EXTENSIONS}
        names = [n for n in z.namelist() if n in allowed]
        for old in (d / "files").glob("*"):
            old.unlink()
        for n in names:
            (d / n).parent.mkdir(exist_ok=True)
            (d / n).write_bytes(z.read(n))
    meta = _read(client_id)
    meta.pop("load", None)
    _write(client_id, meta)
    return _public(client_id, meta)

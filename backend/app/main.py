import hmac

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

from . import chat, data, storage
from .config import ADMIN_TOKEN, DEFAULT_MODEL, FILE_KINDS, MODELS

app = FastAPI(title="Qual Chatbot")


def require_admin(x_admin_token: str = Header(default="")):
    if ADMIN_TOKEN and not hmac.compare_digest(x_admin_token, ADMIN_TOKEN):
        raise HTTPException(401, "Invalid admin token")


def _client_or_404(client_id: str) -> dict:
    try:
        return storage.get_client(client_id)
    except KeyError:
        raise HTTPException(404, "Client not found")


class NewClient(BaseModel):
    name: str
    description: str = ""


class ClientPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    notes: dict[str, str] | None = None  # per-file descriptions, keyed by file kind


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None  # "haiku" | "sonnet"
    detail: str = "short"  # "short" | "detailed"


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def config():
    return {"models": list(MODELS), "default_model": DEFAULT_MODEL, "file_kinds": FILE_KINDS,
            "admin_protected": bool(ADMIN_TOKEN)}


@app.get("/api/admin/check", dependencies=[Depends(require_admin)])
def admin_check():
    return {"ok": True}


# ---- clients -------------------------------------------------------------
@app.get("/api/clients")
def list_clients():
    return storage.list_clients()


@app.get("/api/clients/{client_id}")
def get_client(client_id: str):
    return _client_or_404(client_id)


@app.post("/api/clients", dependencies=[Depends(require_admin)])
def create_client(body: NewClient):
    if not body.name.strip():
        raise HTTPException(422, "Name required")
    return storage.create_client(body.name, body.description)


@app.patch("/api/clients/{client_id}", dependencies=[Depends(require_admin)])
def patch_client(client_id: str, body: ClientPatch):
    _client_or_404(client_id)
    return storage.update_client(client_id, body.name, body.description, body.notes)


@app.delete("/api/clients/{client_id}", dependencies=[Depends(require_admin)])
def delete_client(client_id: str):
    _client_or_404(client_id)
    storage.delete_client(client_id)
    return {"ok": True}


# ---- files ---------------------------------------------------------------
@app.put("/api/clients/{client_id}/files/{kind}", dependencies=[Depends(require_admin)])
def upload_file(client_id: str, kind: str, file: UploadFile = File(...)):
    _client_or_404(client_id)
    try:
        client = storage.save_file(client_id, kind, file.filename or "", file.file)
        data.get_connection(client_id)  # validate the file parses; fail fast
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        storage.delete_file(client_id, kind)
        raise HTTPException(400, f"Could not parse file: {e}")
    return client


@app.delete("/api/clients/{client_id}/files/{kind}", dependencies=[Depends(require_admin)])
def remove_file(client_id: str, kind: str):
    _client_or_404(client_id)
    if kind not in FILE_KINDS:
        raise HTTPException(404, "Unknown file kind")
    return storage.delete_file(client_id, kind)


# ---- data + chat ---------------------------------------------------------
@app.get("/api/clients/{client_id}/schema")
def schema(client_id: str):
    _client_or_404(client_id)
    return data.describe(client_id)


@app.post("/api/clients/{client_id}/chat")
def chat_endpoint(client_id: str, body: ChatRequest):
    _client_or_404(client_id)
    if not body.messages or body.messages[-1].role != "user":
        raise HTTPException(422, "Last message must be from the user")
    try:
        return chat.answer(client_id, [m.model_dump() for m in body.messages], body.model, body.detail)
    except ValueError as e:
        raise HTTPException(400, str(e))

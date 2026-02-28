from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import re
import chromadb
from chromadb.utils import embedding_functions
from chromadb.config import Settings
import uuid
import json

app = FastAPI(title="MCP Memory Server")

BASE_DIR = Path(__file__).resolve().parent
_collections = {}
_client = None
_TEST_MODE = False

def _get_client(persistent: bool = True):
    global _client
    if _client is None:
        if persistent:
            _client = chromadb.PersistentClient(
                path=str(BASE_DIR / "data"),
                settings=Settings(anonymized_telemetry=False),
            )
        else:
            _client = chromadb.Client(settings=Settings(anonymized_telemetry=False))
    return _client

def _build_collection(codename: str, persistent: bool = True):
    embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    client = _get_client(persistent=persistent)
    return client.get_or_create_collection(
        name=f"project_memory_{codename}",
        embedding_function=embedding_function,
    )

def _normalize_codename(codename: str) -> str:
    value = (codename or "").strip().lower()
    if not value or not re.fullmatch(r"[a-z0-9_-]+", value):
        raise ValueError("Invalid codename")
    return value

def get_collection(codename: str):
    codename = _normalize_codename(codename)
    if codename not in _collections:
        _collections[codename] = _build_collection(codename=codename, persistent=True)
    return _collections[codename]

def set_test_collection(codename: str, collection):
    global _TEST_MODE
    codename = _normalize_codename(codename)
    _TEST_MODE = True
    _collections[codename] = collection

# --- ваши модели (можно оставить) ---
class StoreRequest(BaseModel):
    content: str
    tags: list[str] = []

class SearchRequest(BaseModel):
    query: str
    n_results: int = 5

class UpdateRequest(BaseModel):
    content: Optional[str] = None
    tags: Optional[list[str]] = None

class MemoryOut(BaseModel):
    id: str
    content: str
    tags: list[str] = []

def tool_text(text: str, is_error: bool = False):
    return {"content": [{"type": "text", "text": text}], "isError": is_error}

def _normalize_tags(tags: Optional[list[str]]) -> list[str]:
    if not tags:
        return []
    return [t.strip() for t in tags if t and t.strip()]

def _tags_to_metadata(tags: list[str]) -> dict:
    return {"tags": ",".join(tags)}

def _metadata_to_tags(metadata: Optional[dict]) -> list[str]:
    if not metadata:
        return []
    raw = metadata.get("tags") or ""
    if not raw:
        return []
    return [t for t in raw.split(",") if t]

def _serialize_memory(memory_id: str, document: str, metadata: Optional[dict]) -> dict:
    return {
        "id": memory_id,
        "content": document,
        "tags": _metadata_to_tags(metadata),
    }

def _get_memory_by_id(codename: str, memory_id: str) -> Optional[dict]:
    data = get_collection(codename).get(ids=[memory_id])
    if not data or not data.get("ids"):
        return None
    if len(data["ids"]) == 0:
        return None
    return _serialize_memory(data["ids"][0], data["documents"][0], data["metadatas"][0])

def store_memory(codename: str, content: str, tags: list[str]) -> dict:
    memory_id = str(uuid.uuid4())
    get_collection(codename).add(
        documents=[content],
        metadatas=[_tags_to_metadata(tags)],
        ids=[memory_id],
    )
    return _get_memory_by_id(codename, memory_id)

def list_memories(codename: str) -> list[dict]:
    data = get_collection(codename).get()
    memories = []
    for i in range(len(data["documents"])):
        memories.append(_serialize_memory(
            data["ids"][i],
            data["documents"][i],
            data["metadatas"][i],
        ))
    return memories

def search_memories(codename: str, query: str, n_results: int) -> list[dict]:
    results = get_collection(codename).query(query_texts=[query], n_results=n_results)
    memories = []
    for i in range(len(results["documents"][0])):
        memories.append(_serialize_memory(
            results["ids"][0][i],
            results["documents"][0][i],
            results["metadatas"][0][i],
        ))
    return memories

def update_memory(codename: str, memory_id: str, content: Optional[str], tags: Optional[list[str]]) -> Optional[dict]:
    existing = _get_memory_by_id(codename, memory_id)
    if not existing:
        return None
    new_content = content if content is not None else existing["content"]
    new_tags = _normalize_tags(tags) if tags is not None else existing["tags"]
    get_collection(codename).update(
        ids=[memory_id],
        documents=[new_content],
        metadatas=[_tags_to_metadata(new_tags)],
    )
    return _get_memory_by_id(codename, memory_id)

def delete_memory(codename: str, memory_id: str) -> bool:
    existing = _get_memory_by_id(codename, memory_id)
    if not existing:
        return False
    get_collection(codename).delete(ids=[memory_id])
    return True

def list_project_codenames() -> list[str]:
    names = set()
    if _TEST_MODE:
        names.update(_collections.keys())
    client = _get_client(persistent=not _TEST_MODE)
    try:
        collections = client.list_collections()
    except Exception:
        return sorted(names)
    for col in collections:
        name = getattr(col, "name", None)
        if name is None and isinstance(col, dict):
            name = col.get("name")
        if isinstance(name, str) and name.startswith("project_memory_"):
            names.add(name.replace("project_memory_", "", 1))
    return sorted(names)

TOOLS = [
    {
        "name": "memory.store",
        "description": "Store an important fact about the project",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Fact to store"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "memory.search",
        "description": "Search stored project facts",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "n_results": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory.update",
        "description": "Update a stored fact by id",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Memory id"},
                "content": {"type": "string", "description": "Updated fact content"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags"
                }
            },
            "required": ["id"]
        }
    },
    {
        "name": "memory.delete",
        "description": "Delete a stored fact by id",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Memory id"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "memory.all",
        "description": "List all stored facts",
        "inputSchema": {"type": "object", "additionalProperties": False}
    },
]


# --- REST API ---
@app.get("/api/projects/{codename}/memories", response_model=list[MemoryOut])
def api_list_memories(codename: str):
    try:
        codename = _normalize_codename(codename)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid codename")
    return list_memories(codename)

@app.get("/api/projects/{codename}/memories/search", response_model=dict)
def api_search_memories(codename: str, query: str, n_results: int = 5):
    try:
        codename = _normalize_codename(codename)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid codename")
    if not query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    return {"query": query, "results": search_memories(codename, query.strip(), n_results)}

@app.get("/api/projects/{codename}/memories/{memory_id}", response_model=MemoryOut)
def api_get_memory(codename: str, memory_id: str):
    try:
        codename = _normalize_codename(codename)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid codename")
    memory = _get_memory_by_id(codename, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="memory not found")
    return memory

@app.post("/api/projects/{codename}/memories", response_model=MemoryOut)
def api_create_memory(codename: str, body: StoreRequest):
    try:
        codename = _normalize_codename(codename)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid codename")
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    tags = _normalize_tags(body.tags)
    return store_memory(codename, content, tags)

@app.put("/api/projects/{codename}/memories/{memory_id}", response_model=MemoryOut)
def api_update_memory(codename: str, memory_id: str, body: UpdateRequest):
    try:
        codename = _normalize_codename(codename)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid codename")
    if body.content is None and body.tags is None:
        raise HTTPException(status_code=400, detail="content or tags is required")
    content = body.content.strip() if isinstance(body.content, str) else None
    tags = _normalize_tags(body.tags) if body.tags is not None else None
    updated = update_memory(codename, memory_id, content, tags)
    if not updated:
        raise HTTPException(status_code=404, detail="memory not found")
    return updated

@app.delete("/api/projects/{codename}/memories/{memory_id}", response_model=dict)
def api_delete_memory(codename: str, memory_id: str):
    try:
        codename = _normalize_codename(codename)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid codename")
    ok = delete_memory(codename, memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"deleted": True}

@app.get("/api/projects", response_model=list[str])
def api_list_projects():
    return list_project_codenames()

@app.post("/api/projects", response_model=dict)
def api_create_project(payload: dict):
    codename = payload.get("codename") if isinstance(payload, dict) else None
    if not isinstance(codename, str):
        raise HTTPException(status_code=400, detail="codename is required")
    try:
        codename = _normalize_codename(codename)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid codename")
    get_collection(codename)
    return {"codename": codename}

@app.post("/mcp/{codename}")
async def mcp(codename: str, request: Request):
    try:
        codename = _normalize_codename(codename)
    except ValueError:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32602, "message": "invalid codename"}})
    msg = await request.json()
    method = msg.get("method")
    rpc_id = msg.get("id")  # может отсутствовать у notification

    def ok(result: dict):
        # MCP поверх JSON-RPC
        if rpc_id is None:
            return Response(status_code=204)
        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result})

    def err(code: int, message: str):
        if rpc_id is None:
            return Response(status_code=204)
        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}})

    # 1) Handshake
    if method == "initialize":
        # protocolVersion лучше вернуть ту, что прислал клиент, если поддерживаете
        params = msg.get("params") or {}
        protocol_version = params.get("protocolVersion", "2025-11-25")
        return ok({
            "protocolVersion": protocol_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {}
            },
            "serverInfo": {"name": "mcp-memory", "version": "0.1.0"}
        })

    # notification: initialized (без id)
    if method == "initialized":
        return Response(status_code=204)

    # 2) Discovery
    if method == "tools/list":
        return ok({"tools": TOOLS, "nextCursor": None})

    if method == "resources/list":
        params = msg.get("params") or {}
        cursor = params.get("cursor")
        if cursor:
            return err(-32602, "Invalid cursor")
        resources = [
            {
                "uri": f"memory://project_memory/{codename}/all",
                "name": f"project_memory ({codename})",
                "description": "All stored memory entries as JSON",
                "mimeType": "application/json",
            }
        ]
        return ok({"resources": resources, "nextCursor": None})

    if method == "resources/templates/list":
        return ok({"resourceTemplates": [], "nextCursor": None})

    # 3) Tool calls
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}

        if name == "memory.store":
            content = (args.get("content") or "").strip()
            tags = _normalize_tags(args.get("tags") or [])
            if not content:
                return ok(tool_text("content is required", is_error=True))

            memory = store_memory(codename, content, tags)
            return ok(tool_text(f"stored id={memory['id']} tags={memory['tags']}"))


        if name == "memory.search":
            query = (args.get("query") or "").strip()
            n_results = int(args.get("n_results") or 5)
            if not query:
                return ok(tool_text("query is required", is_error=True))

            memories = search_memories(codename, query, n_results)
            return ok({
                "content": [{"type": "text", "text": str(memories)}],
                "structuredContent": {"query": query, "results": memories},
                "isError": False
            })

        if name == "memory.update":
            memory_id = (args.get("id") or "").strip()
            content = args.get("content")
            tags = args.get("tags")
            if not memory_id:
                return ok(tool_text("id is required", is_error=True))
            if content is None and tags is None:
                return ok(tool_text("content or tags is required", is_error=True))
            if isinstance(content, str):
                content = content.strip()
            tags = _normalize_tags(tags) if tags is not None else None
            updated = update_memory(codename, memory_id, content, tags)
            if not updated:
                return ok(tool_text("memory not found", is_error=True))
            return ok(tool_text(f"updated id={memory_id}"))

        if name == "memory.delete":
            memory_id = (args.get("id") or "").strip()
            if not memory_id:
                return ok(tool_text("id is required", is_error=True))
            ok_delete = delete_memory(codename, memory_id)
            if not ok_delete:
                return ok(tool_text("memory not found", is_error=True))
            return ok(tool_text(f"deleted id={memory_id}"))

        if name == "memory.all":
            memories = list_memories(codename)
            return ok({
                "content": [{"type": "text", "text": str(memories)}],
                "structuredContent": {"results": memories},
                "isError": False
            })

        return err(-32602, f"Unknown tool: {name}")

    if method == "resources/read":
        params = msg.get("params") or {}
        uri = params.get("uri")
        if uri == f"memory://project_memory/{codename}/all":
            memories = list_memories(codename)
            return ok({
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(memories, ensure_ascii=False)
                }]
            })
        return err(-32002, f"Resource not found: {uri}")

    # неизвестный метод
    return err(-32601, f"Method not found: {method}")

app.mount("/", StaticFiles(directory="public", html=True), name="static")

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions
from chromadb.config import Settings
import uuid
import json

app = FastAPI(title="MCP Memory Server")

BASE_DIR = Path(__file__).resolve().parent
_collection = None

def _build_collection(persistent: bool = True):
    embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    if persistent:
        client = chromadb.PersistentClient(
            path=str(BASE_DIR / "data"),
            settings=Settings(anonymized_telemetry=False),
        )
    else:
        client = chromadb.Client(settings=Settings(anonymized_telemetry=False))
    return client.get_or_create_collection(
        name="project_memory",
        embedding_function=embedding_function,
    )

def get_collection():
    global _collection
    if _collection is None:
        _collection = _build_collection(persistent=True)
    return _collection

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

def _get_memory_by_id(memory_id: str) -> Optional[dict]:
    data = get_collection().get(ids=[memory_id])
    if not data or not data.get("ids"):
        return None
    if len(data["ids"]) == 0:
        return None
    return _serialize_memory(data["ids"][0], data["documents"][0], data["metadatas"][0])

def store_memory(content: str, tags: list[str]) -> dict:
    memory_id = str(uuid.uuid4())
    get_collection().add(
        documents=[content],
        metadatas=[_tags_to_metadata(tags)],
        ids=[memory_id],
    )
    return _get_memory_by_id(memory_id)

def list_memories() -> list[dict]:
    data = get_collection().get()
    memories = []
    for i in range(len(data["documents"])):
        memories.append(_serialize_memory(
            data["ids"][i],
            data["documents"][i],
            data["metadatas"][i],
        ))
    return memories

def search_memories(query: str, n_results: int) -> list[dict]:
    results = get_collection().query(query_texts=[query], n_results=n_results)
    memories = []
    for i in range(len(results["documents"][0])):
        memories.append(_serialize_memory(
            results["ids"][0][i],
            results["documents"][0][i],
            results["metadatas"][0][i],
        ))
    return memories

def update_memory(memory_id: str, content: Optional[str], tags: Optional[list[str]]) -> Optional[dict]:
    existing = _get_memory_by_id(memory_id)
    if not existing:
        return None
    new_content = content if content is not None else existing["content"]
    new_tags = _normalize_tags(tags) if tags is not None else existing["tags"]
    get_collection().update(
        ids=[memory_id],
        documents=[new_content],
        metadatas=[_tags_to_metadata(new_tags)],
    )
    return _get_memory_by_id(memory_id)

def delete_memory(memory_id: str) -> bool:
    existing = _get_memory_by_id(memory_id)
    if not existing:
        return False
    get_collection().delete(ids=[memory_id])
    return True

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

RESOURCES = [
    {
        "uri": "memory://project_memory/all",
        "name": "project_memory (all)",
        "description": "All stored memory entries as JSON",
        "mimeType": "application/json",
    }
]

# --- REST API ---
@app.get("/api/memories", response_model=list[MemoryOut])
def api_list_memories():
    return list_memories()

@app.get("/api/memories/search", response_model=dict)
def api_search_memories(query: str, n_results: int = 5):
    if not query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    return {"query": query, "results": search_memories(query.strip(), n_results)}

@app.get("/api/memories/{memory_id}", response_model=MemoryOut)
def api_get_memory(memory_id: str):
    memory = _get_memory_by_id(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="memory not found")
    return memory

@app.post("/api/memories", response_model=MemoryOut)
def api_create_memory(body: StoreRequest):
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    tags = _normalize_tags(body.tags)
    return store_memory(content, tags)

@app.put("/api/memories/{memory_id}", response_model=MemoryOut)
def api_update_memory(memory_id: str, body: UpdateRequest):
    if body.content is None and body.tags is None:
        raise HTTPException(status_code=400, detail="content or tags is required")
    content = body.content.strip() if isinstance(body.content, str) else None
    tags = _normalize_tags(body.tags) if body.tags is not None else None
    updated = update_memory(memory_id, content, tags)
    if not updated:
        raise HTTPException(status_code=404, detail="memory not found")
    return updated

@app.delete("/api/memories/{memory_id}", response_model=dict)
def api_delete_memory(memory_id: str):
    ok = delete_memory(memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"deleted": True}

@app.post("/mcp")
async def mcp(request: Request):
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
        return ok({"resources": RESOURCES, "nextCursor": None})

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

            memory = store_memory(content, tags)
            return ok(tool_text(f"stored id={memory['id']} tags={memory['tags']}"))


        if name == "memory.search":
            query = (args.get("query") or "").strip()
            n_results = int(args.get("n_results") or 5)
            if not query:
                return ok(tool_text("query is required", is_error=True))

            memories = search_memories(query, n_results)
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
            updated = update_memory(memory_id, content, tags)
            if not updated:
                return ok(tool_text("memory not found", is_error=True))
            return ok(tool_text(f"updated id={memory_id}"))

        if name == "memory.delete":
            memory_id = (args.get("id") or "").strip()
            if not memory_id:
                return ok(tool_text("id is required", is_error=True))
            ok_delete = delete_memory(memory_id)
            if not ok_delete:
                return ok(tool_text("memory not found", is_error=True))
            return ok(tool_text(f"deleted id={memory_id}"))

        if name == "memory.all":
            memories = list_memories()
            return ok({
                "content": [{"type": "text", "text": str(memories)}],
                "structuredContent": {"results": memories},
                "isError": False
            })

        return err(-32602, f"Unknown tool: {name}")

    if method == "resources/read":
        params = msg.get("params") or {}
        uri = params.get("uri")
        if uri == "memory://project_memory/all":
            memories = list_memories()
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

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import chromadb
from chromadb.utils import embedding_functions
from chromadb.config import Settings
import uuid
import json

app = FastAPI(title="MCP Memory Server")

# --- Embeddings ---
embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

# --- Chroma persistent client (рекомендованный вариант) ---
client = chromadb.PersistentClient(
    path="./data",
    settings=Settings(anonymized_telemetry=False),
)
collection = client.get_or_create_collection(
    name="project_memory",
    embedding_function=embedding_function
)

# --- ваши модели (можно оставить) ---
class StoreRequest(BaseModel):
    content: str
    tags: list[str] = []

class SearchRequest(BaseModel):
    query: str
    n_results: int = 5

def tool_text(text: str, is_error: bool = False):
    return {"content": [{"type": "text", "text": text}], "isError": is_error}

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
            tags = args.get("tags") or []
            if not content:
                return ok(tool_text("content is required", is_error=True))

            memory_id = str(uuid.uuid4())
            collection.add(
                documents=[content],
                metadatas=[{"tags": ",".join(tags)}],
                ids=[memory_id]
            )
            return ok(tool_text(f"stored id={memory_id} tags={tags}"))


        if name == "memory.search":
            query = (args.get("query") or "").strip()
            n_results = int(args.get("n_results") or 5)
            if not query:
                return ok(tool_text("query is required", is_error=True))

            results = collection.query(query_texts=[query], n_results=n_results)
            memories = []
            for i in range(len(results["documents"][0])):
                memories.append({
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                })
            return ok({
                "content": [{"type": "text", "text": str(memories)}],
                "structuredContent": {"query": query, "results": memories},
                "isError": False
            })

        if name == "memory.all":
            data = collection.get()
            memories = []
            for i in range(len(data["documents"])):
                memories.append({
                    "id": data["ids"][i],
                    "content": data["documents"][i],
                    "metadata": data["metadatas"][i]
                })
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
            data = collection.get()
            memories = []
            for i in range(len(data["documents"])):
                memories.append({
                    "id": data["ids"][i],
                    "content": data["documents"][i],
                    "metadata": data["metadatas"][i]
                })
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

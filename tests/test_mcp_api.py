def _rpc(client, codename, payload):
    resp = client.post(f"/mcp/{codename}", json=payload)
    assert resp.status_code in (200, 204)
    if resp.status_code == 204:
        return None
    return resp.json()


def _extract_id(text):
    marker = "id="
    start = text.find(marker)
    if start == -1:
        return None
    start += len(marker)
    end = text.find(" ", start)
    if end == -1:
        end = len(text)
    return text[start:end]


def test_mcp_tools_flow(client, codename):
    init = _rpc(client, codename, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}})
    assert init["result"]["protocolVersion"] == "2025-11-25"

    tools = _rpc(client, codename, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tool_names = [t["name"] for t in tools["result"]["tools"]]
    assert "memory.update" in tool_names
    assert "memory.delete" in tool_names

    stored = _rpc(client, codename, {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "memory.store", "arguments": {"content": "mcp fact", "tags": ["mcp"]}},
    })
    text = stored["result"]["content"][0]["text"]
    memory_id = _extract_id(text)
    assert memory_id

    searched = _rpc(client, codename, {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "memory.search", "arguments": {"query": "mcp", "n_results": 5}},
    })
    results = searched["result"]["structuredContent"]["results"]
    assert len(results) >= 1

    updated = _rpc(client, codename, {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "memory.update", "arguments": {"id": memory_id, "content": "mcp updated"}},
    })
    assert updated["result"]["isError"] is False

    all_items = _rpc(client, codename, {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {"name": "memory.all", "arguments": {}},
    })
    all_results = all_items["result"]["structuredContent"]["results"]
    assert any(item["id"] == memory_id for item in all_results)

    deleted = _rpc(client, codename, {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": "memory.delete", "arguments": {"id": memory_id}},
    })
    assert deleted["result"]["isError"] is False

def test_rest_crud(client):
    resp = client.post("/api/memories", json={"content": "first fact", "tags": ["api", "backend"]})
    assert resp.status_code == 200
    data = resp.json()
    memory_id = data["id"]
    assert data["content"] == "first fact"
    assert data["tags"] == ["api", "backend"]

    resp = client.get("/api/memories")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.put(f"/api/memories/{memory_id}", json={"content": "updated fact"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "updated fact"

    resp = client.get(f"/api/memories/{memory_id}")
    assert resp.status_code == 200
    assert resp.json()["content"] == "updated fact"

    resp = client.delete(f"/api/memories/{memory_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    resp = client.get("/api/memories")
    assert resp.status_code == 200
    assert resp.json() == []


def test_rest_search(client):
    resp = client.post("/api/memories", json={"content": "searchable fact", "tags": ["search"]})
    memory_id = resp.json()["id"]

    resp = client.get("/api/memories/search", params={"query": "search", "n_results": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "search"
    assert len(data["results"]) >= 1
    assert data["results"][0]["id"] == memory_id

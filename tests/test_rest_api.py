def test_rest_crud(client, codename):
    resp = client.post(f"/api/projects/{codename}/memories", json={"content": "first fact", "tags": ["api", "backend"]})
    assert resp.status_code == 200
    data = resp.json()
    memory_id = data["id"]
    assert data["content"] == "first fact"
    assert data["tags"] == ["api", "backend"]

    resp = client.get(f"/api/projects/{codename}/memories")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.put(f"/api/projects/{codename}/memories/{memory_id}", json={"content": "updated fact"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "updated fact"

    resp = client.get(f"/api/projects/{codename}/memories/{memory_id}")
    assert resp.status_code == 200
    assert resp.json()["content"] == "updated fact"

    resp = client.delete(f"/api/projects/{codename}/memories/{memory_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    resp = client.get(f"/api/projects/{codename}/memories")
    assert resp.status_code == 200
    assert resp.json() == []


def test_rest_search(client, codename):
    resp = client.post(f"/api/projects/{codename}/memories", json={"content": "searchable fact", "tags": ["search"]})
    memory_id = resp.json()["id"]

    resp = client.get(f"/api/projects/{codename}/memories/search", params={"query": "search", "n_results": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "search"
    assert len(data["results"]) >= 1
    assert data["results"][0]["id"] == memory_id


def test_projects_endpoints(client, codename):
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert codename in resp.json()

    new_code = f"{codename}_new"
    resp = client.post("/api/projects", json={"codename": new_code})
    assert resp.status_code == 200
    assert resp.json()["codename"] == new_code

    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert new_code in resp.json()

# MCP Memory Server

## Установка и запуск

```sh
python -m venv venv
./venv/Scripts/Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn server:app --reload --port 3123
```

## API

### MCP (JSON-RPC)

Base URL: `/mcp/{codename}`

### REST

- `GET /api/projects` — список проектов (collections).
- `POST /api/projects` — создать проект `{ "codename": "my_project" }`.
- `GET /api/projects/{codename}/memories`
- `GET /api/projects/{codename}/memories/{id}`
- `GET /api/projects/{codename}/memories/search?query=...&n_results=...`
- `POST /api/projects/{codename}/memories`
- `PUT /api/projects/{codename}/memories/{id}`
- `DELETE /api/projects/{codename}/memories/{id}`

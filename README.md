# MCP Memory Server

## Установка и запуск

```sh
python -m venv venv
./venv/Scripts/Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn server:app --reload --port 3123
```

## Prompt

```
У тебя есть доступ к инструменту memory.

Правила:
- Всегда сначала вызывай memory.search перед ответом.
- Если узнаёшь новую важную информацию о проекте — вызывай memory.store.
- Не сохраняй временные данные и куски кода.
- Используй найденную память для ответа.
```

# Execução local

## Pré-requisitos

- Python 3.12
- Docker Desktop em modo Linux (para o ambiente completo e para a suíte de testes)

## Arquivo `.env`

Na raiz do projeto, gere uma chave operacional aleatória. O arquivo é ignorado pelo Git.

```powershell
python -c "import secrets; from pathlib import Path; p=Path('.env'); assert not p.exists(), 'Arquivo já existe'; p.write_text('AUTOFLOW_API_KEY='+secrets.token_hex(32)+'\n', encoding='utf-8')"
```

## Docker Compose (ambiente completo)

```powershell
docker compose up --build -d
docker compose down
```

- O serviço `migrate` aplica as migrações Alembic antes de a API subir.
- API, worker Celery e scheduler (beat) rodam juntos. Sem worker/Redis, o endpoint de execuções aceita o arquivo e ele permanece em `queued`.
- PostgreSQL e Redis não expõem portas no host; a API escuta somente em `127.0.0.1:8000`.
- A senha PostgreSQL do Compose é exclusiva da demonstração local.
- Os containers da aplicação rodam com usuário sem privilégios e `no-new-privileges`; API e worker têm limites de CPU e memória.

## Somente a API (SQLite)

Na pasta `backend`:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m uvicorn app.main:app --env-file ../.env --reload
```

Abra:

- http://localhost:8000 — demonstração pública
- http://localhost:8000/workspace — área privada (convite, ativação e login; veja [contas](accounts.md))
- http://localhost:8000/assistente — assistente por R.E., voz e texto
- http://localhost:8000/docs — Swagger (**Authorize** recebe a `AUTOFLOW_API_KEY`)

As rotas `/api/v1` aceitam sessão individual com proteção CSRF nas escritas, ou `X-API-Key` para o acervo legado. Health e documentação são públicos.

## Migração de banco antigo

Em banco novo, use somente `alembic upgrade head`.

Para um banco criado pelo MVP anterior às migrações, faça backup e confira o schema antes de usar `alembic stamp 0001` seguido de `alembic upgrade head`. Não use `stamp` em banco desconhecido ou vazio e não execute várias migrações simultaneamente.

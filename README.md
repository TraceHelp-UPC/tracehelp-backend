# TraceHelp Backend

Backend monolítico modular de TraceHelp (Python 3.11 + FastAPI + PostgreSQL/pgvector).

## Estructura

```
app/
├── core/            # Configuración y conexión a la base de datos
├── shared/          # Elementos comunes (bus de eventos, excepciones, etc.)
├── iam/             # Bounded Context IAM
├── helpdesk/        # Bounded Context Helpdesk
├── knowledge/       # Bounded Context Knowledge Management
├── smart_triage/    # Bounded Context Smart Triage
└── analytics/       # Bounded Context Analytics
```

Cada contexto tiene las capas `domain`, `application`, `infrastructure` e `interfaces/rest`.
Las tablas llevan el prefijo de su contexto: `iam_`, `helpdesk_`, `kb_`, `triage_`, `analytics_`.

## Ejecutar con Docker (recomendado)

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health (debe mostrar `database: up`, `pgvector: true` y `tesseract: true`)

## Ejecutar sin Docker

Requiere PostgreSQL con pgvector corriendo (puedes levantar solo la base con `docker compose up db`).

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Pruebas

```bash
pytest
```

## Convenciones

- Ramas: GitFlow (`feature/<ID>-<descripcion>` desde `develop`).
- Commits: Conventional Commits con scopes `iam`, `helpdesk`, `smart-triage`, `knowledge`, `analytics`, `infra`.

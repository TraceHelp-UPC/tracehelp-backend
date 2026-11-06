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

## Migraciones (Alembic)

Las migraciones se aplican solas al arrancar el contenedor (`alembic upgrade head`).
Para crear una migración nueva después de cambiar modelos ORM:

```bash
docker compose exec api alembic revision --autogenerate -m "descripcion del cambio"
docker compose exec api alembic upgrade head
```

Los modelos nuevos deben importarse en `app/core/orm_registry.py` para que Alembic los detecte.

## Pruebas

```bash
# Solo pruebas unitarias
pytest

# Unitarias + integración contra PostgreSQL (crea y limpia la base tracehelp_test)
docker compose up -d db
TEST_DATABASE_URL=postgresql+psycopg://tracehelp:tracehelp@localhost:5432/tracehelp_test pytest
```

Pruebas BDD (Behave) con los escenarios Gherkin de `features/`:

```bash
docker compose exec -e TEST_DATABASE_URL=postgresql+psycopg://tracehelp:tracehelp@db:5432/tracehelp_test api behave
```

En PowerShell: `$env:TEST_DATABASE_URL="postgresql+psycopg://tracehelp:tracehelp@localhost:5432/tracehelp_test"; pytest`

## Endpoints protegidos (JWT y RBAC)

1. `POST /api/v1/auth/login` devuelve el `access_token`.
2. Las demás peticiones envían `Authorization: Bearer <access_token>` (en Swagger: botón **Authorize**).
3. Cada endpoint declara el permiso que exige con `require_permission(...)` de `app/iam/interfaces/rest/auth_dependencies.py`:

```python
current_user: CurrentUser = Depends(require_permission(Permission.TICKETS_MANAGE))
```

Respuestas: **401** sin token o con token inválido/expirado; **403** si el rol no tiene el permiso.
La matriz de permisos por rol está en `app/iam/domain/permissions.py`.

Usuarios de prueba: `docker compose exec api python -m app.scripts.seed_demo_data`
(`colaborador@`, `analista@`, `especialista@` y `lider@demo.tracehelp.pe`, contraseña `TraceHelp2026`).

## Convenciones

- Ramas: GitFlow (`feature/<ID>-<descripcion>` desde `develop`).
- Commits: Conventional Commits con scopes `iam`, `helpdesk`, `smart-triage`, `knowledge`, `analytics`, `infra`.

## Anonimización antes de Gemini (PII)

Ningún texto sale hacia Gemini sin pasar por `app/shared/infrastructure/pii_masker.py` (T27). El módulo
oculta credenciales, tokens, correos, IP, DNI, teléfonos, usuarios y nombres de personas (spaCy) y firma el
resultado con un sello HMAC (`PII_AUDIT_SECRET`). Los adaptadores de Gemini reciben `SanitizedText` y llaman a
`ensure_sealed(texto, masker)` antes de enviar; un `str` sin sello se rechaza.

```python
from app.shared.domain.pii import ensure_sealed
from app.shared.infrastructure.pii_masker import get_pii_masker

masker = get_pii_masker()
seguro = masker.mask("Soy Carlos, mi IP es 10.4.2.18")
texto_para_gemini = ensure_sealed(seguro, masker)   # "Soy [REDACTED_PERSON], mi IP es [REDACTED_IP]"
```

## Ingesta de manuales (Knowledge Management)

1. `POST /api/v1/workspaces/{id}/documents` (rol IT_LEADER) recibe un PDF o Markdown de hasta 25 MB y responde
   **202** con `job_id`.
2. Un worker en segundo plano (`app/knowledge/infrastructure/ingestion_worker.py`) extrae el texto por página y
   párrafo, lo divide en fragmentos con solapamiento, lo anonimiza (PII) y genera embeddings con
   `gemini-embedding-001` (768 dimensiones, normalizados) que se guardan en `kb_knowledge_chunks` con índice HNSW.
3. `GET /api/v1/documents/jobs/{job_id}` muestra el avance: `PENDING → PROCESSING → VECTORIZED` o `FAILED` con
   el motivo en `error_message`.

Para probarlo en local hace falta `GEMINI_API_KEY` en el `.env`; sin la clave el documento termina en `FAILED`
con el mensaje "falta GEMINI_API_KEY". Si la API se reinicia a mitad de una ingesta, al arrancar se reanudan los
documentos que quedaron `PENDING` o `PROCESSING`. En las pruebas el worker está desactivado
(`INGESTION_WORKER_ENABLED=false`) y Gemini siempre se simula.

Nota sobre migraciones con pgvector: `alembic revision --autogenerate` genera la columna como
`pgvector.sqlalchemy.vector.VECTOR(dim=768)` sin importar el módulo; cámbiala por `Vector(768)` con
`from pgvector.sqlalchemy import Vector` (ver `alembic/versions/20261106_0003_knowledge_chunks.py`).
## Formato de errores (RFC 7807)

Todos los errores responden `application/problem+json` con `type`, `title`, `status`, `detail` e `instance`
(los de validación agregan `errors` por campo). `detail` siempre es texto, porque Appsmith lo muestra con
`showAlert(Query.data?.detail)`.

Las excepciones de dominio no necesitan traducirse en el router: `ResourceNotFoundError` responde 404,
`DomainValidationError` 400 y cualquier otro `DomainError` 422. Si una excepción necesita otro código
(401, 403, 409...), se agrega en `app/core/error_handlers.py`.

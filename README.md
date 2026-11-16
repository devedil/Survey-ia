# AI Survey Assistant

Aplicación local para asistir a formularios y encuestas con un flujo controlado por usuario y evidencia interna.

## Estado actual

Se han completado la Fase 0, la Fase 1 y la Fase 2 del plan maestro:

- estructura del repositorio;
- backend FastAPI con `/health`;
- API de perfiles y hechos con CRUD en SQLAlchemy;
- carga privada de documentos con validación y extracción PDF/DOCX/TXT/MD/XLSX;
- fragmentación, embeddings OpenAI configurables y recuperación con pgvector;
- frontend Angular base;
- Docker Compose para PostgreSQL compatible con pgvector;
- variables de entorno y documentación base.

## Requisitos

- Python 3.13+
- Node.js 20+
- Docker Desktop / Docker Engine

## Arranque rápido

### 1) Base de datos

```powershell
docker compose up -d
```

### 2) Configuración

Copiar `.env.example` a `.env` y configurar al menos `DATABASE_URL`,
`OPENAI_API_KEY` y `OPENAI_EMBEDDING_MODEL`. El modelo de embeddings debe
devolver vectores de 1536 dimensiones. Los archivos se guardan bajo
`DOCUMENT_STORAGE_PATH` (por defecto `./storage/documents`).

### 3) Migraciones y backend

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
.\.venv\Scripts\python.exe -m alembic -c .\backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 4) Frontend

```powershell
cd frontend
npm install
npm start -- --host 0.0.0.0
```

## Endpoints principales

- `GET /health`
- `POST /api/v1/documents` (multipart: `profile_id`, `file`)
- `GET /api/v1/documents?profile_id=<uuid>`
- `GET /api/v1/documents/{document_id}`
- `POST /api/v1/documents/{document_id}/reindex`
- `POST /api/v1/documents/search`
- `DELETE /api/v1/documents/{document_id}`

Los formatos admitidos son PDF con texto, DOCX, TXT, MD y XLSX. XLSX se lee
en modo de solo lectura y sin evaluar fórmulas ni macros. El contenido del
documento se trata como datos no confiables.

## Seguridad

- No versionar secretos.
- Usar `.env` local y `.env.example` como referencia.
- Mantener el uso de la aplicación en localhost durante la primera versión.

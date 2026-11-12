# AI Survey Assistant

Aplicación local para asistir a formularios y encuestas con un flujo controlado por usuario y evidencia interna.

## Estado actual

Se ha inicializado la Fase 0 y avanzado a la Fase 1 del plan maestro:

- estructura del repositorio;
- backend FastAPI con `/health`;
- API de perfiles y hechos con CRUD en SQLAlchemy;
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

### 2) Backend

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3) Frontend

```powershell
cd frontend
npm install
npm start -- --host 0.0.0.0
```

## Endpoints de salud

- `GET /health`

## Seguridad

- No versionar secretos.
- Usar `.env` local y `.env.example` como referencia.
- Mantener el uso de la aplicación en localhost durante la primera versión.

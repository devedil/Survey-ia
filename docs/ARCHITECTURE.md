# Arquitectura

Este repositorio sigue la propuesta de la Fase 0 del plan maestro:

- backend FastAPI para API local, validación y orquestación de workflows.
- frontend Angular para panel local y revisión humana.
- PostgreSQL con pgvector para almacenamiento estructurado y vectorial.
- Docker Compose para levantar la infraestructura y mantener entornos reproducibles.

## Estructura

```text
backend/
  app/
    core/
    profiles/
    documents/
  tests/
frontend/
  src/
docs/
docker-compose.yml
.env.example
```

## Ejecutar en desarrollo

1. `docker compose up -d`
2. `pip install -r backend/requirements.txt`
3. `uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload`
4. `cd frontend && npm install && npm start -- --host 0.0.0.0`

## Consideraciones

- El almacenamiento permanece local y no se exponen secretos en repositorio.
- La primera versión prioriza validación humana y un alcance acotado.
- Los documentos se guardan en un directorio privado fuera de las rutas servidas por la API.
- Los fragmentos y vectores pgvector se eliminan en cascada con el documento.
- La búsqueda vectorial usa distancia coseno y devuelve el documento y el fragmento de origen.
- Embeddings usan el modelo OpenAI configurado por `OPENAI_EMBEDDING_MODEL`; configura un modelo que produzca 1536 dimensiones.
- Para indexar documentos, configura `OPENAI_API_KEY` y ejecuta primero `alembic upgrade head`.

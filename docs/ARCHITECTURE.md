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
    answers/
    memory/
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
- El enrutador IA requiere `OPENAI_DEFAULT_MODEL`; el nombre y la tarifa del modelo vienen de configuración, no de la lógica de negocio.
- Prompts versionados tratan preguntas y documentos como datos no confiables; las propuestas abstienen si no hay evidencia verificable y requieren revisión humana.
- `model_usage` registra proveedor, modelo, tokens reportados, caché si existe, duración, estado y tarifa/catálogo versionado; sin tarifa se marca costo estimado y no disponible.
- `MAX_INPUT_TOKENS_PER_CALL`, `MAX_OUTPUT_TOKENS_PER_CALL`, `MAX_RETRIES_PER_QUESTION` y `MAX_CALLS_PER_QUESTION` limitan solicitudes y gasto.
- El historial conserva propuestas y decisiones; solo una aprobación/corrección explícita con `save_as_fact=true` crea un hecho reutilizable.
- Los hechos guardan fuente, estado, sensibilidad, consentimiento, vigencia e historial de revisión; la recuperación excluye hechos no verificados, sensibles, sin consentimiento o vencidos.
- La memoria ofrece búsqueda, detección de duplicados, exportación y borrado; las propuestas y correcciones se pueden inspeccionar y las correcciones no aprobadas se pueden revertir.

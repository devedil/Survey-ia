# Arquitectura

Este repositorio sigue la propuesta de la Fase 0 del plan maestro:

- backend FastAPI para API local, validación y orquestación de workflows.
- frontend Angular para panel local y revisión humana.
- extensión Chrome Manifest V3 para asistir en la pestaña activa, conectada
  al backend local mediante token Bearer, CORS exacto y revisión humana.
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
    browser/
  tests/
frontend/
  src/
chrome-extension/
  manifest.json
  service-worker.js
  sidepanel.html
  sidepanel.js
  sidepanel.css
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
- Las sesiones Playwright usan contextos aislados, admiten únicamente orígenes loopback configurados y el sitio de prueba local. CAPTCHA, navegación externa y solicitudes de escritura detienen o bloquean la sesión.
- El navegador inspecciona etiquetas, opciones y atributos de campos, pero no lee valores ya introducidos; `fill-approved` solo usa propuestas persistidas y aprobadas y verifica el valor tras rellenar. Nunca activa controles de envío.
- `browser_audit_events` conserva acciones y estado sin almacenar valores de formularios.
- La extensión Chrome usa permisos `activeTab`, `scripting`, `sidePanel` y `storage`, sin permisos globales de host ni lectura de cookies. El permiso de pestaña se usa tras una acción explícita; la lista de orígenes es exacta y local.
- Las rutas `/api/v1/chrome-extension/*` requieren un token Bearer local de al menos 32 caracteres. `CORS_ALLOWED_ORIGINS` valida orígenes exactos loopback y el ID exacto de la extensión; no admite comodines. El token vive en `chrome.storage.session`, no se envía al proveedor de IA ni se guarda en Git.
- Antes de pedir una propuesta, la extensión informa que pregunta/contexto quedarán en el historial local y pueden enviarse al proveedor configurado; requiere confirmación. El historial persiste la propuesta para permitir revisión/aprobación.
- `chrome_extension_audit_events` registra perfil, origen, acción y tipo de control; no guarda texto de pregunta, respuesta, URL completa ni valores del formulario.
- El relleno está separado de la aprobación, revalida el mismo tab/origen/URL y una firma del control, y solo soporta texto, radio y selección única. No envía ni avanza formularios.
- Playwright continúa limitado a pruebas locales; no se conecta al perfil autenticado de Chrome.

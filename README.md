# AI Survey Assistant

Aplicación local para asistir a formularios y encuestas con un flujo controlado por usuario y evidencia interna.

## Estado actual

Se han completado las Fases 0 a 5 del plan maestro. La Fase 6 (integración
con Chrome) acaba de comenzar:

- estructura del repositorio;
- backend FastAPI con `/health`;
- API de perfiles y hechos con CRUD en SQLAlchemy;
- carga privada de documentos con validación y extracción PDF/DOCX/TXT/MD/XLSX;
- fragmentación, embeddings OpenAI configurables y recuperación con pgvector;
- análisis de preguntas y propuestas de respuesta fundamentadas con abstención;
- validación de citas/formato, detección de contradicciones y revisión humana;
- registro de tokens, duración, estado y costo según catálogo de precios configurado;
- historial de propuestas, aprobación/rechazo/corrección y memoria reutilizable solo con aprobación explícita;
- procedencia, sensibilidad, consentimiento, vigencia, historial/reversión, búsqueda, deduplicación, exportación y borrado de hechos;
- sesiones Playwright restringidas al formulario local, inspección de controles y escritura verificada solo tras aprobación explícita;
- registro persistente de acciones del navegador, con bloqueo de navegación externa, CAPTCHA y solicitudes no seguras;
- prototipo de extensión Chrome Manifest V3 que, tras una acción explícita, inspecciona controles visibles en un origen exacto autorizado;
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

Copiar `.env.example` a `.env`. `BROWSER_ALLOWED_ORIGINS` solo configura el
navegador Playwright de pruebas, que acepta el sitio local de prueba y no
navega a otros dominios. La extensión Chrome es experimental: su primer
incremento solo inspecciona controles visibles en el origen exacto que
agregues manualmente; no se conecta al backend, no rellena campos ni envía
formularios. Para usar documentos, configurar
`OPENAI_API_KEY` y `OPENAI_EMBEDDING_MODEL`; para analizar/proponer respuestas,
configurar además `OPENAI_DEFAULT_MODEL`. Los modelos de embeddings deben
devolver vectores de 1536 dimensiones. La clave puede incorporarse después;
sin ella, los endpoints IA devuelven un error de configuración explícito.
Los archivos se guardan bajo
`DOCUMENT_STORAGE_PATH` (por defecto `./storage/documents`).
`OPENAI_PRICING_CATALOG` acepta un JSON versionado por modelo, por ejemplo:
`{"modelo":{"version":"2026-01","input_usd_per_million":1.0,"output_usd_per_million":2.0}}`.
Sin precio configurado, el uso se registra con costo no disponible y marcado
como estimado; no se codifican tarifas en la lógica.

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
- `POST /api/v1/questions/analyze`
- `POST /api/v1/answers/propose`
- `GET /api/v1/answers?profile_id=<uuid>` y `GET /api/v1/answers/{proposal_id}`
- `POST /api/v1/answers/{proposal_id}/approve|reject|correct`
- `GET /api/v1/answers/{proposal_id}/history`
- `GET|POST|DELETE /api/v1/memory`
- `GET /api/v1/memory/export?profile_id=<uuid>` y `GET /api/v1/memory/duplicates?profile_id=<uuid>`
- `GET /api/v1/browser/test-site` (formulario de prueba local)
- `POST /api/v1/browser/sessions` y `GET /api/v1/browser/sessions/{session_id}`
- `POST /api/v1/browser/sessions/{session_id}/navigate|inspect|propose|fill-approved|stop`
- `GET /api/v1/browser/audit/events`

Los formatos admitidos son PDF con texto, DOCX, TXT, MD y XLSX. XLSX se lee
en modo de solo lectura y sin evaluar fórmulas ni macros. El contenido del
documento se trata como datos no confiables.

Las propuestas de `/api/v1/answers/propose` siempre requieren revisión humana.
Solo usan hechos verificados y fragmentos documentales recuperados, validan
fuentes citadas y formato, y se abstienen ante falta de evidencia, datos
sensibles o hechos contradictorios. Las propuestas se conservan en el historial y nunca se convierten en hechos
por sí solas. Para incorporar un hecho hace falta aprobarlo con
`save_as_fact=true`; la búsqueda reutilizable excluye hechos no verificados,
sensibles, sin consentimiento o vencidos. Los hechos pueden editarse,
consultarse, exportarse y eliminarse. Las llamadas a OpenAI y la memoria
requieren la migración vigente (`alembic upgrade head`).

Playwright abre Chromium en modo headless. Después de instalar las dependencias,
instala el navegador requerido con
`.\.venv\Scripts\python.exe -m playwright install chromium`.
La API solo permite navegar al formulario local de prueba, detecta controles
de formulario sin leer sus valores actuales y nunca pulsa botones ni envía el
formulario. `fill-approved` no acepta texto del cliente: exige una propuesta
respaldada, aprobada y correspondiente a la pregunta inspeccionada, y verifica
que el valor resultante coincida con el aprobado. CAPTCHA o intentos de salir
del sitio permitido bloquean la sesión. Las acciones se guardan en la tabla
`browser_audit_events`; no se guardan respuestas de campos en la auditoría.

## Extensión Chrome (prototipo de solo lectura)

1. Abre `chrome://extensions` en Chrome y activa **Modo de desarrollador**.
2. Selecciona **Cargar descomprimida** y elige la carpeta `chrome-extension`.
3. Abre solo una página cuyo uso asistido esté permitido.
4. Abre la extensión desde la barra de herramientas, agrega el origen HTTPS
   exacto y elige **Inspeccionar pestaña activa**.

Este prototipo solicita únicamente `activeTab`, `scripting`, `sidePanel` y
`storage`; no pide acceso a cookies ni permisos globales de sitios. La lista
de orígenes se guarda localmente. La inspección se ejecuta bajo demanda y
muestra controles nativos visibles; las preguntas todavía no se envían a la
IA. La propuesta, aprobación y relleno desde Chrome se implementarán después
de añadir autenticación segura para la API local. No uses la extensión en
sitios que prohíban este tipo de asistencia.

## Seguridad

- No versionar secretos.
- Usar `.env` local y `.env.example` como referencia.
- Mantener el uso de la aplicación en localhost durante la primera versión.

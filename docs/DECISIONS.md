# Decisiones de implementación

## Entorno

- Python 3.13.7 en el entorno virtual del proyecto.
- Node.js 24 y Angular 20 para el panel local.
- Docker Compose para PostgreSQL con pgvector.

## Política de versiones

- Las dependencias se fijan a versiones compatibles y se documentan en `backend/requirements.txt`.
- No se versionan claves ni tokens reales.

## Seguridad

- La API se conecta en localhost.
- Las variables sensibles se leen desde `.env` y no se suben al repositorio.
- El flujo experimental exige aprobación humana antes de rellenar formularios o almacenar hechos.

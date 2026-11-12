# AI Survey Assistant

## Plan maestro de arquitectura, implementación y desarrollo

**Versión:** 1.0\
**Fecha:** 12 de noviembre de 2026\
**Estado:** Plan de desarrollo\
**Objetivo:** Construir una aplicación local para Windows que asista al
usuario al responder cuestionarios y formularios autorizados, utilizando
información personal proporcionada y verificada, documentos propios y
memoria histórica aprobada.

------------------------------------------------------------------------

# 1. Visión y alcance

AI Survey Assistant será una aplicación local con un panel web y un
agente que interactúa con un navegador y, en una fase posterior, con la
interfaz gráfica de Windows.

El sistema debe:

1.  Mantener un perfil de información aportada y confirmada por el
    usuario.
2.  Indexar documentos que el usuario tenga autorización para utilizar.
3.  Detectar e interpretar preguntas de formularios.
4.  Recuperar información pertinente desde el perfil, documentos y
    memoria histórica.
5.  Proponer respuestas fundamentadas y mostrar las fuentes utilizadas.
6.  Permitir que el usuario revise, edite y apruebe cada respuesta.
7.  Introducir la respuesta aprobada en formularios de prueba o
    plataformas cuyo uso automatizado esté permitido.
8.  Registrar preguntas, decisiones, correcciones, acciones y consumo de
    API.
9.  Evitar inventar experiencias, atributos o datos personales.
10. Detenerse ante preguntas sensibles, ambiguas, contradictorias o sin
    respaldo suficiente.

El sistema no debe utilizarse para hacerse pasar por otra persona,
fabricar experiencias personales, eludir controles de elegibilidad,
manipular encuestas remuneradas ni incumplir los términos de las
plataformas. Debe respetar los límites de automatización de cada sitio.
La aprobación humana no convierte en permitido un uso que la plataforma
prohíba.

## 1.1 Alcance por versión

### MVP (primera versión)

-   Aplicación local.
-   Perfil de usuario editable.
-   Carga e indexación de documentos.
-   Chat para probar preguntas y respuestas sin navegador.
-   Integración con un modelo de IA mediante API.
-   Recuperación RAG con citas a fuentes internas.
-   Registro de tokens y costo estimado.
-   Navegador Playwright en un entorno de pruebas.
-   Detección de campos y preguntas HTML en formularios propios/de
    prueba.
-   Vista previa y aprobación humana antes de rellenar.
-   Registro de auditoría y botón para detener la sesión.

### Versión 2

-   Adaptador de escritorio para aplicaciones permitidas.
-   Capturas de pantalla y OCR/visión solo cuando DOM no sea suficiente.
-   Memoria histórica con aprobación explícita.
-   Perfiles separados y exportación/importación.
-   Mejoras de evaluación de respuestas y presupuesto.

### Fuera del alcance inicial

-   Autonomía irrestricta sobre todo Windows.
-   Envío automático de formularios o encuestas sin aprobación.
-   Resolución de CAPTCHA o evasión de controles anti-bot.
-   Suplantación, creación de identidades ficticias o respuestas
    inventadas.
-   Entrenamiento de un modelo fundacional propio.
-   Automatización de sitios que prohíban bots o interacción
    automatizada.

------------------------------------------------------------------------

# 2. Decisiones tecnológicas

Las versiones concretas de paquetes se fijarán al iniciar el repositorio
y se congelarán en archivos de dependencias. No se deben copiar
versiones supuestas de este documento sin comprobar compatibilidad.

  -----------------------------------------------------------------------
  Capa                    Tecnología propuesta    Responsabilidad
  ----------------------- ----------------------- -----------------------
  Backend                 Python 3.12+ y FastAPI  API, reglas de negocio
                                                  y orquestación

  Validación              Pydantic                Validar entradas y
                                                  salidas estructuradas

  ORM                     SQLAlchemy 2            Acceso a PostgreSQL

  Migraciones             Alembic                 Evolución del esquema

  Base de datos           PostgreSQL              Datos transaccionales

  Búsqueda vectorial      pgvector                Recuperación semántica

  Automatización web      Playwright              Navegador y DOM

  Escritorio              PyAutoGUI, opcional     Mouse/teclado en casos
                                                  autorizados

  OCR/visión              Adaptador desacoplado   Casos donde no exista
                                                  DOM accesible

  IA                      OpenAI API              Análisis y generación
                                                  de respuestas

  Embeddings              Modelo de embeddings    Indexación y búsqueda
                          configurable            semántica

  Frontend                Angular + TypeScript    Dashboard local

  UI                      Angular Material o      Componentes accesibles
                          componentes propios     

  Contenedores            Docker Compose          PostgreSQL y servicios
                                                  auxiliares

  Pruebas backend         pytest                  Pruebas unitarias e
                                                  integración

  Pruebas frontend        Angular testing +       UI y flujos
                          Playwright Test         

  Calidad                 Ruff, mypy opcional,    Estilo y errores
                          ESLint                  

  Observabilidad          logging estructurado    Diagnóstico y auditoría
  -----------------------------------------------------------------------

## 2.1 Política de modelos

No codificar nombres de modelos ni precios en la lógica de negocio. La
disponibilidad y las tarifas de API cambian. Consultar la página oficial
de precios antes de configurar producción:

-   https://openai.com/api/pricing/
-   https://platform.openai.com/docs/pricing
-   https://platform.openai.com/docs/guides/embeddings

Crear un `ModelRouter` configurable por variables de entorno.
Inicialmente basta con un único modelo económico y capaz, y un modelo de
mayor capacidad opcional para casos complejos. No es obligatorio
utilizar dos modelos desde el MVP.

El router debe registrar para cada llamada: - proveedor y modelo; -
tokens de entrada y salida reportados por la API; - tokens de entrada en
caché, si se informan; - duración; - operación funcional; - costo
calculado usando una tabla de precios versionada; - estado y errores.

Si la API no informa el uso, marcar el costo como estimado y no como
exacto.

## 2.2 Principio de automatización

Orden de preferencia:

1.  DOM y selectores semánticos con Playwright.
2.  Accesibilidad/roles y etiquetas del formulario.
3.  OCR o visión como respaldo limitado.
4.  Control de mouse/teclado solo para una interfaz autorizada que no
    pueda operarse por DOM.

No tomar capturas en cada pregunta. No enviar la pantalla completa al
modelo de IA por defecto. No almacenar capturas que contengan datos
personales salvo necesidad justificada y consentimiento.

------------------------------------------------------------------------

# 3. Arquitectura lógica

``` text
┌─────────────────────────────────────────────────────────────┐
│                    Angular Dashboard                        │
│ Inicio | Perfil | Documentos | Sesiones | Memoria | Costos  │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / WebSocket opcional
┌──────────────────────────────▼──────────────────────────────┐
│                       FastAPI Backend                       │
│                                                             │
│ API / Auth local / Validación / Auditoría / Configuración   │
│                                                             │
│ ┌────────────────┐ ┌────────────────┐ ┌───────────────────┐ │
│ │ Agent          │ │ Question       │ │ Answer            │ │
│ │ Orchestrator   │ │ Analyzer       │ │ Generator         │ │
│ └───────┬────────┘ └────────────────┘ └─────────┬─────────┘ │
│         │                                       │           │
│ ┌───────▼────────┐ ┌────────────────┐ ┌─────────▼─────────┐ │
│ │ Memory/RAG     │ │ Document       │ │ Validation        │ │
│ │ Manager        │ │ Processor      │ │ & Approval        │ │
│ └───────┬────────┘ └────────────────┘ └───────────────────┘ │
│         │                                                   │
│ ┌───────▼────────┐ ┌────────────────┐ ┌───────────────────┐ │
│ │ Model Router   │ │ Browser        │ │ Desktop Adapter   │ │
│ │ + Token Meter  │ │ Playwright     │ │ (fase posterior)  │ │
│ └───────┬────────┘ └────────────────┘ └───────────────────┘ │
└─────────┼───────────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────────┐
│ PostgreSQL + pgvector | Archivos locales | Logs             │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
      OpenAI API
```

## 3.1 Flujo de una pregunta

1.  El navegador de pruebas detecta el formulario y obtiene pregunta,
    etiquetas, opciones y tipo de control.
2.  `QuestionAnalyzer` normaliza la pregunta y clasifica su tipo.
3.  `MemoryManager` busca hechos confirmados y fragmentos documentales
    pertinentes.
4.  `AnswerGenerator` recibe la pregunta, el contexto mínimo necesario y
    las reglas de respuesta.
5.  `ValidationEngine` revisa soporte, contradicciones, sensibilidad y
    formato.
6.  El sistema presenta respuesta propuesta, nivel de confianza, fuentes
    y motivo.
7.  El usuario aprueba, edita o rechaza.
8.  Solo después de aprobación, el adaptador puede introducir el texto
    en el formulario de pruebas permitido.
9.  El sistema registra el resultado y solicita permiso antes de
    convertir una corrección en memoria reutilizable.
10. El usuario realiza cualquier envío final en la plataforma, salvo que
    el caso de uso y las reglas del sitio permitan expresamente otra
    cosa.

## 3.2 Contrato de respuesta interno

Todas las salidas del generador deben ajustarse a un esquema Pydantic
equivalente a:

``` json
{
  "suggested_answer": "Texto propuesto",
  "support_status": "supported",
  "confidence": 0.92,
  "sources": [
    {
      "source_type": "profile_fact",
      "source_id": "UUID",
      "excerpt": "Fragmento mínimo que respalda la propuesta"
    }
  ],
  "needs_user_input": false,
  "needs_review": true,
  "review_reason": "Confirmar que el dato sigue vigente",
  "answer_format": "text"
}
```

Valores recomendados para `support_status`: - `supported`: respaldado
por datos confirmados; - `partially_supported`: respaldo incompleto; -
`unsupported`: no existe evidencia suficiente; - `contradictory`: las
fuentes se contradicen; - `sensitive`: requiere revisión y autorización
explícita.

Nunca convertir `unsupported` o `contradictory` en una respuesta
inventada. En esos casos, pedir información o abstenerse.

------------------------------------------------------------------------

# 4. Diseño de módulos backend

## 4.1 `core`

Contendrá configuración y componentes transversales.

Crear: - `config.py`: configuración Pydantic Settings. - `database.py`:
sesión y conexión SQLAlchemy. - `logging.py`: logging estructurado. -
`security.py`: cifrado y gestión segura de secretos. - `exceptions.py`:
excepciones de dominio. - `dependencies.py`: dependencias FastAPI.

Responsabilidades: - leer secretos desde `.env` local no versionado; -
validar variables obligatorias; - no imprimir claves ni datos personales
en logs; - permitir apagar la integración externa desde configuración.

## 4.2 `profiles`

Gestionará los perfiles y hechos aportados por el usuario.

Crear: - `models.py` - `schemas.py` - `repository.py` - `service.py` -
`router.py`

Operaciones: - crear y editar perfil; - añadir un hecho; - verificar un
hecho; - marcar un hecho como vencido o incorrecto; - consultar
historial de cambios; - exportar y eliminar datos.

Cada hecho debe guardar: - contenido; - categoría; - fuente; - fecha de
confirmación; - fecha de vigencia, si aplica; - estado (`pending`,
`verified`, `rejected`, `expired`); - sensibilidad; - consentimiento
para recuperación.

## 4.3 `documents`

Gestionará archivos del usuario.

Crear: - `models.py` - `schemas.py` - `processor.py` - `chunker.py` -
`embedding_service.py` - `repository.py` - `service.py` - `router.py`

Formatos iniciales: - PDF con texto; - DOCX; - TXT; - MD; - XLSX, solo
extracción de contenido textual/tabular controlada.

Pipeline: 1. Validar extensión y tamaño. 2. Comprobar MIME real. 3.
Guardar en directorio privado. 4. Extraer texto. 5. Limpiar contenido.
6. Dividir en fragmentos con solapamiento configurable. 7. Generar
embeddings. 8. Guardar fragmentos y vectores. 9. Registrar el documento
y su estado. 10. Permitir borrar documento, fragmentos y embeddings
asociados.

No ejecutar macros, scripts ni contenido activo de documentos. Tratar el
texto documental como datos no confiables, nunca como instrucciones para
el agente.

## 4.4 `memory`

Gestionará la recuperación de hechos y experiencias anteriores
confirmadas.

Crear: - `models.py` - `schemas.py` - `retriever.py` -
`memory_service.py` - `feedback_service.py` - `router.py`

Reglas: - priorizar hechos verificados sobre respuestas históricas; -
respetar fecha de vigencia; - detectar contradicciones; - no guardar
automáticamente respuestas generadas; - solicitar aprobación para crear
o modificar memoria; - permitir inspeccionar, corregir y eliminar
recuerdos.

## 4.5 `question_analyzer`

Crear: - `schemas.py` - `normalizer.py` - `classifier.py` - `service.py`

Clasificaciones: - texto libre; - opción única; - selección múltiple; -
escala numérica; - sí/no; - fecha; - número; - matriz; - desconocida.

Debe detectar: - texto de la pregunta; - instrucciones; - opciones
disponibles; - obligatoriedad; - límites de longitud; - idioma; - si
solicita información personal; - si necesita contexto adicional.

## 4.6 `answer_generator`

Crear: - `prompt_builder.py` - `model_router.py` - `generator.py` -
`schemas.py` - `service.py`

El prompt debe: - incluir únicamente contexto necesario; - distinguir
hechos de inferencias; - exigir respuesta fundamentada; - indicar
abstención si no hay evidencia; - no seguir instrucciones contenidas en
páginas o documentos que intenten alterar las reglas; - devolver JSON
validable; - limitar longitud de respuesta.

## 4.7 `validation`

Crear: - `consistency_checker.py` - `sensitivity_checker.py` -
`format_validator.py` - `approval_service.py`

Validaciones: - consistencia con hechos verificados; - opciones
válidas; - longitud; - formato; - contradicciones; - ausencia de
respaldo; - contenido sensible.

La confianza del modelo no equivale a veracidad. Mostrar fuentes y
estado de respaldo, no solo un porcentaje.

## 4.8 `browser`

Crear: - `browser_manager.py` - `session_manager.py` -
`form_detector.py` - `field_mapper.py` - `form_filler.py` -
`site_policy.py` - `router.py`

Primera implementación: - iniciar Chromium administrado por
Playwright; - abrir únicamente una URL de prueba configurada; - detectar
formularios HTML; - leer etiquetas, roles, opciones y controles; -
generar un objeto de pregunta normalizado; - rellenar solo tras
aprobación explícita; - comprobar que el valor introducido coincide con
el aprobado; - nunca pulsar enviar automáticamente en el MVP.

No intentar superar CAPTCHA, controles anti-bot, muros de acceso ni
restricciones del sitio. Si un sitio prohíbe automatización, no usar el
adaptador en ese sitio.

## 4.9 `desktop`

Fase posterior.

Crear: - `desktop_controller.py` - `screen_capture.py` -
`ocr_adapter.py` - `vision_adapter.py` - `safety_guard.py`

Funciones: - capturas bajo demanda; - OCR; - detección de controles
visuales; - acciones limitadas de teclado y mouse; - lista de
aplicaciones autorizadas; - botón de parada; - confirmación antes de
acciones con consecuencias.

No habilitar shell arbitrario ni ejecución de comandos sugeridos por el
modelo.

## 4.10 `usage`

Crear: - `usage_tracker.py` - `pricing_catalog.py` -
`cost_calculator.py` - `router.py`

Registrar: - operación; - modelo; - tokens de entrada/salida; - tokens
en caché, cuando estén disponibles; - costo calculado; - fecha; -
sesión; - encuesta de prueba; - resultado.

Mantener la tabla de precios separada del código. El dashboard debe
mostrar costos como estimados cuando el dato de uso o la tarifa no sean
exactos.

------------------------------------------------------------------------

# 5. Modelo de datos inicial

Crear migraciones Alembic para las siguientes entidades.

  -----------------------------------------------------------------------
  Tabla                               Campos principales
  ----------------------------------- -----------------------------------
  `profiles`                          id, name, created_at, updated_at

  `profile_facts`                     id, profile_id, category, fact,
                                      source, status, sensitivity,
                                      valid_until

  `documents`                         id, profile_id, filename,
                                      mime_type, storage_path, status,
                                      created_at

  `document_chunks`                   id, document_id, chunk_index,
                                      content, embedding, metadata

  `survey_sessions`                   id, profile_id, environment, site,
                                      status, started_at, ended_at

  `questions`                         id, session_id, question_text,
                                      question_type, options, metadata

  `answer_proposals`                  id, question_id, answer_text,
                                      support_status, confidence, status

  `answer_sources`                    id, proposal_id, source_type,
                                      source_id, excerpt

  `memory_entries`                    id, profile_id, content, embedding,
                                      source_type, source_id, status

  `user_feedback`                     id, proposal_id, feedback_type,
                                      correction, approved_for_memory

  `model_usage`                       id, session_id, operation,
                                      provider, model, input_tokens,
                                      output_tokens, cost

  `audit_events`                      id, session_id, event_type,
                                      details, created_at

  `site_policies`                     id, domain, automation_allowed,
                                      notes, enabled
  -----------------------------------------------------------------------

Usar UUID como identificador. Añadir índices por `profile_id`,
`session_id`, `status`, fechas y vectores. Definir claves foráneas y
borrado en cascada donde corresponda.

No guardar cookies de sesión ni contraseñas en las tablas de memoria.
Las sesiones del navegador deben estar aisladas y protegidas.

------------------------------------------------------------------------

# 6. API backend propuesta

Prefijo: `/api/v1`

## Salud y configuración

-   `GET /health`
-   `GET /settings`
-   `GET /models`

## Perfil

-   `GET /profiles`
-   `POST /profiles`
-   `GET /profiles/{profile_id}`
-   `PATCH /profiles/{profile_id}`
-   `POST /profiles/{profile_id}/facts`
-   `PATCH /facts/{fact_id}`
-   `DELETE /facts/{fact_id}`

## Documentos

-   `POST /documents`
-   `GET /documents`
-   `GET /documents/{document_id}`
-   `POST /documents/{document_id}/reindex`
-   `DELETE /documents/{document_id}`

## Memoria

-   `GET /memory`
-   `POST /memory`
-   `PATCH /memory/{memory_id}`
-   `DELETE /memory/{memory_id}`
-   `POST /memory/search`

## Preguntas y respuestas

-   `POST /questions/analyze`
-   `POST /answers/propose`
-   `POST /answers/{proposal_id}/approve`
-   `POST /answers/{proposal_id}/reject`
-   `POST /answers/{proposal_id}/correct`

## Navegador

-   `POST /browser/sessions`
-   `GET /browser/sessions/{session_id}`
-   `POST /browser/sessions/{session_id}/navigate`
-   `POST /browser/sessions/{session_id}/inspect`
-   `POST /browser/sessions/{session_id}/fill-approved`
-   `POST /browser/sessions/{session_id}/stop`

## Uso y auditoría

-   `GET /usage/summary`
-   `GET /usage/by-day`
-   `GET /usage/by-model`
-   `GET /audit/events`

No exponer endpoints de ejecución arbitraria de código, shell o
JavaScript proporcionado por el usuario.

------------------------------------------------------------------------

# 7. Frontend Angular

Estructura sugerida:

``` text
frontend/src/app/
├── core/
│   ├── services/
│   ├── interceptors/
│   ├── guards/
│   └── models/
├── shared/
│   ├── components/
│   ├── pipes/
│   └── utils/
└── features/
    ├── dashboard/
    ├── profiles/
    ├── documents/
    ├── memory/
    ├── assistant/
    ├── browser/
    ├── usage/
    └── settings/
```

## Pantallas

### Dashboard

-   estado de backend y base de datos;
-   estado del navegador;
-   preguntas procesadas;
-   propuestas pendientes;
-   tokens y costo estimado;
-   actividad reciente.

### Perfil

-   datos agrupados por categorías;
-   estado de verificación;
-   fecha de actualización;
-   edición, eliminación y exportación.

### Documentos

-   carga;
-   progreso de indexación;
-   estado;
-   búsqueda;
-   eliminación.

### Asistente

-   pregunta detectada;
-   tipo de respuesta;
-   respuesta propuesta;
-   fuentes;
-   advertencias;
-   aprobar, editar o rechazar.

### Memoria

-   búsqueda;
-   hechos y respuestas aprobadas;
-   procedencia;
-   correcciones;
-   eliminación.

### Navegador

-   sesión activa;
-   URL y dominio;
-   pregunta detectada;
-   controles identificados;
-   estado de aprobación;
-   detener sesión.

### Consumo

-   tokens por día;
-   tokens por modelo;
-   costo por operación;
-   costo por sesión;
-   presupuesto mensual configurable.

------------------------------------------------------------------------

# 8. Plan de implementación por fases

Las estimaciones son orientativas para una persona desarrollando con
apoyo de Codex. Cada fase debe terminar con pruebas y un entregable
funcional.

## Fase 0 --- Preparación del entorno

**Duración estimada:** 0.5--1 día.

### Objetivos

-   preparar repositorio;
-   configurar herramientas;
-   fijar convenciones;
-   documentar decisiones.

### Tareas

1.  Crear repositorio `ai-survey-assistant`.
2.  Crear carpetas `backend`, `frontend`, `docs` y `docker`.
3.  Crear `.gitignore`.
4.  Crear `.env.example`.
5.  Configurar Python y entorno virtual.
6.  Inicializar Angular.
7.  Crear Docker Compose para PostgreSQL con pgvector.
8.  Crear `README.md`.
9.  Crear `docs/ARCHITECTURE.md`.
10. Crear `docs/DECISIONS.md`.

### Entregable

Repositorio inicial que arranca frontend, backend y base de datos.

### Criterios de aceptación

-   `docker compose up -d` levanta PostgreSQL.
-   FastAPI responde en `/health`.
-   Angular muestra una pantalla inicial.
-   Ningún secreto está versionado.

## Fase 1 --- Backend y persistencia

**Duración estimada:** 1.5--2 días.

### Tareas

1.  Configurar FastAPI.
2.  Configurar Pydantic Settings.
3.  Configurar SQLAlchemy.
4.  Configurar Alembic.
5.  Configurar conexión PostgreSQL.
6.  Crear modelos iniciales.
7.  Crear primera migración.
8.  Implementar repositorios.
9.  Crear endpoints de salud y perfil.
10. Agregar pruebas de integración.

### Archivos principales

-   `backend/app/main.py`
-   `backend/app/core/config.py`
-   `backend/app/core/database.py`
-   `backend/app/profiles/models.py`
-   `backend/app/profiles/schemas.py`
-   `backend/app/profiles/repository.py`
-   `backend/app/profiles/service.py`
-   `backend/app/profiles/router.py`
-   `backend/alembic/`

### Entregable

API que permite crear un perfil y guardar hechos.

### Criterios de aceptación

-   migraciones ejecutan y revierten;
-   CRUD de perfil funciona;
-   hechos pueden verificarse;
-   pruebas pasan.

## Fase 2 --- Perfil y documentos

**Duración estimada:** 2--3 días.

### Tareas

1.  Crear almacenamiento privado de documentos.
2.  Implementar validación de extensiones y MIME.
3.  Implementar extracción de PDF, DOCX, TXT y MD.
4.  Añadir extracción controlada de XLSX.
5.  Implementar división en fragmentos.
6.  Configurar embeddings.
7.  Guardar vectores en pgvector.
8.  Implementar búsqueda semántica.
9.  Crear endpoints de carga, estado y borrado.
10. Probar recuperación con documentos de ejemplo.

### Entregable

El usuario carga documentos y puede recuperar fragmentos relevantes.

### Criterios de aceptación

-   archivo inválido es rechazado;
-   el documento se indexa;
-   los resultados muestran documento y fragmento de origen;
-   al borrar el documento se borran sus fragmentos y vectores.

## Fase 3 --- Integración de IA y generación fundamentada

**Duración estimada:** 2 días.

### Tareas

1.  Configurar cliente oficial de OpenAI.
2.  Crear `ModelRouter`.
3.  Crear prompts versionados.
4.  Implementar `QuestionAnalyzer`.
5.  Implementar `MemoryManager`.
6.  Implementar `AnswerGenerator`.
7.  Validar salida estructurada con Pydantic.
8.  Implementar abstención por falta de evidencia.
9.  Implementar detección de contradicciones.
10. Registrar uso de tokens y costo.
11. Añadir pruebas con preguntas conocidas y desconocidas.

### Entregable

El usuario introduce una pregunta y obtiene una propuesta con fuentes.

### Criterios de aceptación

-   respuestas respaldadas citan fuentes internas;
-   preguntas desconocidas no provocan invención;
-   contradicciones se reportan;
-   uso de API se registra;
-   errores de proveedor se manejan sin perder la sesión.

## Fase 4 --- Memoria y aprendizaje controlado

**Duración estimada:** 1.5--2 días.

### Tareas

1.  Crear historial de propuestas.
2.  Crear flujo aprobar/rechazar/corregir.
3.  Crear opción "guardar como hecho verificado".
4.  Crear procedencia de cada memoria.
5.  Añadir expiración o revisión de hechos temporales.
6.  Añadir detección de posibles duplicados.
7.  Añadir búsqueda y edición de memoria.
8.  Añadir exportación y borrado.

### Entregable

El sistema conserva únicamente conocimiento confirmado y trazable.

### Criterios de aceptación

-   una propuesta no se convierte en memoria sin aprobación;
-   cada hecho tiene fuente y estado;
-   correcciones pueden revertirse o editarse;
-   se puede eliminar un hecho.

## Fase 5 --- Automatización web controlada

**Duración estimada:** 2--3 días.

### Tareas

1.  Configurar Playwright.
2.  Crear gestor de sesiones.
3.  Configurar un sitio local de prueba con formularios.
4.  Detectar preguntas y controles HTML.
5.  Normalizar opciones y etiquetas.
6.  Enviar pregunta al analizador.
7.  Recuperar propuesta del generador.
8.  Mostrar aprobación en dashboard.
9.  Rellenar el campo aprobado.
10. Verificar el valor introducido.
11. Implementar detener sesión.
12. Registrar cada acción.

### Entregable

El agente puede inspeccionar un formulario propio de prueba y rellenar
un campo únicamente después de aprobación.

### Criterios de aceptación

-   solo navega a dominios autorizados;
-   no envía el formulario;
-   no hace clic en botones de envío;
-   no intenta resolver CAPTCHA;
-   detiene la sesión ante un dominio no autorizado;
-   el valor escrito coincide con el aprobado.

## Fase 6 --- Dashboard Angular

**Duración estimada:** 2--3 días.

### Tareas

1.  Crear layout principal.
2.  Crear navegación lateral.
3.  Crear dashboard.
4.  Crear módulo de perfil.
5.  Crear módulo de documentos.
6.  Crear módulo de memoria.
7.  Crear vista del asistente.
8.  Crear control de navegador.
9.  Crear estadísticas de consumo.
10. Conectar servicios HTTP.
11. Implementar estados de carga y errores.
12. Añadir confirmaciones para operaciones destructivas.

### Entregable

Interfaz desde la que se administra y supervisa el agente.

### Criterios de aceptación

-   todas las pantallas consumen la API real;
-   no se utilizan datos ficticios en producción;
-   errores de backend son visibles;
-   acciones de aprobar, corregir y detener funcionan.

## Fase 7 --- Seguridad, evaluación y estabilización

**Duración estimada:** 2 días.

### Tareas

1.  Revisar almacenamiento de secretos.
2.  Proteger el dashboard local con autenticación.
3.  Añadir protección CSRF/CORS según despliegue.
4.  Limitar tamaño y tipo de archivos.
5.  Limitar dominios y navegación.
6.  Revisar logs para evitar datos sensibles.
7.  Añadir límites de tokens y presupuesto.
8.  Probar interrupción de red.
9.  Probar errores de API.
10. Probar documentos malformados.
11. Probar inyección de instrucciones en documentos y páginas.
12. Probar borrado y exportación de datos.
13. Documentar recuperación y copias de seguridad.

### Entregable

MVP estable, limitado y documentado.

### Criterios de aceptación

-   no hay secretos en repositorio;
-   el usuario puede detener el agente;
-   las preguntas sin respaldo se abstienen;
-   los costos tienen trazabilidad;
-   las pruebas críticas pasan.

## Fase 8 --- Adaptador de escritorio visual

**Duración estimada:** 3--5 días, posterior al MVP.

### Tareas

1.  Definir aplicaciones autorizadas.
2.  Implementar capturas bajo demanda.
3.  Integrar OCR.
4.  Añadir adaptador de visión.
5.  Implementar acciones de teclado y mouse limitadas.
6.  Mostrar previsualización de la acción.
7.  Exigir aprobación antes de interactuar.
8.  Implementar parada global.
9.  Registrar capturas y acciones según política de privacidad.
10. Probar en una aplicación local de laboratorio.

### Entregable

Adaptador visual complementario para interfaces permitidas que
Playwright no pueda manejar.

------------------------------------------------------------------------

# 9. Estimación general

  Fase                           Tiempo
  ----------------------- -------------
  0\. Preparación            0.5--1 día
  1\. Backend               1.5--2 días
  2\. Documentos              2--3 días
  3\. IA                         2 días
  4\. Memoria               1.5--2 días
  5\. Playwright              2--3 días
  6\. Angular                 2--3 días
  7\. Estabilización             2 días
  8\. Escritorio visual       3--5 días

**MVP estimado:** 12--19 días laborables, dependiendo de la experiencia,
los ajustes y los problemas de integración.\
**Con control visual de escritorio:** añadir aproximadamente 3--5 días.

------------------------------------------------------------------------

# 10. Presupuesto y medición de tokens

No asumir tarifas ni nombres de modelos permanentes. Consultar los
precios vigentes de API y configurar un catálogo editable.

## 10.1 Escenario inicial para dimensionar

Suposición de planificación: - 10 encuestas al día; - 25 preguntas por
encuesta; - 30 días al mes; - 7.500 preguntas mensuales.

El consumo real dependerá de la cantidad de contexto recuperado, las
instrucciones, las respuestas y las consultas adicionales.

Para dimensionar, medir durante una semana: - tokens de entrada por
pregunta; - tokens de salida por pregunta; - llamadas por pregunta; -
costo por encuesta; - costo por día; - porcentaje de preguntas resueltas
sin pedir más contexto.

No utilizar la duración de 15--20 minutos como unidad de consumo. Medir
por llamada real a la API.

## 10.2 Presupuesto de seguridad

Configurar: - límite máximo por llamada; - límite diario; - límite
mensual; - aviso al alcanzar 70%; - bloqueo configurable al alcanzar
100%; - límite de contexto recuperado; - máximo de reintentos; - máximo
de llamadas por pregunta.

Crear una pantalla de consumo con costo real reportado o estimado
claramente identificado.

------------------------------------------------------------------------

# 11. Variables de entorno

Crear `backend/.env.example`:

``` dotenv
APP_NAME=AI Survey Assistant
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
APP_SECRET_KEY=replace_me

DATABASE_URL=postgresql+psycopg://survey:survey_dev_password@localhost:5432/survey_assistant

OPENAI_API_KEY=
OPENAI_DEFAULT_MODEL=
OPENAI_ADVANCED_MODEL=
OPENAI_EMBEDDING_MODEL=

DOCUMENT_STORAGE_PATH=./storage/documents
MAX_UPLOAD_MB=20

BROWSER_HEADLESS=false
BROWSER_ALLOWED_DOMAINS=localhost,127.0.0.1
BROWSER_SESSION_TIMEOUT_MINUTES=30

MAX_INPUT_TOKENS_PER_CALL=8000
MAX_OUTPUT_TOKENS_PER_CALL=1000
DAILY_BUDGET_USD=2
MONTHLY_BUDGET_USD=30

LOG_LEVEL=INFO
```

Estos valores son parámetros iniciales de desarrollo, no tarifas ni
límites universales. El archivo `.env` real debe estar ignorado por Git.

------------------------------------------------------------------------

# 12. Docker Compose inicial

Crear un `docker-compose.yml` en la raíz. El contenedor PostgreSQL debe
utilizar una imagen compatible con pgvector y un volumen persistente.

Servicios iniciales: - `db`: PostgreSQL con pgvector; - opcionalmente
`backend`: FastAPI; - `frontend`: Angular se ejecuta inicialmente con el
servidor de desarrollo fuera de Docker.

En desarrollo, se recomienda ejecutar FastAPI y Angular localmente para
facilitar depuración. Docker se utiliza inicialmente para la base de
datos. Más adelante se containeriza el conjunto.

No publicar PostgreSQL en interfaces de red externas. En desarrollo,
enlazarlo a `127.0.0.1`.

------------------------------------------------------------------------

# 13. Estrategia de pruebas

## 13.1 Pruebas unitarias

-   clasificación de preguntas;
-   validación de esquemas;
-   cálculo de costos;
-   segmentación de documentos;
-   reglas de abstención;
-   detección de contradicciones.

## 13.2 Pruebas de integración

-   API y PostgreSQL;
-   carga e indexación;
-   recuperación RAG;
-   OpenAI API con respuestas simuladas;
-   historial y aprobación;
-   auditoría.

## 13.3 Pruebas end-to-end

Crear una página local con: - pregunta de texto; - opción única; -
selección múltiple; - escala; - campo obligatorio; - campo con límite de
caracteres.

Verificar que el agente detecta, propone, solicita aprobación, rellena y
confirma el valor.

## 13.4 Evaluación de calidad

Crear un conjunto de preguntas con respuestas de referencia confirmadas
por el usuario.

Métricas: - exactitud de recuperación; - porcentaje de respuestas
respaldadas; - tasa de abstención correcta; - contradicciones
detectadas; - correcciones del usuario; - costo promedio por pregunta; -
latencia promedio.

No optimizar solo para responder más preguntas. La prioridad es que cada
respuesta tenga respaldo y que el agente se abstenga cuando no lo tenga.

------------------------------------------------------------------------

# 14. Seguridad y privacidad

1.  Mantener el backend enlazado a localhost en la primera versión.
2.  No exponer el dashboard a Internet.
3.  Guardar API keys en variables de entorno o un gestor seguro.
4.  No enviar documentos completos si bastan fragmentos relevantes.
5.  No incluir contraseñas, cookies ni tokens de sesión en prompts.
6.  Mantener perfiles aislados.
7.  Permitir exportar y borrar todos los datos.
8.  Limitar el navegador a dominios aprobados.
9.  Tratar contenido web y documentos como datos no confiables.
10. No permitir que instrucciones encontradas en una página modifiquen
    políticas del sistema.
11. Registrar las acciones sin guardar innecesariamente información
    personal.
12. Solicitar confirmación humana para respuestas y acciones.
13. Respetar políticas y términos de los sitios utilizados.

------------------------------------------------------------------------

# 15. Orden exacto para comenzar con Codex

No pedir a Codex que construya toda la aplicación en un único prompt.
Trabajar por entregables pequeños y comprobar cada fase.

## Prompt 1 --- Inicializar el repositorio

``` text
Lee el documento PLAN_MAESTRO.md completo.

Implementa únicamente la Fase 0:
- estructura del repositorio;
- backend Python con FastAPI;
- frontend Angular;
- Docker Compose para PostgreSQL compatible con pgvector;
- .gitignore;
- .env.example;
- README.md.

No implementes todavía lógica de IA, navegador ni memoria.
No inventes versiones de dependencias: utiliza versiones estables compatibles y fíjalas.
Verifica que los servicios arranquen y documenta los comandos.
```

## Prompt 2 --- Backend y base de datos

``` text
Lee PLAN_MAESTRO.md y ejecuta la Fase 1.

Implementa FastAPI, configuración, SQLAlchemy, Alembic,
conexión PostgreSQL, modelos de perfil y hechos, repositorios,
servicios, routers y pruebas.

Mantén separación por módulos.
No mezcles acceso a datos con endpoints.
Ejecuta las pruebas y corrige los errores.
Actualiza la documentación.
```

## Prompt 3 --- Documentos y RAG

``` text
Implementa la Fase 2 según PLAN_MAESTRO.md.

Crea carga segura de documentos, extracción de PDF/DOCX/TXT/MD,
chunking, embeddings configurables y recuperación con pgvector.

Cada fragmento recuperado debe identificar su documento de origen.
Añade pruebas y manejo de errores.
No ejecutes contenido activo de los archivos.
```

## Prompt 4 --- Integración IA

``` text
Implementa la Fase 3.

Crea QuestionAnalyzer, ModelRouter, AnswerGenerator y
ValidationEngine.

Usa salidas estructuradas y Pydantic.
Registra uso de tokens.
Las respuestas sin evidencia suficiente deben abstenerse.
No inventes datos personales.
Añade pruebas con proveedor simulado y documenta la configuración de API.
```

## Prompt 5 --- Memoria y aprobación

``` text
Implementa la Fase 4.

Crea historial, correcciones, aprobación y memoria reutilizable.
Ninguna respuesta generada se guardará automáticamente como hecho.
Solo se guarda como conocimiento confirmado tras aprobación explícita.
Incluye procedencia, estado, edición y eliminación.
```

## Prompt 6 --- Playwright

``` text
Implementa la Fase 5.

Usa una página HTML local de pruebas.
Detecta preguntas, etiquetas, opciones y controles.
Conecta el flujo de análisis y propuesta.
Exige aprobación antes de rellenar.
No pulses botones de envío.
Limita navegación a localhost y dominios explícitamente autorizados.
Implementa parada inmediata y auditoría.
```

## Prompt 7 --- Angular

``` text
Implementa la Fase 6 con Angular.

Crea dashboard, perfil, documentos, memoria, asistente,
navegador y estadísticas de consumo.
Conecta todos los servicios con FastAPI.
Utiliza componentes reutilizables y estados de carga/error.
No uses datos mock en las pantallas conectadas al backend.
```

## Prompt 8 --- Estabilización

``` text
Ejecuta la Fase 7.

Revisa seguridad, privacidad, logs, límites de consumo,
dominios permitidos, borrado de datos y recuperación ante errores.
Ejecuta pruebas unitarias, integración y end-to-end.
Entrega un informe de defectos, correcciones y pendientes.
No habilites automatización autónoma ni envío de formularios.
```

------------------------------------------------------------------------

# 16. Definición de terminado del MVP

El MVP se considera listo cuando:

-   [ ] El proyecto arranca localmente en Windows.
-   [ ] PostgreSQL y pgvector funcionan.
-   [ ] Se puede crear y editar un perfil.
-   [ ] Se pueden cargar y eliminar documentos.
-   [ ] Los documentos se indexan y recuperan con procedencia.
-   [ ] La IA analiza una pregunta.
-   [ ] La propuesta incluye fuentes y estado de respaldo.
-   [ ] La IA se abstiene cuando no tiene información.
-   [ ] El usuario puede corregir y aprobar propuestas.
-   [ ] Solo las memorias aprobadas se reutilizan.
-   [ ] Playwright reconoce formularios locales de prueba.
-   [ ] El navegador rellena un campo después de aprobación.
-   [ ] El navegador no envía el formulario.
-   [ ] El usuario puede detener la sesión.
-   [ ] El consumo de tokens queda registrado.
-   [ ] Los costos se calculan con tarifas configurables.
-   [ ] Las pruebas críticas pasan.
-   [ ] La documentación permite instalar y ejecutar el proyecto desde
    cero.

------------------------------------------------------------------------

# 17. Documentación oficial de referencia

Consultar siempre la documentación vigente antes de implementar:

-   FastAPI: https://fastapi.tiangolo.com/
-   Python: https://docs.python.org/3/
-   Angular: https://angular.dev/
-   Playwright Python: https://playwright.dev/python/
-   SQLAlchemy: https://docs.sqlalchemy.org/
-   Alembic: https://alembic.sqlalchemy.org/
-   PostgreSQL: https://www.postgresql.org/docs/
-   pgvector: https://github.com/pgvector/pgvector
-   OpenAI API: https://platform.openai.com/docs/
-   OpenAI API pricing: https://openai.com/api/pricing/
-   OpenAI embeddings:
    https://platform.openai.com/docs/guides/embeddings
-   Docker Compose: https://docs.docker.com/compose/

------------------------------------------------------------------------

# 18. Recomendación de ejecución

Comenzar por la Fase 0 y no avanzar hasta que el entorno arranque
correctamente.

Después, implementar y probar una fase a la vez. Mantener
`PLAN_MAESTRO.md` como documento rector y actualizarlo cuando se tomen
decisiones técnicas nuevas.

La primera demostración funcional no necesita un sitio externo: debe
utilizar un formulario HTML local, un perfil de prueba y documentos de
ejemplo. Una vez validado el flujo completo, se podrá evaluar cada
integración adicional de forma controlada.

**Principio rector del proyecto:** el agente recupera información,
propone respuestas fundamentadas y facilita la interacción; el usuario
conserva el control de las respuestas y de las acciones finales.

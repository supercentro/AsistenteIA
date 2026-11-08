> Detalla en esta sección los prompts principales utilizados durante la creación del proyecto, que justifiquen el uso de asistentes de código en todas las fases del ciclo de vida del desarrollo. Esperamos un máximo de 3 por sección, principalmente los de creación inicial o  los de corrección o adición de funcionalidades que consideres más relevantes.
Puedes añadir adicionalmente la conversación completa como link o archivo adjunto si así lo consideras


## Índice

1. [Descripción general del producto](#1-descripción-general-del-producto)
2. [Arquitectura del sistema](#2-arquitectura-del-sistema)
3. [Modelo de datos](#3-modelo-de-datos)
4. [Especificación de la API](#4-especificación-de-la-api)
5. [Historias de usuario](#5-historias-de-usuario)
6. [Tickets de trabajo](#6-tickets-de-trabajo)
7. [Pull requests](#7-pull-requests)

---

## 1. Descripción general del producto

**Prompt 1:**

```
En los archivos adjuntados esta la información sobre el Proyecto Final (readme.md, prompts.md y las
lecciones del máster). Ya realicé el fork y clonado en local del repo del proyecto final. Estos son
repos de ejemplo para referencia (2 completos con todos los entregables, 2 con solo la entrega 1).
La idea es darte contexto de la necesidad, no codifiques nada, quiero que me vayas consultando para
saber si entendiste correctamente y a partir de ahí vamos iterando para cumplimentar el trabajo.

Mi idea de proyecto: un agente de IA generativa diseñado para acompañar a estudiantes y tutores
durante el recorrido académico, generar interacciones de valor y ampliar las oportunidades de
aprendizaje (RAG). Debe estar disponible para varias asignaturas, permitiendo que los estudiantes
aprendan a su propio ritmo, consulten contenidos y resuelvan dudas relacionadas con sus cursos.
Cada asistente es alimentado por los docentes con la bibliografía y los contenidos de la asignatura.
Además contemplo un asistente de servicio al estudiante (matrícula, toma de ramos, titulación,
consultas académicas) y un módulo de monitoreo del aprendizaje para docentes, con integración a un
LMS tipo Moodle.
```

**Prompt 2:**

```
Quiero acotar el alcance del MVP: el foco principal va a ser el asistente académico RAG por
asignatura. La integración con Moodle queda fuera del MVP (los docentes suben material manualmente
vía la propia app). El módulo de monitoreo/analítica para docentes queda como should-have, no
obligatorio. Además quiero agregar protección de datos (GDPR) como parte del alcance.

Datos para la ficha del proyecto:
- Nombre completo: Alejandro Nicolaide
- Nombre del proyecto: AsistenteIA (descartamos "GuIA" por coincidir con un producto real existente)
- Descripción breve: un chatbot RAG diseñado para acompañar a estudiantes y tutores durante el
  recorrido académico, para generar interacciones de valor y ampliar las oportunidades de aprendizaje.
- URL del proyecto: pendiente de despliegue
- Repositorio: https://github.com/AlejandroNicolaide/AI4Devs-finalproject

Con esto, redacta el objetivo (1.1) usando un caso de uso de una institución educativa ficticia, y las
características y funcionalidades principales (1.2), incluyendo la eliminación de historial de
conversaciones como funcionalidad GDPR y dejando la analítica docente marcada como should-have.
```

---

## 2. Arquitectura del Sistema

### **2.1. Diagrama de arquitectura:**

**Prompt 1:**

```
Propón un patrón de arquitectura para el backend (FastAPI + React + Postgres/pgvector + LangChain +
Gemini). Sugiere si conviene una arquitectura por capas con Repository Pattern, cómo se comunican
frontend y backend, y justifica ventajas y déficits de la propuesta antes de escribir nada en el
README.
```

**Prompt 2:**

```
Antes de aceptar la arquitectura propuesta, revisá qué arquitectura usa realmente el repo de
referencia AI4Devs-finalproject-Example2 (README real del repo, no solo el resumen que tengo). Quiero
saber si coincide con lo que me proponés, para tomar una decisión informada y no copiar por
casualidad.
```

**Prompt 3:**

```
Confirmado el patrón (Layered Architecture + Repository Pattern + Service Layer, RAG con LangChain).
Generá el diagrama de arquitectura en formato mermaid (flowchart) mostrando frontend, capas del
backend, PostgreSQL+pgvector, y los servicios externos (Gemini, HuggingFace embeddings), y escribilo
en la sección 2.1 del readme.md junto con la justificación del patrón y sus déficits.
```

### **2.2. Descripción de componentes principales:**

**Prompt 1:**

```
A partir del diagrama de arquitectura ya definido, describe los componentes principales del sistema
(frontend, API layer, service layer -RAGService, SubjectService, ConversationService-, repository
layer, PostgreSQL+pgvector, Gemini, HuggingFace embeddings), indicando la tecnología y responsabilidad
de cada uno, para la sección 2.2 del readme.md.
```

### **2.3. Descripción de alto nivel del proyecto y estructura de ficheros**

**Prompt 1:**

```
Proponeme una estructura de carpetas para backend (FastAPI) y frontend (React+TS) que refleje las
capas ya definidas (api/services/repositories/models/schemas en backend; pages/components/hooks/
services en frontend). Explicá brevemente el propósito de cada carpeta principal y si obedece a algún
patrón específico.
```

### **2.4. Infraestructura y despliegue**

**Prompt 1:**

```
El proyecto todavía no está desplegado (estamos en la Entrega 1, solo documentación). Sugerime una
combinación de infraestructura simple y gestionada (sin Kubernetes/Terraform) para desplegar backend,
frontend y base de datos con pgvector, apta para un MVP académico, y documentala en la sección 2.4
como plan de despliegue (no como despliegue ya realizado), incluyendo un diagrama.
```

### **2.5. Seguridad**

**Prompt 1:**

```
Documenta las prácticas de seguridad del proyecto en la sección 2.5, incluyendo específicamente
protección de datos conforme a GDPR: minimización de datos, consentimiento explícito, derecho al
olvido (relacionado con la funcionalidad de borrado de historial ya definida en 1.2), cifrado en
tránsito y en reposo, retención de datos, gestión de secretos y validación de entrada.
```

### **2.6. Tests**

**Prompt 1:**

```
Como todavía no existe código (Entrega 1 es solo documentación), describe en la sección 2.6 la
estrategia de testing planificada para las próximas entregas: tests unitarios y de integración en
backend (Pytest), tests de componentes en frontend (Vitest + React Testing Library), y un test E2E
del flujo principal (Playwright) para la entrega final.
```

---

### 3. Modelo de Datos

**Prompt 1:**

```
A partir de las funcionalidades ya definidas (gestión de asignaturas y material por parte del
docente, consulta RAG por parte del estudiante, historial de conversación, borrado de historial por
GDPR), proponeme las entidades principales del modelo de datos (usuarios, asignaturas, documentos con
embeddings, conversaciones, mensajes), con sus relaciones.
```

**Prompt 2:**

```
Generá el diagrama del modelo de datos en formato mermaid (erDiagram) con el máximo detalle posible
(claves primarias, foráneas, tipos de dato, restricciones), y la descripción textual de cada entidad
(atributos, tipo, PK/FK, relaciones, restricciones unique/not null), para las secciones 3.1 y 3.2 del
readme.md. Tené en cuenta que la columna embedding debe soportar pgvector.
```

---

### 4. Especificación de la API

**Prompt 1:**

```
Definí los 3 endpoints principales de la API (máximo 3, según la plantilla) que cubran el flujo core
del producto: subida de material por parte del docente, consulta al asistente (chat RAG) por parte
del estudiante, y borrado de historial de conversación (GDPR).
```

**Prompt 2:**

```
Documenta esos 3 endpoints en formato OpenAPI (paths, requestBody, responses con sus schemas) para la
sección 4 del readme.md, agregando un ejemplo de petición y de respuesta en JSON para el endpoint de
chat.
```

---

### 5. Historias de Usuario

**Prompt 1:**

```
Documenta 3 historias de usuario principales del proyecto (una por cada endpoint/funcionalidad core ya
definida: carga de material, consulta RAG, borrado de historial GDPR), usando formato Gherkin (Dado/
Cuando/Entonces) para los criterios de aceptación, e indicando la priorización (MoSCoW) de cada una,
para la sección 5 del readme.md.
```

---

### 6. Tickets de Trabajo

**Prompt 1:**

```
Documenta 3 tickets de trabajo (uno de backend, uno de frontend, uno de base de datos) alineados con
la Historia de Usuario 2 (consulta al asistente RAG), con todo el detalle necesario para desarrollar
la tarea de inicio a fin: descripción, tareas técnicas, criterios de aceptación, estimación y
dependencias entre tickets, para la sección 6 del readme.md.
```

---

### 7. Pull Requests

**Prompt 1:**

```
Esta es la Entrega 1 (solo documentación, sin código). No corresponde documentar Pull Requests
todavía. Dejá la sección 7 del readme.md con una nota indicando que se completará a partir de la
Entrega 2, en lugar de inventar PRs ficticias.
```

---

## 8. Configuración de contexto técnico y SDD (Specboot + OpenSpec)

**Herramienta y modelo:** Claude Code (CLI), modelo Sonnet 5.5. Fase: preparación del contexto técnico del proyecto antes de la implementación (sin código de aplicación). Los prompts de las secciones 1–7 corresponden a la Entrega 1; esta sección se agregó después de ella.

**Contexto estructurado para la IA:** se adaptó Specboot (`docs/`, `ai-specs/`, punteros `CLAUDE.md`/`AGENTS.md`/`codex.md`/`GEMINI.md` hacia `docs/base-standards.md`) y se completó `openspec/config.yaml` con el contexto del producto y reglas por artefacto. No se usaron subagentes.

**Prompt 1 (resumido, no textual):**

```
Actuá como arquitecto de software senior (IA, RAG, seguridad, SDD). Adaptá la configuración de Specboot
a AsistenteIA sin generar código de aplicación. Leé los documentos del Máster, readme.md, prompts.md,
docs/, ai-specs/, AGENTS.md, CLAUDE.md y openspec/config.yaml. Trabajá en dos fases: (A) diagnóstico
sin modificar archivos, con inventario, decisiones confirmadas, inconsistencias por criticidad,
preguntas bloqueantes y plan exacto; detenete y pedí aprobación; (B) aplicá solo lo aprobado y
registrá lo relevante en prompts.md sin inventar interacciones.
```

**Resultado de la Fase A (hallazgos principales que cambiaron las decisiones):**
- Faltaba la entidad de inscripción (HU-2 exige estudiante inscrito).
- La entidad `Document` mezclaba archivo original, fragmento y embedding, y la cita admitía una sola fuente.
- Prompt injection, aislamiento por asignatura y GDPR (consentimiento, borrado total) no estaban cubiertos.
- Los `docs/` de Specboot eran de otro proyecto (Node/Prisma/Cypress/Bootstrap).
- En Windows los symlinks de Specboot quedaron como archivos de texto.

**Prompt 2 (decisión humana):**

```
aprobado con default
```

**Ajustes humanos y decisiones:**
- Se aprobó el plan con las opciones por defecto propuestas por la IA (idioma inglés en `docs/` y código, español en `readme.md`/`prompts.md`; Python 3.12, uv, ruff, mypy strict, Alembic, argon2, hnsw; Docker Compose como camino principal de ejecución).
- Tras la Fase B el usuario pidió actualizar `readme.md` (respuesta literal: "actualiza readme"). La IA alineó las secciones 2.2, 2.3, 2.5, 2.6, 3, 4, 5 (HU-1 y HU-2) y 6 (tickets 1, 2 y 3) con `docs/data-model.md` y `docs/api-spec.yml`, que siguen siendo la fuente canónica.
- El usuario aclaró que esta configuración es una prueba adicional posterior a la entrega ya realizada, por lo que no se consideran las fechas de entrega ni se crean ramas ni commits.

### 8.1 Integración de OpenSpec con Specboot

**Prompt 3 (resumido, no textual):**

```
Actuá como especialista senior en OpenSpec/Specboot/SDD. Integrá OpenSpec con los estándares y agentes de
Specboot para AsistenteIA con una única fuente de verdad por tipo de información. Verificá la versión
instalada de OpenSpec y su esquema de configuración (no asumas que los ejemplos de Specboot son compatibles),
usá solo claves soportadas, revisá CLAUDE.md y AGENTS.md sin duplicar ni contradecir, no crees symlinks sin
verificar en Windows, identificá los comandos reales instalados, validá todo y proponé el comando para
comenzar la primera funcionalidad. Sin código de aplicación.
```

**Ajustes detectados por la IA al verificar contra OpenSpec 1.15.0:**
- La clave `rules: _global`, copiada del ejemplo de Specboot (y usada por la IA en la configuración anterior), no es válida: las claves de `rules` deben ser IDs de artefacto (`proposal`, `specs`, `design`, `tasks`). Se corrigió.
- `docs/openspec-tasks-mandatory-steps.md` mencionaba comandos inexistentes (`/opsx:ff`, `/opsx:continue`); se reemplazaron por los instalados (`/opsx:propose`, `/opsx:update`).
- El flujo de trabajo de 8 pasos se documentó una sola vez en `docs/base-standards.md` §7.1 y `openspec/config.yaml` solo lo referencia.
- Durante la ejecución la IA detectó que permitir `role=teacher` en el registro público era una escalada de privilegios y lo corrigió: los docentes se crean por seed/CLI.
- Limitación detectada: no se pueden crear symlinks sin permisos de administrador, por lo que se usaron archivos puntero y copias en `.claude/` (documentado en `docs/base-standards.md` §6).

## 9. Migración a un repositorio de producto independiente (AsistenteIA)

**Herramienta y modelo:** Claude Code (CLI), modelo Sonnet 5.5. Fase: separar el trabajo de implementación del repositorio académico (`AI4Devs-finalproject`) hacia un repositorio de producto propio, sin código de aplicación. Esta sección se agregó con aprobación explícita del usuario; los prompts están resumidos, no son textuales.

**Prompt 1 (resumido, no textual):**

```
Aprobado el diagnóstico. El repositorio académico debe quedar exactamente como está (sin restore, clean,
reset, commits, push ni cambios en remotos). Preparar primero un plan para copiar el estado actual a una
carpeta hermana AsistenteIA: documentación, OpenSpec, Specboot, agentes, skills y prompts.md completo; sin
.git, repositorios anidados, logs de Playwright, dependencias ni secretos. Crear
docs/academic-requirements.md con un resumen fiel de los requisitos de LIDR. Aplicar las correcciones de
precedencia documental solo en la copia, distinguir Playwright MCP de Playwright Test (manteniendo
Playwright CLI como alternativa), establecer ramas feature/<change-name> con PR hacia main. Esperar mi
aprobación antes de copiar o inicializar Git.
```

**Prompt 2 (decisión humana, resumida):**

```
Apruebo el plan: no copiar lidr-specboot/; copiar readme.md y prompts.md completos con los cambios sin
commitear; main como rama inicial; el repositorio académico intacto; destino local AsistenteIA. Ya creé un
repositorio privado vacío en GitHub (supercentro/AsistenteIA). Ejecutá las fases A-D, inicializá Git solo en
AsistenteIA, configurá origin, y pedime aprobación antes de commit o push.
```

**Ajustes humanos y decisiones:**
- El usuario decidió no copiar `lidr-specboot/` (repositorio Git anidado) porque los componentes necesarios ya estaban instalados en `ai-specs/` y `.claude/`.
- La IA verificó la copia con hashes SHA-256 (84 archivos, 0 diferencias) y confirmó que el repositorio original conservó el mismo `HEAD` y el mismo `git status`.
- Correcciones aplicadas solo en la copia: jerarquía de precedencia documental (documentos originales del Máster > `docs/academic-requirements.md` > `docs/` técnico > `readme.md` §3-4); Playwright MCP (verificación interactiva del agente) separado de Playwright Test (suite E2E versionada) con Playwright CLI como alternativa; flujo `feature/<change-name>` → PR a `main`; `.gitignore` ampliado; URL de clonación de la guía de desarrollo actualizada.
- Divergencia a revisar por el usuario: `readme.md` y las secciones 1-8 de este archivo conservan la URL del repositorio académico (`AlejandroNicolaide/AI4Devs-finalproject`) porque son entregables históricos; no se modificaron.

## 10. Autenticación y roles (`auth-and-roles`, cambio OpenSpec 2 de 13)

**Herramienta y modelo:** Claude Code (CLI), modelo Sonnet 5.5, siguiendo el flujo OpenSpec del repositorio (`/opsx:propose` → validación estricta → `/opsx:apply` con TDD → revisión adversarial → PR → `/opsx:archive`). El contexto lo daban `CLAUDE.md` → `docs/base-standards.md` y `openspec/config.yaml`. Esta sección se agregó con aprobación explícita del usuario. Fase: implementación del backend de autenticación (usuarios, JWT, roles, consentimiento, CLI de administración); el frontend solo recibió una constante.

**Skills y subagentes usados:**
- Skill `adversarial-review`, ejecutada por la propia IA en la misma sesión que implementó (no es una revisión independiente).
- **Un subagente** de Claude Code (tipo `general-purpose`, lanzado con el parámetro `model=opus`), con contexto limpio y de solo lectura, como segunda revisión adversarial independiente.
- Skill `update-docs`: solo se aplicó su checklist a mano durante la implementación; **se invocó el skill propiamente dicho una sola vez**, al final, a petición del usuario.

**Formato de esta sección:** los bloques marcados *(fragmento textual)* son frases literales de los mensajes del usuario en la sesión; los marcados *(resumido, no textual)* son resúmenes. No se reconstruyó ninguna conversación ni se incluye la sesión completa.

### 10.1 Prompts y decisiones del usuario

**Prompt 1 — decisiones de diseño previas a la implementación (fragmentos textuales):**

```
El seed inicial contiene únicamente docente y estudiante, sin asignaturas. Debe ser explícito,
idempotente y no crear credenciales predeterminadas inseguras en producción.

El backend valida `consent_version` contra la versión vigente de la política de privacidad configurada
en el sistema. No se aceptan versiones arbitrarias.

Algoritmo HS256.
Claims sub, iat, exp, iss y aud.
Releer el rol desde PostgreSQL en cada petición autenticada.
```

**Prompt 2 — resumido, no textual:** el usuario aprobó los artefactos OpenSpec (proposal, tres specs, diseño D1–D14, tareas) y pidió empezar `/opsx:apply` exclusivamente para `auth-and-roles`, con TDD, pruebas unitarias e integración, lint, tipos, auditorías y una revisión adversarial obligatoria sobre autenticación, roles, secretos, consentimiento y rate limiting, sin commits, push ni PR sin su aprobación.

**Prompt 3 — tras la primera revisión (fragmentos textuales):**

```
Incorporar rate limiting en POST /auth/register:
  - Límite inicial: 5 solicitudes/minuto por IP.
Incluir tests que comprueben el bloqueo y que la solicitud rechazada no ejecute Argon2id ni persista usuarios.

Realizar una segunda revisión adversarial en una sesión independiente de Claude Code o con otro revisor,
centrada en autenticación, autorización, rate limiting, CLI, JWT y consentimiento.
```

**Prompt 4 — tras la revisión independiente (fragmentos textuales):**

```
Restringir emails a caracteres ASCII.
Verificar si el skill de SpecBoot ya se ejecutó. Si no existe evidencia, ejecutarlo.
Autorizo el squash merge del PR #2.
```

**Prompt de la IA al subagente revisor (resumido, no textual):** se le entregó el alcance del PR #2, las rutas de los artefactos OpenSpec y las áreas de foco (autenticación, JWT, autorización, rate limiting, CLI, consentimiento, secretos y logs, migración y contratos), con reglas estrictas de solo lectura (sin editar archivos, sin git que cambie estado, sin tocar la base de desarrollo) y un formato de informe con ataques probados, hallazgos con severidad y evidencia, y veredicto.

### 10.2 Decisiones técnicas principales
- Argon2id (10–128 caracteres, verificación contra un hash falso cuando el email no existe), JWT HS256 con validación estricta de firma, algoritmo, emisor, audiencia exacta, `sub` canónico y expiración; el rol se relee de PostgreSQL en cada petición y nunca se emite ni se confía en un claim de rol.
- `JWT_SECRET` obligatorio en todos los entornos (≥ 32 bytes, sin marcadores de posición ni baja variedad).
- Rate limiting en memoria con la librería `limits` (login 10/min, registro 5/min por dirección de conexión), elegida frente a `slowapi` por tipado y menor acoplamiento; documentadas sus limitaciones.
- Consentimiento validado contra `PRIVACY_POLICY_VERSION`, con constante equivalente en el frontend y pruebas de consistencia; la exigencia del consentimiento vigente en `/chat` queda para el cambio 9.
- CLI `create-teacher` y `seed` fuera de la API (la contraseña nunca como argumento; seed solo en desarrollo/test y sin credenciales por defecto).

### 10.3 Correcciones y ajustes humanos / de la IA
- **Primera revisión (la propia IA):** un `name` con NUL u otro carácter de control producía un 500; el JWT aceptaba `aud` como lista, `sub` no canónico y booleanos como `iat`; el registro no tenía límite de tasa. Se corrigió todo con pruebas de regresión. Una validación defensiva de codificación agregada por la IA resultó código muerto (una mutación lo demostró) y se eliminó.
- **Segunda revisión (subagente independiente), veredicto PASS WITH GAPS:** F1 (mayor) un error SQL volcaba parámetros —email y hash Argon2id— al log del servidor; F2 (mayor) rotar `X-Forwarded-For` saltaba ambos limitadores porque Uvicorn confía por defecto en el loopback; F3 caracteres bidireccionales y separadores de línea en nombres; F4 el CLI no validaba `--name`; F5 argparse repetía el valor de `--password` en el error; F6 `maxLength` del login ausente del contrato; F7 una caída de la base devolvía 500 en lugar de 503; F8 (pregunta) emails Unicode sin normalizar. F1–F7 se corrigieron con pruebas, incluidas pruebas contra un Uvicorn real (`--no-proxy-headers`); **F8 lo resolvió el usuario**: emails solo ASCII y en minúsculas, validados en registro, login y CLI, más un check en la base de datos.
- **Errores de proceso reconocidos por la IA:** los guards de rol se escribieron junto con `get_current_user` antes de sus tests (se validaron luego por mutación); la primera revisión no detectó F1 ni F2 porque los tests usaban un cliente de prueba que no pasa por Uvicorn; el test de ventana del rate limit usa un `sleep` real porque `limits` no admite reloj inyectable; la variante interactiva de `create-teacher` solo se prueba con un prompt inyectado.

### 10.4 Resultados de validación
- Pruebas: 344 en el backend (unitarias e integración sobre PostgreSQL 15 + pgvector, incluidas pruebas con proceso real de Uvicorn y del CLI), cobertura 97 %; 3 de Vitest y 2 de Playwright en el frontend; `ruff`, `mypy --strict`, ESLint, Prettier y `tsc` limpios; `pip-audit` y `npm audit` sin vulnerabilidades; `openspec validate --strict` válido.
- Entrega: PR #2 con CI en verde (backend y frontend), squash merge `2e87864` y archivado OpenSpec `3ca9b6b` publicado en `main`.

### 10.5 Riesgos residuales (documentados en `docs/development_guide.md` y el PR)
- El rate limit en memoria se pierde al reiniciar, no se comparte entre procesos y no cubre rotación de IPv6 ni NAT compartido; detrás de un proxy todos los clientes comparten un límite hasta configurar proxies confiables.
- Los tokens no se revocan antes de expirar (60 minutos por defecto).
- El registro revela emails existentes (409, según el contrato aprobado); las contraseñas no se normalizan en Unicode.
- `APP_ENV` toma `development` por defecto y `/docs` está abierto en todos los entornos (pendiente para el cambio 13, despliegue).
- Las bases locales que aplicaron una versión previa de la migración `0002` requieren `downgrade -1` y `upgrade head`.

> Nota: el uso de IA del cambio 1 (`project-scaffold`) está en la sección 11.

## 11. Andamiaje del proyecto (`project-scaffold`, cambio OpenSpec 1 de 13)

**Herramienta y modelo:** Claude Code (CLI), modelo Sonnet 5.5, con el flujo OpenSpec del repositorio (`openspec new change`, `openspec instructions`, validación `--strict`, `/opsx:apply`, `openspec archive`). Fase: crear la base ejecutable del producto (backend, frontend, base de datos, Docker Compose, CI) antes de las funcionalidades. Esta sección se agregó con aprobación explícita del usuario y se redactó solo con evidencia verificable: los mensajes del usuario en la sesión, los informes archivados en `openspec/changes/archive/2026-10-27-project-scaffold/reports/`, el historial de Git (`e0e115a`, `d63efd5`) y el PR #1. Los bloques *(fragmento textual)* son frases literales del usuario; los *(resumido, no textual)* son resúmenes. No se usaron subagentes ni se invocó el skill `adversarial-review` en este cambio (la configuración solo lo exige para autenticación, autorización, subida, chat y datos personales); `update-docs` solo se aplicó como checklist manual.

### 11.1 Análisis del README y plan de implementación

**Prompt 1 (fragmentos textuales):**

```
Analizá íntegramente el archivo `readme.md` de este repositorio.
No modificar el alcance ni agregar funcionalidades sin mi autorización.
No implementar código todavía.
Presentar primero un plan de implementación para mi aprobación.
```

La IA leyó `readme.md`, `docs/`, `ai-specs/` y `openspec/config.yaml` y devolvió una tabla de 13 cambios en 5 etapas con dependencias, más contradicciones y vacíos detectados (por ejemplo: la HU-3 usa 403 donde el contrato dice 404; el Ticket 3 declaraba "sin dependencias" pese a depender de `subjects`; la fecha de la Entrega 2 ya había pasado).

**Prompt 2 — decisión humana (fragmentos textuales):**

```
Los recursos pertenecientes a otros usuarios deben responder 404 para evitar revelar su existencia.
El acceso al chat de una asignatura sin inscripción debe responder 403.
Utilizar SQLAlchemy síncrono para el MVP.
Mantener JWT en memoria en el frontend, sin utilizar localStorage.
Utilizar proveedores fake de LLM y embeddings para las pruebas automatizadas.
Ahora quiero comenzar exclusivamente con el primer cambio: `project-scaffold`.
```

### 11.2 Artefactos OpenSpec y ajustes del usuario

La IA creó proposal, cuatro specs (`service-health`, `api-error-handling`, `dev-environment`, `continuous-integration`), diseño (D1–D10) y 15 grupos de tareas, y los presentó antes de implementar.

**Prompt 3 — ajustes obligatorios antes de implementar (fragmentos textuales):**

```
`TEST_DATABASE_URL` debe ser obligatoria únicamente al ejecutar tests de integración, no para iniciar
el backend normalmente.
Garantizar que la base de datos de pruebas esté aislada de desarrollo y producción.
```

Del primer ajuste surgieron `APP_ENV`, la regla de CORS en producción y el guard de aislamiento de la base de pruebas (diseño D11).

### 11.3 Revisión y cierre

**Prompt 4 (fragmentos textuales):**

```
Realizá una revisión completa del diff contra `main`, incluyendo seguridad, dependencias,
configuración, migraciones y archivos no versionados.
Registrá en el informe final la desviación del proceso TDD detectada en `/health`, sin modificar
código innecesariamente.
Incorporar un timeout de conexión PostgreSQL de 5 segundos, configurable si corresponde, con su
prueba automatizada.
```

### 11.4 Correcciones y hallazgos de la IA durante la implementación
- La plantilla de Vite traía React 19, TypeScript 7 y oxlint; se fijaron React 18, TypeScript 5.9 y ESLint/typescript-eslint según los estándares. ESLint quedó en la versión 9 porque la 10 choca con `eslint-plugin-jsx-a11y`.
- El puerto 5432 estaba ocupado por contenedores de otros proyectos locales: la base se publica en `127.0.0.1:5442`. Usar `localhost` colgaba las conexiones desde el host por resolverse primero a IPv6: se usa `127.0.0.1`.
- MSW 3 renombró `onUnhandledRequest` a `onUnhandledFrame`; `fileConfig` de Alembic deshabilitaba los loggers existentes y rompía un test de logs al correr toda la suite.
- La revisión del diff detectó un archivo sobrante de la plantilla (`.oxlintrc.json`), un `.gitattributes` con alcance excesivo y puertos de Docker publicados en todas las interfaces (pasaron a `127.0.0.1`).
- El timeout de conexión se agregó porque `/health` podía colgarse con una base que no responde; se probó con un servidor TCP que acepta y no contesta.
- **Desviación TDD reconocida:** el endpoint `/health` se escribió antes de sus tests de integración (el resto fue test primero); quedó registrada en el informe final archivado.

### 11.5 Resultados verificables
- 62 tests de backend (unitarios e integración sobre PostgreSQL 15 + pgvector), cobertura 98 %; 2 de Vitest y 2 de Playwright; `ruff`, `mypy --strict`, ESLint, Prettier y `tsc` limpios; `pip-audit` y `npm audit` sin vulnerabilidades; arranque limpio con `docker compose up --build`.
- PR #1 con CI en verde, squash merge `e0e115a`; archivado OpenSpec `d63efd5` con 4 specs principales (20 requisitos).

### 11.6 Riesgos residuales
- El guard de aislamiento es una convención de nombres y entorno, no una barrera de privilegios, y no frena un `alembic downgrade` manual contra la base de desarrollo.
- El timeout acota solo el establecimiento de la conexión, no la duración de las consultas.
- ESLint 9 está en desuso; las dependencias del backend usan rangos `>=` fijados por `uv.lock`.

## 12. Asignaturas e inscripciones (`subjects-and-enrollments`, cambio OpenSpec 3 de 13)

**Herramienta y modelo:** Claude Code (CLI), modelo Sonnet 5.5, con el flujo OpenSpec del repositorio (`/opsx:explore`, `/opsx:propose`, `/opsx:update`, `/opsx:apply`, `/opsx:archive`). El contexto lo daban `CLAUDE.md` → `docs/base-standards.md`, `docs/lessons-learned.md` y `docs/technical-debt.md`. Esta sección se agregó con aprobación explícita del usuario.

**Skills y subagentes usados:**
- Skills de OpenSpec `opsx:propose`, `opsx:update`, `opsx:apply` y `opsx:archive`.
- Skill `update-docs`, invocado explícitamente durante la implementación.
- **Dos subagentes** de Claude Code (tipo `general-purpose`, lanzados con `model=opus`), con contexto limpio y de solo lectura, como revisiones adversariales independientes: la primera sobre todo el cambio y la segunda, focalizada en la corrección de F6 y del contrato OpenAPI. Probaron únicamente contra la base de pruebas aislada `asistenteia_test`.

**Formato de esta sección:** los bloques marcados *(fragmento textual)* son frases literales de mensajes del usuario en la sesión; los marcados *(resumido, no textual)* son resúmenes. No se reconstruyó ninguna conversación. Las notas de trabajo están en `openspec/changes/archive/2026-10-28-subjects-and-enrollments/reports/2026-10-28-ai-usage-notes.md`.

### 12.1 Prompts y decisiones del usuario

**Prompt 1 — aprobación del plan, decisiones D1–D12 (fragmentos textuales):**

```
D1: devolver 404 para asignaturas de otros docentes; 403 para roles incorrectos.
D8: mantener listados sin paginacion durante el MVP y registrar TD-016 como deuda tecnica.
```

**Prompt 2 — condiciones sobre los artefactos (fragmentos textuales):**

```
Mantener nombres de asignaturas sensibles a mayusculas, segun el modelo aprobado.
Aceptar como riesgo residual del MVP que la inscripcion por email permite distinguir estudiantes registrados.
```

**Prompt 3 — resumido, no textual:** el usuario aprobó los ajustes B1–B10 derivados de `docs/lessons-learned.md` (evidencia TDD, revisión independiente, pruebas con entradas extremas y protección de logs, trazabilidad entre especificaciones y contrato), y que la corrección de la ruta de los informes de OpenSpec se publicara en un PR aparte antes de implementar.

**Prompt 4 — autorización de implementación (fragmento textual, más resumen):**

```
Apruebo iniciar la implementacion de `subjects-and-enrollments` mediante el workflow oficial de OpenSpec y los estandares del proyecto.
```

*(Resumido, no textual:)* pidió TDD con evidencia de las pruebas fallidas, pruebas negativas y de concurrencia, protección de datos sensibles en errores y logs, revisión independiente, actualización del PR #5, y detenerse antes de pedir el merge.

**Prompt 5 — revisión final del PR #5 (fragmento textual, más resumen):**

```
Apruebo realizar una última corrección antes del merge.
```

*(Resumido, no textual:)* resolver F6 pasando `teacher_id` al repositorio con una restricción de titularidad en el SQL, mantener TD-018 abierto sin tocar el validador compartido, investigar la ausencia de `maxLength` del email en el OpenAPI generado y repetir una revisión independiente focalizada.

**Prompt 6 — cierre (fragmentos textuales):**

```
Autorizo el cierre de la feature 3.
Autorizo finalizar la publicación del archivado y preparar la actualización de prompts.md.
```

**Prompt de la IA a los subagentes revisores (resumido, no textual):** alcance del diff, fuentes a leer, áreas a atacar (aislamiento entre docentes y estudiantes, 404 idénticos, entradas extremas, concurrencia, migración, fugas en logs), prohibición de editar el repositorio y de tocar la base de desarrollo, y formato del informe con severidades y veredicto.

### 12.2 Decisiones técnicas principales
- Repositorios con alcance por actor: ninguna lectura ni borrado sin el usuario autenticado; el rol se comprueba antes que la titularidad (403 antes que 404) y una asignatura ajena responde el mismo 404 que una inexistente.
- Un email desconocido y el de una cuenta que no es estudiante devuelven el mismo 404 sin eco del email; no hay preinscripción.
- 409 para nombre de asignatura duplicado por docente (sensible a mayúsculas) y para inscripción duplicada; savepoints que convierten las violaciones únicas y de clave foránea en errores controlados.
- Migración `0003`: `ON DELETE CASCADE` en las inscripciones y `RESTRICT` para el docente con asignaturas.
- Validadores de nombre, descripción y email extraídos a `schemas/validators.py` sin cambiar el comportamiento de registro, login ni CLI.
- Listados sin paginación (TD-016); la inscripción por email revela qué emails son estudiantes (TD-017, riesgo aceptado).

### 12.3 Correcciones, desviaciones y hallazgos
- **Evidencia TDD:** se registró la ejecución fallida de cada grupo antes de implementar (`reports/2026-10-28-tdd-evidence.md`). No hubo desviaciones del orden. Hubo pruebas que pasaban antes de implementar porque esperaban un 404 (2 en las asignaturas y 7 en las inscripciones), y se compensaron con las pruebas de éxito y con comprobaciones por mutación.
- **Primera revisión independiente (PASS WITH GAPS, sin bloqueantes ni mayores):** F1 (menor) la carrera de borrado devolvía "Resource not found" en vez de "Student not found", corregido; F2 (menor) una descripción en blanco se guardaba como cadena vacía, ahora se recorta y pasa a null; F3 y F4 (menores) el validador compartido recorta espacios Unicode antes de comprobar ASCII y la lista bidi omite U+061C, registrados como TD-018 y sin tocar; F5 (menor) código muerto en un test, eliminado; F6 (pregunta) `EnrollmentRepository.add` no recibía el actor.
- **Corrección final de F6 (decisión del usuario):** `add(subject_id, teacher_id, student_id)` inserta con `INSERT ... SELECT` desde la asignatura del docente titular; el servicio conserva su comprobación. Tests escritos antes (13 fallos iniciales), una prueba de concurrencia con 12 hilos (1 creada, 6 respuestas 404, 5 conflictos) y una mutación detectada por 4 pruebas.
- **Contrato OpenAPI:** el `maxLength: 255` del email faltaba porque el límite vive en un validador. Se añadió a `json_schema_extra`, que solo afecta al esquema generado. Una prueba confirma que la validación no cambia.
- **Segunda revisión independiente (focalizada en F6 y el contrato):** PASS, sin hallazgos mayores ni bloqueantes; dos observaciones menores aceptadas y un test adicional de reutilización de sesión.
- **Incidentes de herramientas y de proceso (reconocidos por la IA):**
  - Las secuencias de escape Unicode y los saltos de línea escritos con barra invertida se colapsaron en heredocs y en la herramienta de escritura; se detectó escaneando caracteres no ASCII y se reconstruyó con puntos de código explícitos.
  - El contenedor de desarrollo ejecutó un `alembic downgrade -1` porque su imagen no incluía la migración `0003`; la base tenía 0 usuarios y no se perdieron datos. Quedó documentado en la guía de desarrollo y en la lección L15.
  - Una prueba de protección de logs pasaba en vacío por un marcador mal elegido; se corrigió y se comprobó que solo falla si se quitan a la vez `hide_parameters` y el middleware que oculta el traceback.
  - Se actualizaron dos pruebas existentes (seed y downgrade de `0002`) por la aparición de las nuevas tablas, manteniendo su intención.

### 12.4 Resultados de validación
- 488 pruebas de backend (344 antes del cambio), cobertura 98 % (servicios 100 %), `ruff`, `ruff format --check` y `mypy --strict` limpios, `alembic check` limpio, `pip-audit` y `npm audit` sin vulnerabilidades.
- 13 mutaciones sobre filtros por actor y comprobaciones de titularidad, todas detectadas.
- 40 casos con curl contra la pila real de Docker Compose y regresión del frontend (3 de Vitest, 2 de Playwright).
- `openspec validate --all --strict`: 9 de 9.
- Entrega: PR #5 con CI en verde, squash merge `9e50724` y archivado `2e25ddf` publicado en `main`.

### 12.5 Riesgos residuales
- TD-016: listados sin paginación.
- TD-017: la inscripción por email permite a un docente distinguir estudiantes registrados.
- TD-018: el validador compartido recorta espacios Unicode antes de comprobar ASCII y omite U+061C; pendiente de aprobación, porque afecta a registro y login.
- `alembic check` sigue siendo un paso manual, fuera de la CI.

## 13. Base del frontend (`frontend-foundation`, cambio OpenSpec 4 de 13)

**Herramienta y modelo:** Claude Code (CLI), modelo Sonnet 5.5, con el flujo OpenSpec del repositorio (`/opsx:explore`, `/opsx:propose`, `/opsx:apply`, `/opsx:archive`). El contexto lo daban `CLAUDE.md` → `docs/base-standards.md`, `docs/frontend-standards.md`, `docs/lessons-learned.md` y `docs/technical-debt.md`. Esta sección se agregó con aprobación explícita del usuario.

**Skills y subagentes usados:**
- Skills de OpenSpec `opsx:explore`, `opsx:propose`, `opsx:apply` y `opsx:archive`.
- Skill `update-docs`, invocado explícitamente durante la implementación.
- **Dos subagentes** de Claude Code (tipo `general-purpose`, `model=opus`), con contexto limpio y de solo lectura, como revisiones adversariales independientes: la primera sobre todo el cambio y la segunda, focalizada en la corrección de CORS (TD-021).
- Playwright MCP (navegador real) para la verificación interactiva contra el stack de Docker Compose.

**Formato de esta sección:** los bloques marcados *(fragmento textual)* son frases literales de mensajes del usuario; los marcados *(resumido, no textual)* son resúmenes. No se reconstruyó ninguna conversación. Las notas de trabajo están en `openspec/changes/archive/2026-10-28-frontend-foundation/reports/2026-10-28-ai-usage-notes.md`.

### 13.1 Prompts y decisiones del usuario

**Prompt 1 — análisis previo (resumido, no textual):** el usuario pidió un análisis de solo lectura de la feature 4 (alcance, dependencias, decisiones por aprobar, riesgos, arquitectura frontend). El alcance no estaba escrito en ningún artefacto del repositorio, así que la IA lo propuso y el usuario lo aprobó.

**Prompt 2 — aprobación de diseño, decisiones D1–D9 (fragmentos textuales):**

```
Documentar que este alcance se define mediante las decisiones actuales del proyecto y no mediante una especificación preexistente.
D2: sesión exclusivamente en memoria. Recargar la página requiere volver a iniciar sesión. Gestionar expiración automática del token.
D3: obtener usuario y rol mediante GET /users/me. El backend es la autoridad sobre permisos.
```

**Prompt 3 — ajustes a la planificación (fragmentos textuales):**

```
Registrar TD-019 diferenciando la pérdida de sesión al recargar del riesgo de exposición ante XSS.
Corregir los campos `required` únicamente cuando la evidencia confirme que son obligatorios.
```

**Prompt 4 — autorización de implementación (fragmento textual, más resumen):**

```
Realizar modificaciones temporales de JWT exclusivamente en un entorno aislado de pruebas.
```

*(Resumido, no textual:)* autorizó publicar la planificación en un PR sin merge e implementar con TDD, pruebas contra backend real (autenticación, CORS, `Authorization`, 401, expiración), revisión adversarial independiente y `update-docs`.

**Prompt 5 — aprobación con condición (fragmentos textuales):**

```
Apruebo la implementación de `frontend-foundation`, condicionada a resolver TD-021 antes del squash merge.
Autorizo finalizar la feature 4 mediante squash merge y archivado OpenSpec.
```

**Prompt de la IA a los subagentes revisores (resumido, no textual):** alcance del diff, fuentes a leer, áreas a atacar (exposición del token, ciclo de vida de la sesión, redirecciones abiertas, mensajes de error, entradas extremas, aislamiento de caché entre usuarios, CI, y para la segunda revisión la política CORS antes y después), prohibición de editar el repositorio y de tocar la base de desarrollo, y formato del informe con severidades y veredicto.

### 13.2 Decisiones técnicas principales
- Sesión solo en memoria (un único almacén en `lib/session.ts`), sin `localStorage`, `sessionStorage`, cookies ni URL; expira por temporizador y por comprobación del reloj antes de cada petición; un 401 en una petición protegida la cierra una sola vez.
- El rol sale de `GET /users/me` y el token nunca se decodifica; las guardas de ruta son una capa de usabilidad y el backend sigue siendo la autoridad.
- Cliente Axios con `ApiError`: el mensaje en español se elige por `code`, nunca se muestra ni registra el texto del servidor; React Query sin reintentos en 4xx y caché por usuario.
- Tipos generados desde `docs/api-spec.yml` con `openapi-typescript`, con verificación en CI; formularios con React Hook Form y Zod.
- Alcance: login, registro de estudiantes, rutas protegidas por rol, shell y listado de asignaturas de solo lectura; sin gestión de asignaturas, documentos, chat ni consentimiento.

### 13.3 Correcciones, desviaciones y hallazgos
- **Evidencia TDD:** fallo previo registrado por grupo. Desviaciones: una sola ejecución roja combinada para los grupos 5 a 7 y el E2E con mocks escrito después de la UI; compensadas con 20 mutaciones de guardas (19 detectadas, 1 equivalente).
- **Hallazgos al ejecutar contra el navegador real:** un desborde horizontal a 320 px con nombres largos (corregido) y que `Retry-After` no llegaba al navegador por la configuración CORS del backend (TD-021).
- **Contrato:** el OpenAPI real confirmó los campos `required` de `User` y `Subject.description`; solo se añadieron esos.
- **Revisión independiente 1 (PASS WITH GAPS, sin bloqueantes ni mayores):** un 401 tardío de una sesión anterior cerraba la sesión del usuario siguiente; el filtro de destino de retorno no resolvía mayúsculas, `..` ni codificación porcentual; el siguiente usuario volvía a la página del anterior tras cerrar sesión; `LoginRequest` estaba escrito a mano; faltaban pruebas de teclado y de otros casos. Todo corregido con tests primero.
- **TD-021 (decisión del usuario):** `expose_headers=["Retry-After"]` en el middleware CORS, con test previo que fallaba, comprobación con curl y en Chrome real ("Espere 47 segundos") y revisión focalizada (PASS WITH GAPS; los huecos eran de documentación y de un test que no fijaba métodos ni `max-age`).
- **Incidentes de herramientas y de proceso (reconocidos por la IA):** el intérprete de comandos colapsó barras invertidas y rechazó heredocs con apóstrofes (se usaron la herramienta de escritura y `String.fromCharCode`); el contenedor de frontend conservó el volumen anónimo de `node_modules` tras añadir dependencias (hace falta `docker compose up -d --build -V frontend`); un intento de ejecutar un comando de reversión innecesario fue bloqueado y no se ejecutó; el primer proceso aislado de Uvicorn sobrevivió a la orden de detención y hubo que cerrarlo por su puerto.

### 13.4 Resultados de validación
- 236 pruebas de frontend (cobertura de sentencias 95,9 %, umbral de 70 % en componentes y hooks comprobado), 11 E2E con mocks en CI, una spec condicionada contra el backend real con 6 casos (5 ejecutados contra el stack de Compose, incluido un 429 real que muestra los segundos; la expiración con `JWT_EXPIRE_MINUTES=1` se ejecutó antes en un entorno aislado y pasó), 20 de 20 casos con curl y verificación interactiva con Playwright MCP.
- Backend: 494 pruebas, cobertura 98 %, `ruff`, `mypy --strict` y `pip-audit` limpios. Frontend: lint, Prettier, `tsc`, `check:api-types`, build y `npm audit` limpios. `openspec validate --all --strict`: 12 de 12 tras el archivado.
- Entrega: PR #6 con CI en verde y squash merge `e603ea4` y archivado `09f741e` publicado en `main`.

### 13.5 Riesgos residuales
- TD-019: (a) la sesión se pierde al recargar la página y (b) el token en memoria queda expuesto ante XSS; se registraron por separado.
- TD-020: el E2E con mocks puede divergir del backend real; se revisa en el cambio 12.
- TD-021 quedó resuelto. `alembic check` sigue siendo un paso manual fuera del CI.


## 14. Esquema de documentos y búsqueda vectorial (`documents-schema-pgvector`, cambio OpenSpec 5 de 13)

**Herramienta y modelo:** Claude Code (CLI), modelo Sonnet 5.5, con el flujo OpenSpec del repositorio (`/opsx:explore`, `/opsx:propose`, `/opsx:apply`, `/opsx:archive`). El contexto lo daban `CLAUDE.md` → `docs/base-standards.md`, `docs/backend-standards.md`, `docs/lessons-learned.md` y `docs/technical-debt.md`. Esta sección se agregó con aprobación explícita del usuario.

**Skills y subagentes usados:**
- Skills de OpenSpec `opsx:explore`, `opsx:propose`, `opsx:apply` y `opsx:archive`.
- Skills `adversarial-review` y `update-docs`.
- **Un subagente** de Claude Code (tipo `Explore`, `model=opus`), con contexto limpio y de solo lectura, como revisor adversarial independiente, en cuatro pasadas: la revisión del grupo 11 (revisión 1 y revisión 2 de las correcciones) y la revisión focalizada de las correcciones F5, F7 y F8 (pasada 1 y pasada 2). La IA le dio el alcance, las áreas a atacar y las restricciones, y ninguna de sus propias conclusiones.

**Formato de esta sección:** los bloques marcados *(fragmento textual)* son frases literales de mensajes del usuario, copiadas del registro `openspec/changes/archive/2026-11-08-documents-schema-pgvector/reports/2026-11-08-user-prompts-verbatim.md` (20 mensajes extraídos de forma mecánica de la transcripción de la sesión, entradas A1 a A20); los marcados *(resumido, no textual)* son resúmenes de la IA. No se reconstruyó ninguna conversación. El mensaje A18 llegó a la sesión cortado en su última sección y así está registrado. Las notas de trabajo por grupo están en `…/reports/2026-11-07-ai-usage-notes.md` (resúmenes) y el cierre del grupo 0 en `…/reports/2026-11-08-group-0-baseline.md`.

### 14.1 Prompts y decisiones del usuario

**Prompt 1 — análisis previo (A1, fragmento textual):**

```
Quiero comenzar el análisis de la feature 5 del proyecto AsistenteIA, manteniendo OpenSpec como fuente de verdad y aplicando los estándares y lecciones aprendidas del proyecto.
```

**Prompt 2 — aprobación de diseño, decisiones D1–D9 (A2, fragmentos textuales):**

```
No implementar ingesta, extracción, chunking, generación de embeddings, endpoints de documentos ni chat/RAG.
D1: usar FK compuesta para impedir inconsistencias entre documento, chunk y asignatura. Incorporar la restricción UNIQUE necesaria.
```

**Prompt 3 — aprobación condicionada, D1–D11 (A3, fragmentos textuales):**

```
Mantener `vector(384)` y el aislamiento por actor dentro de SQL.
Mantener búsqueda exacta como referencia funcional del MVP.
```

**Prompt 4 — planificación y spike de compatibilidad (A4, fragmento textual, más resumen):**

```
Utilizar contenedor PostgreSQL y entorno Python completamente desechables y aislados.
```

*(Resumido, no textual:)* autorizó publicar la planificación en un PR sin merge y ejecutar únicamente el grupo 1 (spike).

**Prompt 5 — resolución de las incidencias I1–I4 y grupo 2 (A5, fragmento textual, más resumen):**

```
Prohibir el registro de `exc.orig` y SQL con parámetros que puedan revelar embeddings o contenido documental.
```

*(Resumido, no textual:)* decidió mantener `alembic check` y ampliar los tests de migración con consultas al catálogo (I1), y pidió definir los límites numéricos de los embeddings únicamente con evidencia reproducible de un experimento aislado (I3).

**Prompts 6 y 7 — grupos 3 y 4 (A6 y A7, resumidos, no textuales):** autorizaciones de un grupo por vez (migración 0004 y modelos; fixtures deterministas), con "detenerse y pedir aprobación" antes del grupo siguiente.

**Prompt 8 — grupo 5, `find_similar` (A8, fragmento textual):**

```
Si HNSW reduce recall o entrega resultados incompletos, detenerse y presentar evidencia y alternativas.
```

**Prompt 9 — grupo 6, regresión (A9, fragmentos textuales):**

```
Registrar como deuda técnica que HNSW no se utiliza en el plan actual.
Dejar su evaluación de rendimiento y estrategia de indexación para el cambio 12.
```

**Prompts 10 y 11 — grupos 7 y 8, seguridad de la base de datos (A10 y A11, fragmentos textuales):**

```
La migración 0004 de la base de desarrollo queda reservada para la tarea 8.1 y no está autorizada en este grupo.
No ejecutar downgrade destructivo sobre la base de desarrollo.
```

**Prompts 12 y 13 — grupos 9 y 10 (A12 y A13, fragmento textual, más resumen):**

```
No considerar `/tmp` del contenedor como almacenamiento duradero.
```

*(Resumido, no textual:)* autorizó documentar en la guía de desarrollo cómo usar un archivo de Compose temporal cuando los puertos 8000 y 5173 están ocupados por otro proyecto, sin cambiar los puertos por defecto.

**Prompt 14 — grupo 11, revisión adversarial (A14, resumido, no textual):** exigió una revisión independiente por un subagente de contexto limpio y solo lectura, TDD para toda corrección funcional y solo un relevamiento (sin ejecutar) de las tareas pendientes del grupo 0.

**Prompt 15 — espera (A15, fragmento textual):**

```
Esperar el informe del revisor
```

**Prompt 16 — resolución de la revisión (A16, fragmentos textuales):**

```
No inventar prompts ni completar huecos con reconstrucciones de memoria.
No registrar secretos en documentos.
```

*(Resumido, no textual:)* corregir F5, F7 y F8 con TDD y revisión independiente focalizada, aceptar F6 como TD-027 y presentar el texto de F9 sin cambiar el enum, y ejecutar el grupo 0 con evidencia.

**Prompt 17 — F9, F12 y N3 (A17, fragmentos textuales):**

```
No modificar la migración 0004 ni crear una 0005.
Si no se puede garantizar almacenamiento persistente, detenerse y reportarlo.
No reescribir el historial Git.
```

**Prompt 18 — verificación final (A18, fragmento textual; el mensaje llegó cortado):**

```
No comenzar la feature 6.
```

**Prompt 19 — aprobación final (A19, fragmento textual):**

```
Ejecutar squash merge sin borrar ramas.
```

**Prompt 20 — publicación del archivado y de esta sección (A20, fragmento textual):**

```
No inventar prompts ni reconstruir conversaciones.
```

**Prompts de la IA al subagente revisor (resumidos, no textuales):** alcance del diff y de la base de datos, fuentes a leer, áreas a atacar (aislamiento, autorización en SQL, vectores extremos, fugas de errores y de logs, concurrencia, reversibilidad de la migración, planes con EXPLAIN), prohibición de editar el repositorio y de tocar la base de desarrollo, y un formato de informe con clasificación de bloqueantes, mayores, menores y riesgos aceptables.

### 14.2 Decisiones técnicas principales
- Tablas `documents` y `document_chunks` con clave foránea compuesta `(document_id, subject_id)` hacia `documents(id, subject_id)` (D1), CHECK de contenido no vacío y de la norma del embedding, y índices B-tree más un índice HNSW coseno (`m=16`, `ef_construction=64`).
- `ChunkRepository.find_similar(actor, subject_id, query_embedding, top_k)`: autorización dentro del SQL (estudiante matriculado o docente titular), solo documentos `ready`, orden por distancia y luego por id de chunk; actor no autorizado, asignatura desconocida o rol desconocido devuelven lista vacía sin error (D2, D11).
- Búsqueda exacta filtrada por asignatura como referencia funcional; el HNSW existe pero el plan no lo usa (TD-022). No se tocaron parámetros del planificador ni de pgvector.
- Validación compartida con la futura ingesta: 384 componentes finitos, norma entre `1e-6` y `1e6` medida sobre los valores en precisión simple con margen relativo de `1e-12`, `top_k` de 1 a 50, ids de asignatura y de actor como UUID; los mensajes de error no contienen valores (D8).
- Imagen `pgvector/pgvector:0.8.7-pg15` fijada en Compose y en CI; paquete Python `pgvector 0.5.1`.

### 14.3 Correcciones, desviaciones y hallazgos
- **Evidencia TDD:** fallo previo registrado por grupo y tablas de mutaciones (por ejemplo 13 de 13 mutaciones de `find_similar` detectadas y 10 de 10 en la corrección final de F5, F7 y F8). Desviaciones registradas en `…/reports/2026-10-28-tdd-evidence.md`.
- **Incidencias del spike (I1–I4):** `alembic check` no ve el operador HNSW, los CHECK ni las cascadas (se amplió con consultas al catálogo); riesgo de fuga de datos por errores de SQL; extensión de pgvector y magnitud de los embeddings (pgvector 0.8.7 devuelve `NaN` o distancias erróneas para magnitudes extremas).
- **Revisión independiente 1 (grupo 11, FAIL por un mayor):** el diseño prometía que `find_similar` traduce errores de base de datos y el código los propaga; se corrigió el artefacto (el usuario confirmó no introducir un tipo de error nuevo). También: un test de logs que no veía el embedding, un entero enorme y una secuencia con longitud falsa que escapaban del error controlado, y una contraseña desechable en un script (se lee ahora del entorno).
- **Revisión 2 (PASS WITH GAPS):** dos hallazgos menores adicionales (un `int` cuya conversión a `float` falla; numeración duplicada), corregidos; la contraseña desechable en el historial se aceptó (N3).
- **Correcciones decididas por el usuario tras la revisión:**
  - F5: el helper y el CHECK `vector_norm` discrepaban en los bordes; se corrigió con TDD y la revisión focalizada halló que la primera corrección era incompleta (valores en puntos medios de float32: 167 de 3.000 vectores; orden de suma de pgvector: 47 de 240); la corrección final devuelve los valores en precisión simple y añade el margen de `1e-12`. La garantía es unidireccional: si el helper acepta, el CHECK acepta.
  - F7: `find_similar` verifica el rol almacenado del usuario dentro del SQL; tests con roles falsos y cambiados en la base.
  - F8: un `subject_id` que no es UUID se rechaza antes del SQL (el revisor halló lo mismo en `actor.user_id`, también corregido).
  - Revisión focalizada: PASS WITH GAPS y luego PASS.
- **Grupo 0:** las tareas 0.1 a 0.4 no se ejecutaron al inicio; se cerraron al final con evidencia de Git, la línea base tomada en el grupo 2 (desviación cronológica registrada) y los prompts literales extraídos de la transcripción.
- **Incidentes de herramientas y de proceso (reconocidos por la IA):** una consulta de solo lectura al contenedor de otro proyecto antes de corregir el destino; la cuenta de GitHub CLI activa era otra y hubo que cambiarla a `supercentro`; los puertos 8000 y 5173 pertenecen a otro proyecto (se usaron 18000 y 15173 con un archivo de Compose fuera del repositorio); un script escribió un carácter de control en una ruta de un informe y se corrigió en un commit aparte; un permiso denegado de forma transitoria se reintentó una vez.

### 14.4 Resultados de validación
- Backend: 712 pruebas, cobertura de `app` 98 %, `ruff`, `ruff format --check`, `mypy --strict` (107 archivos) y `pip-audit` limpios. Frontend sin cambios (236 pruebas, 11 E2E con mocks pasan y 6 se saltan, `npm audit` sin vulnerabilidades).
- Migración `0004`: subida, `alembic check`, bajada a `0003` y subida en una base descartable; la base de desarrollo quedó en `0004` sin filas y con el esquema idéntico antes y después de la verificación final.
- `openspec validate --all --strict`: 14 de 14 tras el archivado.
- Entrega: PR #7 con CI en verde, squash merge `af7a2e2` y archivado `ab22f42` publicado en `main`; 47 de 47 tareas.

### 14.5 Riesgos residuales
- TD-022 (HNSW sin uso), TD-023 (sin cuota ni `statement_timeout`), TD-025 (parámetros HNSW) y TD-026 (sin guarda automática del plan): abiertas, a evaluar en los cambios 6 y 12. TD-024 (dimensión fija y supuestos del margen de F5), TD-027 (contenido que parece vacío) y TD-028 (enum `document_status` preexistente): aceptadas.
- El respaldo previo a `0004` tiene una única copia persistente en un disco local, fuera del repositorio; y una contraseña desechable de un contenedor del spike permanece en el historial de git (commit `f61ce6d`), sin uso en el proyecto.

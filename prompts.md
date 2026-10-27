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

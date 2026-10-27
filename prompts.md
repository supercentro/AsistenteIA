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

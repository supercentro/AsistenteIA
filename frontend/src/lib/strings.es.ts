/** Single location for all user-facing (Spanish) copy. Do not hardcode UI strings in JSX. */
export const strings = {
  app: {
    name: 'AsistenteIA',
    tagline: 'Tu asistente académico basado en el material de cada asignatura.',
  },
  notFound: {
    title: 'Página no encontrada',
    backHome: 'Volver al inicio',
  },
  forbidden: {
    title: 'Acceso no permitido',
    body: 'La cuenta no tiene acceso a esta sección.',
    backHome: 'Volver al inicio',
  },
  nav: {
    label: 'Navegación principal',
    subjects: 'Asignaturas',
    signOut: 'Cerrar sesión',
    signedInAs: (name: string) => `Sesión de ${name}`,
  },
  auth: {
    login: {
      title: 'Iniciar sesión',
      email: 'Correo electrónico',
      password: 'Contraseña',
      submit: 'Entrar',
      submitting: 'Entrando…',
      createAccount: 'Crear una cuenta',
    },
    register: {
      title: 'Crear cuenta de estudiante',
      name: 'Nombre',
      email: 'Correo electrónico',
      password: 'Contraseña',
      passwordHint: 'Entre 10 y 128 caracteres.',
      submit: 'Crear cuenta',
      submitting: 'Creando cuenta…',
      haveAccount: 'Iniciar sesión',
      privacyLink: 'Política de privacidad',
    },
    notices: {
      registered: 'La cuenta se creó correctamente. Ya se puede iniciar sesión.',
      expired: 'La sesión expiró. Es necesario iniciar sesión de nuevo.',
      unauthorized: 'La sesión ya no es válida. Es necesario iniciar sesión de nuevo.',
      signedOut: 'La sesión se cerró correctamente.',
      loginFailed: 'No se pudo completar el inicio de sesión. Inténtelo de nuevo.',
    },
    errors: {
      invalidCredentials: 'Correo o contraseña incorrectos.',
      emailTaken: 'Ya existe una cuenta con ese correo electrónico.',
      loginIncomplete: 'No se pudo completar el inicio de sesión. Inténtelo de nuevo.',
    },
    validation: {
      required: 'Este campo es obligatorio.',
      emailInvalid: 'Ingrese un correo electrónico válido.',
      emailAscii: 'El correo electrónico solo puede contener caracteres ASCII.',
      emailTooLong: 'El correo electrónico no puede superar los 255 caracteres.',
      nameTooLong: 'El nombre no puede superar los 100 caracteres.',
      passwordTooShort: 'La contraseña debe tener al menos 10 caracteres.',
      passwordTooLong: 'La contraseña no puede superar los 128 caracteres.',
      formInvalid: 'Revise los campos marcados.',
    },
  },
  privacy: {
    title: 'Política de privacidad',
    versionLabel: (version: string) => `Versión ${version}`,
    intro:
      'AsistenteIA responde preguntas con el material que el personal docente sube a cada asignatura. Esta política explica qué datos personales se guardan, a quién se envían, cómo se borran y qué derechos reconoce la Ley 25.326 de Protección de los Datos Personales.',
    back: 'Volver al inicio',
    sections: {
      controller: {
        heading: 'Responsable del tratamiento',
        paragraphs: [
          '[A COMPLETAR POR LA INSTITUCIÓN: nombre, domicilio y medio de contacto del responsable de la base de datos.]',
        ],
        items: [] as readonly string[],
      },
      audience: {
        heading: 'A quién está dirigido el servicio',
        paragraphs: [
          'AsistenteIA está destinado exclusivamente a personas mayores de 18 años. Los estudiantes lo declaran al aceptar esta política.',
        ],
        items: [] as readonly string[],
      },
      mandatory: {
        heading: 'Datos necesarios y consecuencias de no aceptar',
        paragraphs: [
          'Los datos de la cuenta (nombre, correo electrónico y contraseña) son necesarios para crearla y usar el servicio.',
          'La aceptación de esta política se solicita a los estudiantes, que son quienes hacen preguntas al asistente. Aceptar esta política es necesario para usar el asistente: sin la aceptación, la aplicación solo permite leer esta política y cerrar la sesión.',
        ],
        items: [] as readonly string[],
      },
      stored: {
        heading: 'Qué datos se guardan',
        paragraphs: [] as readonly string[],
        items: [
          'Los datos de la cuenta: nombre, correo electrónico y contraseña. La contraseña se guarda transformada con un algoritmo de un solo sentido, nunca en texto claro.',
          'Las conversaciones: cada pregunta que se escribe y cada respuesta del asistente.',
          'Por cada respuesta, las fuentes citadas: nombre del archivo, página y la referencia al fragmento del material.',
          'La versión de esta política que se acepta y la fecha y hora de la aceptación.',
        ],
      },
      purpose: {
        heading: 'Para qué se usan y con qué base',
        paragraphs: [
          'Los datos se usan para dar el servicio: autenticar la cuenta, generar respuestas con el material de la asignatura y mostrar el historial de conversaciones. Por cada fuente citada también se guardan su posición y su puntuación de similitud, para poder analizar la calidad de las respuestas. Los registros técnicos de la aplicación no incluyen el contenido de los mensajes.',
          '[A COMPLETAR POR LA INSTITUCIÓN (revisión legal): fundamento jurídico del tratamiento conforme a la Ley 25.326, incluido el alcance del consentimiento.]',
        ],
        items: [] as readonly string[],
      },
      processor: {
        heading: 'Tratamiento por Gemini (Google)',
        paragraphs: [
          'Para generar cada respuesta, el sistema envía a Gemini, el servicio de inteligencia artificial de Google, los siguientes datos:',
        ],
        items: [
          'La pregunta que se escribe.',
          'Los mensajes más recientes de la misma conversación, para dar continuidad.',
          'Los fragmentos del material de la asignatura que son relevantes para la pregunta, con el nombre del archivo y la página de los que provienen.',
        ],
        notes: [
          'No se envían el nombre, el correo electrónico ni la contraseña de la cuenta.',
          'No se envía nada a Gemini mientras no se haya aceptado esta política.',
          'Gemini es un servicio de un tercero y puede procesar estos datos fuera de la República Argentina, incluso en países que la normativa argentina no reconoce como de protección adecuada; según la lista de la Disposición 60-E/2016, Estados Unidos no figura entre los reconocidos.',
          '[A COMPLETAR POR LA INSTITUCIÓN (revisión legal): condiciones de Google aplicables a este tratamiento (servicio contratado, acuerdo de tratamiento de datos, conservación y uso de los datos), lugar donde se realiza y fundamento de la transferencia internacional.]',
        ],
      },
      retention: {
        heading: 'Cuánto tiempo se conservan',
        paragraphs: [
          'Las conversaciones se conservan hasta que se borran. Si el personal docente elimina un documento, sus fragmentos se borran, pero las respuestas ya dadas conservan el nombre del archivo y la página como referencia.',
          'Si el personal docente elimina una asignatura, o si se elimina la cuenta, las conversaciones correspondientes se eliminan con ellas.',
          'Si se deja de estar inscrito en una asignatura, sus conversaciones dejan de mostrarse, pero no se borran: vuelven a verse si se inscribe de nuevo, y se pueden borrar en cualquier momento.',
          '[A COMPLETAR POR LA INSTITUCIÓN: plazo máximo de conservación de las cuentas, si lo hay.]',
        ],
        items: [] as readonly string[],
      },
      deletion: {
        heading: 'Cómo borrar las conversaciones',
        paragraphs: [] as readonly string[],
        items: [
          'Se puede borrar una conversación concreta: se eliminan sus mensajes y las fuentes asociadas de la base de datos de la aplicación.',
          'Se pueden borrar todas las conversaciones de una vez.',
        ],
        notes: [
          '[A COMPLETAR POR LA INSTITUCIÓN: si existen copias de seguridad, cuánto tiempo se conservan y cuándo dejan de contener los datos borrados.]',
        ],
      },
      rights: {
        heading: 'Sus derechos',
        paragraphs: [
          'La Ley 25.326 y su decreto reglamentario reconocen, entre otros, estos derechos sobre sus datos personales:',
        ],
        items: [
          'Acceso: conocer qué datos suyos se tratan. El responsable debe responder en 10 días corridos y el acceso es gratuito a intervalos de al menos seis meses (art. 14).',
          'Rectificación, actualización y supresión de sus datos. El responsable debe resolver el pedido en 5 días hábiles (art. 16).',
          'Retirar en cualquier momento el consentimiento dado, sin efectos retroactivos.',
          'Si el responsable no responde o la respuesta es insuficiente, puede acudirse a la acción de hábeas data (arts. 14, 16 y 33 y siguientes).',
        ],
        notes: [
          'También puede dirigirse a la autoridad de control en materia de protección de datos personales.',
        ],
      },
      notSelfService: {
        heading: 'Lo que todavía no se puede hacer sin ayuda',
        paragraphs: [] as readonly string[],
        items: ['Eliminar la cuenta.', 'Retirar el consentimiento dado.'],
        notes: [
          'Para estos casos, y para ejercer los derechos descritos arriba, es necesario contactar con el responsable de la base de datos.',
          '[A COMPLETAR POR LA INSTITUCIÓN: medio concreto y responsable de atender los pedidos de acceso, rectificación, supresión y retiro del consentimiento, y nombre y datos de contacto de la autoridad de control competente.]',
        ],
      },
    },
  },
  consent: {
    title: 'Aceptar la política de privacidad',
    firstTime: 'Para usar el asistente es necesario leer y aceptar la política de privacidad.',
    changed:
      'La política de privacidad cambió desde la última vez que se aceptó. Es necesario aceptar la versión vigente para continuar.',
    checkbox: (version: string) =>
      `He leído y acepto la política de privacidad (versión ${version}) y declaro ser mayor de 18 años`,
    accept: 'Aceptar y continuar',
    accepting: 'Guardando…',
    signOut: 'Cerrar sesión',
    policyLink: 'Abrir la política en una pestaña nueva',
    versionChanged:
      'La política cambió mientras tanto. Recargue la página para ver la versión vigente.',
  },
  subjects: {
    titleStudent: 'Mis asignaturas',
    titleTeacher: 'Asignaturas a mi cargo',
    loading: 'Cargando asignaturas…',
    emptyStudent: 'Todavía no hay asignaturas en las que la cuenta esté inscrita.',
    emptyTeacher: 'Todavía no hay asignaturas a cargo de esta cuenta.',
    loadError: 'No se pudieron cargar las asignaturas.',
    listLabel: 'Lista de asignaturas',
    create: {
      heading: 'Crear una asignatura',
      name: 'Nombre',
      description: 'Descripción (opcional)',
      submit: 'Crear asignatura',
      submitting: 'Creando…',
      nameTaken: 'Ya existe una asignatura con ese nombre.',
      validation: {
        nameRequired: 'Ingrese el nombre de la asignatura.',
        nameTooLong: 'El nombre no puede superar los 150 caracteres.',
        descriptionTooLong: 'La descripción no puede superar los 2000 caracteres.',
      },
    },
  },
  materials: {
    back: 'Volver a las asignaturas',
    loading: 'Cargando asignatura…',
    notFound: {
      title: 'Asignatura no encontrada',
      body: 'La asignatura no existe o la cuenta no tiene acceso a ella.',
    },
    documents: {
      heading: 'Documentos',
      loading: 'Cargando documentos…',
      empty:
        'Todavía no se subió ningún documento. Use el formulario de arriba para subir el primero.',
      listLabel: 'Documentos de la asignatura',
      refresh: 'Actualizar lista',
      pollFailed: 'No se pudo actualizar la lista. Se muestra la última versión conocida.',
      chunks: (count: number) => `${count} ${count === 1 ? 'fragmento' : 'fragmentos'}`,
      size: (bytes: number) =>
        bytes < 1024
          ? `${bytes} B`
          : bytes < 1024 * 1024
            ? `${Math.round(bytes / 1024)} KB`
            : `${(bytes / (1024 * 1024)).toFixed(1)} MB`,
      types: {
        'application/pdf': 'PDF',
        'text/plain': 'Texto',
        'text/markdown': 'Markdown',
      } as Record<string, string>,
      otherType: 'Otro',
    },
    status: {
      pending: 'Pendiente',
      processing: 'Procesando',
      ready: 'Listo',
      failed: 'Con error',
    },
    announce: {
      ready: (name: string) => `El documento ${name} está listo.`,
      failed: (name: string) => `El documento ${name} no se pudo procesar.`,
    },
    failures: {
      NO_EXTRACTABLE_TEXT:
        'No se pudo extraer texto del archivo. Puede ser un PDF escaneado o sin texto.',
      ENCRYPTED_PDF: 'El PDF está protegido con contraseña. Suba una versión sin protección.',
      CORRUPT_FILE: 'El archivo está dañado o no se pudo leer.',
      TOO_MANY_PAGES: 'El PDF tiene demasiadas páginas. Divídalo en partes más pequeñas.',
      TEXT_TOO_LARGE: 'El texto del archivo es demasiado extenso. Divídalo en partes más pequeñas.',
      TOO_MANY_CHUNKS: 'El archivo genera demasiados fragmentos. Divídalo en partes más pequeñas.',
      PROCESSING_TIMEOUT:
        'El procesamiento tardó demasiado y se canceló. Inténtelo de nuevo con un archivo más pequeño.',
      RESOURCE_LIMIT_EXCEEDED: 'El archivo superó los recursos permitidos para procesarlo.',
      EMBEDDING_FAILED:
        'No se pudo preparar el contenido para las consultas. Inténtelo de nuevo más tarde.',
      PROCESSING_INTERRUPTED:
        'El procesamiento se interrumpió. Elimine el documento y vuelva a subirlo.',
      JOB_EXPIRED:
        'El procesamiento no se completó a tiempo. Elimine el documento y vuelva a subirlo.',
      PROCESSING_FAILED: 'No se pudo procesar el documento. Inténtelo de nuevo.',
      generic: 'El documento no se pudo procesar.',
    },
    upload: {
      heading: 'Subir material',
      fileLabel: 'Archivo',
      notice:
        'Formatos admitidos: PDF, texto (.txt) y Markdown (.md). Esta versión es un MVP de pruebas: suba únicamente documentos ficticios, sin datos personales ni contenido confidencial.',
      submit: 'Subir documento',
      submitting: 'Subiendo…',
      noFile: 'Elija un archivo para subir.',
      timeout:
        'La subida tardó demasiado y no se sabe si el archivo llegó. Revise la lista de documentos antes de volver a intentarlo.',
      reasons: {
        MALFORMED_MULTIPART: 'La solicitud de subida no es válida. Vuelva a elegir el archivo.',
        FILE_PART_MISSING: 'No se recibió ningún archivo. Vuelva a elegirlo.',
        UNEXPECTED_FIELDS: 'La solicitud incluye datos inesperados. Vuelva a intentarlo.',
        EMPTY_FILE: 'El archivo está vacío.',
        INVALID_FILENAME: 'El nombre del archivo no es válido. Cámbielo e inténtelo de nuevo.',
      },
    },
    remove: {
      action: (name: string) => `Eliminar ${name}`,
      confirmQuestion: (name: string) => `¿Eliminar «${name}»?`,
      confirmBody:
        'Esta acción no se puede deshacer. También se borran los fragmentos del documento.',
      confirm: 'Eliminar definitivamente',
      cancel: 'Cancelar',
      working: 'Eliminando…',
      gone: 'El documento ya no existía.',
    },
  },
  enrollments: {
    heading: 'Estudiantes inscritos',
    loading: 'Cargando estudiantes…',
    empty:
      'Todavía no hay estudiantes inscritos. Use el formulario de arriba para inscribir al primero.',
    listLabel: 'Estudiantes inscritos en la asignatura',
    form: {
      field: 'Correo electrónico del estudiante',
      hint: 'La cuenta del estudiante ya debe existir: la persona se registra primero.',
      submit: 'Inscribir estudiante',
      submitting: 'Inscribiendo…',
    },
    errors: {
      notFound: 'No se encontró un estudiante registrado con ese correo.',
      alreadyEnrolled: 'Ese estudiante ya está inscrito en la asignatura.',
    },
    remove: {
      action: (email: string) => `Quitar a ${email}`,
      question: (email: string) => `¿Quitar a ${email} de la asignatura?`,
      body: 'El estudiante dejará de ver la asignatura y sus conversaciones en ella. No se borra nada: si se lo vuelve a inscribir, las recupera.',
      confirm: 'Quitar de la asignatura',
      cancel: 'Cancelar',
      working: 'Quitando…',
      gone: 'La inscripción ya no existía.',
    },
  },
  chat: {
    back: 'Volver a las asignaturas',
    loading: 'Cargando asignatura…',
    unavailable: {
      title: 'Asignatura no disponible',
      body: 'La asignatura no existe o la cuenta ya no tiene acceso a ella.',
    },
    notice:
      'Versión de prueba: las preguntas y los fragmentos del material se envían a Gemini (Google) para generar la respuesta. Use solo datos ficticios. Mencione el tema en cada pregunta: el asistente no usa la conversación anterior para buscar en el material.',
    policyLink: 'Política de privacidad (borrador)',
    openChat: (name: string) => `Preguntar sobre ${name}`,
    box: {
      label: 'Pregunta',
      send: 'Enviar',
      sending: 'Enviando…',
      required: 'Escriba una pregunta.',
      tooLong: 'La pregunta no puede superar los 2000 caracteres.',
      counter: (count: number) => `${count} de 2000 caracteres`,
    },
    answering: 'El asistente está respondiendo…',
    thread: {
      label: 'Mensajes de la conversación',
      empty: 'Escriba la primera pregunta de esta conversación.',
      you: 'Usted',
      assistant: 'Asistente',
    },
    sources: {
      cited: 'Material citado en la respuesta',
      retrieved: 'Material recuperado (la respuesta no indica cuáles fragmentos usó)',
      marker: (rank: number) => `[${rank}]`,
      page: (page: number) => `página ${page}`,
      snippet: 'Ver fragmento',
      note: 'Fragmentos del material asociados a esta respuesta. Compruebe la información en el documento original.',
    },
    conversations: {
      heading: 'Conversaciones',
      loading: 'Cargando conversaciones…',
      empty: 'Todavía no hay conversaciones en esta asignatura.',
      listLabel: 'Conversaciones de la asignatura',
      new: 'Nueva conversación',
      // The API gives no preview today (last_message_preview is null): the date tells them apart.
      untitled: (createdAt: string) =>
        `Conversación del ${new Date(createdAt).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' })}`,
      messagesUnavailable: 'Esta conversación ya no está disponible.',
      gone: 'La conversación ya no existía.',
      remove: {
        action: (preview: string) => `Eliminar la conversación «${preview}»`,
        question: (preview: string) => `¿Eliminar la conversación «${preview}»?`,
        body: 'Se borran la conversación y todos sus mensajes. No se puede deshacer.',
        confirm: 'Eliminar conversación',
        cancel: 'Cancelar',
        working: 'Eliminando…',
      },
    },
    history: {
      heading: 'Mi historial',
      action: 'Borrar todo mi historial',
      question: '¿Borrar todo el historial de conversaciones?',
      body: 'Se borran todas las conversaciones de la cuenta en todas las asignaturas, también las de asignaturas que ya no ve. No se puede deshacer. La cuenta no se elimina.',
      confirm: 'Borrar todo el historial',
      cancel: 'Cancelar',
      working: 'Borrando…',
      done: 'Se borró todo el historial de conversaciones.',
    },
    errors: {
      sharedLimit: 'El límite puede compartirse con otras personas que usen la misma conexión.',
      timeout:
        'La consulta tardó demasiado y la respuesta puede haberse guardado. Revise la conversación abierta y la lista de conversaciones antes de volver a preguntar.',
    },
  },
  activity: {
    link: 'Ver actividad',
    back: 'Volver a la asignatura',
    loading: 'Cargando actividad…',
    title: 'Actividad de la asignatura',
    window: (start: string, end: string) => `Semanas del ${start} al ${end}`,
    insufficient: 'Datos insuficientes',
    cards: {
      enrolled: 'Estudiantes inscriptos',
      active: 'Estudiantes activos',
      activeNote: 'Estudiantes que hicieron al menos una pregunta en estas semanas.',
    },
    weekly: {
      caption: 'Preguntas por semana',
      week: 'Semana',
      questions: 'Preguntas',
    },
    shares: {
      heading: 'Proporción de respuestas',
      noMaterial: 'Respuestas sin material encontrado',
      noCitedSource: 'Respuestas sin fuente citada',
      noCitedSourceNote: 'Incluye las respuestas sin material encontrado.',
    },
    documents: {
      caption: 'Documentos citados en las respuestas',
      name: 'Documento',
      cited: 'Veces que una respuesta citó el documento',
      note: 'Cuenta citas; no mide comprensión ni uso del material.',
    },
    note: (minimumGroup: number) =>
      `Las cifras de actividad solo se muestran cuando provienen de al menos ${minimumGroup} estudiantes. Cuando hay menos, se indica «Datos insuficientes». Las cifras pueden cambiar entre consultas.`,
    allSuppressed: 'Todavía no hay datos suficientes para mostrar la actividad de esta asignatura.',
    wholeWeeksOnly: 'Se muestran solo semanas completas.',
    limited:
      'Por un cambio en las inscripciones, solo se muestran las semanas posteriores a ese cambio.',
    noWeeks: 'Por un cambio en las inscripciones, todavía no hay semanas completas para mostrar.',
  },
  states: {
    loading: 'Cargando…',
    retry: 'Reintentar',
    dismiss: 'Cerrar aviso',
  },
  errors: {
    byCode: {
      UNAUTHORIZED: 'La sesión no es válida. Inicie sesión de nuevo.',
      FORBIDDEN: 'No hay permiso para realizar esta acción.',
      NOT_FOUND: 'No se encontró lo solicitado.',
      CONFLICT: 'La operación entra en conflicto con los datos existentes.',
      VALIDATION_ERROR: 'Los datos enviados no son válidos. Revise los campos.',
      INVALID_CREDENTIALS: 'Correo o contraseña incorrectos.',
      RATE_LIMITED: 'Se realizaron demasiados intentos. Espere un momento e inténtelo de nuevo.',
      SERVICE_UNAVAILABLE:
        'El servicio no está disponible en este momento. Inténtelo de nuevo más tarde.',
      PAYLOAD_TOO_LARGE: 'El archivo supera el tamaño máximo permitido.',
      UNSUPPORTED_MEDIA_TYPE: 'El tipo de archivo no es admitido. Suba un PDF, un .txt o un .md.',
      DOCUMENT_QUOTA_EXCEEDED:
        'La asignatura alcanzó el máximo de documentos. Elimine alguno para subir otro.',
      INGESTION_QUEUE_FULL:
        'El servicio está procesando muchos documentos. Inténtelo de nuevo en unos minutos.',
      REQUEST_TIMEOUT: 'La subida tardó demasiado. Compruebe la conexión e inténtelo de nuevo.',
      LLM_UNAVAILABLE: 'El asistente no está disponible en este momento. Inténtelo de nuevo.',
      LLM_BLOCKED: 'No se pudo dar una respuesta a esa pregunta. Reformúlela e inténtelo de nuevo.',
    },
    byStatus: {
      unauthorized: 'La sesión no es válida. Inicie sesión de nuevo.',
      forbidden: 'No hay permiso para realizar esta acción.',
      notFound: 'No se encontró lo solicitado.',
      conflict: 'La operación entra en conflicto con los datos existentes.',
      validation: 'Los datos enviados no son válidos. Revise los campos.',
      rateLimited: 'Se realizaron demasiados intentos. Espere un momento e inténtelo de nuevo.',
      server: 'El servicio no está disponible en este momento. Inténtelo de nuevo más tarde.',
      client: 'No se pudo completar la solicitud. Inténtelo de nuevo.',
    },
    network: 'No se pudo conectar con el servidor. Compruebe la conexión e inténtelo de nuevo.',
    timeout: 'El servidor tardó demasiado en responder. Inténtelo de nuevo.',
    unknown: 'Ocurrió un error inesperado. Inténtelo de nuevo.',
    waitSeconds: (seconds: number) => `Espere ${seconds} segundos antes de intentarlo de nuevo.`,
    rateLimitedIn: (seconds: number) =>
      `Se realizaron demasiados intentos. Espere ${seconds} segundos e inténtelo de nuevo.`,
  },
} as const

/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  /** Public build-time switch of the teacher activity page; any value but "true" keeps it off. */
  readonly VITE_TEACHER_ACTIVITY_ENABLED?: string
  readonly VITE_TEACHER_TOPICS_ENABLED?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

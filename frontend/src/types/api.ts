import type { components, paths } from './api.generated'

/** Payload types come from docs/api-spec.yml through the generated file; never redeclare them. */
export type User = components['schemas']['User']
export type UserRole = NonNullable<User['role']>
export type Subject = components['schemas']['Subject']
export type SubjectCreate = components['schemas']['SubjectCreate']
export type Document = components['schemas']['Document']
export type Enrollment = components['schemas']['Enrollment']
// The contract does not mark the fields of these four schemas as required, but the API always sends
// them (spec `rag-chat` and `conversation-history`): `Required` states what the backend guarantees.
export type Source = Required<components['schemas']['Source']>
export type Conversation = Required<components['schemas']['Conversation']>
/** Whether the sources of an answer were cited by it or only retrieved (null: no sources). */
export type SourceAttribution = NonNullable<components['schemas']['Message']['attribution']>
export type Message = Omit<
  Required<components['schemas']['Message']>,
  'sources' | 'attribution'
> & {
  sources: Source[]
  /** Absent when the server does not send it: the sources are then shown as retrieved. */
  attribution?: SourceAttribution | null
}
export type ChatResponse = Omit<components['schemas']['ChatResponse'], 'sources'> & {
  sources: Source[]
}
export type DocumentStatus = Document['status']
export type ActivityResponse = components['schemas']['ActivityResponse']
export type TokenResponse = components['schemas']['TokenResponse']
export type RegisterRequest = components['schemas']['RegisterRequest']
export type ApiErrorBody = components['schemas']['Error']
export type LoginRequest =
  paths['/auth/login']['post']['requestBody']['content']['application/json']

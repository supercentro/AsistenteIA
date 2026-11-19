import type { components, paths } from './api.generated'

/** Payload types come from docs/api-spec.yml through the generated file; never redeclare them. */
export type User = components['schemas']['User']
export type UserRole = NonNullable<User['role']>
export type Subject = components['schemas']['Subject']
export type SubjectCreate = components['schemas']['SubjectCreate']
export type Document = components['schemas']['Document']
export type Enrollment = components['schemas']['Enrollment']
export type DocumentStatus = Document['status']
export type TokenResponse = components['schemas']['TokenResponse']
export type RegisterRequest = components['schemas']['RegisterRequest']
export type ApiErrorBody = components['schemas']['Error']
export type LoginRequest =
  paths['/auth/login']['post']['requestBody']['content']['application/json']

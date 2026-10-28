import type { components } from './api.generated'

/** Payload types come from docs/api-spec.yml through the generated file; never redeclare them. */
export type User = components['schemas']['User']
export type UserRole = NonNullable<User['role']>
export type Subject = components['schemas']['Subject']
export type TokenResponse = components['schemas']['TokenResponse']
export type RegisterRequest = components['schemas']['RegisterRequest']
export type ApiErrorBody = components['schemas']['Error']
export type LoginRequest = { email: string; password: string }

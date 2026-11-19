import { describe, expect, it } from 'vitest'
import { enrollmentSchema, registerSchema } from './schemas'

function enrollmentIssues(studentEmail: string): string[] {
  const result = enrollmentSchema.safeParse({ studentEmail })
  return result.success ? [] : result.error.issues.map((issue) => issue.message)
}

function registrationEmailIssues(email: string): string[] {
  const result = registerSchema.safeParse({
    name: 'Ana',
    email,
    password: 'a-very-long-password',
  })
  return result.success ? [] : result.error.issues.map((issue) => issue.message)
}

describe('enrollmentSchema uses the e-mail rule of the registration', () => {
  const cases = [
    '',
    '   ',
    'sin-arroba',
    'a@b',
    'ana@example.com',
    'Ana@Example.COM',
    '  ana@example.com  ',
    'año@example.com',
    `${'a'.repeat(243)}@example.com`,
    `${'a'.repeat(244)}@example.com`,
  ]

  it.each(cases)('gives the same verdict as the registration for %j', (value) => {
    expect(enrollmentIssues(value)).toEqual(registrationEmailIssues(value))
  })

  it('accepts 255 characters and rejects 256', () => {
    const at255 = `${'a'.repeat(243)}@example.com`
    expect(at255).toHaveLength(255)
    expect(enrollmentIssues(at255)).toEqual([])
    expect(enrollmentIssues(`b${at255}`)).not.toEqual([])
  })

  it('trims the value it returns, as the registration does', () => {
    expect(enrollmentSchema.parse({ studentEmail: '  ana@example.com ' }).studentEmail).toBe(
      'ana@example.com',
    )
  })
})

import { describe, expect, it } from 'vitest'
import { subjectSchema } from './schemas'
import { strings } from './strings.es'

const { validation } = strings.subjects.create

function issues(input: unknown): string[] {
  const result = subjectSchema.safeParse(input)
  return result.success ? [] : result.error.issues.map((issue) => issue.message)
}

describe('subjectSchema mirrors the limits of POST /subjects', () => {
  it('accepts a name and an optional description', () => {
    expect(subjectSchema.safeParse({ name: 'Algebra', description: '' }).success).toBe(true)
    expect(subjectSchema.safeParse({ name: 'Algebra', description: 'Unidad 1' }).success).toBe(true)
  })

  it('trims the name and rejects a blank one', () => {
    expect(subjectSchema.parse({ name: '  Algebra  ', description: '' }).name).toBe('Algebra')
    expect(issues({ name: '   ', description: '' })).toEqual([validation.nameRequired])
  })

  it('accepts 150 characters and rejects 151', () => {
    expect(issues({ name: 'N'.repeat(150), description: '' })).toEqual([])
    expect(issues({ name: 'N'.repeat(151), description: '' })).toEqual([validation.nameTooLong])
  })

  it('accepts 2000 characters of description and rejects 2001', () => {
    expect(issues({ name: 'A', description: 'D'.repeat(2000) })).toEqual([])
    expect(issues({ name: 'A', description: 'D'.repeat(2001) })).toEqual([
      validation.descriptionTooLong,
    ])
  })

  it('is not stricter than the API: control characters are left to the server', () => {
    expect(issues({ name: 'Algebra\u0007', description: 'linea\u0001' })).toEqual([])
  })
})

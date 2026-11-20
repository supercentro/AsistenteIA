import { describe, expect, it } from 'vitest'
import { questionSchema } from './schemas'
import { strings } from './strings.es'

function issues(message: string): string[] {
  const result = questionSchema.safeParse({ message })
  return result.success ? [] : result.error.issues.map((issue) => issue.message)
}

describe('questionSchema mirrors the limits of POST /chat', () => {
  it('accepts a question of 1 to 2000 characters', () => {
    expect(issues('a')).toEqual([])
    expect(issues('a'.repeat(2000))).toEqual([])
  })

  it('rejects an empty question and one made only of blanks', () => {
    expect(issues('')).toEqual([strings.chat.box.required])
    expect(issues('   \n  ')).toEqual([strings.chat.box.required])
  })

  it('rejects 2001 characters', () => {
    expect(issues('a'.repeat(2001))).toEqual([strings.chat.box.tooLong])
  })

  it('trims what it returns', () => {
    expect(questionSchema.parse({ message: '  hola  ' }).message).toBe('hola')
  })

  it('is not stricter than the API: control characters are left to the server', () => {
    expect(issues('hola\u0007')).toEqual([])
  })
})

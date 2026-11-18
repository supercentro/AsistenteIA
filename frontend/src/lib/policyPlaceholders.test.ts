import { describe, expect, it } from 'vitest'
import { findOwnerPlaceholders } from './policyPlaceholders'
import { strings } from './strings.es'

describe('findOwnerPlaceholders (the detector itself)', () => {
  it('finds marked placeholders at any depth', () => {
    const tree = {
      a: ['ok', '[A COMPLETAR POR LA INSTITUCIÓN: x]'],
      b: { c: 'also [A COMPLETAR y]' },
    }
    expect(findOwnerPlaceholders(tree)).toEqual([
      '[A COMPLETAR POR LA INSTITUCIÓN: x]',
      'also [A COMPLETAR y]',
    ])
  })

  it('finds nothing in a text without placeholders', () => {
    expect(findOwnerPlaceholders({ a: ['texto', { b: 'otro' }], n: 3 })).toEqual([])
  })
})

describe('release check of the policy text', () => {
  // On demand: POLICY_RELEASE_CHECK=1 npx vitest run src/lib/policyPlaceholders.test.ts
  // It fails while the owner inputs are still placeholders, so the draft cannot be released.
  it.runIf(process.env.POLICY_RELEASE_CHECK === '1')(
    'the policy has no owner placeholders left',
    () => {
      expect(findOwnerPlaceholders(strings.privacy)).toEqual([])
    },
  )
})

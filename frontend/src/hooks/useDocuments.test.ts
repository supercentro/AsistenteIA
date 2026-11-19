import { describe, expect, it } from 'vitest'
import { documentItem } from '../tests/api'
import { DOCUMENTS_POLL_MS, documentsRefetchInterval } from './useDocuments'

describe('documentsRefetchInterval', () => {
  it('polls every 3 seconds while a document is pending', () => {
    expect(DOCUMENTS_POLL_MS).toBe(3000)
    expect(documentsRefetchInterval([documentItem({ status: 'pending' })])).toBe(3000)
  })

  it('polls while a document is processing, even if the others are final', () => {
    expect(
      documentsRefetchInterval([
        documentItem({ status: 'ready' }),
        documentItem({ status: 'processing' }),
        documentItem({ status: 'failed', error_code: 'CORRUPT_FILE' }),
      ]),
    ).toBe(3000)
  })

  it.each([
    ['nothing loaded yet', undefined],
    ['an empty list', []],
    ['all ready', [documentItem({ status: 'ready' })]],
    ['all final', [documentItem({ status: 'ready' }), documentItem({ status: 'failed' })]],
  ])('does not poll with %s', (_name, data) => {
    expect(documentsRefetchInterval(data)).toBe(false)
  })
})

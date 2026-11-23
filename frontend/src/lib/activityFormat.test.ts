import { describe, expect, it } from 'vitest'
import { barWidth, formatDay, formatShare } from './activityFormat'

describe('activityFormat', () => {
  it('writes a calendar day as day, month and year without converting it', () => {
    expect(formatDay('2026-03-02')).toBe('02/03/2026')
    expect(formatDay('2026-12-31')).toBe('31/12/2026')
  })

  it.each([
    [0, '0,0 %'],
    [0.2, '20,0 %'],
    [0.455, '45,5 %'],
    [1, '100,0 %'],
  ])('writes the share %s as %s', (share, text) => {
    expect(formatShare(share)).toBe(text)
  })

  it.each([
    [5, 10, '50%'],
    [10, 10, '100%'],
    [0, 10, '0%'],
    [7, 3, '100%'],
    [-1, 10, '0%'],
    [3, 0, '0%'],
    [0, 0, '0%'],
  ])('draws %s of %s as %s, never NaN or beyond the track', (value, maximum, width) => {
    expect(barWidth(value, maximum)).toBe(width)
  })
})

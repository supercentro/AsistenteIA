import { configureAxe } from 'vitest-axe'
import { expect } from 'vitest'

// Colour contrast needs real layout and rendering, which jsdom cannot provide.
const axe = configureAxe({ rules: { 'color-contrast': { enabled: false } } })

/** Fails on any serious or critical accessibility violation found by axe in the container. */
export async function expectNoSeriousA11yViolations(container: HTMLElement): Promise<void> {
  const results = await axe(container)
  const serious = results.violations.filter(
    (violation) => violation.impact === 'serious' || violation.impact === 'critical',
  )
  expect(
    serious.map((violation) => `${violation.id}: ${violation.help}`),
    'accessibility violations',
  ).toEqual([])
}

import { screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PRIVACY_POLICY_VERSION } from '../lib/privacyPolicy'
import { strings } from '../lib/strings.es'
import { handlers, studentUser, unconsentedStudent, teacherUser } from '../tests/api'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { server } from '../tests/server'
import { renderApp } from '../tests/utils'

describe('PrivacyPage - the policy is public and complete', () => {
  it('shows the policy and its version to an anonymous visitor without any API request', async () => {
    const requests = vi.fn()
    server.events.on('request:start', requests)
    const { container } = renderApp({ route: '/privacy' })

    expect(
      await screen.findByRole('heading', { level: 1, name: strings.privacy.title }),
    ).toBeVisible()
    expect(screen.getByText(strings.privacy.versionLabel(PRIVACY_POLICY_VERSION))).toBeVisible()
    expect(requests).not.toHaveBeenCalled()
    await expectNoSeriousA11yViolations(container)
    server.events.removeListener('request:start', requests)
  })

  it('names Gemini as processor and lists what is sent to it', async () => {
    renderApp({ route: '/privacy' })

    const processor = (
      await screen.findByRole('heading', { name: strings.privacy.sections.processor.heading })
    ).closest('section') as HTMLElement
    expect(within(processor).getAllByText(/Gemini/).length).toBeGreaterThan(0)
    for (const item of strings.privacy.sections.processor.items) {
      expect(within(processor).getByText(item)).toBeVisible()
    }
  })

  it('describes deleting one conversation and deleting all of them', async () => {
    renderApp({ route: '/privacy' })

    const deletion = (
      await screen.findByRole('heading', { name: strings.privacy.sections.deletion.heading })
    ).closest('section') as HTMLElement
    for (const item of strings.privacy.sections.deletion.items) {
      expect(within(deletion).getByText(item)).toBeVisible()
    }
  })

  it('says honestly what is not self-service yet', async () => {
    renderApp({ route: '/privacy' })

    const section = (
      await screen.findByRole('heading', { name: strings.privacy.sections.notSelfService.heading })
    ).closest('section') as HTMLElement
    for (const item of strings.privacy.sections.notSelfService.items) {
      expect(within(section).getByText(item)).toBeVisible()
    }
  })

  it.each([
    ['a student without consent', unconsentedStudent],
    ['a student with consent', studentUser],
    ['a teacher', teacherUser],
  ])('is readable by %s and is never replaced by the consent screen', async (_label, user) => {
    server.use(handlers.me(user), handlers.subjects([]))
    const { currentLocation } = renderApp({ route: '/privacy', session: { user } })

    expect(
      await screen.findByRole('heading', { level: 1, name: strings.privacy.title }),
    ).toBeVisible()
    expect(currentLocation()).toBe('/privacy')
  })
})

describe('Links to the policy', () => {
  it('the registration screen links to /privacy', async () => {
    renderApp({ route: '/register' })

    const link = await screen.findByRole('link', { name: strings.auth.register.privacyLink })
    expect(link).toHaveAttribute('href', '/privacy')
  })
})

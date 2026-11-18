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

describe('PrivacyPage - adapted to Ley 25.326 (Argentina)', () => {
  async function sectionText(heading: string): Promise<string> {
    renderApp({ route: '/privacy' })
    const section = (await screen.findByRole('heading', { name: heading })).closest(
      'section',
    ) as HTMLElement
    return section.textContent ?? ''
  }

  it('states that the service is only for people over 18', async () => {
    const text = await sectionText(strings.privacy.sections.audience.heading)
    expect(text).toMatch(/exclusivamente a personas mayores de 18 años/)
    expect(text).toMatch(/Los estudiantes lo declaran al aceptar esta política/)
  })

  it('says which data is needed and what refusing the policy means', async () => {
    const text = await sectionText(strings.privacy.sections.mandatory.heading)
    expect(text).toMatch(/nombre, correo electrónico y contraseña/)
    expect(text).toMatch(/Aceptar esta política es necesario para usar el asistente/)
  })

  it('discloses that Gemini may process the data outside Argentina and does not assert a processor role', async () => {
    const text = await sectionText(strings.privacy.sections.processor.heading)
    expect(text).toMatch(/fuera de la República Argentina/)
    expect(text).toMatch(/Estados Unidos/)
    expect(text).toMatch(/lista de la Disposición 60-E\/2016/)
    expect(text).not.toMatch(/encargado/i)
  })

  it('lists the rights of Ley 25.326 with their legal deadlines and the revocation', async () => {
    const text = await sectionText(strings.privacy.sections.rights.heading)
    expect(text).toMatch(/La Ley 25\.326 y su decreto reglamentario reconocen/)
    expect(text).toMatch(/10 días corridos/)
    expect(text).toMatch(/5 días hábiles/)
    expect(text).toMatch(/retirar en cualquier momento el consentimiento/i)
    expect(text).toMatch(/sin efectos retroactivos/)
    expect(text).toMatch(/hábeas data \(arts\. 14, 16 y 33 y siguientes\)/)
    expect(text).toMatch(/autoridad de control/)
    expect(text).not.toMatch(/AAIP|Agencia de Acceso/)
  })

  it('does not present GDPR-only rights as rights of the law', async () => {
    const text = await sectionText(strings.privacy.sections.rights.heading)
    expect(text).not.toMatch(/portabilidad|limitación del tratamiento/i)
  })

  it('never asserts a processor role, an approval or a legal conformity anywhere in the policy', () => {
    const everything = JSON.stringify(strings.privacy)
    expect(everything).not.toMatch(/encargado del tratamiento/i)
    expect(everything).not.toMatch(/aprobad[ao]|cumple con|legalmente/i)
  })

  it('makes the 18-year declaration part of the consent tick box', () => {
    expect(strings.consent.checkbox(PRIVACY_POLICY_VERSION)).toMatch(/mayor de 18 años/)
  })
})

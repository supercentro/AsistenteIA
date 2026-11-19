import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { ConfirmPanel } from './ConfirmPanel'

function setup(overrides: Partial<Parameters<typeof ConfirmPanel>[0]> = {}) {
  const onConfirm = vi.fn()
  const view = render(
    <ConfirmPanel
      id="row-1"
      triggerLabel="Quitar a ana@example.com"
      question="¿Quitar a ana@example.com?"
      body="No se borra nada."
      confirmLabel="Confirmar"
      workingLabel="Quitando…"
      cancelLabel="Cancelar"
      pending={false}
      busy={false}
      onConfirm={onConfirm}
      {...overrides}
    />,
  )
  return { onConfirm, user: userEvent.setup(), ...view }
}

describe('ConfirmPanel - the inline confirmation shared by the lists', () => {
  it('shows only the trigger until it is activated, then the question and the body', async () => {
    const { user, container } = setup()
    expect(screen.queryByRole('group')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Quitar a ana@example.com' }))

    const panel = screen.getByRole('group', { name: '¿Quitar a ana@example.com?' })
    expect(panel).toHaveTextContent('No se borra nada.')
    expect(screen.queryByRole('button', { name: 'Quitar a ana@example.com' })).toBeNull()
    await expectNoSeriousA11yViolations(container)
  })

  it('lets a long label wrap instead of widening the page', () => {
    setup({ triggerLabel: `Quitar a ${'a'.repeat(120)}@example.com` })

    const trigger = screen.getByRole('button')
    expect(trigger.className).toContain('max-w-full')
    expect(trigger.className).toContain('[overflow-wrap:anywhere]')
  })

  it('moves the focus into the panel', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'Quitar a ana@example.com' }))

    const panel = screen.getByRole('group', { name: '¿Quitar a ana@example.com?' })
    await waitFor(() => expect(panel).toHaveFocus())
  })

  it('cancelling calls nothing and returns the focus to the trigger', async () => {
    const { user, onConfirm } = setup()
    await user.click(screen.getByRole('button', { name: 'Quitar a ana@example.com' }))

    await user.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(onConfirm).not.toHaveBeenCalled()
    const trigger = screen.getByRole('button', { name: 'Quitar a ana@example.com' })
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('confirming calls once', async () => {
    const { user, onConfirm } = setup()
    await user.click(screen.getByRole('button', { name: 'Quitar a ana@example.com' }))

    await user.click(screen.getByRole('button', { name: 'Confirmar' }))

    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('shows the working label and disables both controls while its own action is pending', async () => {
    const { user } = setup({ pending: true, busy: true })
    await user.click(screen.getByRole('button', { name: 'Quitar a ana@example.com' }))

    expect(screen.getByRole('button', { name: 'Quitando…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeDisabled()
  })

  it('disables the confirm control while another action is in flight', async () => {
    const { user } = setup({ busy: true })
    await user.click(screen.getByRole('button', { name: 'Quitar a ana@example.com' }))

    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeEnabled()
  })
})

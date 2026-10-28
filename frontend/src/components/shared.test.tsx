import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { strings } from '../lib/strings.es'
import { expectNoSeriousA11yViolations } from '../tests/a11y'
import { Alert } from './Alert'
import { Button } from './Button'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'
import { FormField } from './FormField'
import { LoadingState } from './LoadingState'

describe('LoadingState', () => {
  it('announces the wait politely', async () => {
    const { container } = render(<LoadingState label={strings.subjects.loading} />)

    const status = screen.getByRole('status')
    expect(status).toHaveTextContent(strings.subjects.loading)
    expect(status).toHaveAttribute('aria-live', 'polite')
    await expectNoSeriousA11yViolations(container)
  })
})

describe('ErrorState', () => {
  it('announces the error and retries on demand', async () => {
    const onRetry = vi.fn()
    const { container } = render(<ErrorState message="No se pudo cargar" onRetry={onRetry} />)

    expect(screen.getByRole('alert')).toHaveTextContent('No se pudo cargar')
    await userEvent.click(screen.getByRole('button', { name: strings.states.retry }))
    expect(onRetry).toHaveBeenCalledTimes(1)
    await expectNoSeriousA11yViolations(container)
  })
})

describe('EmptyState', () => {
  it('shows the message without an alert role', async () => {
    const { container } = render(<EmptyState message="Nada por aquí" />)

    expect(screen.getByText('Nada por aquí')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await expectNoSeriousA11yViolations(container)
  })
})

describe('Alert', () => {
  it('uses the alert role for errors and the status role for information and success', () => {
    const { rerender } = render(<Alert variant="error">Falló</Alert>)
    expect(screen.getByRole('alert')).toHaveTextContent('Falló')

    rerender(<Alert variant="success">Listo</Alert>)
    expect(screen.getByRole('status')).toHaveTextContent('Listo')

    rerender(<Alert variant="info">Aviso</Alert>)
    expect(screen.getByRole('status')).toHaveTextContent('Aviso')
  })

  it('renders its content as text, never as markup', () => {
    render(<Alert variant="error">{'<img src=x onerror=alert(1)>'}</Alert>)

    expect(screen.getByRole('alert')).toHaveTextContent('<img src=x onerror=alert(1)>')
    expect(document.querySelector('img')).toBeNull()
  })
})

describe('Button', () => {
  it('is disabled and busy while pending, so it cannot be activated twice', async () => {
    const onClick = vi.fn()
    render(
      <Button pending onClick={onClick}>
        Enviar
      </Button>,
    )

    const button = screen.getByRole('button', { name: 'Enviar' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('calls the handler when enabled', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Enviar</Button>)

    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('defaults to a button that does not submit forms unless told so', () => {
    render(<Button>Uno</Button>)
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button')
  })
})

describe('FormField', () => {
  it('gives the input an accessible name from its visible label', async () => {
    const { container } = render(<FormField name="email" label="Correo" type="email" />)

    expect(screen.getByLabelText('Correo')).toHaveAttribute('type', 'email')
    await expectNoSeriousA11yViolations(container)
  })

  it('ties the hint and the error to the input and marks it invalid', async () => {
    const { container } = render(
      <FormField
        name="password"
        label="Clave"
        type="password"
        hint="Entre 10 y 128"
        error="Muy corta"
      />,
    )

    const input = screen.getByLabelText('Clave')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAccessibleDescription('Entre 10 y 128 Muy corta')
    expect(screen.getByRole('alert')).toHaveTextContent('Muy corta')
    await expectNoSeriousA11yViolations(container)
  })

  it('is not marked invalid without an error', () => {
    render(<FormField name="name" label="Nombre" />)
    expect(screen.getByLabelText('Nombre')).not.toHaveAttribute('aria-invalid', 'true')
  })
})

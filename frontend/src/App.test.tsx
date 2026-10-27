import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'
import { strings } from './lib/strings.es'
import { renderWithProviders } from './tests/utils'

describe('App', () => {
  it('renders the home page heading from the UI strings module at "/"', () => {
    renderWithProviders(<App />, { route: '/' })

    expect(screen.getByRole('heading', { level: 1, name: strings.home.title })).toBeInTheDocument()
    expect(screen.getByText(strings.home.subtitle)).toBeInTheDocument()
  })

  it('renders a not-found message for unknown routes', () => {
    renderWithProviders(<App />, { route: '/does-not-exist' })

    expect(screen.getByRole('heading', { name: strings.notFound.title })).toBeInTheDocument()
  })
})

import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useLocation } from 'react-router-dom'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { FormField } from '../components/FormField'
import { LoginIncompleteError, useLogin } from '../hooks/useLogin'
import { ApiError, messageFor } from '../lib/apiError'
import { loginSchema, type LoginValues } from '../lib/schemas'
import { clearNotice, peekNotice, type EndReason } from '../lib/session'
import { strings } from '../lib/strings.es'

const SESSION_NOTICES: Record<EndReason, string> = {
  expired: strings.auth.notices.expired,
  unauthorized: strings.auth.notices.unauthorized,
  'signed-out': strings.auth.notices.signedOut,
  'login-failed': strings.auth.notices.loginFailed,
}

function loginErrorMessage(error: Error): string {
  if (error instanceof LoginIncompleteError) {
    return strings.auth.errors.loginIncomplete
  }
  if (error instanceof ApiError) {
    // A 401 here always means bad credentials: the endpoint is public.
    return error.status === 401 ? strings.auth.errors.invalidCredentials : messageFor(error)
  }
  return strings.errors.unknown
}

export default function LoginPage() {
  const location = useLocation()
  const [notice] = useState<string | null>(() => {
    if ((location.state as { registered?: unknown } | null)?.registered === true) {
      return strings.auth.notices.registered
    }
    const reason = peekNotice()
    return reason ? SESSION_NOTICES[reason] : null
  })
  useEffect(() => {
    clearNotice()
  }, [])

  const login = useLogin()
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })

  const onSubmit = handleSubmit((values) => {
    if (!login.isPending) {
      login.mutate(values)
    }
  })

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-4 py-8">
      <h1 className="text-2xl font-bold text-slate-900">{strings.auth.login.title}</h1>
      {notice ? (
        <Alert variant={notice === strings.auth.notices.registered ? 'success' : 'info'}>
          {notice}
        </Alert>
      ) : null}
      {login.error ? <Alert variant="error">{loginErrorMessage(login.error)}</Alert> : null}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <FormField
          label={strings.auth.login.email}
          type="email"
          autoComplete="username"
          error={errors.email?.message}
          {...register('email')}
        />
        <FormField
          label={strings.auth.login.password}
          type="password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register('password')}
        />
        <Button type="submit" pending={login.isPending}>
          {login.isPending ? strings.auth.login.submitting : strings.auth.login.submit}
        </Button>
      </form>
      <Link className="text-sm text-slate-900 underline" to="/register">
        {strings.auth.login.createAccount}
      </Link>
    </main>
  )
}

import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { FormField } from '../components/FormField'
import { useRegister } from '../hooks/useRegister'
import { ApiError, messageFor } from '../lib/apiError'
import { registerSchema, type RegisterValues } from '../lib/schemas'
import { strings } from '../lib/strings.es'

function registerErrorMessage(error: Error): string {
  if (error instanceof ApiError) {
    return messageFor(error, { CONFLICT: strings.auth.errors.emailTaken })
  }
  return strings.errors.unknown
}

export default function RegisterPage() {
  const navigate = useNavigate()
  const registration = useRegister()
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) })

  const onSubmit = handleSubmit((values) => {
    if (registration.isPending) {
      return
    }
    // Only these three fields are ever sent: the role is decided by the server.
    registration.mutate(
      { name: values.name, email: values.email, password: values.password },
      { onSuccess: () => navigate('/login', { replace: true, state: { registered: true } }) },
    )
  })

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-4 py-8">
      <h1 className="text-2xl font-bold text-slate-900">{strings.auth.register.title}</h1>
      {registration.error ? (
        <Alert variant="error">{registerErrorMessage(registration.error)}</Alert>
      ) : null}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <FormField
          label={strings.auth.register.name}
          autoComplete="name"
          error={errors.name?.message}
          {...register('name')}
        />
        <FormField
          label={strings.auth.register.email}
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register('email')}
        />
        <FormField
          label={strings.auth.register.password}
          type="password"
          autoComplete="new-password"
          hint={strings.auth.register.passwordHint}
          error={errors.password?.message}
          {...register('password')}
        />
        <Button type="submit" pending={registration.isPending}>
          {registration.isPending ? strings.auth.register.submitting : strings.auth.register.submit}
        </Button>
      </form>
      <Link className="text-sm text-slate-900 underline" to="/privacy">
        {strings.auth.register.privacyLink}
      </Link>
      <Link className="text-sm text-slate-900 underline" to="/login">
        {strings.auth.register.haveAccount}
      </Link>
    </main>
  )
}

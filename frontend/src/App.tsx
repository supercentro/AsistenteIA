import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { LoadingState } from './components/LoadingState'
import { DEFAULT_HOME, RedirectIfAuthenticated } from './components/RedirectIfAuthenticated'
import { RequireAuth } from './components/RequireAuth'
import { RequireRole } from './components/RequireRole'
import { strings } from './lib/strings.es'

// Each area is its own chunk: a visitor does not download screens they cannot open.
const LoginPage = lazy(() => import('./pages/LoginPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))
const SubjectsPage = lazy(() => import('./pages/SubjectsPage'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))

export default function App() {
  return (
    <Suspense fallback={<LoadingState label={strings.states.loading} />}>
      <Routes>
        <Route element={<RedirectIfAuthenticated />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>
        <Route element={<RequireAuth />}>
          <Route path="/" element={<Navigate to={DEFAULT_HOME} replace />} />
          <Route element={<AppShell />}>
            <Route element={<RequireRole roles={['student', 'teacher']} />}>
              <Route path="/subjects" element={<SubjectsPage />} />
            </Route>
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  )
}

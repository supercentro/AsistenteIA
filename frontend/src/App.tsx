import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { LoadingState } from './components/LoadingState'
import { DEFAULT_HOME, RedirectIfAuthenticated } from './components/RedirectIfAuthenticated'
import { RequireAuth } from './components/RequireAuth'
import { RequireConsent } from './components/RequireConsent'
import { RequireRole } from './components/RequireRole'
import { teacherActivityEnabled, teacherTopicsEnabled } from './lib/features'
import { strings } from './lib/strings.es'

// Each area is its own chunk: a visitor does not download screens they cannot open.
const LoginPage = lazy(() => import('./pages/LoginPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))
const PrivacyPage = lazy(() => import('./pages/PrivacyPage'))
const ConsentPage = lazy(() => import('./pages/ConsentPage'))
const SubjectsPage = lazy(() => import('./pages/SubjectsPage'))
const TeacherSubjectPage = lazy(() => import('./pages/TeacherSubjectPage'))
const TeacherActivityPage = lazy(() => import('./pages/TeacherActivityPage'))
const TeacherTopicsPage = lazy(() => import('./pages/TeacherTopicsPage'))
const DocumentTopicsPage = lazy(() => import('./pages/DocumentTopicsPage'))
const ChatPage = lazy(() => import('./pages/ChatPage'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))

export default function App() {
  return (
    <Suspense fallback={<LoadingState label={strings.states.loading} />}>
      <Routes>
        <Route element={<RedirectIfAuthenticated />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<Navigate to={DEFAULT_HOME} replace />} />
          <Route path="/consent" element={<ConsentPage />} />
          <Route element={<RequireConsent />}>
            <Route element={<AppShell />}>
              <Route element={<RequireRole roles={['student', 'teacher']} />}>
                <Route path="/subjects" element={<SubjectsPage />} />
              </Route>
              <Route element={<RequireRole roles={['teacher']} />}>
                <Route path="/subjects/:subjectId" element={<TeacherSubjectPage />} />
                {teacherActivityEnabled() ? (
                  <Route path="/subjects/:subjectId/activity" element={<TeacherActivityPage />} />
                ) : null}
                {teacherTopicsEnabled() ? (
                  <>
                    <Route
                      path="/subjects/:subjectId/activity/topics"
                      element={<TeacherTopicsPage />}
                    />
                    <Route
                      path="/subjects/:subjectId/documents/:documentId/topics"
                      element={<DocumentTopicsPage />}
                    />
                  </>
                ) : null}
              </Route>
              <Route element={<RequireRole roles={['student']} />}>
                <Route path="/subjects/:subjectId/chat" element={<ChatPage />} />
              </Route>
            </Route>
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  )
}

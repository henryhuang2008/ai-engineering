import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from '@/lib/auth-context'
import {
  ConversationPage,
  ConversationWelcome,
  ConversationsLayout,
} from '@/pages/conversations'
import { LoginPage } from '@/pages/login'

function ProtectedHome() {
  const { session, isLoading, error } = useAuth()

  if (isLoading) {
    return (
      <main className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        Loading your session...
      </main>
    )
  }
  if (error && !session) {
    return (
      <main className="flex min-h-svh items-center justify-center px-4 text-sm text-destructive">
        {error}
      </main>
    )
  }
  if (!session) {
    return <Navigate to="/login" replace />
  }
  return (
    <Routes>
      <Route path="/chat" element={<ConversationsLayout />}>
        <Route index element={<ConversationWelcome />} />
        <Route path=":threadId" element={<ConversationPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/*" element={<ProtectedHome />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App

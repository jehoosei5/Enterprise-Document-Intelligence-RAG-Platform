import { Navigate, Route, Routes } from 'react-router-dom'

import RequireAuth from './components/RequireAuth'
import DocumentsPage from './pages/DocumentsPage'
import LoginPage from './pages/LoginPage'
import UploadPage from './pages/UploadPage'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/documents/upload" element={<UploadPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/documents" replace />} />
    </Routes>
  )
}

export default App

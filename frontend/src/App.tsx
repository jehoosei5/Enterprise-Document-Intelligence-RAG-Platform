import { Navigate, Route, Routes } from 'react-router-dom'

import RequireAuth from './components/RequireAuth'
import DocumentsPage from './pages/DocumentsPage'
import DocumentViewerPage from './pages/DocumentViewerPage'
import LoginPage from './pages/LoginPage'
import UploadPage from './pages/UploadPage'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/documents/upload" element={<UploadPage />} />
        <Route path="/documents/:id" element={<DocumentViewerPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/documents" replace />} />
    </Routes>
  )
}

export default App

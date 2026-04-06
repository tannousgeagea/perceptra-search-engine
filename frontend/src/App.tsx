import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { AlertProvider } from './context/AlertContext'
import { CompareProvider } from './context/CompareContext'
import CompareTray from './components/CompareTray'
import AppLayout from './components/Layout/AppLayout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Search from './pages/Search'
import MediaLibrary from './pages/MediaLibrary'
import Upload from './pages/Upload'
import Analytics from './pages/Analytics'
import Settings from './pages/Settings'
import HazardConfig from './pages/HazardConfig'
import Alerts from './pages/Alerts'
import Reports from './pages/Reports'
import Compare from './pages/Compare'
import Checklists from './pages/Checklists'
import ImageDetail from './pages/ImageDetail'
import VideoDetail from './pages/VideoDetail'
import DetectionDetail from './pages/DetectionDetail'
import WasteVisionPage from './pages/WasteVision'
import type { ReactNode } from 'react'

function AuthGuard({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <AuthGuard>
            <AppLayout />
          </AuthGuard>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/checklists" element={<Checklists />} />
        <Route path="/search" element={<Search />} />
        <Route path="/media" element={<MediaLibrary />} />
        <Route path="/media/images/:id" element={<ImageDetail />} />
        <Route path="/media/videos/:id" element={<VideoDetail />} />
        <Route path="/media/detections/:id" element={<DetectionDetail />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/hazard-config" element={<HazardConfig />} />
        <Route path="/wastevision" element={<WasteVisionPage />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AlertProvider>
          <CompareProvider>
            <BrowserRouter>
              <AppRoutes />
              <CompareTray />
            </BrowserRouter>
          </CompareProvider>
        </AlertProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}

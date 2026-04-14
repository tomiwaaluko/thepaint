import { StrictMode, lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'

const App = lazy(() => import('./App'))
const LandingPage = lazy(() => import('./pages/LandingPage'))

function LoadingFallback() {
  return (
    <div className="min-h-screen bg-navy-900 flex items-center justify-center">
      <span className="text-xl font-black text-chalk-orange">CHALK</span>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Suspense fallback={<LoadingFallback />}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/dashboard" element={<App />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  </StrictMode>,
)

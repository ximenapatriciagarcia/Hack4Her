import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { Toaster } from 'sileo'
import 'sileo/styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <Toaster position="bottom-right" options={{ roundness: 12, fill: '#0f0f0f', duration: 5000 }} />
  </StrictMode>,
)

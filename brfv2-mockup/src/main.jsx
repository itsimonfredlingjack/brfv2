import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// First, and deliberately: the token layer every other stylesheet resolves its
// variables against. Component stylesheets are imported by the components
// themselves and therefore reach the bundle before App.css — a foundation
// imported anywhere else would be a foundation half the product cannot see.
import './theme.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

const { getDefaultConfig } = require('expo/metro-config')
const http = require('http')

const config = getDefaultConfig(__dirname)

/* Dev-only: proxies /api to the backend so `expo start --web` can reach it
 * same-origin, mirroring xs_mobilapp's vite.config.ts proxy. The shipped
 * Android app talks to the backend directly over native HTTP (no CORS
 * concept there at all) — this exists purely for the web preview target
 * used during development/verification. */
const BACKEND_URL = process.env.KALLA_DEV_BACKEND_URL

if (BACKEND_URL) {
  const target = new URL(BACKEND_URL)
  config.server = {
    ...config.server,
    enhanceMiddleware: (middleware) => (req, res, next) => {
      if (req.url.startsWith('/api')) {
        const proxyReq = http.request(
          { host: target.hostname, port: target.port, path: req.url, method: req.method, headers: req.headers },
          (proxyRes) => {
            res.writeHead(proxyRes.statusCode, proxyRes.headers)
            proxyRes.pipe(res)
          },
        )
        req.pipe(proxyReq)
        proxyReq.on('error', (err) => {
          res.writeHead(502)
          res.end(String(err))
        })
        return
      }
      return middleware(req, res, next)
    },
  }
}

module.exports = config

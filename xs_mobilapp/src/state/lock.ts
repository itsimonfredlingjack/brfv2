/* An optional device lock over an already-valid session.
 *
 * IMPORTANT: this is a LOCAL UI LOCK, not authentication. It does not
 * re-authenticate to the backend and it is not a server-side boundary — the
 * session cookie stays valid the whole time. Its job is narrower and real:
 * the answer journal holds verbatim text from the förening's documents, and
 * a handed-over or borrowed phone should not open straight into it.
 */

const PIN_KEY = 'kalla.pinHash'
const SALT_KEY = 'kalla.pinSalt'
const LOCK_AFTER_MS = 5 * 60 * 1000

/** WebCrypto needs a secure context. Over plain http on a LAN address it is
 * absent, and a PIN we cannot hash is a PIN we will not pretend to offer. */
export function lockAvailable(): boolean {
  return typeof crypto !== 'undefined' && typeof crypto.subtle?.digest === 'function'
}

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // Storage unavailable — the lock simply stays off.
  }
}

function salt(): string {
  let value = read(SALT_KEY)
  if (!value) {
    const bytes = new Uint8Array(16)
    crypto.getRandomValues(bytes)
    value = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
    write(SALT_KEY, value)
  }
  return value
}

async function hash(pin: string): Promise<string> {
  const data = new TextEncoder().encode(`${salt()}:${pin}`)
  const digest = await crypto.subtle.digest('SHA-256', data)
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
}

export function hasPin(): boolean {
  return lockAvailable() && read(PIN_KEY) !== null
}

export async function setPin(pin: string): Promise<void> {
  write(PIN_KEY, await hash(pin))
}

export function clearPin(): void {
  write(PIN_KEY, null)
  write(SALT_KEY, null)
}

export async function verifyPin(pin: string): Promise<boolean> {
  const stored = read(PIN_KEY)
  if (!stored) return true
  return (await hash(pin)) === stored
}

/** Whether a return to the app after `hiddenSince` should re-lock. */
export function shouldLock(hiddenSince: number | null, now: number = Date.now()): boolean {
  if (!hasPin()) return false
  if (hiddenSince === null) return false
  return now - hiddenSince >= LOCK_AFTER_MS
}

export const LOCK_AFTER_MINUTES = LOCK_AFTER_MS / 60_000

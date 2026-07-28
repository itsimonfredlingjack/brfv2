"""Minimal real auth: SQLite-backed users, tenants, memberships, sessions.

Passwords: stdlib scrypt with a per-user salt, constant-time comparison.
Sessions: opaque 256-bit tokens; only their SHA-256 lands in the database, so
a DB leak leaks no usable tokens. Tokens travel as an HttpOnly cookie or an
Authorization: Bearer header. Membership roles are exactly 'member' and
'admin' — no SSO, no org hierarchies, no permission matrices (SPEC-PILOT §3).

Separate from membership, an account may hold *installation-administrator*
authority. That is not a role inside a BRF: it governs settings that belong to
the installed machine rather than to any one association, and the desktop
adapter is what grants and requires it.

Framework-free by design: FastAPI glue lives in main.py.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BRF_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 64}
_DUMMY_SALT = b"brf-dummy-salt--"  # equalizes timing for unknown emails

# Login throttle: after MAX_FAILURES failed attempts for one email within
# WINDOW_S, further attempts are refused for WINDOW_S. In-memory: a restart
# clears it, which is acceptable at pilot scale.
MAX_FAILURES = 10
WINDOW_S = 15 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthError(ValueError):
    pass


class AuthStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._throttle_lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id TEXT PRIMARY KEY,
                  email TEXT UNIQUE NOT NULL,
                  name TEXT NOT NULL DEFAULT '',
                  password_hash BLOB NOT NULL,
                  salt BLOB NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tenants (
                  brf_id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memberships (
                  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  brf_id TEXT NOT NULL REFERENCES tenants(brf_id) ON DELETE CASCADE,
                  role TEXT NOT NULL CHECK (role IN ('member', 'admin')),
                  PRIMARY KEY (user_id, brf_id)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                  token_hash TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  created_at TEXT NOT NULL,
                  expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS installation_admins (
                  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                  granted_at TEXT NOT NULL
                );
                """
            )

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ---------- users ----------

    def create_user(self, email: str, password: str, name: str = "") -> str:
        email = email.strip().lower()
        if "@" not in email or len(email) < 5:
            raise AuthError("Ogiltig e-postadress.")
        if len(password) < 8:
            raise AuthError("Lösenordet måste vara minst 8 tecken.")
        user_id = uuid.uuid4().hex[:12]
        salt = secrets.token_bytes(16)
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO users (id, email, name, password_hash, salt, created_at) VALUES (?,?,?,?,?,?)",
                    (user_id, email, name, _hash_password(password, salt), salt, _now().isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise AuthError("E-postadressen är redan registrerad.") from exc
        return user_id

    def _throttled(self, email: str) -> bool:
        now = time.monotonic()
        with self._throttle_lock:
            attempts = [t for t in self._failures.get(email, []) if now - t < WINDOW_S]
            self._failures[email] = attempts
            return len(attempts) >= MAX_FAILURES

    def _record_failure(self, email: str) -> None:
        with self._throttle_lock:
            self._failures.setdefault(email, []).append(time.monotonic())

    def verify_login(self, email: str, password: str) -> str | None:
        """Returns user_id on success, None on bad credentials.
        Raises AuthError when the account is throttled."""
        email = email.strip().lower()
        if self._throttled(email):
            raise AuthError("För många misslyckade försök — vänta 15 minuter.")
        with self._conn() as conn:
            row = conn.execute("SELECT id, password_hash, salt FROM users WHERE email = ?", (email,)).fetchone()
        if row is None:
            _hash_password(password, _DUMMY_SALT)  # constant-ish time for unknown emails
            self._record_failure(email)
            return None
        if hmac.compare_digest(_hash_password(password, row["salt"]), row["password_hash"]):
            with self._throttle_lock:
                self._failures.pop(email, None)
            return row["id"]
        self._record_failure(email)
        return None

    def get_user(self, user_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT id, email, name FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str) -> dict | None:
        email = email.strip().lower()
        with self._conn() as conn:
            row = conn.execute("SELECT id, email, name FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

    # ---------- installation administrators ----------
    #
    # A membership role answers "what may this account do inside one BRF".
    # It deliberately does not answer "what may this account change about the
    # installation itself" — the model service every association's documents
    # are sent to is one setting for the whole machine, so it needs an
    # authority that is not handed out with an ordinary account.  This is that
    # authority: granted once, at first-run provisioning, to the account that
    # set the installation up.

    def grant_installation_admin(self, user_id: str) -> None:
        if self.get_user(user_id) is None:
            raise AuthError("Okänt konto.")
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO installation_admins (user_id, granted_at) VALUES (?,?)",
                (user_id, _now().isoformat()),
            )

    def revoke_installation_admin(self, user_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM installation_admins WHERE user_id = ?", (user_id,))
        return cur.rowcount > 0

    def is_installation_admin(self, user_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM installation_admins WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row is not None

    def list_installation_admins(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT user_id FROM installation_admins ORDER BY granted_at, user_id"
            ).fetchall()
        return [r["user_id"] for r in rows]

    def backfill_installation_admin(self) -> str | None:
        """Adopt an installation provisioned before this authority existed.

        Without it, restoring a backup taken by an older build would leave a
        machine where *nobody* can change the model service.  The account that
        was created first is the one that ran first-run provisioning, so it is
        the one that already held this authority in practice.  Returns the
        adopted user id, or ``None`` when nothing had to be done.
        """

        with self._conn() as conn:
            if conn.execute("SELECT 1 FROM installation_admins LIMIT 1").fetchone():
                return None
            row = conn.execute(
                "SELECT id FROM users ORDER BY created_at, id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "INSERT INTO installation_admins (user_id, granted_at) VALUES (?,?)",
                (row["id"], _now().isoformat()),
            )
        return row["id"]

    # ---------- tenants & memberships ----------

    def create_tenant(self, name: str, brf_id: str | None = None) -> str:
        brf_id = brf_id or uuid.uuid4().hex[:12]
        if not BRF_ID_RE.match(brf_id):
            raise AuthError("Ogiltigt brf_id (tillåtet: a-z, 0-9, bindestreck).")
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO tenants (brf_id, name, created_at) VALUES (?,?,?)",
                    (brf_id, name, _now().isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise AuthError(f"brf_id '{brf_id}' finns redan.") from exc
        return brf_id

    def get_tenant(self, brf_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT brf_id, name, created_at FROM tenants WHERE brf_id = ?", (brf_id,)).fetchone()
        return dict(row) if row else None

    def list_tenants(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT brf_id, name, created_at FROM tenants ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def delete_tenant(self, brf_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM tenants WHERE brf_id = ?", (brf_id,))
        return cur.rowcount > 0  # memberships cascade

    def add_membership(self, user_id: str, brf_id: str, role: str) -> None:
        if role not in ("member", "admin"):
            raise AuthError("Roll måste vara 'member' eller 'admin'.")
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO memberships (user_id, brf_id, role) VALUES (?,?,?)",
                (user_id, brf_id, role),
            )

    def remove_membership(self, user_id: str, brf_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM memberships WHERE user_id = ? AND brf_id = ?", (user_id, brf_id)
            )
        return cur.rowcount > 0

    def role_for(self, user_id: str, brf_id: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT role FROM memberships WHERE user_id = ? AND brf_id = ?", (user_id, brf_id)
            ).fetchone()
        return row["role"] if row else None

    def memberships_for(self, user_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT m.brf_id, t.name, m.role FROM memberships m
                   JOIN tenants t ON t.brf_id = m.brf_id
                   WHERE m.user_id = ? ORDER BY t.name""",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- sessions ----------

    def create_session(self, user_id: str, ttl_hours: float | None = None) -> str:
        ttl = ttl_hours if ttl_hours is not None else float(os.environ.get("BRF_SESSION_TTL_HOURS", "336"))
        token = secrets.token_urlsafe(32)
        now = _now()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                (_token_hash(token), user_id, now.isoformat(), (now + timedelta(hours=ttl)).isoformat()),
            )
        return token

    def resolve_session(self, token: str) -> dict | None:
        """Returns {id, email, name} for a live session, else None."""
        if not token:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """SELECT u.id, u.email, u.name, s.expires_at FROM sessions s
                   JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?""",
                (_token_hash(token),),
            ).fetchone()
            if row is None:
                return None
            if datetime.fromisoformat(row["expires_at"]) < _now():
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
                return None
        return {"id": row["id"], "email": row["email"], "name": row["name"]}

    def delete_session(self, token: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    def delete_expired_sessions(self) -> int:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_now().isoformat(),))
        return cur.rowcount

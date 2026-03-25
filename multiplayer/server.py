#!/usr/bin/env python3
"""Lightweight Endless Sky multiplayer account/session server.

This service is intentionally standalone so it does not alter the existing
single-player client behavior. It can be hosted and used as the foundation
for shared account login and pilot presence.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

DB_PATH = os.environ.get("ES_MMO_DB", "multiplayer.db")
HOST = os.environ.get("ES_MMO_HOST", "0.0.0.0")
PORT = int(os.environ.get("ES_MMO_PORT", "8080"))
TOKEN_TTL_SECONDS = int(os.environ.get("ES_MMO_TOKEN_TTL", "604800"))  # 7 days
SECRET = os.environ.get("ES_MMO_SECRET") or secrets.token_urlsafe(32)


@dataclass
class RequestContext:
    body: dict[str, Any]
    auth_token: str | None


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                """
            )

    @staticmethod
    def _hash_password(password: str, salt: bytes | None = None) -> str:
        if salt is None:
            salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return f"{salt.hex()}:{digest.hex()}"

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        salt_hex, digest_hex = stored_hash.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return hmac.compare_digest(candidate.hex(), digest_hex)

    def register(self, username: str, password: str) -> tuple[bool, str]:
        now = int(time.time())
        with self._lock, self._conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, self._hash_password(password), now),
                )
                return True, "ok"
            except sqlite3.IntegrityError:
                return False, "username already exists"

    def create_session(self, username: str, password: str) -> tuple[bool, str, int | None, str | None]:
        now = int(time.time())
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT id, password_hash FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if row is None or not self._verify_password(password, row["password_hash"]):
                return False, "invalid credentials", None, None

            user_id = int(row["id"])
            token = secrets.token_urlsafe(32)
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user_id, now, now + TOKEN_TTL_SECONDS),
            )
            return True, "ok", user_id, token

    def validate_token(self, token: str) -> tuple[bool, dict[str, Any] | None]:
        now = int(time.time())
        with self._lock, self._conn() as conn:
            row = conn.execute(
                """
                SELECT users.id, users.username, sessions.expires_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()
            if row is None:
                return False, None
            if int(row["expires_at"]) < now:
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                return False, None
            return True, {"user_id": int(row["id"]), "username": row["username"]}


storage = Storage(DB_PATH)


class Handler(BaseHTTPRequestHandler):
    server_version = "EndlessSkyMMOServer/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._send_json(HTTPStatus.OK, {"ok": True, "service": "endless-sky-mmo"})
            return

        if self.path == "/whoami":
            ctx = self._read_context(expect_body=False)
            if not ctx.auth_token:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "missing bearer token"})
                return
            valid, profile = storage.validate_token(ctx.auth_token)
            if not valid:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "invalid or expired token"})
                return
            self._send_json(HTTPStatus.OK, profile)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/register":
            ctx = self._read_context()
            username = str(ctx.body.get("username", "")).strip()
            password = str(ctx.body.get("password", ""))
            if len(username) < 3 or len(password) < 8:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "username must be >= 3 chars and password >= 8 chars"},
                )
                return
            ok, message = storage.register(username, password)
            if not ok:
                self._send_json(HTTPStatus.CONFLICT, {"error": message})
                return
            self._send_json(HTTPStatus.CREATED, {"ok": True})
            return

        if self.path == "/login":
            ctx = self._read_context()
            username = str(ctx.body.get("username", "")).strip()
            password = str(ctx.body.get("password", ""))
            ok, message, user_id, token = storage.create_session(username, password)
            if not ok:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": message})
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "user_id": user_id,
                    "token": token,
                    "expires_in": TOKEN_TTL_SECONDS,
                },
            )
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _read_context(self, expect_body: bool = True) -> RequestContext:
        body: dict[str, Any] = {}
        if expect_body:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})
                raise

        token = None
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()

        return RequestContext(body=body, auth_token=token)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    print(f"Starting Endless Sky MMO server on {HOST}:{PORT}")
    print("Set ES_MMO_SECRET in production for stable token signing.")
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.serve_forever()


if __name__ == "__main__":
    main()

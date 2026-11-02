"""
Notizen-API – kleine Web-API mit Benutzern, Rollen, API-Tokens und Audit-Log.

Start:  pip install -r requirements.txt
        ADMIN_PASSWORD='ein-langes-passwort' uvicorn app:app --reload
Doku:   http://127.0.0.1:8000/docs  (automatisch erzeugte OpenAPI-Oberfläche)
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Iterator

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

# ─── Konfiguration ─────────────────────────────────────────────────────────────
DB_PATH = os.environ.get("NOTES_DB", "notes.db")
LOGIN_TOKEN_HOURS = 8   # Gültigkeit der Tokens aus /auth/login
MAX_TOKEN_DAYS = 90     # Höchstlaufzeit selbst erstellter API-Tokens
TOKEN_PREFIX = "nt_"    # macht geleakte Tokens für Secret-Scanner erkennbar

# Höchstrechte je Rolle. Effektive Rechte eines Requests:
#   Scopes des Tokens  ∩  Scopes der *aktuellen* Rolle des Benutzers
ROLE_SCOPES: dict[str, set[str]] = {
    "viewer": {"read"},
    "editor": {"read", "write"},
    "admin": {"read", "write", "admin"},
}


class Role(str, Enum):
    viewer = "viewer"
    editor = "editor"
    admin = "admin"


class Scope(str, Enum):
    read = "read"
    write = "write"
    admin = "admin"


class Visibility(str, Enum):
    private = "private"  # nur Eigentümer (und Admins)
    team = "team"        # alle mit Leserecht


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('viewer', 'editor', 'admin')),
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS api_tokens (
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    token_hash   TEXT    NOT NULL UNIQUE,   -- nur SHA-256, nie der Klartext
    prefix       TEXT    NOT NULL,          -- erste Zeichen zur Wiedererkennung
    scopes       TEXT    NOT NULL,          -- kommagetrennt, z. B. "read,write"
    expires_at   TEXT    NOT NULL,
    revoked      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL,
    last_used_at TEXT
);
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY,
    owner_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT    NOT NULL,
    body       TEXT    NOT NULL,
    visibility TEXT    NOT NULL CHECK (visibility IN ('private', 'team')),
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_owner ON notes(owner_id);
CREATE TABLE IF NOT EXISTS audit_log (
    id       INTEGER PRIMARY KEY,
    ts       TEXT    NOT NULL,
    actor_id INTEGER,                       -- NULL = System / unbekannt
    action   TEXT    NOT NULL,
    target   TEXT,
    ip       TEXT,
    detail   TEXT    NOT NULL DEFAULT '{}'
);
"""


# ─── Hilfsfunktionen ───────────────────────────────────────────────────────────
def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(digest.hex(), digest_hex)


# Wird geprüft, wenn der Benutzername nicht existiert, damit die Antwortzeit
# nicht verrät, ob es ein Konto gibt.
DUMMY_HASH = hash_password(secrets.token_hex(16))


def hash_token(token: str) -> str:
    # Tokens haben 256 Bit Zufall, daher genügt ein schneller Hash.
    return hashlib.sha256(token.encode()).hexdigest()


def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def write_audit(db: sqlite3.Connection, actor_id: int | None, action: str,
                target: str | None, ip: str | None, detail: dict | None = None) -> None:
    db.execute(
        "INSERT INTO audit_log (ts, actor_id, action, target, ip, detail) VALUES (?, ?, ?, ?, ?, ?)",
        (iso(now()), actor_id, action, target, ip, json.dumps(detail or {}, ensure_ascii=False)),
    )


# ─── Datenbank ─────────────────────────────────────────────────────────────────
def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()  # nicht committete Änderungen werden verworfen


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(16)
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
                ("admin", hash_password(password), iso(now())),
            )
            write_audit(conn, None, "user.bootstrap", "user:admin", None)
            if not os.environ.get("ADMIN_PASSWORD"):
                print(f"[bootstrap] Konto 'admin' angelegt, Passwort: {password}")
        conn.commit()
    finally:
        conn.close()


# ─── Authentifizierung und Autorisierung ──────────────────────────────────────
class Principal(BaseModel):
    """Wer ruft auf, mit welchem Token und welchen effektiven Rechten."""
    user_id: int
    username: str
    role: Role
    token_id: int
    scopes: set[str]


bearer = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungültiges oder abgelaufenes Token",
                         headers={"WWW-Authenticate": "Bearer"})


def get_principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> Principal:
    if creds is None:
        raise unauthorized()
    row = db.execute(
        """SELECT t.id AS token_id, t.scopes, t.expires_at, t.revoked,
                  u.id AS user_id, u.username, u.role, u.active
           FROM api_tokens t JOIN users u ON u.id = t.user_id
           WHERE t.token_hash = ?""",
        (hash_token(creds.credentials),),
    ).fetchone()
    if (row is None or row["revoked"] or not row["active"]
            or datetime.fromisoformat(row["expires_at"]) <= now()):
        raise unauthorized()
    db.execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (iso(now()), row["token_id"]))
    db.commit()
    return Principal(
        user_id=row["user_id"], username=row["username"], role=row["role"], token_id=row["token_id"],
        scopes=set(row["scopes"].split(",")) & ROLE_SCOPES[row["role"]],
    )


def require(scope: str):
    def checker(p: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if scope not in p.scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Scope '{scope}' erforderlich")
        return p
    return checker


def is_admin(p: Principal) -> bool:
    return "admin" in p.scopes


DB = Annotated[sqlite3.Connection, Depends(get_db)]
Authenticated = Annotated[Principal, Depends(get_principal)]
Reader = Annotated[Principal, Depends(require("read"))]
Writer = Annotated[Principal, Depends(require("write"))]
Admin = Annotated[Principal, Depends(require("admin"))]


# ─── Schemas (Ein- und Ausgabe) ────────────────────────────────────────────────
class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    scopes: list[str]


class MeOut(BaseModel):
    id: int
    username: str
    role: Role
    token_id: int
    scopes: list[str]


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=10_000)
    visibility: Visibility = Visibility.private


class NoteOut(BaseModel):
    id: int
    owner_id: int
    owner: str
    title: str
    body: str
    visibility: Visibility
    created_at: str
    updated_at: str


class ApiTokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    scopes: list[Scope] = Field(min_length=1)
    valid_days: int = Field(default=30, ge=1, le=MAX_TOKEN_DAYS)


class ApiTokenInfo(BaseModel):
    id: int
    user_id: int
    name: str
    prefix: str
    scopes: list[str]
    expires_at: str
    revoked: bool
    created_at: str
    last_used_at: str | None


class ApiTokenCreated(ApiTokenInfo):
    token: str = Field(description="Klartext – wird nur bei der Erstellung ein einziges Mal ausgegeben")


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)
    role: Role = Role.viewer


class UserUpdate(BaseModel):
    role: Role | None = None
    active: bool | None = None


class UserOut(BaseModel):
    id: int
    username: str
    role: Role
    active: bool
    created_at: str


class AuditEntry(BaseModel):
    id: int
    ts: str
    actor_id: int | None
    action: str
    target: str | None
    ip: str | None
    detail: dict


def issue_token(db: sqlite3.Connection, user_id: int, name: str,
                scopes: set[str], lifetime: timedelta) -> tuple[str, sqlite3.Row]:
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    created = now()
    cur = db.execute(
        """INSERT INTO api_tokens (user_id, name, token_hash, prefix, scopes, expires_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, name, hash_token(token), token[:10], ",".join(sorted(scopes)),
         iso(created + lifetime), iso(created)),
    )
    return token, db.execute("SELECT * FROM api_tokens WHERE id = ?", (cur.lastrowid,)).fetchone()


def token_info(row: sqlite3.Row) -> ApiTokenInfo:
    return ApiTokenInfo(
        id=row["id"], user_id=row["user_id"], name=row["name"], prefix=row["prefix"],
        scopes=row["scopes"].split(","), expires_at=row["expires_at"], revoked=row["revoked"],
        created_at=row["created_at"], last_used_at=row["last_used_at"],
    )


def user_out(row: sqlite3.Row) -> UserOut:
    return UserOut(id=row["id"], username=row["username"], role=row["role"],
                   active=row["active"], created_at=row["created_at"])


# ─── App ───────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Notizen-API",
    version="1.0.0",
    description="Notizen mit Benutzern, Rollen, persönlichen API-Tokens und Audit-Log.",
    lifespan=lifespan,
)


@app.get("/health", tags=["System"])
def health() -> dict:
    return {"status": "ok"}


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.post("/auth/login", response_model=LoginOut, tags=["Auth"])
def login(body: LoginIn, request: Request, db: DB):
    user = db.execute("SELECT * FROM users WHERE username = ?", (body.username,)).fetchone()
    password_ok = verify_password(body.password, user["password_hash"] if user else DUMMY_HASH)
    if user is None or not password_ok or not user["active"]:
        write_audit(db, user["id"] if user else None, "auth.login_failed",
                    f"user:{body.username}", client_ip(request))
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Benutzername oder Passwort falsch")
    scopes = ROLE_SCOPES[user["role"]]
    token, row = issue_token(db, user["id"], "login", scopes, timedelta(hours=LOGIN_TOKEN_HOURS))
    write_audit(db, user["id"], "auth.login", f"token:{row['id']}", client_ip(request))
    db.commit()
    return LoginOut(access_token=token, expires_at=row["expires_at"], scopes=sorted(scopes))


@app.post("/auth/logout", status_code=204, tags=["Auth"])
def logout(request: Request, p: Authenticated, db: DB):
    db.execute("UPDATE api_tokens SET revoked = 1 WHERE id = ?", (p.token_id,))
    write_audit(db, p.user_id, "auth.logout", f"token:{p.token_id}", client_ip(request))
    db.commit()
    return Response(status_code=204)


@app.get("/me", response_model=MeOut, tags=["Auth"])
def me(p: Authenticated):
    return MeOut(id=p.user_id, username=p.username, role=p.role,
                 token_id=p.token_id, scopes=sorted(p.scopes))


# ── Notizen ───────────────────────────────────────────────────────────────────
NOTE_SELECT = "SELECT n.*, u.username AS owner FROM notes n JOIN users u ON u.id = n.owner_id"


def note_out(row: sqlite3.Row) -> NoteOut:
    return NoteOut(**{field: row[field] for field in NoteOut.model_fields})


def load_note(db: sqlite3.Connection, note_id: int, p: Principal) -> sqlite3.Row:
    """Liefert die Notiz nur, wenn der Aufrufer sie sehen darf – sonst 404,
    damit nicht erkennbar ist, ob eine fremde private Notiz existiert."""
    row = db.execute(NOTE_SELECT + " WHERE n.id = ?", (note_id,)).fetchone()
    if row is None or not (is_admin(p) or row["owner_id"] == p.user_id or row["visibility"] == "team"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notiz nicht gefunden")
    return row


def ensure_can_modify(row: sqlite3.Row, p: Principal) -> None:
    if row["owner_id"] != p.user_id and not is_admin(p):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur Eigentümer oder Admins dürfen das")


@app.get("/notes", response_model=list[NoteOut], tags=["Notizen"])
def list_notes(
    p: Reader,
    db: DB,
    q: Annotated[str | None, Query(max_length=100, description="Suche in Titel und Text")] = None,
    visibility: Visibility | None = None,
    owner: Annotated[str | None, Query(max_length=32, description="Benutzername")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    sql, params = NOTE_SELECT + " WHERE 1 = 1", []
    if not is_admin(p):
        sql += " AND (n.owner_id = ? OR n.visibility = 'team')"
        params.append(p.user_id)
    if q:
        like = f"%{escape_like(q)}%"
        sql += " AND (n.title LIKE ? ESCAPE '\\' OR n.body LIKE ? ESCAPE '\\')"
        params += [like, like]
    if visibility:
        sql += " AND n.visibility = ?"
        params.append(visibility.value)
    if owner:
        sql += " AND u.username = ?"
        params.append(owner)
    sql += " ORDER BY n.updated_at DESC, n.id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    return [note_out(row) for row in db.execute(sql, params)]


@app.post("/notes", response_model=NoteOut, status_code=201, tags=["Notizen"])
def create_note(body: NoteIn, p: Writer, db: DB):
    ts = iso(now())
    cur = db.execute(
        """INSERT INTO notes (owner_id, title, body, visibility, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (p.user_id, body.title, body.body, body.visibility.value, ts, ts),
    )
    db.commit()
    return note_out(load_note(db, cur.lastrowid, p))


@app.get("/notes/{note_id}", response_model=NoteOut, tags=["Notizen"])
def get_note(note_id: Annotated[int, Path(ge=1)], p: Reader, db: DB):
    return note_out(load_note(db, note_id, p))


@app.put("/notes/{note_id}", response_model=NoteOut, tags=["Notizen"])
def update_note(note_id: Annotated[int, Path(ge=1)], body: NoteIn, p: Writer, db: DB):
    ensure_can_modify(load_note(db, note_id, p), p)
    db.execute(
        "UPDATE notes SET title = ?, body = ?, visibility = ?, updated_at = ? WHERE id = ?",
        (body.title, body.body, body.visibility.value, iso(now()), note_id),
    )
    db.commit()
    return note_out(load_note(db, note_id, p))


@app.delete("/notes/{note_id}", status_code=204, tags=["Notizen"])
def delete_note(note_id: Annotated[int, Path(ge=1)], request: Request, p: Writer, db: DB):
    row = load_note(db, note_id, p)
    ensure_can_modify(row, p)
    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    write_audit(db, p.user_id, "note.delete", f"note:{note_id}", client_ip(request),
                {"owner_id": row["owner_id"], "title": row["title"]})
    db.commit()
    return Response(status_code=204)


# ── API-Tokens ────────────────────────────────────────────────────────────────
@app.get("/tokens", response_model=list[ApiTokenInfo], tags=["API-Tokens"])
def list_tokens(p: Authenticated, db: DB, include_revoked: bool = False):
    sql = "SELECT * FROM api_tokens WHERE user_id = ?"
    if not include_revoked:
        sql += " AND revoked = 0"
    return [token_info(row) for row in db.execute(sql + " ORDER BY id DESC", (p.user_id,))]


@app.post("/tokens", response_model=ApiTokenCreated, status_code=201, tags=["API-Tokens"])
def create_token(body: ApiTokenIn, request: Request, p: Authenticated, db: DB):
    requested = {scope.value for scope in body.scopes}
    # Ein Token kann höchstens die Rechte weitergeben, die es selbst hat.
    excess = requested - p.scopes
    if excess:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Nicht erlaubte Scopes: {', '.join(sorted(excess))}")
    token, row = issue_token(db, p.user_id, body.name, requested, timedelta(days=body.valid_days))
    write_audit(db, p.user_id, "token.create", f"token:{row['id']}", client_ip(request),
                {"name": body.name, "scopes": sorted(requested), "valid_days": body.valid_days})
    db.commit()
    return ApiTokenCreated(**token_info(row).model_dump(), token=token)


@app.delete("/tokens/{token_id}", status_code=204, tags=["API-Tokens"])
def revoke_token(token_id: Annotated[int, Path(ge=1)], request: Request, p: Authenticated, db: DB):
    row = db.execute("SELECT user_id FROM api_tokens WHERE id = ?", (token_id,)).fetchone()
    if row is None or (row["user_id"] != p.user_id and not is_admin(p)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token nicht gefunden")
    db.execute("UPDATE api_tokens SET revoked = 1 WHERE id = ?", (token_id,))
    write_audit(db, p.user_id, "token.revoke", f"token:{token_id}", client_ip(request),
                {"token_owner_id": row["user_id"]})
    db.commit()
    return Response(status_code=204)


# ── Administration ────────────────────────────────────────────────────────────
@app.get("/admin/users", response_model=list[UserOut], tags=["Administration"])
def list_users(p: Admin, db: DB, role: Role | None = None, active: bool | None = None):
    sql, params = "SELECT * FROM users WHERE 1 = 1", []
    if role:
        sql += " AND role = ?"
        params.append(role.value)
    if active is not None:
        sql += " AND active = ?"
        params.append(int(active))
    return [user_out(row) for row in db.execute(sql + " ORDER BY id", params)]


@app.post("/admin/users", response_model=UserOut, status_code=201, tags=["Administration"])
def create_user(body: UserCreate, request: Request, p: Admin, db: DB):
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (body.username, hash_password(body.password), body.role.value, iso(now())),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Benutzername bereits vergeben")
    write_audit(db, p.user_id, "user.create", f"user:{cur.lastrowid}", client_ip(request),
                {"username": body.username, "role": body.role.value})
    db.commit()
    return user_out(db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())


@app.patch("/admin/users/{user_id}", response_model=UserOut, tags=["Administration"])
def update_user(user_id: Annotated[int, Path(ge=1)], body: UserUpdate,
                request: Request, p: Admin, db: DB):
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benutzer nicht gefunden")
    new_role = body.role.value if body.role else user["role"]
    new_active = body.active if body.active is not None else bool(user["active"])

    loses_admin = user["role"] == "admin" and user["active"] and (new_role != "admin" or not new_active)
    if loses_admin:
        others = db.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1 AND id != ?", (user_id,)
        ).fetchone()[0]
        if others == 0:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Der letzte aktive Admin kann weder herabgestuft noch deaktiviert werden")

    db.execute("UPDATE users SET role = ?, active = ? WHERE id = ?", (new_role, int(new_active), user_id))
    revoked = 0
    if not new_active:  # Deaktivierung entzieht sofort alle Tokens
        revoked = db.execute(
            "UPDATE api_tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0", (user_id,)
        ).rowcount
    write_audit(db, p.user_id, "user.update", f"user:{user_id}", client_ip(request), {
        "role": [user["role"], new_role],
        "active": [bool(user["active"]), new_active],
        "tokens_revoked": revoked,
    })
    db.commit()
    return user_out(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


@app.get("/admin/audit", response_model=list[AuditEntry], tags=["Administration"])
def list_audit(
    p: Admin,
    db: DB,
    action: Annotated[str | None, Query(max_length=64, description="Präfix, z. B. 'auth.' oder 'token.create'")] = None,
    actor_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
):
    sql, params = "SELECT * FROM audit_log WHERE 1 = 1", []
    if action:
        sql += " AND action LIKE ? ESCAPE '\\'"
        params.append(escape_like(action) + "%")
    if actor_id is not None:
        sql += " AND actor_id = ?"
        params.append(actor_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return [
        AuditEntry(id=r["id"], ts=r["ts"], actor_id=r["actor_id"], action=r["action"],
                   target=r["target"], ip=r["ip"], detail=json.loads(r["detail"]))
        for r in db.execute(sql, params)
    ]
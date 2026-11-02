"""Tests der Notizen-API. Ausführen mit:  pytest -q"""
import pytest
from fastapi.testclient import TestClient

import app as api

ADMIN_PW = "admin-passwort-fuer-tests"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", ADMIN_PW)
    with TestClient(api.app) as c:
        yield c


def login(client, username, password):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def h(client):
    """Auth-Header für admin, erika (editor) und max (viewer)."""
    admin = login(client, "admin", ADMIN_PW)
    for name, role in [("erika", "editor"), ("max", "viewer")]:
        r = client.post("/admin/users", headers=admin,
                        json={"username": name, "password": f"{name}-passwort-123", "role": role})
        assert r.status_code == 201, r.text
    return {
        "admin": admin,
        "erika": login(client, "erika", "erika-passwort-123"),
        "max": login(client, "max", "max-passwort-123"),
    }


def user_id(client, h, name):
    users = client.get("/admin/users", headers=h["admin"]).json()
    return next(u["id"] for u in users if u["username"] == name)


def test_ohne_token_gibt_401(client):
    assert client.get("/notes").status_code == 401
    assert client.get("/notes", headers={"Authorization": "Bearer nt_erfunden"}).status_code == 401


def test_fehlgeschlagener_login_wird_protokolliert(client, h):
    r = client.post("/auth/login", json={"username": "erika", "password": "falsch"})
    assert r.status_code == 401
    log = client.get("/admin/audit", params={"action": "auth.login_failed"}, headers=h["admin"]).json()
    assert log[0]["target"] == "user:erika"


def test_sichtbarkeit_von_notizen(client, h):
    privat = client.post("/notes", headers=h["erika"], json={"title": "Geheim"}).json()
    team = client.post("/notes", headers=h["erika"], json={"title": "Für alle", "visibility": "team"}).json()
    assert client.get(f"/notes/{privat['id']}", headers=h["max"]).status_code == 404
    assert client.get(f"/notes/{team['id']}", headers=h["max"]).status_code == 200
    assert [n["title"] for n in client.get("/notes", headers=h["max"]).json()] == ["Für alle"]
    assert client.get(f"/notes/{privat['id']}", headers=h["admin"]).status_code == 200


def test_viewer_darf_weder_schreiben_noch_verwalten(client, h):
    assert client.post("/notes", headers=h["max"], json={"title": "x"}).status_code == 403
    assert client.get("/admin/users", headers=h["max"]).status_code == 403


def test_fremde_notiz_nicht_aenderbar(client, h):
    note = client.post("/notes", headers=h["admin"], json={"title": "Admin", "visibility": "team"}).json()
    assert client.put(f"/notes/{note['id']}", headers=h["erika"], json={"title": "gekapert"}).status_code == 403
    assert client.delete(f"/notes/{note['id']}", headers=h["erika"]).status_code == 403


def test_suche_behandelt_platzhalter_woertlich(client, h):
    client.post("/notes", headers=h["erika"], json={"title": "100% fertig"})
    client.post("/notes", headers=h["erika"], json={"title": "1000 Dinge"})
    r = client.get("/notes", params={"q": "100%"}, headers=h["erika"])
    assert [n["title"] for n in r.json()] == ["100% fertig"]


def test_token_kann_rechte_nicht_erweitern(client, h):
    r = client.post("/tokens", headers=h["erika"], json={"name": "nur-lesen", "scopes": ["read"]})
    assert r.status_code == 201
    nur_lesen = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.post("/notes", headers=nur_lesen, json={"title": "x"}).status_code == 403
    r = client.post("/tokens", headers=nur_lesen, json={"name": "mehr", "scopes": ["read", "write"]})
    assert r.status_code == 403
    r = client.post("/tokens", headers=h["erika"], json={"name": "admin?", "scopes": ["admin"]})
    assert r.status_code == 403


def test_token_widerrufen(client, h):
    created = client.post("/tokens", headers=h["erika"], json={"name": "ci", "scopes": ["read"]}).json()
    tok = {"Authorization": f"Bearer {created['token']}"}
    assert client.get("/me", headers=tok).status_code == 200
    assert client.delete(f"/tokens/{created['id']}", headers=h["max"]).status_code == 404  # fremdes Token
    assert client.delete(f"/tokens/{created['id']}", headers=h["erika"]).status_code == 204
    assert client.get("/me", headers=tok).status_code == 401
    listing = client.get("/tokens", headers=h["erika"], params={"include_revoked": True}).json()
    assert all("token" not in t for t in listing)  # Klartext nie wieder sichtbar


def test_herabstufung_wirkt_sofort(client, h):
    erika = user_id(client, h, "erika")
    assert client.patch(f"/admin/users/{erika}", headers=h["admin"], json={"role": "viewer"}).status_code == 200
    assert client.get("/me", headers=h["erika"]).json()["scopes"] == ["read"]
    assert client.post("/notes", headers=h["erika"], json={"title": "x"}).status_code == 403


def test_deaktivierung_entzieht_tokens(client, h):
    erika = user_id(client, h, "erika")
    r = client.patch(f"/admin/users/{erika}", headers=h["admin"], json={"active": False})
    assert r.json()["active"] is False
    assert client.get("/me", headers=h["erika"]).status_code == 401
    log = client.get("/admin/audit", params={"action": "user.update"}, headers=h["admin"]).json()
    assert log[0]["detail"]["tokens_revoked"] >= 1


def test_letzter_admin_ist_geschuetzt(client, h):
    admin = user_id(client, h, "admin")
    r = client.patch(f"/admin/users/{admin}", headers=h["admin"], json={"role": "editor"})
    assert r.status_code == 409
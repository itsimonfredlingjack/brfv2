from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import llm as llm_mod
from app.auth import AuthStore
from app.model_endpoint import EndpointRejected, policy_document
from app.desktop import (
    BACKUP_MANIFEST,
    BACKUP_SCHEMA,
    CSP,
    STARTUP_SCHEMA,
    STATE_SCHEMA,
    ModelRuntimeConfig,
    apply_model_runtime,
    apply_pending_restore,
    create_backup,
    create_desktop_app,
    read_backup_manifest,
    slugify_brf_id,
    stage_restore,
)

OWNER = {
    "name": "Maria Ordförande",
    "email": "ordforande@brf.example",
    "password": "byt-detta-lösenord",
    "brfName": "Brf Sjöutsikten 7",
}


_DESKTOP_ENV = (
    "BRF_MODE",
    "BRF_LLM",
    "BRF_LLM_BASE_URL",
    "BRF_LLM_MODEL",
    "BRF_LLM_API_KEY",
    "BRF_LLM_TIMEOUT_S",
    "BRF_LLM_RUNTIME_LABEL",
)


@pytest.fixture(autouse=True)
def desktop_env():
    """The desktop adapter configures generation through the process
    environment (that is how ``app.llm`` reads it), so every test here has to
    hand the environment and the memoized provider back untouched."""
    saved = {name: os.environ.get(name) for name in _DESKTOP_ENV}
    llm_mod.reset_provider_cache()
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        llm_mod.reset_provider_cache()


def _dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text(
        '<!doctype html><script type="module" src="/brfv2/assets/app.js"></script>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("document.body.textContent = 'desktop'", encoding="utf-8")
    return dist


def _client(
    tmp_path: Path,
    *,
    seed_demo: bool = False,
    request_restart=None,
) -> TestClient:
    origin = "http://127.0.0.1:43123"
    app = create_desktop_app(
        dist_dir=_dist(tmp_path),
        data_root=tmp_path / "data",
        expected_origin=origin,
        request_restart=request_restart,
        seed_demo=seed_demo,
    )
    return TestClient(app, base_url=origin)


def _provisioned(tmp_path: Path, **kwargs) -> TestClient:
    client = _client(tmp_path, **kwargs)
    response = client.post("/api/desktop/setup", json=OWNER)
    assert response.status_code == 200, response.text
    return client


def test_same_origin_serves_real_ui_and_api_with_security_headers(tmp_path):
    with _client(tmp_path) as client:
        root = client.get("/", follow_redirects=False)
        ui = client.get("/brfv2/")
        health = client.get("/api/health")
        readiness = client.get("/api/desktop/readiness")

    assert root.status_code == 307
    assert root.headers["location"] == "/brfv2/"
    assert ui.status_code == 200
    assert "/brfv2/assets/app.js" in ui.text
    assert health.status_code == 200
    assert readiness.json() == {
        "schema": STARTUP_SCHEMA,
        "status": "ready",
        "host": "127.0.0.1",
        "port": 43123,
        "origin": "http://127.0.0.1:43123",
    }
    for response in (root, ui, health, readiness):
        assert response.headers["content-security-policy"] == CSP
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"


def test_desktop_boundary_rejects_other_hosts_ports_and_origins(tmp_path):
    with _client(tmp_path) as client:
        wrong_host = client.get("/api/health", headers={"host": "127.0.0.1:8787"})
        wrong_hostname = client.get("/api/health", headers={"host": "localhost:43123"})
        wrong_origin = client.post(
            "/api/auth/login",
            headers={"origin": "http://127.0.0.1:5173"},
            json={"email": "x@example.se", "password": "does-not-matter"},
        )

    assert wrong_host.status_code == 403
    assert wrong_hostname.status_code == 403
    assert wrong_origin.status_code == 403
    assert wrong_origin.headers["content-security-policy"] == CSP


def test_desktop_cookie_is_installation_specific_and_api_scoped(tmp_path):
    with _client(tmp_path, seed_demo=True) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "max@demo.se", "password": "max-demo-2026"},
        )
        me = client.get("/api/auth/me")

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert re.search(r"^brf_desktop_[a-f0-9]{24}=", cookie)
    assert "HttpOnly" in cookie
    assert "Path=/api/" in cookie
    assert "SameSite=lax" in cookie
    assert me.status_code == 200
    assert {row["brf_id"] for row in me.json()["memberships"]} == {
        "gjutformen-12",
        "sjoutsikten-7",
    }


def test_cookie_identifier_is_stable_for_one_installation(tmp_path):
    _client(tmp_path)
    # Recreating the app over the same Tauri data root must reuse the cookie
    # name so persisted sessions remain usable between desktop launches.
    first_id = (tmp_path / "data" / ".desktop-cookie-id").read_text().strip()
    _client(tmp_path)
    second_id = (tmp_path / "data" / ".desktop-cookie-id").read_text().strip()

    assert first_id == second_id
    assert re.fullmatch(r"[a-f0-9]{24}", first_id)


def test_missing_built_frontend_fails_closed(tmp_path):
    missing = tmp_path / "missing-dist"
    try:
        create_desktop_app(
            dist_dir=missing,
            data_root=tmp_path / "data",
            expected_origin="http://127.0.0.1:43123",
        )
    except RuntimeError as exc:
        assert str(missing / "index.html") in str(exc)
    else:
        raise AssertionError("missing dist must not start an API-only desktop shell")


# ---------------------------------------------------------------------------
# First-run provisioning: the product ships with no accounts at all
# ---------------------------------------------------------------------------


def test_fresh_installation_is_unprovisioned_and_ships_no_credentials(tmp_path):
    with _client(tmp_path) as client:
        state = client.get("/api/desktop/state").json()
        # The one credential pair the spike shipped with must not work.
        login = client.post(
            "/api/auth/login",
            json={"email": "max@demo.se", "password": "max-demo-2026"},
        )

    assert state["schema"] == STATE_SCHEMA
    assert state["provisioned"] is False
    assert login.status_code == 401
    assert (tmp_path / "data" / "tenants").is_dir()


def test_setup_creates_the_owner_and_first_brf_then_closes_permanently(tmp_path):
    with _client(tmp_path) as client:
        created = client.post("/api/desktop/setup", json=OWNER)
        me = client.get("/api/auth/me")
        state = client.get("/api/desktop/state").json()
        again = client.post(
            "/api/desktop/setup",
            json={**OWNER, "email": "angripare@example.com"},
        )

    assert created.status_code == 200, created.text
    body = created.json()
    assert body["user"]["email"] == OWNER["email"]
    assert [row["role"] for row in body["memberships"]] == ["admin"]
    assert body["memberships"][0]["brf_id"] == "brf-sjoutsikten-7"
    assert me.status_code == 200
    assert state["provisioned"] is True
    # A second setup would be a way to mint an owner without authenticating.
    assert again.status_code == 409


@pytest.mark.parametrize(
    "patch, field",
    [
        ({"password": "kort"}, "Lösenordet"),
        ({"email": "inte-en-adress"}, "e-postadress"),
        ({"brfName": " "}, "föreningens namn"),
    ],
)
def test_setup_refuses_unusable_input(tmp_path, patch, field):
    with _client(tmp_path) as client:
        response = client.post("/api/desktop/setup", json={**OWNER, **patch})
        state = client.get("/api/desktop/state").json()

    assert response.status_code == 422
    assert field.lower() in response.json()["detail"].lower()
    assert state["provisioned"] is False


def test_slugify_keeps_ids_valid_and_out_of_the_validation_namespace():
    assert slugify_brf_id("Brf Gjutformen 12") == "brf-gjutformen-12"
    assert slugify_brf_id("Brf Sjöutsikten 7") == "brf-sjoutsikten-7"
    assert slugify_brf_id("Brf Åkerö & Väst") == "brf-akero-vast"
    # `val-` is reserved for the public_scraped validation corpus.
    assert slugify_brf_id("Val Hall") == "brf-val-hall"
    assert slugify_brf_id("Valhall") == "valhall"
    assert re.fullmatch(r"brf-[0-9a-f]{12}", slugify_brf_id("###"))


def test_owner_can_add_a_second_brf_and_switch_between_them(tmp_path):
    with _provisioned(tmp_path) as client:
        created = client.post("/api/desktop/brf", json={"name": "Brf Gjutformen 12"})
        me = client.get("/api/auth/me").json()

    assert created.status_code == 200, created.text
    assert created.json()["brf_id"] == "brf-gjutformen-12"
    assert {row["brf_id"] for row in me["memberships"]} == {
        "brf-sjoutsikten-7",
        "brf-gjutformen-12",
    }


def test_every_desktop_operation_requires_a_session(tmp_path):
    with _provisioned(tmp_path) as client:
        client.cookies.clear()
        statuses = {
            "brf": client.post("/api/desktop/brf", json={"name": "Brf X"}).status_code,
            "model-get": client.get("/api/desktop/model-runtime").status_code,
            "model-put": client.put("/api/desktop/model-runtime", json={"baseUrl": ""}).status_code,
            "backups": client.get("/api/desktop/backups").status_code,
            "backup": client.post("/api/desktop/backups").status_code,
            "restart": client.post("/api/desktop/restart").status_code,
        }

    assert set(statuses.values()) == {401}, statuses


# ---------------------------------------------------------------------------
# Model runtime: one configured connection, never an ambient one
# ---------------------------------------------------------------------------


def test_desktop_mode_disables_the_destructive_dev_reset_route(tmp_path):
    with _provisioned(tmp_path) as client:
        health = client.get("/api/health").json()
        reset = client.post("/api/reset")

    assert health["mode"] == "desktop"
    assert reset.status_code == 403


def test_generation_can_never_select_an_ambient_hosted_provider(monkeypatch):
    """The structural half of the no-hidden-egress guarantee.

    With an Anthropic key exported and the `claude` CLI on PATH, provider
    auto-detection would pick one of them.  The desktop adapter pins
    BRF_LLM=selfhosted, so an unconfigured installation degrades to `none`
    instead of quietly answering through a third party.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-be-used")
    monkeypatch.delenv("BRF_LLM", raising=False)

    apply_model_runtime(ModelRuntimeConfig())
    unconfigured = llm_mod.pick_provider()

    apply_model_runtime(ModelRuntimeConfig(baseUrl="http://127.0.0.1:8000/v1"))
    configured = llm_mod.pick_provider()

    assert os.environ["BRF_LLM"] == "selfhosted"
    assert unconfigured.name == "none"
    assert configured.name == "selfhosted"


def test_model_runtime_is_persisted_and_never_returns_the_bearer_token(tmp_path):
    with _provisioned(tmp_path) as client:
        saved = client.put(
            "/api/desktop/model-runtime",
            json={
                "baseUrl": "http://127.0.0.1:8000/v1/",
                "model": "gemma4:e12b",
                "apiKey": "hemlig-token",
                "label": "agenntserver",
                "timeoutS": 300,
            },
        )
        fetched = client.get("/api/desktop/model-runtime").json()
        state = client.get("/api/desktop/state").json()
        # null keeps the stored token; "" clears it.
        kept = client.put(
            "/api/desktop/model-runtime",
            json={"baseUrl": "http://127.0.0.1:8000/v1", "model": "gemma4:e12b", "label": ""},
        ).json()

    assert saved.status_code == 200, saved.text
    assert saved.json()["baseUrl"] == "http://127.0.0.1:8000/v1"  # trailing slash normalized
    assert "apiKey" not in fetched and fetched["hasApiKey"] is True
    assert kept["hasApiKey"] is True
    assert state["modelRuntime"]["provider"] == "selfhosted"
    assert state["modelRuntime"]["ready"] is True

    on_disk = json.loads((tmp_path / "data" / "desktop-config.json").read_text(encoding="utf-8"))
    assert on_disk["llm"]["apiKey"] == "hemlig-token"
    assert (tmp_path / "data" / "desktop-config.json").stat().st_mode & 0o777 == 0o600


def test_unconfigured_model_runtime_reads_as_not_ready(tmp_path):
    with _provisioned(tmp_path) as client:
        state = client.get("/api/desktop/state").json()
        health = client.get("/api/health").json()

    assert state["modelRuntime"]["configured"] is False
    assert state["modelRuntime"]["provider"] == "none"
    assert state["modelRuntime"]["ready"] is False
    assert health["llm"]["ready"] is False


def test_model_runtime_rejects_a_non_http_address(tmp_path):
    with _provisioned(tmp_path) as client:
        response = client.put("/api/desktop/model-runtime", json={"baseUrl": "file:///etc/passwd"})

    assert response.status_code == 422
    assert "http" in response.json()["detail"]


# ---------------------------------------------------------------------------
# The self-hosted boundary: who may repoint the model service, and where to
# ---------------------------------------------------------------------------


def _ordinary_user(tmp_path: Path, client: TestClient) -> str:
    """A second, non-privileged account on the same installation.

    Admin of the association — the strongest authority an ordinary account can
    hold — so a rejection below is about installation authority and not about
    membership.  Created directly in the store because the shipped product has
    no route that mints a second installation administrator, which is the
    point.
    """

    store = AuthStore(tmp_path / "data" / "auth.db")
    user_id = store.create_user("kassor@brf.example", "ett-annat-lösenord", "Karin Kassör")
    for membership in store.list_tenants():
        store.add_membership(user_id, membership["brf_id"], "admin")
    response = client.post(
        "/api/auth/login",
        json={"email": "kassor@brf.example", "password": "ett-annat-lösenord"},
    )
    assert response.status_code == 200, response.text
    return user_id


def test_the_setup_owner_is_the_installation_administrator(tmp_path):
    with _provisioned(tmp_path) as client:
        owner_state = client.get("/api/desktop/state").json()
        store = AuthStore(tmp_path / "data" / "auth.db")
        owner = store.get_user_by_email(OWNER["email"])
        ordinary = _ordinary_user(tmp_path, client)
        ordinary_state = client.get("/api/desktop/state").json()

    assert owner_state["installationAdmin"] is True
    assert ordinary_state["installationAdmin"] is False
    assert store.list_installation_admins() == [owner["id"]]
    assert store.is_installation_admin(ordinary) is False
    # Association admin, and still not an installation administrator.
    assert {m["role"] for m in store.memberships_for(ordinary)} == {"admin"}


def test_changing_the_model_service_requires_installation_authority(tmp_path):
    """An ordinary account cannot repoint where the documents are sent."""

    with _provisioned(tmp_path) as client:
        client.put(
            "/api/desktop/model-runtime",
            json={"baseUrl": "http://127.0.0.1:8000/v1", "model": "gemma4:e12b"},
        )
        _ordinary_user(tmp_path, client)
        readable = client.get("/api/desktop/model-runtime")
        repoint = client.put(
            "/api/desktop/model-runtime",
            json={"baseUrl": "https://192.168.13.13:8000/v1", "model": "gemma4:e12b"},
        )
        probe = client.post("/api/desktop/model-runtime/test")
        after = client.get("/api/desktop/state").json()

    # Provenance stays readable — every answer is labelled with it.
    assert readable.status_code == 200
    assert repoint.status_code == 403
    assert "installationsadministratör" in repoint.json()["detail"]
    assert probe.status_code == 403
    # Neither the process nor the file on disk moved.
    assert after["modelRuntime"]["baseUrl"] == "http://127.0.0.1:8000/v1"
    assert os.environ["BRF_LLM_BASE_URL"] == "http://127.0.0.1:8000/v1"
    on_disk = json.loads((tmp_path / "data" / "desktop-config.json").read_text(encoding="utf-8"))
    assert on_disk["llm"]["baseUrl"] == "http://127.0.0.1:8000/v1"


@pytest.mark.parametrize(
    "url,code",
    [
        ("https://api.openai.com/v1", "hostname_not_allowed"),
        ("https://8.8.8.8/v1", "address_not_self_hosted"),
        ("http://192.168.1.50:8000/v1", "plaintext_off_host"),
        ("http://169.254.169.254/latest/meta-data", "link_local_address"),
    ],
)
def test_the_installed_api_refuses_endpoints_outside_the_policy(tmp_path, url, code):
    with _provisioned(tmp_path) as client:
        response = client.put("/api/desktop/model-runtime", json={"baseUrl": url})
        state = client.get("/api/desktop/state").json()

    assert response.status_code == 422, response.text
    assert response.headers["x-model-endpoint-rejection"] == code
    assert state["modelRuntime"]["configured"] is False
    assert state["modelRuntime"]["provider"] == "none"


def test_the_policy_the_ui_is_served_is_the_policy_that_is_enforced(tmp_path):
    with _provisioned(tmp_path) as client:
        served = client.get("/api/desktop/model-endpoint-policy").json()
        in_state = client.get("/api/desktop/state").json()["modelEndpointPolicy"]

    assert served == in_state == policy_document()
    assert served["authority"] == "installation-administrator"


def test_a_hand_edited_config_file_cannot_smuggle_in_a_foreign_endpoint(tmp_path):
    """The configuration file is writable by the OS user, so it is a proposal.

    A process running as the same user could rewrite it; the installation must
    then start with no generation provider rather than start sending documents
    to whatever the file now names.
    """

    with _provisioned(tmp_path) as client:
        client.put(
            "/api/desktop/model-runtime",
            json={"baseUrl": "http://127.0.0.1:8000/v1", "apiKey": "hemlig-token"},
        )

    config_path = tmp_path / "data" / "desktop-config.json"
    tampered = json.loads(config_path.read_text(encoding="utf-8"))
    tampered["llm"]["baseUrl"] = "https://api.openai.com/v1"
    config_path.write_text(json.dumps(tampered), encoding="utf-8")

    with _client(tmp_path) as client:
        state = client.get("/api/desktop/state").json()

    assert state["modelRuntime"]["configured"] is False
    assert state["modelRuntime"]["provider"] == "none"
    assert state["modelRuntime"]["ready"] is False
    assert os.environ["BRF_LLM_BASE_URL"] == ""
    # The rejected file's bearer token is not carried over either.
    assert os.environ.get("BRF_LLM_API_KEY") is None


def test_apply_model_runtime_refuses_a_disallowed_endpoint():
    """The last gate before the address becomes process state."""

    with pytest.raises(EndpointRejected) as raised:
        apply_model_runtime(ModelRuntimeConfig(baseUrl="https://api.openai.com/v1"))
    assert raised.value.code == "hostname_not_allowed"
    assert os.environ.get("BRF_LLM_BASE_URL") in (None, "")


def test_an_installation_from_before_this_authority_existed_is_adopted(tmp_path):
    """A backup restored from an older build must not strand the machine."""

    with _provisioned(tmp_path) as client:
        owner = AuthStore(tmp_path / "data" / "auth.db").get_user_by_email(OWNER["email"])

    store = AuthStore(tmp_path / "data" / "auth.db")
    assert store.revoke_installation_admin(owner["id"]) is True
    assert store.list_installation_admins() == []

    with _client(tmp_path) as client:
        client.post("/api/auth/login", json={"email": OWNER["email"], "password": OWNER["password"]})
        state = client.get("/api/desktop/state").json()
        allowed = client.put(
            "/api/desktop/model-runtime",
            json={"baseUrl": "http://127.0.0.1:8000/v1", "model": "gemma4:e12b"},
        )

    assert state["installationAdmin"] is True
    assert allowed.status_code == 200, allowed.text
    assert AuthStore(tmp_path / "data" / "auth.db").list_installation_admins() == [owner["id"]]


# ---------------------------------------------------------------------------
# Backup and restore
# ---------------------------------------------------------------------------


def test_backup_captures_the_data_root_and_lists_its_tenants(tmp_path):
    with _provisioned(tmp_path) as client:
        created = client.post("/api/desktop/backups")
        listed = client.get("/api/desktop/backups").json()

    assert created.status_code == 200, created.text
    meta = created.json()
    assert meta["tenants"] == [{"brf_id": "brf-sjoutsikten-7", "name": OWNER["brfName"], "documents": 0}]
    assert [row["name"] for row in listed["backups"]] == [meta["name"]]

    archive = tmp_path / "backups" / meta["name"]
    assert archive.stat().st_mode & 0o777 == 0o600
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    assert BACKUP_MANIFEST in names
    assert "data/auth.db" in names
    # Backups live beside the data root, so they are never inside their own
    # payload and survive the restore that replaces it.
    assert not any(name.startswith("data/backups") for name in names)


def test_restore_is_staged_and_applied_before_any_store_opens(tmp_path):
    with _provisioned(tmp_path) as client:
        backup = client.post("/api/desktop/backups").json()
        # Diverge from the backup: a second BRF that must be gone afterwards.
        client.post("/api/desktop/brf", json={"name": "Brf Gjutformen 12"})
        assert len(client.get("/api/auth/me").json()["memberships"]) == 2
        staged = client.post(f"/api/desktop/backups/{backup['name']}/restore")

    assert staged.status_code == 200, staged.text
    assert staged.json()["restartRequired"] is True

    applied = apply_pending_restore(tmp_path / "data", tmp_path / "restore-staging")
    assert applied["status"] == "restored"

    with _client(tmp_path) as client:
        client.post(
            "/api/auth/login",
            json={"email": OWNER["email"], "password": OWNER["password"]},
        )
        memberships = client.get("/api/auth/me").json()["memberships"]
        state = client.get("/api/desktop/state").json()

    assert [row["brf_id"] for row in memberships] == ["brf-sjoutsikten-7"]
    assert state["lastRestore"]["status"] == "restored"
    # A pending restore is consumed exactly once.
    assert apply_pending_restore(tmp_path / "data", tmp_path / "restore-staging") is None


def test_restore_refuses_archives_that_are_not_ours(tmp_path):
    hostile = tmp_path / "hostile.zip"
    with zipfile.ZipFile(hostile, "w") as zf:
        zf.writestr(BACKUP_MANIFEST, json.dumps({"schema": BACKUP_SCHEMA}))
        zf.writestr("data/../../../../etc/cron.d/pwn", "* * * * * root id\n")
    with pytest.raises(ValueError, match="Otillåten sökväg"):
        read_backup_manifest(hostile)

    foreign = tmp_path / "foreign.zip"
    with zipfile.ZipFile(foreign, "w") as zf:
        zf.writestr("data/auth.db", "not ours")
    with pytest.raises(ValueError, match="innehållsförteckning"):
        read_backup_manifest(foreign)

    with pytest.raises(ValueError, match="zip-arkiv"):
        read_backup_manifest(_dist(tmp_path) / "index.html")


def test_failed_restore_leaves_the_live_data_untouched(tmp_path):
    data_root = tmp_path / "data"
    with _provisioned(tmp_path):
        pass
    staging = tmp_path / "restore-staging"
    truncated = create_backup(data_root, tmp_path / "backups")
    archive = tmp_path / "backups" / truncated["name"]
    stage_restore(archive, staging)
    # Corrupt the staged copy after validation, the way a bad disk would.
    (staging / "pending-restore.zip").write_bytes(b"PK\x03\x04 corrupted")

    result = apply_pending_restore(data_root, staging)

    assert result["status"] == "failed"
    assert (data_root / "auth.db").is_file()
    with _client(tmp_path) as client:
        assert client.get("/api/desktop/state").json()["provisioned"] is True


def test_restart_is_delegated_to_the_shell_and_reported_in_state(tmp_path):
    calls: list[int] = []
    with _provisioned(tmp_path, request_restart=lambda: calls.append(1)) as client:
        state = client.get("/api/desktop/state").json()
        response = client.post("/api/desktop/restart")

    assert state["restartSupported"] is True
    assert response.status_code == 200
    assert calls == [1]


def test_state_never_leaks_the_model_bearer_token(tmp_path):
    with _provisioned(tmp_path) as client:
        client.put(
            "/api/desktop/model-runtime",
            json={"baseUrl": "http://127.0.0.1:8000/v1", "apiKey": "hemlig-token"},
        )
        state = client.get("/api/desktop/state").text

    assert "hemlig-token" not in state


def test_unauthenticated_state_does_not_reveal_the_model_address(tmp_path):
    # 192.168.255.254 is an allowed private-network literal that is
    # unmistakably not the pilot's host. The deployment contract forbids
    # writing the model service's actual private address into tracked files.
    address = "https://192.168.255.254:8000/v1"
    with _provisioned(tmp_path) as client:
        client.put(
            "/api/desktop/model-runtime",
            json={"baseUrl": address, "model": "gemma4:e12b"},
        )
        signed_in = client.get("/api/desktop/state").json()
        client.cookies.clear()
        anonymous = client.get("/api/desktop/state").json()

    assert signed_in["modelRuntime"]["baseUrl"] == address
    assert signed_in["modelRuntime"]["deploymentClass"] == "private-network"
    # A caller without a session still learns whether answers can be generated,
    # but not which private host would generate them.
    assert "baseUrl" not in anonymous["modelRuntime"]
    assert anonymous["modelRuntime"] == {"configured": True, "provider": "selfhosted", "ready": True}
    assert "192.168.255.254" not in json.dumps(anonymous)


def test_state_does_not_load_the_embedder_just_to_name_it(tmp_path, monkeypatch):
    """The state route gates the first paint of the whole UI.

    Constructing the model2vec embedder loads ~500 MB of weights, so a cold
    start — a fresh launch, where nothing is cached yet — would stall the
    window on a blank loading screen. The weights still load lazily on the
    first ingestion or question, and provisioning a tenant still builds them.
    """
    from app import embeddings

    monkeypatch.setenv("BRF_EMBEDDER", "model2vec")
    with _provisioned(tmp_path) as client:
        # A fresh launch starts with nothing built.
        embeddings._build_embedder.cache_clear()
        class Tripwire(embeddings.Model2VecEmbedder):
            def __init__(self):
                pytest.fail("desktop state must not construct the embedder")

        monkeypatch.setattr(embeddings, "Model2VecEmbedder", Tripwire)
        state = client.get("/api/desktop/state").json()

    assert state["embedding"]["provider"] == "model2vec:potion-multilingual-128M"
    assert embeddings.configured_provider_name() == "model2vec:potion-multilingual-128M"

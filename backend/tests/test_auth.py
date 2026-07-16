"""Auth primitives: hashing, sessions, memberships, throttling."""

import pytest

from app.auth import AuthError, AuthStore, _token_hash


@pytest.fixture()
def auth(tmp_path) -> AuthStore:
    return AuthStore(tmp_path / "auth.db")


class TestUsers:
    def test_create_and_login(self, auth):
        uid = auth.create_user("Anna@Exempel.SE", "hemligt-lösen", "Anna")
        assert auth.verify_login("anna@exempel.se", "hemligt-lösen") == uid  # email normalized
        assert auth.verify_login("anna@exempel.se", "fel-lösen") is None

    def test_password_not_stored_plaintext(self, auth, tmp_path):
        auth.create_user("b@exempel.se", "supersecret-1", "B")
        raw = (tmp_path / "auth.db").read_bytes()
        assert b"supersecret-1" not in raw

    def test_short_password_rejected(self, auth):
        with pytest.raises(AuthError):
            auth.create_user("c@exempel.se", "kort")

    def test_duplicate_email_rejected(self, auth):
        auth.create_user("d@exempel.se", "lösenord-1", "D")
        with pytest.raises(AuthError):
            auth.create_user("d@exempel.se", "lösenord-2", "D2")

    def test_unknown_email_login_is_none(self, auth):
        assert auth.verify_login("ingen@exempel.se", "vadsomhelst") is None


class TestThrottle:
    def test_throttle_after_max_failures(self, auth):
        auth.create_user("e@exempel.se", "rätt-lösenord", "E")
        for _ in range(10):
            assert auth.verify_login("e@exempel.se", "fel") is None
        with pytest.raises(AuthError, match="För många"):
            auth.verify_login("e@exempel.se", "rätt-lösenord")  # locked even with right pw

    def test_success_resets_failures(self, auth):
        auth.create_user("f@exempel.se", "rätt-lösenord", "F")
        for _ in range(5):
            auth.verify_login("f@exempel.se", "fel")
        assert auth.verify_login("f@exempel.se", "rätt-lösenord")  # resets counter
        for _ in range(9):
            auth.verify_login("f@exempel.se", "fel")
        assert auth.verify_login("f@exempel.se", "rätt-lösenord")  # still under threshold


class TestSessions:
    def test_session_roundtrip(self, auth):
        uid = auth.create_user("g@exempel.se", "lösenord-1", "G")
        token = auth.create_session(uid)
        user = auth.resolve_session(token)
        assert user and user["id"] == uid and user["email"] == "g@exempel.se"

    def test_only_hash_stored(self, auth, tmp_path):
        uid = auth.create_user("h@exempel.se", "lösenord-1", "H")
        token = auth.create_session(uid)
        raw = (tmp_path / "auth.db").read_bytes()
        assert token.encode() not in raw
        assert _token_hash(token).encode() in raw

    def test_expired_session_rejected(self, auth):
        uid = auth.create_user("i@exempel.se", "lösenord-1", "I")
        token = auth.create_session(uid, ttl_hours=-1)  # already expired
        assert auth.resolve_session(token) is None

    def test_deleted_session_rejected(self, auth):
        uid = auth.create_user("j@exempel.se", "lösenord-1", "J")
        token = auth.create_session(uid)
        auth.delete_session(token)
        assert auth.resolve_session(token) is None

    def test_garbage_token_rejected(self, auth):
        assert auth.resolve_session("inte-en-token") is None
        assert auth.resolve_session("") is None


class TestMemberships:
    def test_role_scoping(self, auth):
        uid = auth.create_user("k@exempel.se", "lösenord-1", "K")
        auth.create_tenant("Brf Ett", "ett")
        auth.create_tenant("Brf Två", "tva")
        auth.add_membership(uid, "ett", "admin")
        assert auth.role_for(uid, "ett") == "admin"
        assert auth.role_for(uid, "tva") is None  # no membership → no role

    def test_memberships_listing(self, auth):
        uid = auth.create_user("l@exempel.se", "lösenord-1", "L")
        auth.create_tenant("Brf Ett", "ett")
        auth.add_membership(uid, "ett", "member")
        mems = auth.memberships_for(uid)
        assert mems == [{"brf_id": "ett", "name": "Brf Ett", "role": "member"}]

    def test_invalid_role_rejected(self, auth):
        uid = auth.create_user("m@exempel.se", "lösenord-1", "M")
        auth.create_tenant("Brf Ett", "ett")
        with pytest.raises(AuthError):
            auth.add_membership(uid, "ett", "superadmin")

    def test_invalid_brf_id_rejected(self, auth):
        with pytest.raises(AuthError):
            auth.create_tenant("Bad", "../escape")

    def test_delete_tenant_cascades_memberships(self, auth):
        uid = auth.create_user("n@exempel.se", "lösenord-1", "N")
        auth.create_tenant("Brf Ett", "ett")
        auth.add_membership(uid, "ett", "admin")
        assert auth.delete_tenant("ett")
        assert auth.role_for(uid, "ett") is None
        assert auth.memberships_for(uid) == []

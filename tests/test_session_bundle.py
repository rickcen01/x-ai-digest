import pytest

from x_ai_digest.session_bundle import decrypt_state, encrypt_state


def test_session_bundle_round_trip():
    state = {"cookies": [{"name": "test", "value": "value", "domain": ".example.com", "path": "/"}], "origins": []}
    bundle = encrypt_state(state, "a-strong-test-passphrase")
    assert decrypt_state(bundle, "a-strong-test-passphrase") == state
    assert "value" not in bundle["ciphertext"]


def test_session_bundle_rejects_wrong_password():
    state = {"cookies": [], "origins": []}
    bundle = encrypt_state(state, "a-strong-test-passphrase")
    with pytest.raises(Exception):
        decrypt_state(bundle, "another-strong-passphrase")

from __future__ import annotations

from quantum_one.core.redaction import MASK, Redactor

SECRET = "s3cr3t-value-XYZ"


def test_sensitive_keys_masked_recursively() -> None:
    r = Redactor()
    data = {
        "password": "a",
        "apiKey": "b",
        "nested": {"X-MBX-APIKEY": "c", "signature": "d", "listenKey": "e", "ok": 1},
        "items": [{"token": "f"}],
        "Authorization": "Bearer g",
    }
    out = r.redact(data)
    assert out["password"] == MASK
    assert out["apiKey"] == MASK
    assert out["nested"] == {"X-MBX-APIKEY": MASK, "signature": MASK, "listenKey": MASK, "ok": 1}
    assert out["items"] == [{"token": MASK}]
    assert out["Authorization"] == MASK


def test_known_secret_removed_from_free_text() -> None:
    r = Redactor([SECRET])
    out = r.redact({"event": f"falhou conexão com senha {SECRET} aqui", "n": [SECRET]})
    assert SECRET not in str(out)
    assert MASK in out["event"]


def test_url_credentials_masked() -> None:
    r = Redactor()
    text = "postgresql://q1_api:qualquercoisa@postgres:5432/db"
    assert r.redact_str(text) == f"postgresql://q1_api:{MASK}@postgres:5432/db"


def test_short_secrets_ignored_to_avoid_false_positives() -> None:
    r = Redactor(["abc"])
    assert r.redact_str("abcdef") == "abcdef"


def test_non_string_types() -> None:
    r = Redactor([SECRET])
    assert r.redact(b"\x00\x01") == "<2 bytes>"
    assert r.redact(3) == 3
    assert r.redact(None) is None
    assert r.redact((1, "x")) == [1, "x"]

    class Obj:
        def __repr__(self) -> str:
            return f"Obj({SECRET})"

    assert SECRET not in r.redact(Obj())


def test_depth_limit() -> None:
    deep: dict[str, object] = {}
    cur = deep
    for _ in range(30):
        nxt: dict[str, object] = {}
        cur["k"] = nxt
        cur = nxt
    assert MASK in str(Redactor().redact(deep))

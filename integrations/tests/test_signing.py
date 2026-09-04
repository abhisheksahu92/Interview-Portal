"""The signature contract customers verify against."""

import json
import time

import pytest

from integrations import verify_signature
from integrations.signing import build_signature


def test_round_trip():
    body = json.dumps({"event": "application.hired"}).encode()
    signature = build_signature("s3cret", "1700000000", body)
    assert verify_signature("s3cret", "1700000000", body, signature)


def test_accepts_str_and_bytes_bodies_alike():
    body = '{"a":1}'
    signature = build_signature("s3cret", 1700000000, body)
    assert verify_signature("s3cret", "1700000000", body.encode(), signature)


@pytest.mark.parametrize(
    "secret,timestamp,body,signature",
    [
        ("wrong", "1700000000", b"{}", None),
        ("s3cret", "1700000001", b"{}", None),
        ("s3cret", "1700000000", b'{"tampered":true}', None),
        ("", "1700000000", b"{}", "deadbeef"),
    ],
)
def test_rejects_any_mismatch(secret, timestamp, body, signature):
    good = build_signature("s3cret", "1700000000", b"{}")
    assert not verify_signature(secret, timestamp, body, signature or good)


def test_rejects_missing_signature():
    assert not verify_signature("s3cret", "1", b"{}", "")


def test_max_age_rejects_stale_timestamp():
    body = b"{}"
    stale = str(int(time.time()) - 3600)
    signature = build_signature("s3cret", stale, body)
    assert verify_signature("s3cret", stale, body, signature)
    assert not verify_signature("s3cret", stale, body, signature, max_age_seconds=300)


def test_max_age_accepts_fresh_timestamp():
    now = str(int(time.time()))
    signature = build_signature("s3cret", now, b"{}")
    assert verify_signature("s3cret", now, b"{}", signature, max_age_seconds=300)


def test_max_age_rejects_unparseable_timestamp():
    signature = build_signature("s3cret", "not-a-time", b"{}")
    assert not verify_signature(
        "s3cret", "not-a-time", b"{}", signature, max_age_seconds=300
    )

"""Parser smoke tests."""

from pathlib import Path

from app.parser import _decode_cstr


def test_decode_cstr():
    assert _decode_cstr(b"hello\x00world") == "hello"

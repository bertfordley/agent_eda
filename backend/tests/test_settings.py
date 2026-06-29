"""
Unit tests for config/settings.py helper functions.

Tests the pure env-var parsing helpers (_parse_bool, _parse_int, _parse_float,
_parse_mcp_servers) in isolation. These helpers are module-level functions,
so they can be imported and called directly without constructing Settings.

The Settings singleton itself is not reconstructed here — that runs at module
import time and is already tested implicitly by every test file that imports
config.settings (via conftest.py's env-var setup).
"""

from __future__ import annotations

import json

import pytest

from config.settings import _parse_bool, _parse_float, _parse_int, _parse_mcp_servers


# ── _parse_bool ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "YES", "ON", "True"])
def test_parse_bool_truthy(monkeypatch, val):
    monkeypatch.setenv("_TEST_BOOL", val)
    assert _parse_bool("_TEST_BOOL", "false") is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "FALSE", "NO", "OFF"])
def test_parse_bool_falsy(monkeypatch, val):
    monkeypatch.setenv("_TEST_BOOL", val)
    assert _parse_bool("_TEST_BOOL", "true") is False


def test_parse_bool_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("_TEST_BOOL", raising=False)
    assert _parse_bool("_TEST_BOOL", "true") is True
    assert _parse_bool("_TEST_BOOL", "false") is False


# ── _parse_int ────────────────────────────────────────────────────────────────


def test_parse_int_valid(monkeypatch):
    monkeypatch.setenv("_TEST_INT", "42")
    assert _parse_int("_TEST_INT", "0") == 42


def test_parse_int_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("_TEST_INT", raising=False)
    assert _parse_int("_TEST_INT", "99") == 99


def test_parse_int_invalid_raises(monkeypatch):
    monkeypatch.setenv("_TEST_INT", "not_a_number")
    with pytest.raises(ValueError, match="_TEST_INT"):
        _parse_int("_TEST_INT", "0")


def test_parse_int_float_string_raises(monkeypatch):
    monkeypatch.setenv("_TEST_INT", "3.14")
    with pytest.raises(ValueError, match="_TEST_INT"):
        _parse_int("_TEST_INT", "0")


# ── _parse_float ──────────────────────────────────────────────────────────────


def test_parse_float_valid(monkeypatch):
    monkeypatch.setenv("_TEST_FLOAT", "3.14")
    assert _parse_float("_TEST_FLOAT", "0.0") == pytest.approx(3.14)


def test_parse_float_integer_string(monkeypatch):
    monkeypatch.setenv("_TEST_FLOAT", "2")
    assert _parse_float("_TEST_FLOAT", "0.0") == pytest.approx(2.0)


def test_parse_float_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("_TEST_FLOAT", raising=False)
    assert _parse_float("_TEST_FLOAT", "1.5") == pytest.approx(1.5)


def test_parse_float_invalid_raises(monkeypatch):
    monkeypatch.setenv("_TEST_FLOAT", "not_a_float")
    with pytest.raises(ValueError, match="_TEST_FLOAT"):
        _parse_float("_TEST_FLOAT", "0.0")


# ── _parse_mcp_servers ────────────────────────────────────────────────────────


def test_parse_mcp_servers_empty_when_unset(monkeypatch):
    monkeypatch.delenv("MCP_SERVERS", raising=False)
    assert _parse_mcp_servers("MCP_SERVERS") == []


def test_parse_mcp_servers_empty_string(monkeypatch):
    monkeypatch.setenv("MCP_SERVERS", "")
    assert _parse_mcp_servers("MCP_SERVERS") == []


def test_parse_mcp_servers_valid_single(monkeypatch):
    servers = [{"name": "kb", "url": "https://kb.internal/mcp"}]
    monkeypatch.setenv("MCP_SERVERS", json.dumps(servers))
    result = _parse_mcp_servers("MCP_SERVERS")
    assert result == servers


def test_parse_mcp_servers_valid_multiple(monkeypatch):
    servers = [
        {"name": "kb", "url": "https://kb.internal/mcp"},
        {"name": "search", "url": "https://search.internal/mcp", "transport": "streamable_http"},
    ]
    monkeypatch.setenv("MCP_SERVERS", json.dumps(servers))
    result = _parse_mcp_servers("MCP_SERVERS")
    assert len(result) == 2
    assert result[0]["name"] == "kb"


def test_parse_mcp_servers_invalid_json_raises(monkeypatch):
    monkeypatch.setenv("MCP_SERVERS", "{not valid json")
    with pytest.raises(ValueError, match="not valid JSON"):
        _parse_mcp_servers("MCP_SERVERS")


def test_parse_mcp_servers_not_a_list_raises(monkeypatch):
    monkeypatch.setenv("MCP_SERVERS", '{"name": "kb", "url": "https://kb.internal/mcp"}')
    with pytest.raises(ValueError, match="JSON list"):
        _parse_mcp_servers("MCP_SERVERS")


def test_parse_mcp_servers_missing_url_raises(monkeypatch):
    servers = [{"name": "kb"}]  # missing "url"
    monkeypatch.setenv("MCP_SERVERS", json.dumps(servers))
    with pytest.raises(ValueError, match="'url'"):
        _parse_mcp_servers("MCP_SERVERS")


def test_parse_mcp_servers_missing_name_raises(monkeypatch):
    servers = [{"url": "https://kb.internal/mcp"}]  # missing "name"
    monkeypatch.setenv("MCP_SERVERS", json.dumps(servers))
    with pytest.raises(ValueError, match="'name'"):
        _parse_mcp_servers("MCP_SERVERS")

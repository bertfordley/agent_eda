"""
tests/test_sanitize_client_history.py
──────────────────────────────────────────────────────────────────────────────
Unit tests for sanitize_client_history().

The function lives in history.py and has no external dependencies, so no
mocking or environment setup is required.
"""

from history import sanitize_client_history


# ── empty input ───────────────────────────────────────────────────────────────


def test_empty_list_returns_empty():
    assert sanitize_client_history([]) == []


# ── content filtering ─────────────────────────────────────────────────────────


def test_drops_empty_content_string():
    assert sanitize_client_history([{"role": "user", "content": ""}]) == []


def test_drops_whitespace_only_content():
    assert sanitize_client_history([{"role": "assistant", "content": "   \t\n  "}]) == []


def test_drops_none_content():
    assert sanitize_client_history([{"role": "user", "content": None}]) == []


def test_drops_missing_content_key():
    assert sanitize_client_history([{"role": "user"}]) == []


# ── field stripping ───────────────────────────────────────────────────────────


def test_strips_extra_fields():
    # Arrange
    raw = [
        {
            "role": "user",
            "content": "hello",
            "id": "msg_123",
            "status": "complete",
            "artifactIds": ["art_456"],
            "createdAt": 1700000000,
        }
    ]

    # Act
    result = sanitize_client_history(raw)

    # Assert
    assert result == [{"role": "user", "content": "hello"}]
    assert "id" not in result[0]
    assert "status" not in result[0]
    assert "artifactIds" not in result[0]
    assert "createdAt" not in result[0]


def test_output_contains_only_role_and_content_keys():
    raw = [{"role": "assistant", "content": "answer", "extra": "noise"}]
    result = sanitize_client_history(raw)
    assert set(result[0].keys()) == {"role", "content"}


# ── role values ───────────────────────────────────────────────────────────────


def test_user_role_passes_through():
    raw = [{"role": "user", "content": "what is the total?"}]
    assert sanitize_client_history(raw) == [{"role": "user", "content": "what is the total?"}]


def test_assistant_role_passes_through():
    raw = [{"role": "assistant", "content": "The total is 42."}]
    assert sanitize_client_history(raw) == [{"role": "assistant", "content": "The total is 42."}]


# ── ordering and mixed inputs ─────────────────────────────────────────────────


def test_preserves_message_order():
    # Arrange
    raw = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ]

    # Act
    result = sanitize_client_history(raw)

    # Assert
    assert [m["content"] for m in result] == ["first", "second", "third"]
    assert [m["role"] for m in result] == ["user", "assistant", "user"]


def test_drops_empty_turns_while_keeping_valid_ones():
    # Arrange — a realistic history with some failed/empty assistant turns
    raw = [
        {"role": "user", "content": "valid first"},
        {"role": "assistant", "content": ""},           # dropped: empty
        {"role": "assistant", "content": "valid reply"},
        {"role": "user", "content": "  "},              # dropped: whitespace
        {"role": "user", "content": "valid last"},
    ]

    # Act
    result = sanitize_client_history(raw)

    # Assert
    assert result == [
        {"role": "user", "content": "valid first"},
        {"role": "assistant", "content": "valid reply"},
        {"role": "user", "content": "valid last"},
    ]


def test_strips_leading_trailing_whitespace_from_content():
    raw = [{"role": "user", "content": "  hello world  "}]
    assert sanitize_client_history(raw) == [{"role": "user", "content": "hello world"}]


def test_single_valid_message_returned_as_list():
    raw = [{"role": "user", "content": "hi"}]
    result = sanitize_client_history(raw)
    assert isinstance(result, list)
    assert len(result) == 1


def test_all_messages_dropped_returns_empty():
    raw = [
        {"role": "user", "content": ""},
        {"role": "assistant", "content": None},
        {"role": "user", "content": "\n"},
    ]
    assert sanitize_client_history(raw) == []

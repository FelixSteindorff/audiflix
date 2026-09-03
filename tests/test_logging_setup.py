"""Tests for log redaction.

A URL with a token in it must never reach the log file - the log is a plain
text file that users routinely attach to bug reports.
"""

import logging

from audiflix.logging_setup import RedactingFilter, redact


def test_redacts_a_token_query_parameter():
    assert redact("GET https://h/x?token=abc123") == "GET https://h/x?token=<redacted>"


def test_redacts_a_token_in_the_middle_of_a_query():
    result = redact("https://h/x?token=abc123&foo=bar")
    assert "abc123" not in result
    assert "foo=bar" in result


def test_redacts_bearer_headers():
    assert "eyJhbGciOi" not in redact("Authorization: Bearer eyJhbGciOi.J9.sig")


def test_redacts_refresh_token_headers():
    assert "r3fr3sh" not in redact("x-refresh-token: r3fr3sh")


def test_leaves_ordinary_text_alone():
    assert redact("Loaded 12 items from library lib1") == "Loaded 12 items from library lib1"


def test_filter_redacts_the_message_and_arguments():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="playing %s", args=("https://h/x?token=abc123",), exc_info=None,
    )
    RedactingFilter().filter(record)
    assert "abc123" not in record.getMessage()

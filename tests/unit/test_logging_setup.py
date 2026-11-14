"""Tests for secret redaction in logging."""

import io
import logging

from papersonar.logging_setup import RedactingFormatter, redact_text, setup_logging

SECRET = "super-secret-value-123"
PEM = "-----BEGIN PRIVATE KEY-----\nMIIEvQIB\n-----END PRIVATE KEY-----"


class TestRedactText:
    def test_exact_secret_replaced(self):
        assert redact_text(f"token {SECRET} leaked", [SECRET]) == "token ***REDACTED*** leaked"

    def test_api_key_param(self):
        assert redact_text("GET /works?api_key=abc123&page=2", []) == "GET /works?***REDACTED***&page=2"

    def test_authorization_header(self):
        assert redact_text("Authorization: Bearer abc.def.ghi", []) == "***REDACTED***"

    def test_pem_block_multiline(self):
        out = redact_text(f"key material:\n{PEM}\nend", [])
        assert "MIIEvQIB" not in out
        assert "***REDACTED***" in out

    def test_resumption_token_not_redacted(self):
        text = "oai resumption_token=abc123/def continues"
        assert redact_text(text, []) == text

    def test_cursor_not_redacted(self):
        text = "cursor=eyJvYWxleF9pZCI6InczIn0="
        assert redact_text(text, []) == text

    def test_short_secrets_ignored(self):
        assert redact_text("abc here", ["abc"]) == "abc here"


class TestRedactingFormatter:
    def test_format_redacts_message_and_args(self):
        formatter = RedactingFormatter("%(message)s", secrets=[SECRET])
        record = logging.LogRecord(
            name="t", level=logging.INFO, pathname=__file__, lineno=1,
            msg="key=%s status=%s", args=(SECRET, "ok"), exc_info=None,
        )
        out = formatter.format(record)
        assert SECRET not in out
        assert "ok" in out

    def test_format_redacts_traceback(self):
        formatter = RedactingFormatter("%(message)s", secrets=[SECRET])
        try:
            raise ValueError(f"connect failed with {SECRET}")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="t", level=logging.ERROR, pathname=__file__, lineno=1,
                msg="failure", args=(), exc_info=sys.exc_info(),
            )
        out = formatter.format(record)
        assert SECRET not in out


class TestSetupLogging:
    def test_setup_logging_installs_redacting_handler(self, capsys):
        import sys

        stream = io.StringIO()
        handler_holder = []

        import logging as _logging

        original_stderr = sys.stderr
        sys.stderr = stream
        try:
            setup_logging("INFO", [SECRET])
            handler_holder.extend(_logging.getLogger().handlers)
            _logging.getLogger().info("openalex api_key=%s", "abcdef123456")
        finally:
            sys.stderr = original_stderr
        assert "abcdef123456" not in stream.getvalue()
        assert "***REDACTED***" in stream.getvalue()

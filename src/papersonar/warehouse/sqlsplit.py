"""SQL statement splitting that understands Snowflake syntax.

Splitting a script naively on ``;`` is wrong in two ways that bit us on a live
Snowflake account:

1. A trailing comment block after the last ``;`` becomes a statement of pure
   comments — Snowflake rejects it with ``000900 (42601): Empty SQL statement``.
2. Semicolons inside string literals (e.g. ``COMMENT = 'a; b'``), inside
   ``--`` / ``/* */`` comments, inside quoted identifiers, or inside
   ``$$ ... $$`` dollar-quoted constants split statements mid-literal.

``split_sql_statements`` is a small state machine that respects all of the
above and yields only statements with actual content (empty and comment-only
chunks are dropped). Used by both the real adapter and the test mock so they
cannot diverge.
"""

from __future__ import annotations

_DEFAULT = "default"
_STRING = "string"
_QUOTED_IDENTIFIER = "quoted_identifier"
_DOLLAR = "dollar"


def split_sql_statements(sql_text: str) -> list[str]:
    """Split a SQL script into statements, dropping empty/comment-only chunks."""
    statements: list[str] = []
    current: list[str] = []
    content_seen = False
    state = _DEFAULT
    i = 0
    n = len(sql_text)

    def flush() -> None:
        nonlocal current, content_seen
        text = "".join(current).strip()
        if text and content_seen:
            statements.append(text)
        current = []
        content_seen = False

    while i < n:
        ch = sql_text[i]
        nxt = sql_text[i + 1] if i + 1 < n else ""

        if state == _DEFAULT:
            if ch == "'" and nxt == "'":  # escaped quote inside nothing — literal '' pair
                current.append("''")
                content_seen = True
                i += 2
                continue
            if ch == "'":
                state = _STRING
                content_seen = True
                current.append(ch)
            elif ch == '"':
                state = _QUOTED_IDENTIFIER
                content_seen = True
                current.append(ch)
            elif ch == "-" and nxt == "-":  # line comment: keep text, not content
                current.append(sql_text[i : _line_comment_end(sql_text, i)])
                i = _line_comment_end(sql_text, i)
                continue
            elif ch == "/" and nxt == "*":  # block comment: keep text, not content
                end = _block_comment_end(sql_text, i)
                current.append(sql_text[i:end])
                i = end
                continue
            elif ch == "$" and nxt == "$":
                state = _DOLLAR
                content_seen = True
                current.append("$$")
                i += 2
                continue
            elif ch == ";":
                flush()
            elif not ch.isspace():
                content_seen = True
                current.append(ch)
            else:
                current.append(ch)
        elif state == _STRING:
            if ch == "'" and nxt == "'":
                current.append("''")
                i += 2
                continue
            if ch == "'":
                state = _DEFAULT
            current.append(ch)
        elif state == _QUOTED_IDENTIFIER:
            if ch == '"' and nxt == '"':
                current.append('""')
                i += 2
                continue
            if ch == '"':
                state = _DEFAULT
            current.append(ch)
        else:  # _DOLLAR
            if ch == "$" and nxt == "$":
                current.append("$$")
                state = _DEFAULT
                i += 2
                continue
            current.append(ch)
        i += 1

    flush()  # final statement without trailing ';'
    return statements


def _line_comment_end(sql_text: str, start: int) -> int:
    """Index just past a ``--`` comment's final newline (not consuming it)."""
    i = sql_text.find("\n", start)
    return i if i != -1 else len(sql_text)


def _block_comment_end(sql_text: str, start: int) -> int:
    """Index just past a ``/* ... */`` block comment's terminator."""
    end = sql_text.find("*/", start + 2)
    return len(sql_text) if end == -1 else end + 2

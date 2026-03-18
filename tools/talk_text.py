# utils/talk_text.py
"""
Utility functions for retrieving talk text from the content database.
These functions can be used by multiple MCP tools in /tools.
"""

from db import content_db


def get_talk_textsimple(talk_id: int) -> str:
    """Read plain text from talkbody.TextSimple.

    Behavior:
    - Returns the exact contents of TextSimple as a Python str.
    - Returns an empty string when the row is missing or TextSimple is NULL/empty.
    - No fallbacks to other Text* columns or legacy compressed Text.

    Args:
        talk_id: The talk ID to retrieve text for

    Returns:
        The text content or empty string if not found
    """
    row = content_db.select_one(
        "SELECT TextSimple FROM talkbody WHERE TalkID = ?", (talk_id,)
    )

    if not row:
        return ""

    value = row.get("TextSimple")
    if value is None:
        return ""

    # Ensure str, and treat whitespace-only as empty
    text = str(value)
    return text if text.strip() != "" else ""


def get_talk_textraw(talk_id: int) -> str:
    """Placeholder accessor for talkbody.TextRaw (not used yet). Returns empty string if unset.
    This is provided to document intended symmetry with TextSimple/TextMinimal/TextEnhanced.

    Args:
        talk_id: The talk ID to retrieve text for

    Returns:
        The raw text content or empty string if not found
    """
    row = content_db.select_one(
        "SELECT TextRaw FROM talkbody WHERE TalkID = ?", (talk_id,)
    )

    if not row:
        return ""

    value = row.get("TextRaw")
    if value is None:
        return ""

    text = str(value)
    return text if text.strip() != "" else ""


def get_talk_textminimal(talk_id: int) -> str:
    """Placeholder accessor for talkbody.TextMinimal (not used yet). Returns empty string if unset.

    Args:
        talk_id: The talk ID to retrieve text for

    Returns:
        The minimal text content or empty string if not found
    """
    row = content_db.select_one(
        "SELECT TextMinimal FROM talkbody WHERE TalkID = ?", (talk_id,)
    )

    if not row:
        return ""

    value = row.get("TextMinimal")
    if value is None:
        return ""

    text = str(value)
    return text if text.strip() != "" else ""


def get_talk_textenhanced(talk_id: int) -> str:
    """Placeholder accessor for talkbody.TextEnhanced (not used yet). Returns empty string if unset.

    Args:
        talk_id: The talk ID to retrieve text for

    Returns:
        The enhanced text content or empty string if not found
    """
    row = content_db.select_one(
        "SELECT TextEnhanced FROM talkbody WHERE TalkID = ?", (talk_id,)
    )

    if not row:
        return ""

    value = row.get("TextEnhanced")
    if value is None:
        return ""

    text = str(value)
    return text if text.strip() != "" else ""

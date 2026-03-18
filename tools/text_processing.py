# utils/text_processing.py
"""
Utility functions for text processing, searching, and windowing.
Used by tools that need to find and extract context windows around search terms.
"""

from typing import Optional, List, Dict, Any


def find_all_occurrences(haystack_lower: str, needle_lower: str) -> List[int]:
    """Find all occurrences of a needle in a haystack (case-insensitive).

    Args:
        haystack_lower: The text to search in (already lowercased)
        needle_lower: The pattern to find (already lowercased)

    Returns:
        List of start positions where the needle was found
    """
    if not needle_lower:
        return []
    positions = []
    start = 0
    while True:
        idx = haystack_lower.find(needle_lower, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def build_windows(
    text: str,
    match_positions: List[int],
    match_len: int,
    window_chars: int = 1000
) -> List[Dict[str, Any]]:
    """Build rolling context windows around match positions, merging overlaps.

    Args:
        text: The full text to extract windows from
        match_positions: List of positions where matches were found
        match_len: Length of the matched pattern
        window_chars: Total window size (default 1000)

    Returns:
        List of window dictionaries with pre_text, match_text, post_text, etc.
    """
    if not text:
        return []
    half = max(0, window_chars // 2)
    windows = []
    for pos in match_positions:
        start = max(0, pos - half)
        end = min(len(text), pos + match_len + half)
        windows.append((start, end, pos, pos + match_len))

    # Merge overlapping windows
    if not windows:
        return []
    windows.sort(key=lambda w: (w[0], w[1]))
    merged = []
    cur_s, cur_e, cur_ms, cur_me = windows[0]
    for s, e, ms, me in windows[1:]:
        if s <= cur_e:  # overlap
            cur_e = max(cur_e, e)
            # keep match bounds as-is; they are informational only
        else:
            merged.append((cur_s, cur_e, cur_ms, cur_me))
            cur_s, cur_e, cur_ms, cur_me = s, e, ms, me
    merged.append((cur_s, cur_e, cur_ms, cur_me))

    result = []
    for s, e, ms, me in merged:
        pre_text = text[s:ms]
        match_text = text[ms:me]
        post_text = text[me:e]
        result.append({
            "start": s,
            "end": e,
            "pre_text": pre_text,
            "match_text": match_text,
            "post_text": post_text,
            "match_type": "text",
            "confidence": 0.5
        })
    return result


def format_speaker_name(given_names: Optional[str], last_names: Optional[str]) -> str:
    """Format speaker name from given and last names.

    Args:
        given_names: Speaker's given names (can be None)
        last_names: Speaker's last names (can be None)

    Returns:
        Formatted name or "Unknown" if both are None/empty
    """
    parts = []
    if given_names:
        parts.append(given_names)
    if last_names:
        parts.append(last_names)
    return " ".join(parts) if parts else "Unknown"

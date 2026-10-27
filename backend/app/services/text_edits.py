"""Locating and replacing passages of text in a document."""

import re


class PassageError(ValueError):
    """Raised when a passage cannot be located exactly once."""


def locate_passage(content: str, original: str) -> tuple[int, int]:
    """Return the start and end offsets of the single occurrence of ``original``.

    An exact match is attempted first. If there is none, runs of whitespace are treated as
    equivalent, so a passage still matches after line wrapping or indentation has changed.
    """
    if not original.strip():
        raise PassageError("The original passage is empty.")

    matches = _exact_matches(content, original) or _whitespace_insensitive_matches(
        content, original
    )
    if not matches:
        raise PassageError("The original passage was not found in the document.")
    if len(matches) > 1:
        raise PassageError(
            f"The original passage occurs {len(matches)} times. Include more of the surrounding "
            "text so it is unique."
        )
    return matches[0]


def replace_passage(content: str, original: str, replacement: str) -> str:
    start, end = locate_passage(content, original)
    return content[:start] + replacement + content[end:]


def _exact_matches(content: str, original: str) -> list[tuple[int, int]]:
    matches = []
    index = content.find(original)
    while index != -1:
        matches.append((index, index + len(original)))
        index = content.find(original, index + 1)
    return matches


def _whitespace_insensitive_matches(content: str, original: str) -> list[tuple[int, int]]:
    pattern = r"\s+".join(re.escape(word) for word in original.split())
    return [match.span() for match in re.finditer(pattern, content)]

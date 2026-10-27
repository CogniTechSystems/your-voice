"""Reading documents out of tool calls that are still being generated.

While the model streams a ``write_document`` call, its arguments are incomplete JSON. Extracting
the string values received so far lets the interface show the document as it is written.
"""

import re
from dataclasses import dataclass

from app.services.llm_client import Progress

ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
UNICODE_ESCAPE_LENGTH = 4


@dataclass(frozen=True)
class LiveWrite:
    path: str
    content: str


def partial_string_argument(arguments: str, name: str) -> str | None:
    """Decode the value of string argument ``name`` from possibly unterminated JSON text."""
    match = re.search(rf'"{re.escape(name)}"\s*:\s*"', arguments)
    if match is None:
        return None
    characters: list[str] = []
    index = match.end()
    while index < len(arguments):
        character = arguments[index]
        if character == '"':
            break
        if character != "\\":
            characters.append(character)
            index += 1
            continue
        if index + 1 >= len(arguments):
            break
        code = arguments[index + 1]
        if code == "u":
            decoded = _unicode_escape(arguments, index)
            if decoded is None:
                break
            text, length = decoded
            characters.append(text)
            index += length
            continue
        characters.append(ESCAPES.get(code, code))
        index += 2
    return "".join(characters)


def _unicode_escape(arguments: str, index: int) -> tuple[str, int] | None:
    """Decode the ``\\uXXXX`` escape at ``index``, joining surrogate pairs.

    Returns the text and the number of characters consumed, or ``None`` if the escape has not
    been received completely. Invalid or unpaired escapes decode to an empty string.
    """
    escape_length = 2 + UNICODE_ESCAPE_LENGTH
    digits = arguments[index + 2 : index + escape_length]
    if len(digits) < UNICODE_ESCAPE_LENGTH:
        return None
    try:
        code = int(digits, 16)
    except ValueError:
        return "", escape_length
    if not 0xD800 <= code <= 0xDFFF:
        return chr(code), escape_length
    if code > 0xDBFF:
        return "", escape_length

    low = arguments[index + escape_length : index + 2 * escape_length]
    if len(low) < escape_length:
        return None
    try:
        low_code = int(low[2:], 16) if low.startswith("\\u") else -1
    except ValueError:
        low_code = -1
    if not 0xDC00 <= low_code <= 0xDFFF:
        return "", escape_length
    combined = 0x10000 + ((code - 0xD800) << 10) + (low_code - 0xDC00)
    return chr(combined), 2 * escape_length


def live_write(progress: Progress) -> LiveWrite | None:
    """The document being written by the latest streamed ``write_document`` call, if any."""
    for call in reversed(progress.tool_calls):
        if call.name != "write_document":
            continue
        path = partial_string_argument(call.arguments, "path")
        content = partial_string_argument(call.arguments, "content")
        if path is None or content is None:
            return None
        return LiveWrite(path=path.strip(), content=content)
    return None

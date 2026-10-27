import json

import pytest

from app.services.agent.live import LiveWrite, live_write, partial_string_argument
from app.services.llm_client import Progress, ToolCall


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ('{"content": "Hello', "Hello"),
        ('{"content": "Hello"}', "Hello"),
        ('{"content": "Line one\\nLine', "Line one\nLine"),
        ('{"content": "Say \\"hi\\" now', 'Say "hi" now'),
        ('{"content": "Trailing \\', "Trailing "),
        ('{"content": "Caf\\u00e9', "Café"),
        ('{"content": "Caf\\u00', "Caf"),
        ('{"content": "Rocket \\ud83d\\ude80!', "Rocket 🚀!"),
        ('{"content": "Rocket \\ud83d', "Rocket "),
        ('{"path": "a.md"', None),
    ],
)
def test_partial_string_argument(arguments: str, expected: str | None):
    assert partial_string_argument(arguments, "content") == expected


def test_complete_arguments_decode_like_json():
    text = 'Quotes " and \\ backslashes,\ttabs and émoji 🎉'
    arguments = json.dumps({"path": "a.md", "content": text})
    assert partial_string_argument(arguments, "content") == text


def test_live_write_uses_the_latest_write_call():
    progress = Progress(
        reasoning="",
        content="",
        tool_calls=(
            ToolCall("1", "write_document", '{"path": "a.md", "content": "Done"}'),
            ToolCall("2", "write_document", '{"path": "b.html", "content": "<h1>Dra'),
        ),
    )
    assert live_write(progress) == LiveWrite(path="b.html", content="<h1>Dra")


def test_live_write_ignores_other_tools_and_incomplete_paths():
    assert live_write(Progress("", "", (ToolCall("1", "read_sample", "{}"),))) is None
    assert live_write(Progress("", "", (ToolCall("1", "write_document", '{"pa'),))) is None

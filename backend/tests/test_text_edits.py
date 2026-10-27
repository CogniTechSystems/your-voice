import pytest

from app.services.text_edits import PassageError, locate_passage, replace_passage

ARTICLE = """# Shipping small

We ship small changes because they are
easy to review and easy to undo.

Small changes are easy to review.
"""


def test_exact_replacement():
    revised = replace_passage(ARTICLE, "# Shipping small", "# Ship small, ship often")
    assert revised.startswith("# Ship small, ship often\n")


def test_whitespace_differences_are_tolerated():
    revised = replace_passage(
        ARTICLE, "they are easy to review and easy to undo.", "they are cheap to undo."
    )
    assert "We ship small changes because they are cheap to undo.\n" in revised


def test_ambiguous_passage_is_rejected():
    with pytest.raises(PassageError, match="occurs 2 times"):
        locate_passage(ARTICLE, "easy to review")


def test_missing_passage_is_rejected():
    with pytest.raises(PassageError, match="not found"):
        replace_passage(ARTICLE, "not present", "anything")


def test_empty_passage_is_rejected():
    with pytest.raises(PassageError, match="empty"):
        locate_passage(ARTICLE, "   ")

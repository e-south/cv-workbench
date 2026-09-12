from subprocess import CompletedProcess

import pytest

from cvworkbench.ops.review import ReviewError, markdown


@pytest.mark.parametrize(
    ("help_text", "flag"),
    [
        ("--markdown-headings=setext|atx", "--markdown-headings=atx"),
        ("--markdown-headings --atx-headers", "--markdown-headings=atx"),
        ("--atx-headers", "--atx-headers"),
    ],
)
def test_review_conversion_uses_supported_heading_option(monkeypatch, help_text, flag):
    monkeypatch.setattr(markdown.shutil, "which", lambda _: "/tools/pandoc")

    def run(command, **kwargs):
        if command == ["/tools/pandoc", "--help"]:
            return CompletedProcess(command, 0, stdout=help_text, stderr="")
        if flag not in command:
            return CompletedProcess(command, 2, stdout="", stderr="Unknown heading option")
        assert kwargs["input"] == "# Example\n"
        return CompletedProcess(command, 0, stdout="# Example\n", stderr="")

    monkeypatch.setattr(markdown.subprocess, "run", run)
    assert markdown.normalize_markdown("# Example\n") == "# Example\n"


def test_review_rejects_unknown_pandoc_options_before_conversion(monkeypatch):
    monkeypatch.setattr(markdown.shutil, "which", lambda _: "/tools/pandoc")

    def run(command, **kwargs):
        assert command == ["/tools/pandoc", "--help"]
        return CompletedProcess(command, 0, stdout="unexpected executable", stderr="")

    monkeypatch.setattr(markdown.subprocess, "run", run)
    with pytest.raises(ReviewError, match="heading option"):
        markdown.normalize_markdown("# Example\n")

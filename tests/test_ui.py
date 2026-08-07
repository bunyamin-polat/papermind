"""The UI's two testable parts: the boundary it must not cross, and the citation
linking. Streamlit rendering itself is not tested — it is the least load-bearing
code in the repo and a browser is the honest way to check it."""

import ast
from pathlib import Path

import pytest

UI_DIR = Path(__file__).parent.parent / "ui"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("path", sorted(UI_DIR.glob("*.py")), ids=lambda p: p.name)
def test_ui_never_imports_the_backend(path):
    """The boundary step 7 exists to create.

    Importing `retrieval` or `app` here would work — same repo, same interpreter —
    and would make the API decorative: untested by anything a user touches, and at
    step 9 a container with two entrypoints pretending to be one. The UI is an HTTP
    client, including when both run on the same machine.
    """
    forbidden = {"retrieval", "app", "storage", "ingestion", "evaluation", "core"}
    assert not (_imports(path) & forbidden), f"{path.name} imports the backend directly"


def test_citation_linking_maps_markers_to_their_own_paper():
    import sys

    sys.path.insert(0, str(UI_DIR))
    from Home import link_citations

    sources = [
        {"marker": 1, "url": "https://arxiv.org/abs/1111.1111"},
        {"marker": 2, "url": "https://arxiv.org/abs/2222.2222"},
    ]
    linked = link_citations("First [1], then [2].", sources)
    assert "[[1]](https://arxiv.org/abs/1111.1111)" in linked
    assert "[[2]](https://arxiv.org/abs/2222.2222)" in linked


def test_unmapped_markers_are_left_as_plain_text():
    """The API drops invented citations before they reach the UI, so `[9]` should
    never arrive. If it ever does, showing it unlinked is better than crashing or
    linking it to the wrong paper."""
    import sys

    sys.path.insert(0, str(UI_DIR))
    from Home import link_citations

    linked = link_citations("As shown in [9].", [{"marker": 1, "url": "https://x"}])
    assert linked == "As shown in [9]."

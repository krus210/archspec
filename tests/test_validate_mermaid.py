import pytest
from validate_mermaid import MermaidError, validate_mermaid_text


def test_valid_flowchart_passes():
    text = "flowchart LR\n  a-->b\n"
    validate_mermaid_text(text)


def test_unknown_diagram_type_fails():
    with pytest.raises(MermaidError, match="unknown diagram type"):
        validate_mermaid_text("randomGraph TB\n  a-->b\n")


def test_empty_text_fails():
    with pytest.raises(MermaidError, match="empty"):
        validate_mermaid_text("")


def test_unbalanced_subgraph_fails():
    text = "flowchart LR\n  subgraph s\n    a-->b\n"
    with pytest.raises(MermaidError, match="unbalanced subgraph"):
        validate_mermaid_text(text)

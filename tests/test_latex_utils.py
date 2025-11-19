import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.utils import latex_to_plain, render_inline_math_html


def test_latex_to_plain_bar_combiner():
    assert latex_to_plain(r"\bar{w}") == "w\u0304"


def test_render_inline_math_html_preserves_bar():
    html, has_math = render_inline_math_html(r"$\bar{w}$")
    assert has_math
    assert "w\u0304" in html

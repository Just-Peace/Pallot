"""A swipe sideways in Details (swipe.js) steps to the next or the previous candidate; a vertical
scroll, a short move or a slow drag doesn't. Run in Node, which loads the module as the browser does."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pallot.api import STATIC_DIR

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

MODULE = (STATIC_DIR / "js" / "swipe.js").as_uri()


def test_a_swipe_left_is_the_next_and_right_the_previous_and_the_rest_are_nothing():
    moves = [
        (-120, 10, 200),  # left: the next
        (120, -20, 300),  # right: the previous
        (-40, 0, 100),  # too short
        (-100, 80, 200),  # mostly a scroll
        (0, -300, 200),  # a scroll
        (-200, 0, 1500),  # a slow drag
    ]
    source = f'const m = await import("{MODULE}");\nconsole.log(JSON.stringify({json.dumps(moves)}.map((a) => m.swipeStep(...a))));'
    done = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    assert json.loads(done.stdout) == [1, -1, 0, 0, 0, 0]

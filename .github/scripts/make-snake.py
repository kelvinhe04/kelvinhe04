"""Contribution snake that never leaves the grid.

Platane/snk lets the snake wander outside the contribution grid to take
shortcuts. This generator keeps the organic, varied routes (always heading for
the nearest contribution, random tie-breaks, seeded by the date so it changes
every day) but the snake only ever moves on the grid cells.

usage: make-snake.py OUT.svg [--data contributions.json] [--seed N]
  Without --data the calendar is fetched with $GITHUB_TOKEN for $SNAKE_USER
  (or $GITHUB_ACTOR).
"""
import datetime
import json
import os
import random
import sys
import urllib.request
from collections import deque

PITCH, CELL = 16, 12
EMPTY = "#171b21"
LEVELS = {  # contribution level -> color
    "NONE": EMPTY,
    "FIRST_QUARTILE": "#214d3c",
    "SECOND_QUARTILE": "#347659",
    "THIRD_QUARTILE": "#55b685",
    "FOURTH_QUARTILE": "#6ad09d",
}
ORDER = list(LEVELS)
SNAKE = "#64d0ea"
SEGMENTS = [(14.4, 4.5), (12.3, 4.1), (10.8, 3.6), (9.9, 3.3)]  # (size, radius)
STEP = 0.11       # seconds per cell
HOLD = 2.5        # pause at the end before the loop restarts
BAR_Y = 144
LENGTH = len(SEGMENTS)

QUERY = """query($login:String!){user(login:$login){contributionsCollection{
contributionCalendar{weeks{contributionDays{weekday contributionLevel}}}}}}"""


def load_weeks(argv):
    if "--data" in argv:
        raw = json.load(open(argv[argv.index("--data") + 1], encoding="utf-8"))
    else:
        user = os.environ.get("SNAKE_USER") or os.environ["GITHUB_ACTOR"]
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": QUERY, "variables": {"login": user}}).encode(),
            headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
                     "User-Agent": "profile-snake"},
        )
        raw = json.load(urllib.request.urlopen(req))
    return raw["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]


def plan_route(level, cols, rng):
    """Walk to the nearest uneaten contribution, never leaving the grid or
    biting the body (length 4). Returns (path, {cell: first step that eats it})."""
    targets = {(c, r) for c in range(cols) for r in range(7) if level[c][r] != "NONE"}
    path = [(0, 0)]
    eaten_at = {}
    if (0, 0) in targets:
        eaten_at[(0, 0)] = 0
        targets.discard((0, 0))

    def neighbours(cell):
        c, r = cell
        out = [(c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)]
        rng.shuffle(out)
        return [(x, y) for x, y in out if 0 <= x < cols and 0 <= y < 7]

    def body_after(trail):
        return (path + list(trail))[-LENGTH:]

    guard = 0
    while targets and guard < 20000:
        guard += 1
        head = path[-1]
        best = None
        queue = deque([(head, ())])
        seen = {head}
        while queue:
            cell, trail = queue.popleft()
            if cell in targets and trail:
                best = trail
                break
            body = body_after(trail)
            for nxt in neighbours(cell):
                if nxt in seen or nxt in body[1:]:   # tail cell is freed by the move
                    continue
                seen.add(nxt)
                queue.append((nxt, trail + (nxt,)))
        if best is None:                              # boxed in: any free step
            body = body_after(())
            free = [x for x in neighbours(head) if x not in body[1:]]
            best = (free[0] if free else rng.choice(neighbours(head)),)
        for cell in best:
            path.append(cell)
            if cell in targets:
                eaten_at[cell] = len(path) - 1
                targets.discard(cell)
    return path, eaten_at


def main():
    out = sys.argv[1]
    weeks = load_weeks(sys.argv)
    cols = len(weeks)

    # full rectangle: days GitHub doesn't report (first/last week) are empty cells
    level = [["NONE"] * 7 for _ in range(cols)]
    for c, week in enumerate(weeks):
        for day in week["contributionDays"]:
            level[c][day["weekday"]] = day["contributionLevel"]

    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv         else int(datetime.date.today().strftime("%Y%m%d"))
    rng = random.Random(seed)
    path, eaten_at = plan_route(level, cols, rng)
    n = len(path)
    total = (n + 3) * STEP + HOLD

    def pct(t):
        return f"{t / total * 100:.3f}%"

    def px(cell):
        return f"translate({cell[0] * PITCH}px,{cell[1] * PITCH}px)"

    css, cells, bar = [], [], []

    # ---- cells: contribution color until the head arrives, then empty
    eaten = []  # (level index, k)
    for c in range(cols):
        for r in range(7):
            lv = level[c][r]
            style = f"fill:{LEVELS[lv]}"
            if lv != "NONE":
                k = eaten_at[(c, r)]
                t = k * STEP
                css.append(
                    f"@keyframes e{c}_{r}{{0%,{pct(t)}{{fill:{LEVELS[lv]}}}"
                    f"{pct(t + 0.02)},100%{{fill:{EMPTY}}}}}"
                )
                style += f";animation:e{c}_{r} {total:.2f}s linear infinite"
                eaten.append((ORDER.index(lv), k))
            cells.append(
                f'<rect x="{c * PITCH + 2}" y="{r * PITCH + 2}" width="{CELL}" height="{CELL}" '
                f'rx="2" ry="2" style="{style}"/>'
            )

    # ---- progress bar: one slice per eaten cell, grouped by level like snk
    width = cols * PITCH
    if eaten:
        slice_w = width / len(eaten)
        for slot, (lv, k) in enumerate(sorted(eaten)):
            t = k * STEP
            css.append(
                f"@keyframes b{slot}{{0%,{pct(t)}{{opacity:0}}{pct(t + 0.02)},100%{{opacity:1}}}}"
            )
            bar.append(
                f'<rect x="{slot * slice_w:.2f}" y="{BAR_Y}" width="{slice_w + 0.3:.2f}" height="12" '
                f'style="fill:{LEVELS[ORDER[lv]]};opacity:0;animation:b{slot} {total:.2f}s linear infinite"/>'
            )

    # ---- snake: segment i trails the head by i cells; fades at loop boundaries
    end = (n + 3) * STEP
    css.append(
        f"@keyframes v{{0%{{opacity:0}}{pct(0.4)}{{opacity:1}}{pct(end + HOLD * 0.55)}{{opacity:1}}"
        f"{pct(end + HOLD * 0.85)},100%{{opacity:0}}}}"
    )
    snake = []
    for i, (size, radius) in enumerate(SEGMENTS):
        stops = []
        for k in range(n + 3 + 1):
            cell = path[min(max(k - i, 0), n - 1)]
            stops.append(f"{pct(k * STEP)}{{transform:{px(cell)}}}")
        css.append(f"@keyframes s{i}{{{''.join(stops)}100%{{transform:{px(path[n - 1])}}}}}")
        off = (PITCH - size) / 2
        snake.append(
            f'<rect x="{off:.2f}" y="{off:.2f}" width="{size}" height="{size}" rx="{radius}" ry="{radius}" '
            f'style="fill:{SNAKE};transform:{px(path[0])};animation:s{i} {total:.2f}s linear infinite,v {total:.2f}s linear infinite"/>'
        )

    svg = (
        f'<svg viewBox="-16 -8 {width + 32} 168" width="{width + 32}" height="168" '
        f'xmlns="http://www.w3.org/2000/svg"><desc>Generated by make-snake.py</desc>'
        f'<style>{"".join(css)}</style>'
        f'{"".join(cells)}{"".join(bar)}{"".join(snake)}</svg>'
    )
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"{cols} weeks, {len(eaten)} contributions, loop {total:.1f}s, {len(svg) // 1024} KB")


main()

#!/usr/bin/env python3
"""Regenerate Images/README.md as a 3-column image gallery.

Ordering:
  1. Images whose creation time can be parsed from their filename
     (ChatGPT downloads, assets_task_*, gemini-3-pro-*), oldest first.
  2. nano-banana 3x3 grid sets, grouped by their shared UUID, row-major.
  3. Everything else: ordered by the date each file was first added to
     git history (oldest first), falling back to filename order for
     files git has no history for yet (e.g. newly added, uncommitted).

Run manually with `python3 scripts/generate_gallery.py`, or via the
"Update Gallery" GitHub Actions workflow (workflow_dispatch).
"""
import datetime
import glob
import os
import re
import subprocess
import unicodedata
import urllib.parse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(REPO_ROOT, "Images")
README_PATH = os.path.join(IMAGES_DIR, "README.md")
IMAGE_EXTS = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif")
COLS = 3

KST = datetime.timezone(datetime.timedelta(hours=9))
UTC = datetime.timezone.utc


def enc(filename):
    return urllib.parse.quote(filename)


def parse_chatgpt(filename):
    name = unicodedata.normalize("NFC", filename)
    m = re.search(
        r"(\d{4})년\s*(\d{2})월\s*(\d{2})일\s*(오전|오후)\s*(\d{2})_(\d{2})_(\d{2})",
        name,
    )
    if not m:
        return None
    y, mo, d, ampm, h, mi, s = m.groups()
    h = int(h)
    if ampm == "오후" and h != 12:
        h += 12
    if ampm == "오전" and h == 12:
        h = 0
    return datetime.datetime(int(y), int(mo), int(d), h, int(mi), int(s), tzinfo=KST)


def parse_assets_task(filename):
    m = re.search(r"assets_task_\w+_(\d{10})_img", filename)
    if not m:
        return None
    return datetime.datetime.fromtimestamp(int(m.group(1)), UTC)


def parse_gemini(filename):
    m = re.search(r"gemini-3-pro-(\d{13})", filename)
    if not m:
        return None
    return datetime.datetime.fromtimestamp(int(m.group(1)) / 1000, UTC)


def parse_nano_banana_grid(filename):
    return re.match(
        r"nano-banana-([0-9a-f]{8}-[0-9a-f-]+)_row(\d)_col(\d)\.\w+$", filename
    )


def git_first_added(filename):
    """Return the datetime a file was first committed, or None if untracked/no git."""
    try:
        out = subprocess.run(
            [
                "git", "log", "--diff-filter=A", "--follow",
                "--format=%aI", "--", os.path.join("Images", filename),
            ],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip().splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    if not out:
        return None
    return datetime.datetime.fromisoformat(out[-1])


def build_order(files):
    dated, undated = [], []
    for f in files:
        dt = parse_chatgpt(f) or parse_assets_task(f) or parse_gemini(f)
        (dated if dt else undated).append((dt, f))
    dated.sort(key=lambda x: x[0])

    grid_groups = {}
    rest = []
    for _, f in undated:
        m = parse_nano_banana_grid(f)
        if m:
            uid, r, c = m.group(1), int(m.group(2)), int(m.group(3))
            grid_groups.setdefault(uid, {})[(r, c)] = f
        else:
            rest.append(f)

    ordered = [f for _, f in dated]
    for uid in sorted(grid_groups):
        group = grid_groups[uid]
        for r in (1, 2, 3):
            for c in (1, 2, 3):
                f = group.get((r, c))
                if f:
                    ordered.append(f)

    # Remaining files (anything not matching a known pattern): order by
    # when git first saw them, oldest first; brand-new/untracked files
    # (no git history yet) sort after known-dated ones, alphabetically.
    rest_dated = [(git_first_added(f), f) for f in rest]
    rest_dated.sort(key=lambda x: (x[0] is None, x[0] or datetime.datetime.min.replace(tzinfo=UTC), x[1]))
    ordered += [f for _, f in rest_dated]
    return ordered


def render(ordered, total):
    lines = []
    lines.append("# Images 갤러리")
    lines.append("")
    lines.append(
        f"`Images/` 폴더의 모든 이미지 {total}장입니다. 생성 시점을 알 수 있는 이미지는 앞쪽에 시간순으로, "
        "시점을 알 수 없는 이미지는 뒤쪽에 같은 생성 배치끼리 모아 이어서 배치했습니다."
    )
    lines.append("")
    lines.append(
        "> 이 파일은 `scripts/generate_gallery.py`로 자동 생성됩니다. "
        "GitHub Actions의 **Update Gallery** 워크플로를 수동 실행하면 새로 추가된 이미지가 반영됩니다."
    )
    lines.append("")
    lines.append("| " + " | ".join(["미리보기"] * COLS) + " |")
    lines.append("|" + "---|" * COLS)
    for i in range(0, len(ordered), COLS):
        row = ordered[i:i + COLS]
        cells = [f'<img src="{enc(f)}" width="240" alt="{f}"><br>{f}' for f in row]
        cells += [""] * (COLS - len(cells))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def main():
    files = sorted(
        os.path.basename(p)
        for pattern in IMAGE_EXTS
        for p in glob.glob(os.path.join(IMAGES_DIR, pattern))
    )
    ordered = build_order(files)
    assert len(ordered) == len(files), f"ordering dropped files: {len(ordered)} != {len(files)}"
    content = render(ordered, len(files))
    with open(README_PATH, "w", encoding="utf-8") as fp:
        fp.write(content)
    print(f"Wrote {README_PATH} with {len(files)} images.")


if __name__ == "__main__":
    main()

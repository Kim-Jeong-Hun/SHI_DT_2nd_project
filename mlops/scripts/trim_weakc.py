"""약신호 필터 막대 그림(s{k}_weakt.webp)에서 0% 행을 잘라 낸 요약판(s{k}_weakc.webp)을 만든다.

막대가 있는 행 + (있으면) 범례·x축만 남기고, 잘린 자리는 회색 점선으로 표시한다.
반환값: 선종 인덱스별 {"shown": 남긴 행 수, "zero": 생략한 0% 행 수}
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def trim_one(src: Path, dst: Path) -> dict:
    im = Image.open(src).convert("RGB")
    a = np.array(im).astype(int)
    H, W, _ = a.shape
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    bar = ((b > 140) & (r < 120) & (g < 150) & (b - r > 50)) | ((r > 170) & (g < 110) & (b < 110))
    ys, xs = np.where(bar)
    left = int(xs.min())
    rows = np.unique(ys)
    cl, s, p = [], rows[0], rows[0]
    for y in rows[1:]:
        if y - p > 3:
            cl.append((s, p))
            s = y
        p = y
    cl.append((s, p))
    gap = int(np.median([cl[i + 1][0] - cl[i][0] for i in range(len(cl) - 1)]))
    dark = (r < 90) & (g < 90) & (b < 90)
    dx = left + 5 + int(np.argmax(dark[:, left + 5:].sum(0)))  # 제거 기준 점선
    gray = (r < 225) & (r > 140) & (abs(r - b) < 12)
    fr = W
    for x in range(dx + 3, min(W, dx + 200)):
        if gray[cl[0][0]:cl[-1][1], x].mean() > 0.9:
            fr = x + 3
            break
    right = min(W, fr + 30)
    ink = (r < 160) & (g < 160) & (b < 160)
    ytop = max(0, int(np.where(ink[:, :right].sum(1) > 2)[0][0]) - 10)
    ycut = int(cl[-1][1] + gap * 0.22)
    parts = [im.crop((0, ytop, right, ycut))]
    rowg = gray[:, left:fr - 3].mean(1)
    fb = [y for y in range(ycut, H) if rowg[y] > 0.85]
    yb = fb[-1] if fb else None
    has_ticks = yb is not None and dark[yb + 5:min(H, yb + 60), left + 5:dx - 6].sum() > 30
    lab = dark[:int(H * 0.97), :left - 10]
    lr = np.where(lab.sum(1) > 2)[0]
    c0 = (cl[0][0] + cl[0][1]) / 2
    lastlab = lr[lr < (yb if has_ticks else H)].max()
    zero = max(0, int(round((lastlab - c0) / gap)) + 1 - len(cl))
    if has_ticks:
        rr = np.where(dark[ycut:yb - 3, left + 6:left + 600].sum(1) > 3)[0]
        y0 = ycut + int(rr[0]) - 12 if len(rr) else yb - 4
        bot = im.crop((0, y0, right, H)).copy()
        ImageDraw.Draw(bot).rectangle((0, 0, left - 3, max(0, yb - y0)), fill="white")
        parts.append(bot)
    else:
        parts.append(Image.new("RGB", (right, 6), "white"))
    out = Image.new("RGB", (right, sum(q.height for q in parts) + 24), "white")
    d = ImageDraw.Draw(out)
    out.paste(parts[0], (0, 0))
    y = parts[0].height
    for x in range(left, right - 10, 18):
        d.line((x, y + 12, x + 9, y + 12), fill=(150, 150, 150), width=2)
    out.paste(parts[1], (0, y + 24))
    out.save(dst, quality=90)
    return {"shown": len(cl), "zero": zero}


def trim_all(img_dir: Path, n: int = 5) -> dict:
    return {k: trim_one(img_dir / f"s{k}_weakt.webp", img_dir / f"s{k}_weakc.webp") for k in range(n)}


if __name__ == "__main__":
    print(trim_all(Path(__file__).resolve().parents[1] / "serving/static/story/img"))

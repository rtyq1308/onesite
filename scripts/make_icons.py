#!/usr/bin/env python3
"""홈 화면 추가(PWA)용 아이콘을 assets/logo-source.png 에서 만든다.

한 번만 돌리면 되고 결과물(public/*.png)은 저장소에 커밋한다.
매월 자동 갱신에서는 실행되지 않는다.

  python scripts/make_icons.py
"""

import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(ROOT, "public")
SOURCE = os.path.join(ROOT, "assets", "logo-source.png")

# 원본 배경과 같은 색. 여백을 채울 때 이음매가 보이지 않게 한다.
BG = (26, 26, 28)


def sample_bg(img):
    """모서리 네 곳 평균으로 배경색을 잡는다. 원본을 바꿔도 따라간다."""
    w, h = img.size
    pad = max(2, w // 40)
    pts = [(pad, pad), (w - pad, pad), (pad, h - pad), (w - pad, h - pad)]
    px = img.convert("RGB").load()
    vals = [px[x - 1, y - 1] for x, y in pts]
    return tuple(sum(v[i] for v in vals) // len(vals) for i in range(3))


def build(size, padding_ratio=0.0):
    """padding_ratio 를 주면 maskable 아이콘용 안전 여백을 확보한다."""
    src = Image.open(SOURCE).convert("RGB")
    bg = sample_bg(src)

    inner = int(round(size * (1 - padding_ratio * 2)))
    art = src.resize((inner, inner), Image.LANCZOS)

    out = Image.new("RGB", (size, size), bg)
    off = (size - inner) // 2
    out.paste(art, (off, off))
    return out


def main():
    if not os.path.exists(SOURCE):
        raise SystemExit("원본이 없습니다: %s" % SOURCE)

    os.makedirs(PUBLIC, exist_ok=True)
    jobs = [
        ("icon-192.png", 192, 0.0),
        ("icon-512.png", 512, 0.0),
        ("icon-512-maskable.png", 512, 0.12),   # 안드로이드가 원형으로 잘라낼 여백
        ("apple-touch-icon.png", 180, 0.0),     # iOS 는 자체적으로 모서리를 깎는다
    ]
    for name, size, pad in jobs:
        path = os.path.join(PUBLIC, name)
        build(size, pad).save(path, "PNG", optimize=True)
        print("%-26s %dx%d  %s bytes" % (name, size, size, os.path.getsize(path)))

    # SNS 공유 썸네일. 카카오톡·페이스북이 1200x630 가로형을 기대한다.
    src = Image.open(SOURCE).convert("RGB")
    bg = sample_bg(src)
    og = Image.new("RGB", (1200, 630), bg)
    art = src.resize((580, 580), Image.LANCZOS)
    og.paste(art, ((1200 - 580) // 2, (630 - 580) // 2))
    path = os.path.join(PUBLIC, "og.png")
    og.save(path, "PNG", optimize=True)
    print("%-26s 1200x630  %s bytes" % ("og.png", os.path.getsize(path)))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""홈 화면 추가(PWA)용 아이콘을 만든다.

한 번만 돌리면 되고 결과물(public/*.png)은 저장소에 커밋한다.
매월 자동 갱신에서는 실행되지 않으므로 한글 폰트가 없는 서버에서도 문제없다.

  python scripts/make_icons.py
"""

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(ROOT, "public")

GREEN = (26, 122, 92)
WHITE = (255, 255, 255)

# 윈도우 기본 한글 폰트. 없으면 라틴 폰트로 떨어진다.
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
]


def pick_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def draw_icon(size, padding_ratio=0.0):
    """padding_ratio 를 주면 maskable 아이콘용 안전 여백을 확보한다."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = int(size * padding_ratio)
    box = (pad, pad, size - pad - 1, size - pad - 1)
    radius = int((size - pad * 2) * 0.22)
    d.rounded_rectangle(box, radius=radius, fill=GREEN)

    inner = size - pad * 2
    # 한 줄로 넣는다. '공짜/맵' 으로 쪼개면 '맵' 이 홀로 남아 어색하다.
    lines = ["공짜맵"]

    # 긴 줄('주차장')이 아이콘 폭에 딱 차도록 글자 크기를 역산한다.
    # 크기를 고정하면 아이콘 해상도마다 여백이 들쭉날쭉해진다.
    target = inner * 0.80
    font_size = int(inner * 0.34)
    for _ in range(24):
        probe = pick_font(font_size)
        l, t, r, b = d.textbbox((0, 0), lines[-1], font=probe)
        width = r - l
        if width == 0:
            break
        if abs(width - target) <= inner * 0.02:
            break
        font_size = max(8, int(font_size * target / width))
    font = pick_font(font_size)

    metrics = [d.textbbox((0, 0), s, font=font) for s in lines]
    heights = [m[3] - m[1] for m in metrics]
    gap = int(font_size * 0.14)
    total = sum(heights) + gap * (len(lines) - 1)

    # 글자를 위로 올리고 아래에 자동차를 둔다.
    y = pad + inner * 0.20
    for text, (l, t, r, b) in zip(lines, metrics):
        d.text((pad + (inner - (r - l)) / 2 - l, y - t), text, font=font, fill=WHITE)
        y += (b - t) + gap

    draw_car(d, pad + inner / 2, pad + inner * 0.74, inner * 0.60)
    return img


def draw_car(d, cx, cy, width):
    """옆에서 본 자동차. 바퀴를 차체 아래로 빼서 그린다.
    차체에 구멍을 파는 방식은 작게 줄이면 콧구멍처럼 보인다."""
    body_h = width * 0.27
    roof_w = width * 0.46
    roof_h = width * 0.19
    roof_shift = -width * 0.07     # 지붕을 뒤로 밀어야 승용차 옆모습이 된다
    body_top = cy - body_h / 2
    body_bottom = cy + body_h / 2

    # 지붕(캐빈)
    d.rounded_rectangle(
        (cx + roof_shift - roof_w / 2, body_top - roof_h,
         cx + roof_shift + roof_w / 2, body_top + body_h * 0.4),
        radius=roof_h * 0.5, fill=WHITE)
    # 차체
    d.rounded_rectangle(
        (cx - width / 2, body_top, cx + width / 2, body_bottom),
        radius=body_h * 0.45, fill=WHITE)

    # 바퀴는 차체 바깥으로 내려 붙인다. 가운데 축만 배경색으로 찍는다.
    wheel_r = width * 0.155
    wheel_y = body_bottom + wheel_r * 0.30
    for dx in (-width * 0.28, width * 0.30):
        d.ellipse((cx + dx - wheel_r, wheel_y - wheel_r,
                   cx + dx + wheel_r, wheel_y + wheel_r), fill=WHITE)
        hub = wheel_r * 0.34
        d.ellipse((cx + dx - hub, wheel_y - hub,
                   cx + dx + hub, wheel_y + hub), fill=GREEN)


def main():
    os.makedirs(PUBLIC, exist_ok=True)
    jobs = [
        ("icon-192.png", 192, 0.0),
        ("icon-512.png", 512, 0.0),
        ("icon-512-maskable.png", 512, 0.12),   # 안드로이드가 원형으로 잘라낼 여백
        ("apple-touch-icon.png", 180, 0.0),     # iOS 는 자체적으로 모서리를 깎는다
    ]
    for name, size, pad in jobs:
        img = draw_icon(size, pad)
        path = os.path.join(PUBLIC, name)
        img.save(path, "PNG", optimize=True)
        print("%-26s %dx%d  %s bytes" % (name, size, size, os.path.getsize(path)))


if __name__ == "__main__":
    main()

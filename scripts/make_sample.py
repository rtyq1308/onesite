#!/usr/bin/env python3
"""인증키 없이 화면을 먼저 보고 싶을 때 쓰는 가짜 원본 데이터 생성기.

  python scripts/make_sample.py && python scripts/build_site.py

실제 배포 전에는 반드시 scripts/fetch_data.py 로 진짜 데이터를 받아야 한다.
"""

import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")

SPOTS = [
    ("서울특별시 종로구 세종대로 172", 37.5720, 126.9769),
    ("서울특별시 강남구 테헤란로 152", 37.5000, 127.0364),
    ("부산광역시 해운대구 우동 1408", 35.1631, 129.1636),
    ("경기도 수원시 팔달구 효원로 241", 37.2636, 127.0286),
    ("제주특별자치도 제주시 문연로 6", 33.4890, 126.4983),
]


def main():
    random.seed(7)
    rows = []
    for i, (addr, lat, lng) in enumerate(SPOTS):
        for n in range(12):
            jitter = lambda v: round(v + random.uniform(-0.02, 0.02), 6)
            rows.append({
                "prkplceNm": "%s 공영주차장 %d호" % (addr.split()[1], n + 1),
                "prkplceType": "공영",
                "prkplceSe": "노외" if n % 2 else "노상",
                "rdnmadr": addr,
                "prkcmprt": str(random.randint(10, 200)),
                "parkingchrgeInfo": "무료" if n % 3 else "유료",
                "operDay": "평일+토요일+공휴일",
                "weekdayOperOpenHhmm": "0900", "weekdayOperColseHhmm": "1800",
                "phoneNumber": "02-000-000%d" % i,
                "latitude": jitter(lat), "longitude": jitter(lng),
            })

    os.makedirs(RAW_DIR, exist_ok=True)
    with open(os.path.join(RAW_DIR, "parking.json"), "w", encoding="utf-8") as fp:
        json.dump(rows, fp, ensure_ascii=False)
    print("샘플 생성: 주차장 %d건" % len(rows))


if __name__ == "__main__":
    main()

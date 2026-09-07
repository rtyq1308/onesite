#!/usr/bin/env python3
"""서울 열린데이터광장 공영주차장(GetParkInfo)을 받아 data/raw/seoul.json 으로 저장한다.

전국주차장정보표준데이터에 서울이 15곳밖에 없어서 서울만 따로 보충한다.
저장 형식은 표준데이터와 같은 필드명으로 맞춰두기 때문에 build_site.py 는
두 파일을 그냥 이어붙여 쓰면 된다.

  인증키 발급: https://data.seoul.go.kr/together/mypage/actkeyMain.do

사용법
  $env:SEOUL_API_KEY="발급받은_인증키"
  python scripts/fetch_seoul.py --check   # 좌표·요금 분포만 확인
  python scripts/fetch_seoul.py           # 전체 수집
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")

SERVICE = "GetParkInfo"
BASE = "http://openapi.seoul.go.kr:8088"
PAGE_SIZE = 1000   # 한 번에 최대 1,000건


def request_page(key, start, end):
    url = "%s/%s/json/%s/%d/%d/" % (BASE, key, SERVICE, start, end)
    req = urllib.request.Request(url, headers={"User-Agent": "freemap-kr/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise SystemExit("인증 실패(HTTP %s). SEOUL_API_KEY 를 확인하세요." % exc.code)
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    raise SystemExit("요청 실패: %s" % url)


def unwrap(payload):
    """정상 응답이면 (rows, total), 오류면 SystemExit."""
    if SERVICE in payload:
        block = payload[SERVICE]
        result = block.get("RESULT", {})
        if result.get("CODE", "INFO-000") != "INFO-000":
            raise SystemExit("API 오류: %s %s" % (result.get("CODE"), result.get("MESSAGE")))
        return block.get("row", []), int(block.get("list_total_count") or 0)

    result = payload.get("RESULT", {})
    raise SystemExit(
        "API 오류: %s %s\n인증키가 맞는지, '일반 인증키'로 신청했는지 확인하세요."
        % (result.get("CODE"), result.get("MESSAGE"))
    )


def to_float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def has_coords(row):
    lat, lng = to_float(row.get("LAT")), to_float(row.get("LOT"))
    return 33.0 <= lat <= 39.5 and 124.0 <= lng <= 132.0


def hhmm4(value):
    """'0900' / '900' / '09:00' 을 모두 'HHMM' 으로."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 3:
        digits = "0" + digits
    if digits == "2400":
        digits = "2359"
    return digits if len(digits) == 4 else ""


def free_labels(row):
    """상시 무료가 아니어도 언제 공짜인지는 알려줄 가치가 있다."""
    labels = []
    if str(row.get("SAT_CHGD_FREE_NM") or "").strip() == "무료":
        labels.append("토요일 무료")
    if str(row.get("LHLDY_NM") or "").strip() == "무료":
        labels.append("공휴일 무료")
    if str(row.get("NGHT_FREE_OPN_YN") or "").strip() == "Y":
        labels.append("야간 무료개방")
    return labels


def to_standard(row):
    """표준데이터(tn_pubr_prkplce_info_api)와 같은 필드명으로 변환한다."""
    address = str(row.get("ADDR") or "").strip()
    if address and not address.startswith("서울"):
        address = "서울특별시 " + address   # 서울 API 주소에는 시도명이 없다

    kind = str(row.get("PKLT_KND_NM") or "")      # '노외 주차장'
    place = next((k for k in ("노상", "노외", "부설") if k in kind), "")

    return {
        "prkplceNm": str(row.get("PKLT_NM") or "").strip(),
        "rdnmadr": address,
        "lnmadr": address,
        "parkingchrgeInfo": str(row.get("CHGD_FREE_NM") or "").strip(),
        "prkcmprt": str(int(to_float(row.get("TPKCT")))),
        "phoneNumber": str(row.get("TELNO") or "").strip(),
        "prkplceSe": "공영",
        "prkplceType": place,
        "operDay": "",
        "weekdayOperOpenHhmm": hhmm4(row.get("WD_OPER_BGNG_TM")),
        "weekdayOperColseHhmm": hhmm4(row.get("WD_OPER_END_TM")),
        "latitude": row.get("LAT"),
        "longitude": row.get("LOT"),
        "freeLabels": free_labels(row),
        "_source": "seoul",
    }


def fetch_all(key, max_rows=None):
    rows, start = [], 1
    total = None
    while True:
        end = start + PAGE_SIZE - 1
        page, total_count = unwrap(request_page(key, start, end))
        if total is None:
            total = total_count
            print("서울 공영주차장 전체 %s건" % format(total, ","))
        rows.extend(page)
        print("  %d~%d -> 누적 %s건" % (start, end, format(len(rows), ",")))
        if not page or len(rows) >= total or (max_rows and len(rows) >= max_rows):
            break
        start = end + 1
        time.sleep(0.2)
    return rows


def check(key):
    rows, total = unwrap(request_page(key, 1, PAGE_SIZE))
    print("=" * 58)
    print("서울 공영주차장 데이터 점검")
    print("=" * 58)
    print("전체 %s건 중 %s건 확인" % (format(total, ","), format(len(rows), ",")))

    with_coords = [r for r in rows if has_coords(r)]
    free = [r for r in rows if str(r.get("CHGD_FREE_NM") or "").strip() == "무료"]
    free_coords = [r for r in free if has_coords(r)]
    sat = [r for r in rows if str(r.get("SAT_CHGD_FREE_NM") or "").strip() == "무료"]
    holiday = [r for r in rows if str(r.get("LHLDY_NM") or "").strip() == "무료"]
    night = [r for r in rows if str(r.get("NGHT_FREE_OPN_YN") or "").strip() == "Y"]

    pct = lambda n: (100.0 * n / len(rows)) if rows else 0.0
    print()
    print("  좌표 있음        : %5d건 (%.1f%%)" % (len(with_coords), pct(len(with_coords))))
    print("  상시 무료        : %5d건 (%.1f%%)" % (len(free), pct(len(free))))
    print("   └ 좌표까지 있음 : %5d건" % len(free_coords))
    print("  토요일 무료      : %5d건" % len(sat))
    print("  공휴일 무료      : %5d건" % len(holiday))
    print("  야간 무료개방    : %5d건" % len(night))
    print()

    if len(with_coords) == 0:
        print("→ 좌표가 전혀 없습니다. 지도에 찍으려면 주소를 좌표로 바꾸는")
        print("  지오코딩(카카오 로컬 API)이 필요합니다.")
    elif pct(len(with_coords)) < 60:
        print("→ 좌표가 있는 것과 없는 것이 섞여 있습니다.")
        print("  없는 것만 골라 지오코딩하면 됩니다.")
    else:
        print("→ 좌표가 충분합니다. 지오코딩 없이 바로 붙일 수 있습니다.")

    sample = (with_coords or rows)[:3]
    print()
    print("샘플:")
    for r in sample:
        print("  %-28s %-4s LAT=%s LOT=%s  %s"
              % (str(r.get("PKLT_NM"))[:28], r.get("CHGD_FREE_NM"),
                 r.get("LAT"), r.get("LOT"), r.get("ADDR")))
    print("=" * 58)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="좌표·요금 분포만 확인")
    args = parser.parse_args()

    key = re.sub(r"\s+", "", os.environ.get("SEOUL_API_KEY", ""))
    if not key:
        raise SystemExit(
            "환경변수 SEOUL_API_KEY 가 비어 있습니다.\n"
            "인증키 발급: https://data.seoul.go.kr/together/mypage/actkeyMain.do"
        )

    if args.check:
        check(key)
        return

    rows = fetch_all(key)
    converted = [to_standard(r) for r in rows]
    converted = [r for r in converted if r["prkplceNm"]]

    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, "seoul.json")
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(converted, fp, ensure_ascii=False)
    print("저장 %s (%s건)" % (path, format(len(converted), ",")))


if __name__ == "__main__":
    sys.exit(main())

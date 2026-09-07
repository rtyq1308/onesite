#!/usr/bin/env python3
"""공공데이터포털 표준데이터를 내려받아 data/raw/*.json 으로 저장한다.

  전국주차장정보표준데이터   http://api.data.go.kr/openapi/tn_pubr_prkplce_info_api
  전국공중화장실표준데이터   http://api.data.go.kr/openapi/tn_pubr_public_toilet_api

사용법
  set DATA_GO_KR_KEY=디코딩된_인증키        (PowerShell: $env:DATA_GO_KR_KEY="...")
  python scripts/fetch_data.py
  python scripts/fetch_data.py --probe parking   # 첫 레코드 필드명만 출력
  python scripts/fetch_data.py --limit 3         # 3페이지만 (동작 확인용)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")

# 공중화장실 표준데이터는 2025년 2월부터 원천데이터에서 WGS84 위경도가 빠져서
# 지도에 찍을 수 없다. 그래서 이 사이트는 주차장만 다룬다.
SOURCES = {
    "parking": {
        "url": "http://api.data.go.kr/openapi/tn_pubr_prkplce_info_api",
        "label": "전국주차장정보표준데이터",
    },
}

PAGE_SIZE = 1000
ALREADY_ENCODED = re.compile(r"%[0-9A-Fa-f]{2}")

# 포털 화면에서 인증키가 두 줄로 접혀 보이기 때문에, 긁어서 복사하면 줄바꿈/공백이
# 섞여 들어온다. 키에는 공백이 들어갈 일이 없으므로 전부 제거한다.
def clean_key(key):
    return re.sub(r"\s+", "", key or "")


ERROR_HINTS = {
    "30": "인증키가 아직 등록되지 않았습니다. ①발급 직후라면 최대 1시간 기다리세요. "
          "②키를 복사하다 일부가 잘렸을 수 있습니다.",
    "20": "키는 맞지만 이 API를 '활용신청'하지 않았습니다. data.go.kr에서 해당 "
          "데이터의 [오픈 API] 탭 → [활용신청]을 누르세요.",
    "22": "일일 트래픽을 초과했습니다. 내일 다시 시도하거나 운영계정으로 전환하세요.",
    "12": "해당 오픈API 서비스가 없거나 폐기되었습니다(주소 오류).",
    "10": "요청 변수가 잘못되었습니다.",
}


def encode_key(key):
    """포털은 인증키를 '인코딩'/'디코딩' 두 벌로 준다. 어느 쪽을 넣어도 되게 맞춘다."""
    if ALREADY_ENCODED.search(key):
        return key
    return urllib.parse.quote(key, safe="")


def request_page(base_url, key, page):
    url = "%s?serviceKey=%s&pageNo=%d&numOfRows=%d&type=json" % (
        base_url,
        encode_key(key),
        page,
        PAGE_SIZE,
    )
    req = urllib.request.Request(url, headers={"User-Agent": "freemap-kr/1.0"})
    last_error = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            # 인증 오류는 재시도해도 소용없다.
            if exc.code in (401, 403) or "SERVICE_KEY" in body or "ACCESS_DENIED" in body:
                found = re.search(r'"returnReasonCode"\s*:\s*"?(\d+)', body)
                hint = ERROR_HINTS.get(found.group(1), "") if found else ""
                raise SystemExit(
                    "인증 실패(HTTP %s).\n%s\n\n무엇이 문제인지 아래 명령으로 확인하세요:\n"
                    "  진단.bat 더블클릭  (또는 python scripts/fetch_data.py --check)"
                    % (exc.code, hint or body[:300])
                )
            last_error = exc
        except Exception as exc:  # 네트워크 순단
            last_error = exc
        time.sleep(2 * (attempt + 1))
    raise SystemExit("요청 실패: %s (%s)" % (base_url, last_error))


def parse_items(payload):
    """JSON 우선, 실패하면 XML로 파싱한다. (items, total_count) 반환."""
    text = payload.decode("utf-8", "replace").strip()
    if text.startswith("{"):
        data = json.loads(text)
        # 이 API는 {"header":..,"body":..} 로 바로 오지만, 다른 공공 API는
        # {"response":{"header":..,"body":..}} 로 한 겹 더 감싸서 온다. 둘 다 받는다.
        root = data.get("response") if isinstance(data.get("response"), dict) else data
        body = root.get("body", {}) or {}
        items = body.get("items", [])
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        return items or [], int(body.get("totalCount") or 0)

    root = ET.fromstring(text)
    err = root.findtext(".//errMsg") or root.findtext(".//resultMsg")
    if err and "NORMAL" not in err:
        raise SystemExit("API 오류: %s" % err)
    items = []
    for node in root.findall(".//items/item"):
        items.append({child.tag: (child.text or "").strip() for child in node})
    total = root.findtext(".//totalCount")
    return items, int(total or 0)


def fetch_all(name, key, max_pages=None):
    src = SOURCES[name]
    print("[%s] %s 수집 시작" % (name, src["label"]))
    rows, page, total = [], 1, None
    while True:
        items, total_count = parse_items(request_page(src["url"], key, page))
        if total is None:
            total = total_count
            print("[%s] 전체 %s건" % (name, format(total, ",")))
        rows.extend(items)
        print("  page %d -> 누적 %s건" % (page, format(len(rows), ",")))
        if not items or len(items) < PAGE_SIZE:
            break
        if max_pages and page >= max_pages:
            break
        if total and len(rows) >= total:
            break
        page += 1
        time.sleep(0.2)
    return rows


def describe_shape(text):
    """응답이 어떤 모양인지 요약해서 보여준다. 파싱 경로가 맞는지 확인용."""
    try:
        data = json.loads(text)
    except Exception:
        return "  JSON이 아닙니다. 앞부분: " + text[:200].replace("\n", " ")

    lines = []

    def walk(node, depth):
        pad = "  " * (depth + 1)
        if len(lines) > 40:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, dict):
                    lines.append("%s%s {}" % (pad, key))
                    walk(value, depth + 1)
                elif isinstance(value, list):
                    lines.append("%s%s [%d개]" % (pad, key, len(value)))
                    if value:
                        walk(value[0], depth + 1)
                else:
                    lines.append("%s%s = %s" % (pad, key, str(value)[:70]))
        elif isinstance(node, list):
            lines.append("%s[%d개]" % (pad, len(node)))
            if node:
                walk(node[0], depth + 1)

    walk(data, 0)
    return "\n".join(lines[:40])


def diagnose(raw_key):
    """인증키가 왜 안 먹는지 하나씩 짚어준다. 키 자체는 화면에 찍지 않는다."""
    key = clean_key(raw_key)
    print("=" * 58)
    print("인증키 진단")
    print("=" * 58)
    print("길이            : %d자" % len(key))
    print("앞/뒤 6자       : %s ... %s" % (key[:6], key[-6:]))
    print("공백·줄바꿈 제거 : %s" % ("있었음 (제거함)" if key != (raw_key or "") else "없음"))
    print("키 종류         : %s" % ("Encoding 키" if ALREADY_ENCODED.search(key) else "Decoding 키"))
    if len(key) < 60:
        print("\n※ 키가 너무 짧습니다. 복사하다 잘렸을 가능성이 높습니다.")
        print("  포털의 [인증키 복사(Decoding)] 버튼을 눌러 복사하세요.")
    print()

    ok = False
    for name, src in SOURCES.items():
        url = "%s?serviceKey=%s&pageNo=1&numOfRows=1&type=json" % (
            src["url"], encode_key(key))
        req = urllib.request.Request(url, headers={"User-Agent": "freemap-kr/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", "replace")
            code, msg = "00", "정상"
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            code = (re.search(r'"returnReasonCode"\s*:\s*"?(\d+)', body) or
                    re.search(r"<returnReasonCode>(\d+)", body))
            code = code.group(1) if code else str(exc.code)
            msg = (re.search(r'"errMsg"\s*:\s*"([^"]+)', body) or
                   re.search(r"<errMsg>([^<]+)", body))
            msg = msg.group(1) if msg else body[:80]
        except Exception as exc:
            code, msg = "NET", "네트워크 오류: %s" % exc

        if code == "00":
            # 원문을 남겨둔다. 파싱이 안 맞을 때 이 파일을 보고 고친다.
            os.makedirs(RAW_DIR, exist_ok=True)
            dump = os.path.join(RAW_DIR, "_check_%s.txt" % name)
            with open(dump, "w", encoding="utf-8") as fp:
                fp.write(body)

            items, total = [], 0
            try:
                items, total = parse_items(body.encode("utf-8"))
            except Exception as exc:
                print("[%-7s] 응답 파싱 실패: %s" % (src["label"][:7], exc))

            if items:
                print("[%-7s] 정상 - 전체 %s건, 첫 레코드 필드 %d개"
                      % (src["label"][:7], format(total, ","), len(items[0])))
                ok = True
            else:
                print("[%-7s] 인증은 통과했지만 데이터가 0건입니다. 응답 구조:"
                      % src["label"][:7])
                print(describe_shape(body))
                print("  (원문 저장: %s)" % dump)
        else:
            print("[%-7s] 실패 (코드 %s) %s" % (src["label"][:7], code, msg))
            hint = ERROR_HINTS.get(code)
            if hint:
                print("            → %s" % hint)
    print()
    if ok:
        print("사용 가능합니다. 실행.bat 을 다시 돌리세요.")
    else:
        print("아직 안 됩니다. 위 안내를 먼저 처리한 뒤 다시 진단하세요.")
    print("=" * 58)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="인증키가 왜 안 되는지 진단")
    parser.add_argument("--probe", choices=sorted(SOURCES), help="첫 레코드 필드명만 확인")
    parser.add_argument("--limit", type=int, help="최대 페이지 수(테스트용)")
    parser.add_argument("--only", choices=sorted(SOURCES), help="한쪽만 수집")
    args = parser.parse_args()

    raw = os.environ.get("DATA_GO_KR_KEY", "")
    key = clean_key(raw)
    if not key:
        raise SystemExit("환경변수 DATA_GO_KR_KEY 가 비어 있습니다. README 1번 참고.")

    if args.check:
        diagnose(raw)
        return

    if args.probe:
        items, _ = parse_items(request_page(SOURCES[args.probe]["url"], key, 1))
        if not items:
            raise SystemExit("레코드가 비어 있습니다.")
        print(json.dumps(items[0], ensure_ascii=False, indent=2))
        return

    os.makedirs(RAW_DIR, exist_ok=True)
    targets = [args.only] if args.only else list(SOURCES)
    for name in targets:
        rows = fetch_all(name, key, args.limit)
        path = os.path.join(RAW_DIR, name + ".json")
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(rows, fp, ensure_ascii=False)
        print("[%s] 저장 %s (%s건)" % (name, path, format(len(rows), ",")))


if __name__ == "__main__":
    sys.exit(main())

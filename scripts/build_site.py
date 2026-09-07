#!/usr/bin/env python3
"""data/raw/parking.json 을 읽어 dist/ 아래에 정적 사이트를 통째로 생성한다.

  dist/index.html                     전국 홈 + 내 주변 찾기
  dist/{시도}/index.html              시군구 목록
  dist/{시도}/{시군구}/index.html     지도 + 목록 (SEO 대상 페이지)
  dist/data/{시도}/{시군구}.json      해당 지역 데이터만 담은 조각
  dist/data/index.json                지역 목록 + 중심좌표(내 주변 찾기용)

사용법:  python scripts/build_site.py
"""

import datetime
import html
import json
import os
import re
import shutil
import time
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
STATIC_DIR = os.path.join(ROOT, "static")
DIST = os.path.join(ROOT, "dist")

SITE_URL = os.environ.get("SITE_URL", "https://freemap-kr.pages.dev").rstrip("/")
SITE_NAME = "공짜맵"
TODAY = datetime.date.today().isoformat()

# 애드센스 - 값이 비면 광고 태그를 아예 넣지 않는다(승인 전 빈 ins 태그 방지).
ADSENSE_CLIENT = os.environ.get("ADSENSE_CLIENT", "").strip()
AD_SLOTS = {
    "top": os.environ.get("ADSENSE_SLOT_TOP", "").strip(),
    "feed": os.environ.get("ADSENSE_SLOT_FEED", "").strip(),
    "bottom": os.environ.get("ADSENSE_SLOT_BOTTOM", "").strip(),
}
# 이만큼도 안 되는 지역은 색인 제외 + 광고 미노출 (빈약한 콘텐츠 정책 회피).
THIN_PAGE_MIN = 3

SIDO_ALIASES = {
    "서울": "서울특별시", "서울시": "서울특별시", "서울특별시": "서울특별시",
    "부산": "부산광역시", "부산시": "부산광역시", "부산광역시": "부산광역시",
    "대구": "대구광역시", "대구시": "대구광역시", "대구광역시": "대구광역시",
    "인천": "인천광역시", "인천시": "인천광역시", "인천광역시": "인천광역시",
    "광주": "광주광역시", "광주시": "광주광역시", "광주광역시": "광주광역시",
    "대전": "대전광역시", "대전시": "대전광역시", "대전광역시": "대전광역시",
    "울산": "울산광역시", "울산시": "울산광역시", "울산광역시": "울산광역시",
    "세종": "세종특별자치시", "세종시": "세종특별자치시",
    "세종특별자치시": "세종특별자치시",
    "경기": "경기도", "경기도": "경기도",
    "강원": "강원특별자치도", "강원도": "강원특별자치도",
    "강원특별자치도": "강원특별자치도",
    "충북": "충청북도", "충청북도": "충청북도",
    "충남": "충청남도", "충청남도": "충청남도",
    "전북": "전북특별자치도", "전라북도": "전북특별자치도",
    "전북특별자치도": "전북특별자치도",
    "전남": "전라남도", "전라남도": "전라남도",
    "경북": "경상북도", "경상북도": "경상북도",
    "경남": "경상남도", "경상남도": "경상남도",
    "제주": "제주특별자치도", "제주도": "제주특별자치도",
    "제주특별자치도": "제주특별자치도",
}

SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라남도": "전남", "경상북도": "경북",
    "경상남도": "경남", "제주특별자치도": "제주",
}

SIDO_ORDER = [
    "서울특별시", "경기도", "인천광역시", "부산광역시", "대구광역시",
    "광주광역시", "대전광역시", "울산광역시", "세종특별자치시",
    "강원특별자치도", "충청북도", "충청남도", "전북특별자치도",
    "전라남도", "경상북도", "경상남도", "제주특별자치도",
]


# --------------------------------------------------------------------------
# 원본 레코드 정규화
# --------------------------------------------------------------------------

def pick(row, *names):
    """표준데이터 필드명이 기관·연도별로 조금씩 달라서 후보를 순서대로 훑는다."""
    for name in names:
        value = row.get(name)
        if value is None:
            continue
        value = str(value).strip()
        if value and value not in ("null", "None", "-"):
            return value
    return ""


def to_float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def to_int(value):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def coords(row):
    lat = to_float(pick(row, "latitude", "la", "lat", "위도"))
    lng = to_float(pick(row, "longitude", "lo", "lng", "경도"))
    if lat is None or lng is None:
        return None
    if 124.0 <= lat <= 132.0 and 33.0 <= lng <= 39.5:  # 위경도가 뒤집힌 레코드
        lat, lng = lng, lat
    if not (33.0 <= lat <= 39.5 and 124.0 <= lng <= 132.0):
        return None
    return round(lat, 6), round(lng, 6)


def split_region(address):
    tokens = re.split(r"\s+", address.strip())
    if not tokens:
        return None, None
    sido = SIDO_ALIASES.get(tokens[0])
    if not sido:
        return None, None
    if sido == "세종특별자치시":
        return sido, "세종특별자치시"
    sigungu = tokens[1] if len(tokens) > 1 else ""
    if not re.search(r"(시|군|구)$", sigungu):
        return sido, None
    return sido, sigungu


def hhmm(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 4:
        return digits[:2] + ":" + digits[2:]
    return ""


def parking_hours(row):
    day = pick(row, "operDay")
    if day in ("평일+토요일+공휴일", "평일+토요일+일요일+공휴일"):
        day = "연중무휴"

    start = hhmm(pick(row, "weekdayOperOpenHhmm", "weekdayOperOpenHhmn"))
    end = hhmm(pick(row, "weekdayOperColseHhmm", "weekdayOperCloseHhmm", "weekdayOperColseHhmn"))
    if start == "00:00" and end in ("23:59", "24:00"):
        span = "24시간"
    elif start and end and start != end:
        span = start + "~" + end
    else:
        span = ""

    return " ".join(p for p in (day, span) if p)


# 지자체마다 두 필드에 넣는 값이 뒤바뀌어 있어서, 필드명이 아니라 값으로 구분한다.
OWNER_VALUES = ("공영", "민영")
PLACE_VALUES = ("노상", "노외", "부설")


def parking_kinds(row):
    values = [pick(row, "prkplceSe"), pick(row, "prkplceType")]
    owner = next((v for v in values if v in OWNER_VALUES), "")
    place = next((v for v in values if v in PLACE_VALUES), "")
    return owner, place


def normalize_parking(rows):
    out = []
    for row in rows:
        fee = pick(row, "parkingchrgeInfo", "parkingchrgeinfo", "chargeInfo")
        always_free = "무료" in fee
        # 서울 데이터에만 있는 조건부 무료(토요일·공휴일 등). 상시 무료가 아니어도
        # '언제 공짜인지'는 알려줄 값어치가 있어 포함하되, 반드시 라벨을 달아 구분한다.
        labels = [str(x).strip() for x in (row.get("freeLabels") or []) if str(x).strip()]
        if not always_free and not labels:
            continue
        address = pick(row, "rdnmadr", "lnmadr")
        sido, sigungu = split_region(address)
        point = coords(row)
        name = pick(row, "prkplceNm")
        if not (sido and sigungu and point and name):
            continue
        owner, place = parking_kinds(row)
        out.append({
            "sido": sido, "sigungu": sigungu,
            "nm": name, "ad": address,
            "la": point[0], "lo": point[1],
            "tm": parking_hours(row),
            "cp": to_int(pick(row, "prkcmprt")),
            "tel": pick(row, "phoneNumber"),
            "kd": owner,   # 공영 / 민영
            "se": place,   # 노상 / 노외 / 부설
            # 비어 있으면 상시 무료, 값이 있으면 그 때만 무료
            "fl": [] if always_free else labels,
        })
    return out


def dedupe(rows):
    seen, out = set(), []
    for row in rows:
        key = (row["nm"], round(row["la"], 5), round(row["lo"], 5))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<meta name="description" content="{{DESC}}">
<link rel="canonical" href="{{CANONICAL}}">
<meta property="og:type" content="website">
<meta property="og:title" content="{{TITLE}}">
<meta property="og:description" content="{{DESC}}">
<meta property="og:url" content="{{CANONICAL}}">
<meta property="og:site_name" content="공짜맵">
<meta property="og:locale" content="ko_KR">
{{ROBOTS}}
<link rel="stylesheet" href="{{ROOT}}assets/style.css">
{{HEAD}}
</head>
<body>
<header class="site"><div class="wrap">
<a class="brand" href="{{ROOT}}">공짜맵</a>
<span class="tag">전국 무료주차장 지도</span>
</div></header>
<main class="wrap">
{{BODY}}
</main>
<footer class="site"><div class="wrap">
자료 출처: 공공데이터포털 「전국주차장정보표준데이터」 (갱신 {{UPDATED}})<br>
요금과 운영시간은 현장 사정에 따라 달라질 수 있으니 방문 전 확인하세요.
</div></footer>
{{SCRIPTS}}
</body>
</html>
"""

MAP_HEAD = (
    '<link rel="stylesheet" '
    'href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">'
)
MAP_SCRIPTS = (
    '<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>'
)


def e(text):
    return html.escape(str(text), quote=True)


def adsense_head():
    if not ADSENSE_CLIENT:
        return ""
    return ('<meta name="google-adsense-account" content="%s">'
            '<script async crossorigin="anonymous" '
            'src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=%s">'
            "</script>") % (ADSENSE_CLIENT, ADSENSE_CLIENT)


def ad_unit(kind, allowed=True):
    """지면 하나. 슬롯 ID가 없거나 빈약한 페이지면 빈 문자열."""
    slot = AD_SLOTS.get(kind, "")
    if not (allowed and ADSENSE_CLIENT and slot):
        return ""
    return ('<aside class="ad-slot ad-%s"><span class="ad-label">광고</span>'
            '<ins class="adsbygoogle" style="display:block"'
            ' data-ad-client="%s" data-ad-slot="%s"'
            ' data-ad-format="auto" data-full-width-responsive="true"></ins>'
            "<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></aside>"
            ) % (kind, ADSENSE_CLIENT, slot)


def share_bar(prompt):
    """공유 버튼. 주소·제목은 JS가 location.href 에서 읽으므로 도메인이 바뀌어도 그대로 동작한다."""
    buttons = [
        ("native", "공유하기", " hidden"),   # navigator.share 가 있을 때만 JS가 켠다
        ("copy", "주소 복사", ""),
        ("naver", "네이버 블로그", ""),
        ("x", "X", ""),
        ("facebook", "페이스북", ""),
    ]
    tags = "".join(
        '<button type="button" class="btn" data-share="%s"%s>%s</button>' % (key, extra, label)
        for key, label, extra in buttons
    )
    return ('<section class="share"><p class="share-label">%s</p>'
            '<div class="share-btns">%s</div></section>') % (e(prompt), tags)


# 실제 자동완성에 뜨는 연관 검색어(무료주차장 찾기 / 어플 / 찾는법 / 장기주차 /
# 사이트 / 사고 책임)를 그대로 질문으로 받아 답한다. FAQPage 스키마로도 내보낸다.
FAQ = [
    ("무료주차장 찾는 법이 있나요?",
     "위 “내 주변 무료주차장 찾기” 버튼을 누르면 현재 위치에서 가까운 무료 주차장을 "
     "가까운 순서로 보여줍니다. 위치 권한을 주기 싫다면 시·도와 시군구를 눌러 "
     "지역별 무료주차장 목록으로 바로 들어가도 됩니다."),
    ("무료주차장 어플을 따로 설치해야 하나요?",
     "설치할 필요 없습니다. 이 사이트는 웹에서 바로 열리는 무료주차장 사이트라 "
     "앱 설치나 회원가입이 없습니다. 휴대폰 브라우저 메뉴에서 “홈 화면에 추가”를 "
     "하면 무료주차장 어플처럼 아이콘으로 쓸 수 있습니다."),
    ("무료주차장에서 장기주차를 해도 되나요?",
     "대부분 안 됩니다. 무료라도 운영시간과 이용시간 제한이 있는 곳이 많고, "
     "노상 주차면은 특히 짧습니다. 각 주차장 카드에 표시된 운영시간을 먼저 확인하고, "
     "며칠 단위 장기주차가 필요하면 카드의 전화번호로 관리기관에 직접 문의하세요. "
     "무단 장기주차는 견인이나 과태료 대상이 될 수 있습니다."),
    ("무료주차장에서 사고가 나면 책임은 누구에게 있나요?",
     "차량 간 접촉사고는 원칙적으로 사고 당사자와 보험으로 처리합니다. 관리자가 있는 "
     "주차장이라면 시설 하자 등에 대해 관리 주체의 책임이 문제될 수 있지만, 무인으로 "
     "개방된 무료 주차면은 관리 책임이 제한되는 경우가 많습니다. 실제 분쟁은 상황에 "
     "따라 달라지므로 보험사와 해당 주차장 관리기관에 문의하시기 바랍니다."),
    ("정보가 실제와 다르면 어떻게 하나요?",
     "이 사이트는 지자체가 공공데이터로 신고한 내용을 그대로 보여줍니다. 요금이나 "
     "운영시간이 바뀌었는데 반영이 안 됐을 수 있으니, 현장 안내판과 다르면 반드시 "
     "현장 기준을 따르세요. 데이터는 매달 자동으로 다시 받아 갱신합니다."),
]


def faq_html():
    items = "".join(
        '<details class="faq"><summary>%s</summary><p>%s</p></details>' % (e(q), e(a))
        for q, a in FAQ
    )
    return "<h2>무료주차장 자주 묻는 질문</h2>" + items


def faq_ld():
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in FAQ
        ],
    }


def list_block():
    return '<div id="list" class="list"></div><p id="more" class="note"></p>'


def stat_block(pairs):
    cells = "".join(
        '<div class="stat"><b>%s</b><span>%s</span></div>' % (e(value), e(label))
        for label, value in pairs
    )
    return '<div class="stats">%s</div>' % cells


def render(path, title, desc, canonical, body, root, head="", scripts="", indexable=True):
    page = PAGE
    robots = "" if indexable else '<meta name="robots" content="noindex,follow">'
    for key, value in [
        ("{{TITLE}}", title), ("{{DESC}}", desc), ("{{CANONICAL}}", canonical),
        ("{{BODY}}", body), ("{{ROOT}}", root),
        ("{{HEAD}}", adsense_head() + head), ("{{ROBOTS}}", robots),
        ("{{SCRIPTS}}", scripts), ("{{UPDATED}}", TODAY),
    ]:
        page = page.replace(key, value)
    full = os.path.join(DIST, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fp:
        fp.write(page)


# --------------------------------------------------------------------------
# 페이지 생성
# --------------------------------------------------------------------------

FIELDS = ["nm", "ad", "la", "lo", "tm", "cp", "tel", "kd", "se", "fl"]


def lead_text(always_n, partly_n):
    """상시 무료가 아예 없는 지역이 흔해서(서울 대부분) 문구를 따로 둔다."""
    if not partly_n:
        return ("공공데이터에 요금이 “무료”로 등록된 주차장 %d곳입니다. "
                "주차면수가 많은 순서로 보여줍니다." % always_n)
    if not always_n:
        return ("이 지역에는 상시 무료 주차장이 없습니다. 대신 특정 요일에만 무료로 "
                "풀리는 공영주차장 %d곳을 모았습니다. 카드에 “토요일 무료”처럼 언제 "
                "공짜인지 표시했습니다." % partly_n)
    return ("상시 무료 %d곳과, 특정 요일에만 무료로 풀리는 %d곳입니다. "
            "조건부인 곳은 카드에 언제 공짜인지 표시했으니 방문 요일을 확인하세요."
            % (always_n, partly_n))


def build_region_json(sido, sigungu, rows):
    payload = {
        "sido": sido,
        "sigungu": sigungu,
        "p": {"f": FIELDS, "d": [[r[k] for k in FIELDS] for r in rows]},
    }
    path = os.path.join(DIST, "data", sido, sigungu + ".json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, separators=(",", ":"))


def build_region_page(sido, sigungu, rows, siblings):
    url_path = "%s/%s/" % (sido, sigungu)
    short = SIDO_SHORT.get(sido, sido)
    total_slots = sum(r["cp"] for r in rows)
    rich = len(rows) >= THIN_PAGE_MIN
    always = [r for r in rows if not r["fl"]]
    partly = [r for r in rows if r["fl"]]

    title = "%s %s 무료주차장 %d곳 지도 | %s" % (short, sigungu, len(rows), SITE_NAME)
    desc = (("%s %s에서 토요일·공휴일에 무료로 풀리는 공영주차장 %d곳을 지도에서 "
             "확인하세요. 주차면수와 운영시간, 길찾기를 제공합니다."
             % (sido, sigungu, len(partly)))
            if not always else
            ("%s %s의 무료주차장 %d곳(상시 무료 %d곳)을 지도에서 확인하세요. "
             "주차면수, 운영시간, 길찾기까지 한 번에 제공합니다."
             % (sido, sigungu, len(rows), len(always))))

    nearby = "".join(
        '<a href="../%s/">%s<small>무료주차장 %d곳</small></a>' % (name, e(name), count)
        for name, count in siblings if name != sigungu
    )

    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "홈", "item": SITE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": sido, "item": "%s/%s/" % (SITE_URL, sido)},
            {"@type": "ListItem", "position": 3, "name": sigungu, "item": "%s/%s" % (SITE_URL, url_path)},
        ],
    }

    body = (
        '<p class="crumb"><a href="../../">홈</a> › <a href="../">%s</a> › %s</p>' % (e(sido), e(sigungu))
        + "<h1>%s %s 무료주차장</h1>" % (e(sido), e(sigungu))
        + '<p class="lead">%s</p>' % lead_text(len(always), len(partly))
        + stat_block(
            [("상시 무료", "%d곳" % len(always))]
            + ([("요일별 무료", "%d곳" % len(partly))] if partly else [])
            + [("전체 주차면", format(total_slots, ",") + "면")])
        + '<div id="map"></div>'
        # 공유는 목록 앞에 둔다. 목록이 수백 장까지 늘어나기 때문에 뒤에 두면
        # 화면상 만 픽셀 아래로 밀려 아무도 못 본다.
        + share_bar("%s %s 무료주차장, 필요한 사람에게 보내주세요" % (sido, sigungu))
        + ad_unit("top", rich)
        + list_block()
        + ad_unit("bottom", rich)
        + ("<h2>%s의 다른 지역</h2><div class=\"grid\">%s</div>" % (e(sido), nearby) if nearby else "")
        + "<h2>이용 전에 확인하세요</h2>"
        + ('<p class="note"><b>“토요일 무료”, “공휴일 무료”로 표시된 곳은 그 날에만 '
           '무료이고 평일에는 요금을 받습니다.</b> 방문 요일을 꼭 확인하세요.</p>'
           if partly else "")
        + '<p class="note">여기 나오는 곳은 지자체가 요금 정보를 “무료”로 신고한 주차장입니다. '
          "다만 야간·주말에만 무료로 풀리는 곳, 이용시간이 제한된 곳, 특정 시설 이용자만 "
          "쓸 수 있는 곳이 섞여 있습니다. 카드에 표시된 운영시간을 함께 확인하고, "
          "현장 안내판이 데이터와 다르면 현장 기준을 따르세요. "
          "노상은 길가 주차면, 노외는 별도 부지의 주차장을 뜻합니다.</p>"
    )

    config = {
        "mode": "region",
        "dataUrl": "../../data/%s/%s.json" % (sido, sigungu),
        "ad": {"client": ADSENSE_CLIENT, "slot": AD_SLOTS["feed"]}
        if (rich and ADSENSE_CLIENT and AD_SLOTS["feed"]) else None,
    }
    scripts = (
        MAP_SCRIPTS
        + "<script>window.FREEMAP=%s;</script>" % json.dumps(config, ensure_ascii=False)
        + '<script src="../../assets/app.js"></script>'
        + '<script type="application/ld+json">%s</script>' % json.dumps(breadcrumb, ensure_ascii=False)
    )
    render(os.path.join(sido, sigungu, "index.html"), title, desc,
           "%s/%s" % (SITE_URL, url_path), body, "../../", MAP_HEAD, scripts,
           indexable=rich)
    return url_path if rich else None


def build_sido_page(sido, siblings, total):
    short = SIDO_SHORT.get(sido, sido)
    grid = "".join(
        '<a href="%s/">%s<small>무료주차장 %d곳</small></a>' % (e(name), e(name), count)
        for name, count in siblings
    )
    title = "%s 무료주차장 %s곳 지도 | %s" % (short, format(total, ","), SITE_NAME)
    desc = ("%s 무료주차장 %s곳을 시군구별로 정리했습니다. 지역을 고르면 지도와 "
            "무료 주차장 목록, 주차면수와 운영시간을 볼 수 있습니다."
            % (sido, format(total, ",")))
    body = (
        '<p class="crumb"><a href="../">홈</a> › %s</p>' % e(sido)
        + "<h1>%s 무료주차장</h1>" % e(sido)
        + '<p class="lead">시군구를 선택하면 지도와 무료 주차장 목록이 열립니다.</p>'
        + stat_block([("무료주차장", format(total, ",") + "곳"),
                      ("지역", "%d개 시군구" % len(siblings))])
        + "<h2>%s 시군구별 무료주차장</h2>" % e(short)
        + '<div class="grid">%s</div>' % grid
        + share_bar("%s 무료주차장 지도, 주변에 공유해보세요" % sido)
        + ad_unit("bottom")
    )
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "홈", "item": SITE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": sido, "item": "%s/%s/" % (SITE_URL, sido)},
        ],
    }
    scripts = ('<script>window.FREEMAP={mode:"static"};</script>'
               '<script src="../assets/app.js"></script>'
               '<script type="application/ld+json">%s</script>'
               % json.dumps(breadcrumb, ensure_ascii=False))
    render(os.path.join(sido, "index.html"), title, desc,
           "%s/%s/" % (SITE_URL, sido), body, "../", scripts=scripts)


def build_home(index, total, total_slots, top_regions):
    grid = "".join(
        '<a href="%s/">%s<small>%s곳</small></a>'
        % (e(s["nm"]), e(s["nm"]), format(s["p"], ","))
        for s in index["sido"]
    )
    # 무료주차장이 많은 시군구로 바로 들어가는 링크. 사용자에게도 쓸모 있고,
    # 크롤러가 홈에서 세부 페이지까지 한 번에 닿게 해준다.
    top_links = "".join(
        '<a href="%s/%s/">%s %s<small>무료주차장 %d곳</small></a>'
        % (e(sido), e(sgg), e(SIDO_SHORT.get(sido, sido)), e(sgg), count)
        for sido, sgg, count in top_regions
    )

    count_text = format(total, ",")
    title = "전국 무료주차장 지도 | 무료 주차장 %s곳 - %s" % (count_text, SITE_NAME)
    desc = ("전국 무료주차장 %s곳을 지도 한 장에 모았습니다. 내 위치에서 가까운 무료 주차장을 "
            "바로 찾고, 시·도별 무료주차장 목록과 주차면수·운영시간·길찾기까지 확인하세요."
            % count_text)

    body = (
        "<h1>전국 무료주차장 지도</h1>"
        + '<p class="lead">돈 안 내고 대는 곳만 모았습니다. 공공데이터에 요금이 “무료”로 '
          "등록된 전국 무료 주차장 %s곳을, 내 위치 기준으로 가까운 순서로 찾아드립니다.</p>" % count_text
        + stat_block([("전국 무료주차장", count_text + "곳"),
                      ("전체 주차면", format(total_slots, ",") + "면"),
                      ("갱신일", TODAY)])
        + '<p><button class="btn primary" id="nearby">내 주변 무료주차장 찾기</button></p>'
        + '<p class="note" id="nearby-msg"></p>'
        + '<div id="map"></div>'
        # 지역 페이지와 같은 이유로 공유를 목록 앞에 둔다.
        + share_bar("전국 무료주차장 지도, 필요한 사람에게 보내주세요")
        + '<div id="nearby-result" hidden>%s</div>' % list_block()
        + ad_unit("top")
        + "<h2>시·도별 무료주차장</h2>"
        + '<div class="grid">%s</div>' % grid
        + ("<h2>무료주차장이 많은 지역</h2><div class=\"grid\">%s</div>" % top_links
           if top_links else "")
        + ad_unit("bottom")
        + faq_html()
        + "<h2>무료 주차장 정보는 어디서 왔나요</h2>"
        + '<p class="note">행정안전부가 공공데이터포털에 개방한 「전국주차장정보표준데이터」에서 '
          "요금이 무료로 등록된 주차장만 추려 매달 자동으로 갱신합니다. 노상·노외·부설 주차장이 "
          "모두 포함되며, 각 무료주차장의 주차면수와 운영시간을 함께 보여줍니다. 서버 없이 미리 "
          "만들어 둔 파일만 내려받는 구조라 지역을 눌러도 바로 열립니다.</p>"
    )

    site_ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "%s - 전국 무료주차장 지도" % SITE_NAME,
        "url": SITE_URL + "/",
        "description": desc,
        "inLanguage": "ko-KR",
    }
    dataset_ld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "전국 무료주차장 목록",
        "description": "전국 무료주차장 %s곳의 위치, 주차면수, 운영시간 정보." % count_text,
        "url": SITE_URL + "/",
        "keywords": ["무료주차장", "전국 무료주차장", "무료 주차장", "공영주차장", "주차장 지도"],
        "spatialCoverage": "대한민국",
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "행정안전부"},
        "license": "https://www.kogl.or.kr/info/license.do",
    }

    config = {
        "mode": "home", "indexUrl": "data/index.json", "dataBase": "data/",
        "ad": {"client": ADSENSE_CLIENT, "slot": AD_SLOTS["feed"]}
        if (ADSENSE_CLIENT and AD_SLOTS["feed"]) else None,
    }
    scripts = (
        MAP_SCRIPTS
        + "<script>window.FREEMAP=%s;</script>" % json.dumps(config, ensure_ascii=False)
        + '<script src="assets/app.js"></script>'
        + '<script type="application/ld+json">%s</script>' % json.dumps(site_ld, ensure_ascii=False)
        + '<script type="application/ld+json">%s</script>' % json.dumps(dataset_ld, ensure_ascii=False)
        + '<script type="application/ld+json">%s</script>' % json.dumps(faq_ld(), ensure_ascii=False)
    )
    render("index.html", title, desc, SITE_URL + "/", body, "", MAP_HEAD, scripts)


def write_support_files(urls):
    entries = "".join(
        "<url><loc>%s</loc><lastmod>%s</lastmod></url>" % (loc, TODAY) for loc in urls
    )
    with open(os.path.join(DIST, "sitemap.xml"), "w", encoding="utf-8") as fp:
        fp.write('<?xml version="1.0" encoding="UTF-8"?>'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                 + entries + "</urlset>")
    with open(os.path.join(DIST, "robots.txt"), "w", encoding="utf-8") as fp:
        fp.write("User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % SITE_URL)
    with open(os.path.join(DIST, "_headers"), "w", encoding="utf-8") as fp:
        fp.write("/assets/*\n  Cache-Control: public, max-age=604800\n"
                 "/data/*\n  Cache-Control: public, max-age=21600\n")
    if ADSENSE_CLIENT.startswith("ca-pub-"):
        with open(os.path.join(DIST, "ads.txt"), "w", encoding="utf-8") as fp:
            fp.write("google.com, %s, DIRECT, f08c47fec0942fa0\n"
                     % ADSENSE_CLIENT.replace("ca-", ""))


# --------------------------------------------------------------------------

def reset_dist():
    """dist를 비운다. OneDrive/백신이 폴더 핸들을 잡고 있으면 rmtree가 실패하므로
    몇 번 재시도하고, 그래도 안 되면 파일만 지워서 이어서 진행한다."""
    for _ in range(5):
        if not os.path.isdir(DIST):
            break
        try:
            shutil.rmtree(DIST)
            break
        except OSError:
            time.sleep(0.7)
    else:
        for base, _dirs, files in os.walk(DIST):
            for name in files:
                try:
                    os.remove(os.path.join(base, name))
                except OSError:
                    pass
        print("경고: dist 폴더를 완전히 삭제하지 못해 파일만 덮어씁니다.")
    os.makedirs(DIST, exist_ok=True)


def load_parking():
    """표준데이터 + (있으면) 서울 열린데이터광장 데이터를 이어붙인다.
    서울 파일은 같은 필드명으로 저장되므로 그대로 섞어도 된다."""
    rows = []
    for name in ("parking.json", "seoul.json"):
        path = os.path.join(RAW_DIR, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fp:
            part = json.load(fp)
        rows.extend(part)
        print("  %s: %s건" % (name, format(len(part), ",")))
    if not rows:
        raise SystemExit(
            "data/raw 에 원본이 없습니다. 먼저 실행.bat 을 실행하세요."
        )
    return rows


def main():
    raw = load_parking()
    rows = dedupe(normalize_parking(raw))
    print("원본 %s건 → 무료주차장 %s건" % (format(len(raw), ","), format(len(rows), ",")))
    if not rows:
        raise SystemExit(
            "쓸 수 있는 레코드가 0건입니다.\n"
            " - 원본이 0건이면 수집 단계 문제입니다: 진단.bat 을 실행하세요.\n"
            " - 원본은 있는데 0건이면 요금·주소·좌표 필드명이 바뀐 것입니다: "
            "python scripts/fetch_data.py --probe parking 로 필드명을 확인하세요."
        )

    regions = {}
    for row in rows:
        regions.setdefault((row["sido"], row["sigungu"]), []).append(row)

    reset_dist()
    shutil.copytree(STATIC_DIR, os.path.join(DIST, "assets"), dirs_exist_ok=True)

    by_sido = {}
    for (sido, sigungu), bucket in regions.items():
        by_sido.setdefault(sido, []).append((sigungu, bucket))

    urls = [SITE_URL + "/"]
    index = {"updated": TODAY, "sido": []}
    total_slots = sum(r["cp"] for r in rows)

    ordered_sido = [s for s in SIDO_ORDER if s in by_sido]
    ordered_sido += sorted(s for s in by_sido if s not in SIDO_ORDER)

    for sido in ordered_sido:
        items = sorted(by_sido[sido], key=lambda x: x[0])
        siblings = [(name, len(bucket)) for name, bucket in items]
        sido_total = sum(count for _name, count in siblings)

        sido_entry = {"nm": sido, "p": sido_total, "sgg": []}
        for sigungu, bucket in items:
            # 주차면수가 많은 곳이 대체로 더 쓸모 있으니 그 순서로 노출한다.
            bucket.sort(key=lambda r: (1 if r["fl"] else 0, -r["cp"], r["nm"]))
            build_region_json(sido, sigungu, bucket)
            url_path = build_region_page(sido, sigungu, bucket, siblings)
            if url_path:  # 항목이 너무 적은 지역은 noindex라 사이트맵에서도 뺀다
                urls.append(SITE_URL + "/" + url_path)
            centre = [round(statistics.median(r["la"] for r in bucket), 5),
                      round(statistics.median(r["lo"] for r in bucket), 5)]
            sido_entry["sgg"].append({"nm": sigungu, "p": len(bucket), "c": centre})

        build_sido_page(sido, siblings, sido_total)
        urls.append("%s/%s/" % (SITE_URL, sido))
        index["sido"].append(sido_entry)

    with open(os.path.join(DIST, "data", "index.json"), "w", encoding="utf-8") as fp:
        json.dump(index, fp, ensure_ascii=False, separators=(",", ":"))

    top_regions = sorted(
        ((sido, sgg, len(bucket)) for (sido, sgg), bucket in regions.items()),
        key=lambda x: -x[2],
    )[:12]

    build_home(index, len(rows), total_slots, top_regions)
    write_support_files(urls)
    print("페이지 %d개 생성 완료 -> %s" % (len(urls), DIST))


if __name__ == "__main__":
    main()

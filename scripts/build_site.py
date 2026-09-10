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
import email.utils
import hashlib
import html
import json
import os
import re
import shutil
import time
import statistics
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
STATIC_DIR = os.path.join(ROOT, "static")
# 사이트 루트에 그대로 올라가야 하는 파일들(검색엔진 소유확인 등)
PUBLIC_DIR = os.path.join(ROOT, "public")
DIST = os.path.join(ROOT, "dist")

def env(name, default=""):
    """GitHub Actions 는 등록하지 않은 vars 를 '빈 문자열'로 넘긴다.
    os.environ.get 의 기본값은 그때 적용되지 않아서, 아래 기본값들이
    통째로 빈 값으로 덮여버린다(주소가 깨지고 광고가 사라진다).
    값이 비어 있으면 없는 것으로 본다."""
    value = os.environ.get(name, "")
    value = value.strip() if value else ""
    return value or default


# canonical·사이트맵은 빌드 시점에 고정된다. 기본값을 실제 도메인으로 둬서
# 로컬에서 다시 빌드해도 주소가 어긋나지 않게 한다. 환경변수로 덮어쓸 수 있다.
SITE_URL = env("SITE_URL", "https://parking.itfinancelab.com").rstrip("/")
SITE_NAME = "공짜맵"
TODAY = datetime.date.today().isoformat()

# 애드센스 - 값이 비면 광고 태그를 아예 넣지 않는다(승인 전 빈 ins 태그 방지).
# 루트 도메인 itfinancelab.com 이 승인돼 있어 서브도메인은 별도 심사가 필요 없다.
ADSENSE_CLIENT = env("ADSENSE_CLIENT", "ca-pub-8832347985556850")
AD_SLOTS = {
    "top": env("ADSENSE_SLOT_TOP", "7312787841"),        # 지도 아래
    "feed": env("ADSENSE_SLOT_FEED", "2367582929"),      # 목록 5번째 뒤
    "bottom": env("ADSENSE_SLOT_BOTTOM", "1054501259"),  # 목록 끝
}
WRITE_ADS_TXT = os.environ.get("WRITE_ADS_TXT", "").strip() not in ("", "0", "false")


def asset_version(name):
    """assets 는 7일 캐시라, 파일이 바뀌어도 이미 방문한 기기는 옛 파일을 계속 쓴다.
    내용 해시를 주소에 붙여 내용이 바뀌면 즉시 새로 받게 한다."""
    try:
        with open(os.path.join(STATIC_DIR, name), "rb") as fp:
            return hashlib.md5(fp.read()).hexdigest()[:8]
    except OSError:
        return "0"


JS_VER = asset_version("app.js")
CSS_VER = asset_version("style.css")

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


def per30(charge, minutes):
    """기본요금은 '10분 300원', '30분 600원' 처럼 단위가 제각각이라 그대로 비교할 수 없다.
    30분 기준으로 환산해야 지도에서 싼 곳과 비싼 곳을 견줄 수 있다."""
    if charge and minutes:
        return int(round(charge * 30.0 / minutes))
    return 0


def normalize_parking(rows):
    """무료와 유료를 함께 담는다. 구분은 세 값으로 한다.
       fr=1        상시 무료
       fl=[...]    그 요일에만 무료 (평일 유료)
       p30>0       유료. 30분 환산 요금
       셋 다 비면  유료지만 요금 미신고
    """
    out = []
    for row in rows:
        fee = pick(row, "parkingchrgeInfo", "parkingchrgeinfo", "chargeInfo")
        always_free = "무료" in fee
        # 서울 데이터에만 있는 조건부 무료(토요일·공휴일 등).
        labels = [str(x).strip() for x in (row.get("freeLabels") or []) if str(x).strip()]

        address = pick(row, "rdnmadr", "lnmadr")
        sido, sigungu = split_region(address)
        point = coords(row)
        name = pick(row, "prkplceNm")
        if not (sido and sigungu and point and name):
            continue

        owner, place = parking_kinds(row)
        base_charge = to_int(pick(row, "basicCharge"))
        base_time = to_int(pick(row, "basicTime"))
        add_charge = to_int(pick(row, "addUnitCharge"))
        add_time = to_int(pick(row, "addUnitTime"))
        day_max = to_int(pick(row, "dayCmmtkt"))

        out.append({
            "sido": sido, "sigungu": sigungu,
            "nm": name, "ad": address,
            "la": point[0], "lo": point[1],
            "tm": parking_hours(row),
            "cp": to_int(pick(row, "prkcmprt")),
            "tel": pick(row, "phoneNumber"),
            "kd": owner,   # 공영 / 민영
            "se": place,   # 노상 / 노외 / 부설
            "fr": 1 if always_free else 0,
            "fl": [] if always_free else labels,
            "p30": 0 if always_free else per30(base_charge, base_time),
            "bc": 0 if always_free else base_charge,
            "bt": 0 if always_free else base_time,
            "ac": 0 if always_free else add_charge,
            "at": 0 if always_free else add_time,
            "dm": 0 if always_free else day_max,
        })
    return out


def spot_group(row):
    """목록·마커 정렬용. 무료 → 요일별 무료 → 싼 유료 → 요금 미상 순."""
    if row["fr"]:
        return 0
    if row["fl"]:
        return 1
    if row["p30"]:
        return 2
    return 3


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
<!-- 전화번호 자동 링크를 끈다. 켜두면 버튼 안 숫자를 브라우저가
     제 파란색 링크로 다시 감싸 흰 글자가 파랗게 보인다. -->
<meta name="format-detection" content="telephone=no">
<title>{{TITLE}}</title>
<meta name="description" content="{{DESC}}">
<link rel="canonical" href="{{CANONICAL}}">
<meta property="og:type" content="website">
<meta property="og:title" content="{{TITLE}}">
<meta property="og:description" content="{{DESC}}">
<meta property="og:url" content="{{CANONICAL}}">
{{VERIFY}}
<meta property="og:site_name" content="공짜맵">
<meta property="og:locale" content="ko_KR">
<meta property="og:image" content="{{SITE}}/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{{SITE}}/og.png">
{{ROBOTS}}
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#1a7a5c">
<link rel="icon" href="/icon-192.png" sizes="192x192">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="apple-mobile-web-app-title" content="공짜맵">
<meta name="mobile-web-app-capable" content="yes">
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
자료 출처: 공공데이터포털 「전국주차장정보표준데이터」, 서울 열린데이터광장<br>
매월 자동으로 다시 받아 갱신합니다. 마지막 갱신 {{UPDATED}}<br>
요금과 운영시간은 현장 사정에 따라 달라질 수 있으니 방문 전 확인하세요.<br>
<a href="{{ROOT}}privacy/">개인정보처리방침</a>
</div></footer>
{{SCRIPTS}}
</body>
</html>
"""

# 공유 썸네일 주소는 페이지마다 같으므로 템플릿에서 한 번만 박아 넣는다.
PAGE = PAGE.replace("{{SITE}}", SITE_URL)

# 네이버 지도 Client ID. HTML 소스에 그대로 실리는 공개 값이고 등록된
# 도메인에서만 동작한다. 기본값이 없으면 매월 자동 갱신 빌드가 멈춘다.
NAVER_MAP_CLIENT_ID = env("NAVER_MAP_CLIENT_ID", "y4040h6goe")

# 목적지 검색창 노출 여부. 검색 인증값을 Cloudflare 에 넣은 뒤 "1" 로 켠다.
SHOW_DESTINATION_SEARCH = env("SHOW_DESTINATION_SEARCH") != "0"
MAP_HEAD = ""
MAP_SCRIPTS = (
    '<script src="https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=%s&amp;submodules=geocoder"></script>'
    % urllib.parse.quote(NAVER_MAP_CLIENT_ID, safe="")
) if NAVER_MAP_CLIENT_ID else ""


def destination_search():
    # 검색용 인증값(NAVER_SEARCH_*)이 준비되기 전까지 검색창을 내려둔다.
    # 마크업만 있고 서버가 503 을 주면 쓸 수 없는 입력창이 그냥 보이게 된다.
    if not SHOW_DESTINATION_SEARCH:
        return ""
    return ('<section class="destination-search" aria-label="목적지 검색">'
            '<form id="destination-form" role="search">'
            '<label for="destination-query">어디에 주차하시나요?</label>'
            '<div class="search-input-row"><input id="destination-query" type="search" '
            'placeholder="장소명 또는 도로명 주소 검색" minlength="2" maxlength="100" required '
            'autocomplete="off"><button class="btn primary" type="submit">검색</button></div>'
            '</form><p id="destination-status" role="status" aria-live="polite"></p>'
            '<div id="destination-results" aria-label="목적지 검색 결과"></div></section>')



def e(text):
    return html.escape(str(text), quote=True)


def kakao_sdk():
    if not KAKAO_JS_KEY:
        return ""
    return ('<script src="https://t1.kakaocdn.net/kakao_js_sdk/2.7.5/kakao.min.js" '
            'crossorigin="anonymous"></script>')


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
            # push 는 app.js 가 로드 완료 후에 한다. 파싱 도중 인라인으로 부르면
            # 아직 레이아웃 전이라 availableWidth=0 오류로 광고가 안 뜬다.
            "</aside>") % (kind, ADSENSE_CLIENT, slot)


def share_bar(prompt):
    """공유 버튼. 주소·제목은 JS가 location.href 에서 읽으므로 도메인이 바뀌어도 그대로 동작한다."""
    buttons = [
        # SDK 가 준비돼야 동작하므로 JS 가 켤 때까지 숨겨둔다
        ("kakao", "카카오톡 공유", " hidden"),
        ("instagram", "인스타그램 공유", ""),
        ("facebook", "페이스북 공유", ""),
        ("native", "공유하기", " hidden"),   # navigator.share 가 있을 때만 JS가 켠다
        ("copy", "주소 복사", ""),
        ("naver", "네이버 블로그", ""),
        ("x", "X", ""),
    ]
    # 브랜드 색을 쓰는 버튼은 같은 이름의 클래스를 함께 준다.
    branded = {"kakao", "instagram", "facebook"}
    tags = "".join(
        '<button type="button" class="btn%s" data-share="%s"%s>%s</button>'
        % ((" " + key) if key in branded else "", key, extra, label)
        for key, label, extra in buttons
    )
    return ('<section class="share"><p class="share-label">%s</p>'
            '<div class="share-btns">%s</div></section>') % (e(prompt), tags)


# 실제 자동완성에 뜨는 연관 검색어(무료주차장 찾기 / 어플 / 찾는법 / 장기주차 /
# 사이트 / 사고 책임)를 그대로 질문으로 받아 답한다. FAQPage 스키마로도 내보낸다.
FAQ = [
    # 브랜드명으로 검색해서 들어온 사람에게 이 사이트가 맞는지 바로 확인시켜 준다.
    ("공짜맵은 어떤 사이트인가요?",
     "공짜맵은 전국 주차장 18,000여 곳의 무료 여부와 주차요금을 지도 한 장에서 "
     "비교하는 무료주차장 지도 사이트입니다. 공짜로 댈 수 있는 곳은 “무료”로, "
     "돈을 내야 하는 곳은 30분 요금으로 표시합니다. 회원가입도, 앱 설치도 "
     "필요 없이 웹에서 바로 열립니다."),
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


# 개인정보처리방침에 공개되는 문의처. 애드센스 승인 필수 항목이다.
CONTACT_EMAIL = env("CONTACT_EMAIL", "rtyq1308@gmail.com")

# 검색엔진 소유권 확인 메타태그. 값이 비면 태그를 넣지 않는다.
GOOGLE_VERIFY = env("GOOGLE_SITE_VERIFICATION", "ek4vpJNgTIsiM8ANiutfJvFiyOw_L92I-BwNjx0U4CM")
NAVER_VERIFY = env("NAVER_SITE_VERIFICATION")

# 카카오톡 공유용 JavaScript 앱 키. 도메인 제한이 걸리는 공개 키라 노출돼도 된다.
# https://developers.kakao.com 앱 만들기 -> 앱 키 -> JavaScript 키
# 값이 없으면 카카오톡 공유 버튼을 아예 렌더링하지 않는다.
# REST API 키나 네이티브 앱 키가 아니라 JavaScript 키를 넣어야 한다.
# 도메인이 등록된 곳에서만 동작하므로 HTML 에 노출돼도 된다.
KAKAO_JS_KEY = env("KAKAO_JS_KEY", "e4aea89052f4eee41ab344a66531fddd")

# 구글 애널리틱스 4 측정 ID. 메인 도메인과 다른 속성이라 데이터가 섞이지 않는다.
# 페이지 소스에 그대로 노출되는 공개 값이다.
GA_ID = env("GA_MEASUREMENT_ID", "G-7R6BSLQN06")


def analytics_tag():
    """값이 비면 스크립트를 아예 넣지 않는다."""
    if not GA_ID:
        return ""
    return ('<script async src="https://www.googletagmanager.com/gtag/js?id=%s"></script>'
            "<script>window.dataLayer=window.dataLayer||[];"
            "function gtag(){dataLayer.push(arguments);}"
            'gtag("js",new Date());gtag("config","%s");</script>') % (e(GA_ID), e(GA_ID))


# 마이크로소프트 클래리티 프로젝트 ID. 히트맵·세션 기록용.
CLARITY_ID = env("CLARITY_ID", "yf827u85ho")


def clarity_tag():
    """값이 비면 스크립트를 아예 넣지 않는다."""
    if not CLARITY_ID:
        return ""
    return ('<script>(function(c,l,a,r,i,t,y){'
            'c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};'
            't=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;'
            'y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);'
            '})(window, document, "clarity", "script", "%s");</script>') % e(CLARITY_ID)


def verification_tags():
    tags = []
    if GOOGLE_VERIFY:
        tags.append('<meta name="google-site-verification" content="%s">' % e(GOOGLE_VERIFY))
    if NAVER_VERIFY:
        tags.append('<meta name="naver-site-verification" content="%s">' % e(NAVER_VERIFY))
    return "".join(tags)

# 애드센스 승인 필수 요건. 내용은 이 사이트가 실제로 하는 일과 정확히 일치해야 한다.
PRIVACY_SECTIONS = [
    ("수집하는 개인정보", [
        "이 사이트는 회원가입과 로그인이 없으며, 이름·전화번호·이메일 등 개인을 "
        "식별할 수 있는 정보를 직접 수집하지 않습니다.",
        "별도의 데이터베이스 서버를 운영하지 않고, 미리 만들어 둔 정적 파일만 "
        "제공합니다. 이용자가 입력한 내용을 저장하는 기능 자체가 없습니다.",
    ]),
    ("위치정보 처리", [
        "“내 주변 무료주차장 찾기” 기능은 브라우저의 위치정보 기능(Geolocation API)을 "
        "사용합니다. 이 위치는 <b>이용자의 기기 안에서만</b> 가까운 주차장을 계산하는 데 "
        "쓰이며, 서버로 전송하거나 저장하지 않습니다.",
        "위치 권한 요청을 거부해도 사이트의 다른 기능은 모두 정상적으로 이용할 수 "
        "있습니다. 권한은 브라우저 설정에서 언제든 철회할 수 있습니다.",
    ]),
    ("쿠키와 광고", [
        "이 사이트는 구글 애드센스를 통해 광고를 게재할 수 있습니다. 구글을 포함한 "
        "제3자 광고 공급업체는 쿠키를 사용하여 이용자의 이전 방문 기록을 바탕으로 "
        "광고를 게재할 수 있습니다.",
        "구글의 광고 쿠키 사용은 "
        '<a href="https://policies.google.com/technologies/ads" target="_blank" '
        'rel="noopener">구글 광고 정책</a>을 따릅니다. 개인 맞춤 광고는 '
        '<a href="https://myadcenter.google.com" target="_blank" rel="noopener">'
        "구글 광고 설정</a>에서 해제할 수 있습니다.",
        "또한 방문자 수와 어떤 지역이 많이 조회되는지 파악하기 위해 구글 애널리틱스를 "
        "사용합니다. 방문 시각·페이지 주소·기기 종류·대략적인 지역 같은 통계 정보만 "
        "수집하며, 이름이나 연락처 같은 개인 식별 정보는 수집하지 않습니다.",
        "화면의 어느 부분이 많이 눌리는지 살펴 사용성을 개선하기 위해 마이크로소프트 "
        "클래리티(Microsoft Clarity)도 함께 사용합니다. 클릭·스크롤 위치와 화면 이동 "
        "기록이 남으며, 입력창에 적은 내용은 자동으로 가려져 수집되지 않습니다.",
        "브라우저 설정에서 쿠키를 차단할 수 있으며, 차단하더라도 주차장 정보 조회에는 "
        "지장이 없습니다.",
    ]),
    ("접속 기록", [
        "이 사이트는 Cloudflare Pages로 호스팅됩니다. 호스팅 제공자는 서비스 운영과 "
        "보안을 위해 접속 IP, 브라우저 종류 등의 기술적 기록을 처리할 수 있습니다. "
        "운영자는 이 기록을 개별적으로 조회하거나 다른 정보와 결합하지 않습니다.",
    ]),
    ("외부 서비스 연결", [
        "지도는 OpenStreetMap의 타일 이미지를 사용합니다. 각 주차장의 “카카오맵 길찾기”, "
        "“구글맵” 버튼을 누르면 해당 외부 서비스로 이동하며, 이동한 뒤에는 각 서비스의 "
        "개인정보 처리방침이 적용됩니다.",
    ]),
    ("정보의 정확성", [
        "주차장 정보는 행정안전부 「전국주차장정보표준데이터」와 서울 열린데이터광장의 "
        "공영주차장 정보를 가공한 것입니다. 지방자치단체가 신고한 내용을 그대로 반영하므로 "
        "실제 요금·운영시간과 다를 수 있으며, 이용자는 방문 전 현장 안내를 확인해야 합니다.",
        "잘못된 정보로 인해 발생한 손해에 대해 운영자는 책임을 지지 않습니다.",
    ]),
    ("만 14세 미만 아동", [
        "이 사이트는 만 14세 미만 아동을 대상으로 하지 않으며, 아동의 개인정보를 "
        "고의로 수집하지 않습니다.",
    ]),
]


def build_privacy_page():
    blocks = []
    for index, (title, paragraphs) in enumerate(PRIVACY_SECTIONS, start=1):
        body = "".join("<p>%s</p>" % p for p in paragraphs)   # 링크·<b> 유지 위해 이스케이프 안 함
        blocks.append("<h2>%d. %s</h2>%s" % (index, e(title), body))

    contact = (
        '<p>개인정보 처리에 관한 문의는 <a href="mailto:%s">%s</a> 로 보내주시기 바랍니다.</p>'
        % (e(CONTACT_EMAIL), e(CONTACT_EMAIL))
        if CONTACT_EMAIL else
        '<p class="note">※ 운영자 연락처가 아직 설정되지 않았습니다. '
        "빌드 시 환경변수 <code>CONTACT_EMAIL</code> 을 지정하면 이 자리에 표시됩니다. "
        "애드센스 승인 신청 전에 반드시 채워야 합니다.</p>"
    )

    body = (
        '<p class="crumb"><a href="../">홈</a> › 개인정보처리방침</p>'
        + "<h1>개인정보처리방침</h1>"
        + '<p class="lead">공짜맵(이하 “사이트”)은 이용자의 개인정보를 소중히 다루며, '
          "이 사이트가 정보를 어떻게 다루는지 아래와 같이 안내합니다.</p>"
        + "".join(blocks)
        + "<h2>%d. 문의처</h2>%s" % (len(PRIVACY_SECTIONS) + 1, contact)
        + "<h2>%d. 방침의 변경</h2>" % (len(PRIVACY_SECTIONS) + 2)
        + "<p>이 방침의 내용이 바뀌는 경우 이 페이지를 통해 알립니다.</p>"
        + '<p class="note">시행일: %s</p>' % TODAY
    )
    render("privacy/index.html", "개인정보처리방침 | %s" % SITE_NAME,
           "공짜맵의 개인정보처리방침입니다. 위치정보 처리, 쿠키와 광고, 접속 기록에 "
           "대한 안내를 담고 있습니다.",
           SITE_URL + "/privacy/", body, "../")


def listbar_block(hidden=False):
    """무료만 보기 필터. 목록 바로 위가 아니라 지도 바로 아래에 둔다.
    공유 상자와 광고를 지나 한참 스크롤해야 나오면 아무도 못 누른다."""
    return ('<div class="listbar" id="listbar"%s>' % (" hidden" if hidden else "")
            + '<button type="button" class="btn" id="only-free" aria-pressed="false">'
              '가까운 무료 주차장 우선으로 확인하기</button>'
              '<span class="note" id="list-count"></span>'
              "</div>")


def list_block():
    return '<div id="list" class="list"></div><p id="more" class="note"></p>'



def stat_block(pairs):
    cells = "".join(
        '<div class="stat"><b>%s</b><span>%s</span></div>' % (e(value), e(label))
        for label, value in pairs
    )
    return '<div class="stats">%s</div>' % cells


def map_workspace(body):
    """Keep regional content crawlable in a menu; give the map the main viewport."""
    body = body.replace(destination_search(), '') if destination_search() else body
    body = re.sub(r'<div id="map"[^>]*></div>', '', body)
    body = re.sub(r'<p class="cta">.*?</p>', '', body, flags=re.S)
    body = body.replace('<p class="note" id="nearby-msg"></p>', '')
    body = body.replace('<div id="nearby-result" hidden>%s</div>' % list_block(), '')
    body = body.replace(list_block(), '').replace(listbar_block(), '').replace(listbar_block(True), '')
    ads = re.findall(r'<aside class="ad-slot ad-top">.*?</aside>', body, re.S)
    # Responsive ads force fixed-height ancestors to auto height. Use a standard
    # fixed slot inside the independently scrolling results panel instead.
    ads = [ad.replace('style="display:block"', 'style="display:block;width:300px;height:250px"')
           .replace(' data-ad-format="auto" data-full-width-responsive="true"', '') for ad in ads]
    body = re.sub(r'<aside class="ad-slot ad-(?:top|bottom)">.*?</aside>', '', body, flags=re.S)
    navigation = re.findall(r'<h2>[^<]*</h2><div class="grid">.*?</div>', body, re.S)
    sharing = re.findall(r'<section class="share">.*?</section>', body, re.S)
    for section in navigation + sharing:
        body = body.replace(section, '')
    return (
        '<div class="map-workspace">'
        '<div class="map-topbar"><a class="map-brand" href="/">공짜맵<small>전국 무료주차장 지도</small></a>'
        '<div class="map-top-tools"><button class="btn" id="nearby">내 주변 찾기</button>'
        '<button class="btn" id="only-free" aria-pressed="false">상시 무료</button>'
        '<button class="btn" id="install-app">앱 설치</button></div></div>'
        '<nav class="map-actions" aria-label="지도 도구">'
        '<button id="search-toggle" aria-label="검색" title="검색" aria-expanded="false" aria-controls="map-search-panel">'
        '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></svg></button>'
        '<button data-menu-open aria-label="메뉴" title="메뉴"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg></button>'
        '<button data-share="quick" aria-label="공유하기" title="공유하기"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="12" r="3"/><circle cx="18" cy="5" r="3"/><circle cx="18" cy="19" r="3"/><path d="m9 10 6-4m-6 8 6 4"/></svg></button></nav>'
        '<section class="map-controls" id="map-search-panel" aria-label="주차장 찾기" hidden>'
        + destination_search() + '</section>'
        '<div class="map-feedback"><p id="nearby-msg" class="note" role="status"></p></div>'
          '<section class="map-canvas" aria-label="지도 탐색">'
          '<div id="map" role="region" aria-label="주차장 지도"></div>'
          '<div class="map-zoom" aria-label="지도 확대 축소"><button id="zoom-in" aria-label="지도 확대">+</button><button id="zoom-out" aria-label="지도 축소">−</button></div>'
          '<button class="btn map-research" id="map-research">이 지도 중심에서 찾기</button>'
          '<div class="map-legend"><span>● 무료</span><span>● 요일별 무료</span><span>● 유료</span></div>'
          '</section><section class="map-results" aria-label="주차장 목록">'
          '<button class="sheet-toggle" id="sheet-toggle" aria-expanded="false" aria-controls="results-scroll">'
          '<span class="sheet-grip"></span><span>주차장 목록 <span id="sheet-action">펼치기 ↑</span></span></button>'
          '<div class="results-heading"><div><span class="map-eyebrow">PARKING AROUND YOU</span>'
          '<h2>주차할 곳, 한눈에</h2></div><span id="list-count" role="status"></span></div>'
          '<div id="results-scroll" class="results-scroll">'
          '<p class="results-context" id="results-context">지도를 확대하거나 목적지를 검색해 주세요.</p>'
          + list_block()
          + '<p class="results-disclaimer">요금·운영시간은 방문 전 현장에서 확인하세요.</p></div></section>'
          '<dialog id="spot-detail" aria-label="주차장 상세 정보"></dialog>'
          '<dialog id="map-menu" aria-labelledby="menu-title"><div class="menu-heading">'
          '<h2 id="menu-title">지역 탐색 · 이용 안내</h2><button class="btn" id="menu-close">닫기 ✕</button></div>'
          + '<details open><summary>지역별 주차장 찾기</summary>' + ''.join(navigation) + '</details>'
          + '<details><summary>공짜맵 공유하기</summary>' + ''.join(sharing) + '</details>'
          + '<details><summary>서비스 소개 · 이용 안내</summary>' + body + '</details>'
          + '<p class="note">자료: 공공데이터포털 · 서울 열린데이터광장</p>'
          '<a href="/privacy/">개인정보처리방침</a></dialog>'
          '<noscript><p>지도 검색은 자바스크립트가 필요합니다. <a href="/서울특별시/">서울 지역 목록 보기</a></p></noscript>'
          '</div>'
    )


def render(path, title, desc, canonical, body, root, head="", scripts="", indexable=True):
    page = PAGE
    if 'id="map"' in body:
        body = map_workspace(body)
        page = page.replace('<body>', '<body class="map-page">')
        head += '<link rel="stylesheet" href="%sassets/map-layout.css?v=%s">' % (root, asset_version('map-layout.css'))
    robots = "" if indexable else '<meta name="robots" content="noindex,follow">'
    for key, value in [
        ("{{TITLE}}", title), ("{{DESC}}", desc), ("{{CANONICAL}}", canonical),
        ("{{BODY}}", body), ("{{ROOT}}", root),
        ("{{HEAD}}", analytics_tag() + clarity_tag() + adsense_head() + head),
        ("{{ROBOTS}}", robots),
        ("{{VERIFY}}", verification_tags()),
        ("{{SCRIPTS}}", kakao_sdk() + scripts), ("{{UPDATED}}", TODAY),
    ]:
        page = page.replace(key, value)

    # 캐시 무효화. 파일 내용이 바뀔 때만 주소가 바뀌므로 캐시 이점은 그대로 둔다.
    page = page.replace('assets/app.js"', 'assets/app.js?v=%s"' % JS_VER)
    page = page.replace('assets/style.css"', 'assets/style.css?v=%s"' % CSS_VER)

    full = os.path.join(DIST, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(page)


# --------------------------------------------------------------------------
# 페이지 생성
# --------------------------------------------------------------------------

FIELDS = ["nm", "ad", "la", "lo", "tm", "cp", "tel", "kd", "se",
          "fr", "fl", "p30", "bc", "bt", "ac", "at", "dm"]


def lead_text(free_n, partly_n, paid_n, cheapest):
    """지역마다 구성이 크게 달라서(서울은 상시 무료가 거의 없다) 문구를 나눠 쓴다."""
    bits = []
    if free_n:
        bits.append("언제 가도 공짜인 곳 %d곳" % free_n)
    if partly_n:
        bits.append("특정 요일에만 무료로 풀리는 곳 %d곳" % partly_n)
    if paid_n:
        if cheapest:
            bits.append("유료 %d곳(가장 싼 곳은 30분 %s원)" % (paid_n, format(cheapest, ",")))
        else:
            bits.append("유료 %d곳" % paid_n)

    if not bits:
        return "등록된 주차장 정보가 없습니다."
    head = ", ".join(bits[:-1])
    tail = bits[-1]
    joined = (head + ", " + tail) if head else tail
    return (joined + "입니다. 무료가 먼저 나오고, 유료는 30분 요금이 싼 순서로 "
            "보여줍니다. 요금은 카드와 지도에 함께 표시했습니다.")


def build_region_json(sido, sigungu, rows):
    payload = {
        "sido": sido,
        "sigungu": sigungu,
        "p": {"f": FIELDS, "d": [[r[k] for k in FIELDS] for r in rows]},
    }
    path = os.path.join(DIST, "data", sido, sigungu + ".json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        json.dump(payload, fp, ensure_ascii=False, separators=(",", ":"))


def build_region_page(sido, sigungu, rows, siblings):
    url_path = "%s/%s/" % (sido, sigungu)
    short = SIDO_SHORT.get(sido, sido)
    total_slots = sum(r["cp"] for r in rows)
    rich = len(rows) >= THIN_PAGE_MIN
    always = [r for r in rows if r["fr"]]
    partly = [r for r in rows if r["fl"]]
    paid = [r for r in rows if not r["fr"] and not r["fl"]]
    priced = [r for r in paid if r["p30"]]
    cheapest = min((r["p30"] for r in priced), default=0)

    title = "%s %s 주차장 %d곳 | 무료 %d곳·요금 비교 - %s" % (
        short, sigungu, len(rows), len(always), SITE_NAME)
    desc = ("%s %s의 주차장 %d곳을 한눈에. 상시 무료 %d곳과 유료 %d곳의 30분 요금을 "
            "지도에서 비교하고 길찾기까지 바로 하세요."
            % (sido, sigungu, len(rows), len(always), len(paid)))

    nearby = "".join(
        '<a href="../%s/">%s<small>주차장 %d곳</small></a>' % (name, e(name), count)
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
        + "<h1>%s %s 무료·유료 주차장</h1>" % (e(sido), e(sigungu))
        + '<p class="lead">%s</p>' % lead_text(len(always), len(partly), len(paid), cheapest)
        + stat_block(
            [("상시 무료", "%d곳" % len(always))]
            + ([("요일별 무료", "%d곳" % len(partly))] if partly else [])
            + ([("유료", "%d곳" % len(paid))] if paid else [])
            + [("전체 주차면", format(total_slots, ",") + "면")])
        + destination_search()
        + '<div id="map" role="region" aria-label="주차장 지도"></div>'
        + ad_unit("top", rich)
        + listbar_block()
        # 공유는 목록 앞에 둔다. 목록이 수백 장까지 늘어나기 때문에 뒤에 두면
        # 화면상 만 픽셀 아래로 밀려 아무도 못 본다.
        + share_bar("%s %s 주차장 요금 지도, 필요한 사람에게 보내주세요" % (sido, sigungu))
        + list_block()
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
        "mode": "region", "indexUrl": "/data/index.json", "dataBase": "/data/",
        "kakaoKey": KAKAO_JS_KEY,
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
        '<a href="%s/">%s<small>주차장 %d곳</small></a>' % (e(name), e(name), count)
        for name, count in siblings
    )
    title = "%s 주차장 %s곳 | 무료주차장·요금 지도 - %s" % (short, format(total, ","), SITE_NAME)
    desc = ("%s의 무료·유료 주차장 %s곳을 시군구별로 정리했습니다. 지역을 고르면 지도와 "
            "목록에서 무료 여부와 30분 요금을 바로 비교할 수 있습니다."
            % (sido, format(total, ",")))
    body = (
        '<p class="crumb"><a href="../">홈</a> › %s</p>' % e(sido)
        + "<h1>%s 무료·유료 주차장</h1>" % e(sido)
        + '<p class="lead">시군구를 선택하면 지도와 목록이 열립니다. '
          '무료가 먼저 나오고, 유료는 30분 요금이 싼 순서로 보여줍니다.</p>'
        + stat_block([("주차장", format(total, ",") + "곳"),
                      ("지역", "%d개 시군구" % len(siblings))])
        + "<h2>%s 시군구별 주차장</h2>" % e(short)
        + '<div class="grid">%s</div>' % grid
        + share_bar("%s 주차장 요금 지도, 주변에 공유해보세요" % sido)
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
    scripts = ('<script>window.FREEMAP={mode:"static",kakaoKey:%s};</script>'
               % json.dumps(KAKAO_JS_KEY)
               + '<script src="../assets/app.js"></script>'
               + '<script type="application/ld+json">%s</script>'
               % json.dumps(breadcrumb, ensure_ascii=False))
    render(os.path.join(sido, "index.html"), title, desc,
           "%s/%s/" % (SITE_URL, sido), body, "../", scripts=scripts)


def build_home(index, total, total_slots, top_regions, free_total):
    grid = "".join(
        '<a href="%s/">%s<small>%s곳</small></a>'
        % (e(s["nm"]), e(s["nm"]), format(s["p"], ","))
        for s in index["sido"]
    )
    # 무료주차장이 많은 시군구로 바로 들어가는 링크. 사용자에게도 쓸모 있고,
    # 크롤러가 홈에서 세부 페이지까지 한 번에 닿게 해준다.
    top_links = "".join(
        '<a href="%s/%s/">%s %s<small>주차장 %d곳</small></a>'
        % (e(sido), e(sgg), e(SIDO_SHORT.get(sido, sido)), e(sgg), count)
        for sido, sgg, count in top_regions
    )

    count_text = format(total, ",")
    # 브랜드명('공짜맵')으로 검색했을 때 잡히도록 제목 맨 앞에 둔다.
    title = "%s - 전국 무료주차장·주차요금 지도 | 주차장 %s곳" % (SITE_NAME, count_text)
    desc = ("전국 주차장 %s곳을 지도 한 장에. 무료주차장은 무료로, 유료는 30분 요금으로 "
            "표시해 바로 비교됩니다. 내 위치에서 가까운 순으로 찾고 길찾기까지 하세요."
            % count_text)

    body = (
        "<h1>전국 무료주차장 · 주차요금 지도</h1>"
        + '<p class="lead">공짜로 댈 수 있는 곳은 “무료”로, 돈을 내야 하는 곳은 '
          "30분 요금으로 지도에 바로 띄웁니다. 전국 주차장 %s곳 가운데 "
          "상시 무료가 %s곳입니다.</p>" % (count_text, format(free_total, ","))
        + '<p class="cta"><button class="btn primary" id="nearby">내 주변 무료주차장 찾기</button>'
          '<button type="button" class="btn" id="install-app" hidden>앱 설치 바로가기</button></p>'
        + '<p class="note" id="nearby-msg"></p>'
        + destination_search()
        + '<div id="map" role="region" aria-label="주차장 지도"></div>'
        + ad_unit("top")
        + listbar_block(hidden=True)
        # 지역 페이지와 같은 이유로 공유를 목록 앞에 둔다.
        + share_bar("전국 주차장 요금 지도, 필요한 사람에게 보내주세요")
        + '<div id="nearby-result" hidden>%s</div>' % list_block()
        + "<h2>시·도별 무료주차장</h2>"
        + '<div class="grid">%s</div>' % grid
        + ("<h2>무료주차장이 많은 지역</h2><div class=\"grid\">%s</div>" % top_links
           if top_links else "")
        + ad_unit("bottom")
        + faq_html()
        + "<h2>공짜맵 소개</h2>"
        + '<p class="note">공짜맵은 전국 주차장의 무료 여부와 주차요금을 지도에서 '
          "바로 비교하는 무료주차장 지도입니다. 공영·노상·노외·부설 주차장을 모두 모아 "
          "상시 무료인 곳은 “무료”로, 요금을 받는 곳은 30분 기준 요금으로 표시합니다. "
          "회원가입과 앱 설치 없이 열리고, 휴대폰에서는 “앱 설치 바로가기”로 "
          "홈 화면에 추가해 앱처럼 쓸 수 있습니다.</p>"
        + "<h2>무료 주차장 정보는 어디서 왔나요</h2>"
        + '<p class="note">행정안전부가 공공데이터포털에 개방한 「전국주차장정보표준데이터」에서 '
          "요금이 무료로 등록된 주차장만 추려 매달 자동으로 갱신합니다. 노상·노외·부설 주차장이 "
          "모두 포함되며, 각 무료주차장의 주차면수와 운영시간을 함께 보여줍니다. 서버 없이 미리 "
          "만들어 둔 파일만 내려받는 구조라 지역을 눌러도 바로 열립니다.</p>"
        # 요약 숫자는 첫 화면을 밀어내지 않게 맨 아래에 둔다.
        + stat_block([("무료주차장", format(free_total, ",") + "곳"),
                      ("전체 주차장", count_text + "곳"),
                      ("갱신일 · 매월 자동 갱신", TODAY)])
    )

    site_ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "alternateName": ["공짜맵", "공짜 맵", "무료주차장 지도"],
        "url": SITE_URL + "/",
        "description": desc,
        "inLanguage": "ko-KR",
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": SITE_URL + "/",
            "logo": {"@type": "ImageObject", "url": SITE_URL + "/icon-512.png"},
        },
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
        "kakaoKey": KAKAO_JS_KEY,
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


LASTMOD_PATH = os.path.join(ROOT, "data", "lastmod.json")


def load_lastmod():
    """페이지별 '내용 해시 + 마지막으로 실제 바뀐 날짜'. 저장소에 함께 커밋한다."""
    try:
        with open(LASTMOD_PATH, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, ValueError):
        return {}


def resolve_lastmod(entries):
    """내용이 그대로면 예전 날짜를 유지한다.

    매번 오늘 날짜를 넣으면 바뀌지도 않은 242개 페이지가 전부 '오늘 수정됨'이
    되어, 검색엔진이 lastmod 자체를 신뢰하지 않게 되고 크롤 예산도 낭비된다.
    entries: [(url, content_hash)] -> {url: 'YYYY-MM-DD'}
    """
    old = load_lastmod()
    new, dates, changed = {}, {}, 0
    for url, digest in entries:
        prev = old.get(url)
        if prev and prev.get("h") == digest:
            dates[url] = prev.get("d", TODAY)
        else:
            dates[url] = TODAY
            changed += 1
        new[url] = {"h": digest, "d": dates[url]}

    with open(LASTMOD_PATH, "w", encoding="utf-8", newline="\n") as fp:
        json.dump(new, fp, ensure_ascii=False, indent=0, sort_keys=True)
    print("  변경된 페이지 %d개 / 전체 %d개" % (changed, len(entries)))
    return dates


def content_hash(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def esc_url(url):
    """사이트맵·RSS 규격은 주소를 URL 이스케이프하도록 요구한다.
    주소에 한글이 들어가므로 그대로 두면 검증에서 거절될 수 있다."""
    return urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=~-._")


def write_rss(items, dates):
    """네이버 웹마스터도구는 사이트맵과 별개로 RSS 도 받는다.
    글이 쌓이는 사이트가 아니므로, 주차장이 많은 지역 페이지를 항목으로 낸다."""
    now = email.utils.formatdate(usegmt=True)
    entries = []
    for title, link, desc in items[:100]:
        # 실제로 내용이 바뀐 날. 매번 빌드 시각을 넣으면 네이버가
        # 매주 '새 글 100개'로 오인한다.
        day = dates.get(link, TODAY)
        pub = email.utils.formatdate(
            time.mktime(datetime.date.fromisoformat(day).timetuple()), usegmt=True)
        entries.append(
            "<item>"
            "<title>%s</title>"
            "<link>%s</link>"
            "<guid isPermaLink=\"true\">%s</guid>"
            "<description>%s</description>"
            "<pubDate>%s</pubDate>"
            "</item>" % (e(title), esc_url(link), esc_url(link), e(desc), pub)
        )
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<rss version="2.0"><channel>'
           "<title>%s</title>"
           "<link>%s/</link>"
           "<description>전국 주차장의 무료 여부와 30분 요금을 지도에서 비교합니다.</description>"
           "<language>ko</language>"
           "<lastBuildDate>%s</lastBuildDate>"
           "%s</channel></rss>"
           ) % (e("%s - 전국 무료주차장·주차요금 지도" % SITE_NAME), SITE_URL, now, "".join(entries))
    with open(os.path.join(DIST, "rss.xml"), "w", encoding="utf-8", newline="\n") as fp:
        fp.write(xml)


def write_support_files(urls, dates):
    entries = "".join(
        "<url><loc>%s</loc><lastmod>%s</lastmod></url>"
        % (e(esc_url(loc)), dates.get(loc, TODAY))
        for loc in urls
    )
    with open(os.path.join(DIST, "sitemap.xml"), "w", encoding="utf-8", newline="\n") as fp:
        fp.write('<?xml version="1.0" encoding="UTF-8"?>'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                 + entries + "</urlset>")
    with open(os.path.join(DIST, "robots.txt"), "w", encoding="utf-8", newline="\n") as fp:
        fp.write("User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % SITE_URL)
    with open(os.path.join(DIST, "_headers"), "w", encoding="utf-8", newline="\n") as fp:
        fp.write("/assets/*\n  Cache-Control: public, max-age=604800\n"
                 "/data/*\n  Cache-Control: public, max-age=21600\n")
    # ads.txt 는 기본적으로 만들지 않는다.
    # 이 사이트는 서브도메인이고, 애드센스는 루트 도메인(itfinancelab.com)의
    # ads.txt 로 서브도메인까지 판정한다. 루트가 이미 승인된 상태라 서브도메인에
    # 별도 파일을 두면 오히려 충돌 소지가 있다.
    # 독립 도메인으로 옮길 때만 WRITE_ADS_TXT=1 로 켠다.
    if WRITE_ADS_TXT and ADSENSE_CLIENT.startswith("ca-pub-"):
        with open(os.path.join(DIST, "ads.txt"), "w", encoding="utf-8", newline="\n") as fp:
            fp.write("google.com, %s, DIRECT, f08c47fec0942fa0\n"
                     % ADSENSE_CLIENT.replace("ca-", ""))


# --------------------------------------------------------------------------

def reset_dist():
    """dist를 비운다. OneDrive/백신이 폴더 핸들을 잡고 있으면 rmtree가 실패하므로
    몇 번 재시도하고, 그래도 안 되면 파일만 지워서 이어서 진행한다."""
    if os.path.realpath(DIST) not in {os.path.realpath(os.path.join(ROOT, name)) for name in ("dist", ".preview")}:
        raise RuntimeError("허용된 출력 폴더가 아닙니다.")
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
    if os.path.basename(DIST) == "dist" and not NAVER_MAP_CLIENT_ID:
        raise SystemExit("NAVER_MAP_CLIENT_ID 설정이 필요합니다. 연결 전 화면 점검은 --preview를 사용하세요.")
    raw = load_parking()
    rows = dedupe(normalize_parking(raw))
    free_n = sum(1 for r in rows if r["fr"])
    part_n = sum(1 for r in rows if r["fl"])
    paid_n = len(rows) - free_n - part_n
    print("원본 %s건 → 주차장 %s건 (상시무료 %s / 요일별 %s / 유료 %s)"
          % (format(len(raw), ","), format(len(rows), ","),
             format(free_n, ","), format(part_n, ","), format(paid_n, ",")))
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
    if os.path.isdir(PUBLIC_DIR):
        shutil.copytree(PUBLIC_DIR, DIST, dirs_exist_ok=True)

    by_sido = {}
    for (sido, sigungu), bucket in regions.items():
        by_sido.setdefault(sido, []).append((sigungu, bucket))

    urls = [SITE_URL + "/"]
    feed_items = []
    hashes = []   # (url, 내용 해시) - 실제로 바뀐 페이지만 lastmod 를 올린다
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
            bucket.sort(key=lambda r: (spot_group(r), r["p30"], -r["cp"], r["nm"]))
            build_region_json(sido, sigungu, bucket)
            url_path = build_region_page(sido, sigungu, bucket, siblings)
            if url_path:  # 항목이 너무 적은 지역은 noindex라 사이트맵에서도 뺀다
                page_url = SITE_URL + "/" + url_path
                urls.append(page_url)
                hashes.append((page_url, content_hash(bucket)))
                free_here = sum(1 for r in bucket if r["fr"])
                feed_items.append((
                    len(bucket),
                    "%s %s 무료·유료 주차장 %d곳" % (SIDO_SHORT.get(sido, sido), sigungu, len(bucket)),
                    SITE_URL + "/" + url_path,
                    "상시 무료 %d곳을 포함한 주차장 %d곳의 위치와 30분 요금."
                    % (free_here, len(bucket)),
                ))
            centre = [round(statistics.median(r["la"] for r in bucket), 5),
                      round(statistics.median(r["lo"] for r in bucket), 5)]
            # f: 상시 무료 수. 홈 지도의 묶음 풍선에 쓴다.
            sido_entry["sgg"].append({
                "nm": sigungu, "p": len(bucket),
                "f": sum(1 for r in bucket if r["fr"]), "c": centre,
            })

        build_sido_page(sido, siblings, sido_total)
        sido_url = "%s/%s/" % (SITE_URL, sido)
        urls.append(sido_url)
        hashes.append((sido_url, content_hash(siblings)))
        index["sido"].append(sido_entry)

    with open(os.path.join(DIST, "data", "index.json"), "w", encoding="utf-8", newline="\n") as fp:
        json.dump(index, fp, ensure_ascii=False, separators=(",", ":"))

    top_regions = sorted(
        ((sido, sgg, len(bucket)) for (sido, sgg), bucket in regions.items()),
        key=lambda x: -x[2],
    )[:12]

    build_home(index, len(rows), total_slots, top_regions, free_n)
    hashes.append((SITE_URL + "/", content_hash(index)))

    build_privacy_page()
    urls.append(SITE_URL + "/privacy/")
    hashes.append((SITE_URL + "/privacy/", content_hash([PRIVACY_SECTIONS, CONTACT_EMAIL])))

    dates = resolve_lastmod(hashes)
    write_support_files(urls, dates)
    # RSS 는 주차장이 많은 지역부터. 네이버가 사이트맵과 별개로 받는다.
    feed_items.sort(key=lambda x: -x[0])
    write_rss([(t, l, d) for _n, t, l, d in feed_items], dates)
    print("페이지 %d개 생성 완료 (RSS %d건) -> %s"
          % (len(urls), min(len(feed_items), 100), DIST))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="운영 dist를 보존하고 .preview에 생성")
    if parser.parse_args().preview:
        DIST = os.path.join(ROOT, ".preview")
        LASTMOD_PATH = os.path.join(DIST, "lastmod.json")
        ADSENSE_CLIENT = ""
    main()

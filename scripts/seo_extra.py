# -*- coding: utf-8 -*-
"""지역 페이지를 서로 다른 내용으로 만드는 재료 (2026-11-11).

지역 페이지 247개가 지역 이름과 숫자만 다르고 문구가 같았고, 주차장 목록은 지도 스크립트로만 보여
검색 로봇이 받는 HTML 에는 없었다(구글 색인 0쪽). 여기서 자료로부터
  - 주차장 표(이름·주소·구분·30분 요금·운영시간·주차면) — HTML 그대로
  - 지역별 수치 문장(공영/민영, 노상/노외/부설, 30분 요금 중간값, 가장 큰 곳)
  - 지역별 질문과 답(FAQPage)
  - 시·도 비교 표와 가이드 글
을 만든다. 숫자는 전부 원자료에서 센 값이고, 매월 빌드 때 다시 계산된다.
"""
import html
import statistics

TABLE_LIMIT = 200  # 표에 싣는 최대 줄 수(제주시 1,444곳처럼 큰 지역은 나머지를 지도·목록으로 안내)


def e(text):
    return html.escape(str(text), quote=True)


def won(n):
    return format(int(n), ",") + "원"


def kind_label(r):
    if r["fr"]:
        return "무료"
    if r["fl"]:
        return "·".join(r["fl"]) + " 무료"
    return "유료"


def split(rows):
    always = [r for r in rows if r["fr"]]
    partly = [r for r in rows if r["fl"]]
    paid = [r for r in rows if not r["fr"] and not r["fl"]]
    priced = [r for r in paid + partly if r["p30"]]
    return always, partly, paid, priced


def region_title(short, sigungu, rows):
    always, partly, _paid, _priced = split(rows)
    if always:
        head = "%s %s 무료주차장 %d곳·공영주차장 요금" % (short, sigungu, len(always))
    elif partly:
        head = "%s %s 공영주차장 요금·주말 무료 주차장 %d곳" % (short, sigungu, len(partly))
    else:
        head = "%s %s 공영주차장 요금·위치" % (short, sigungu)
    return "%s | 주차장 %d곳 지도" % (head, len(rows))


def region_h1(short, sigungu, rows):
    always, _partly, _paid, _priced = split(rows)
    return "%s %s %s" % (short, sigungu, "무료주차장·공영주차장 요금" if always else "공영주차장 요금·무료 주차 정보")


def region_desc(sido, sigungu, rows):
    always, partly, paid, priced = split(rows)
    bits = ["%s %s 주차장 %d곳" % (sido, sigungu, len(rows))]
    bits.append("상시 무료 %d곳" % len(always))
    if partly:
        bits.append("요일별 무료 %d곳" % len(partly))
    if priced:
        lo, hi = min(r["p30"] for r in priced), max(r["p30"] for r in priced)
        bits.append("30분 요금 %s" % (won(lo) if lo == hi else "%s~%s" % (won(lo), won(hi))))
    return ", ".join(bits) + ". 이름·주소·운영시간을 표로 확인하고 지도에서 길찾기까지 하세요."


def region_facts(sido, sigungu, rows):
    """지역마다 다른 수치 문장 (<p> 여러 개)."""
    always, partly, paid, priced = split(rows)
    out = []
    owners = {k: sum(1 for r in rows if r["kd"] == k) for k in ("공영", "민영")}
    places = {k: sum(1 for r in rows if r["se"] == k) for k in ("노상", "노외", "부설")}
    s = "%s %s에는 주차장 %d곳, 주차면 %s면이 등록돼 있습니다." % (sido, sigungu, len(rows), format(sum(r["cp"] for r in rows), ","))
    kinds = [("%s %d곳" % (k, v)) for k, v in list(owners.items()) + list(places.items()) if v]
    if kinds:
        s += " 구분별로는 " + ", ".join(kinds) + "입니다."
    out.append(s)
    if always:
        big = sorted(always, key=lambda r: -r["cp"])[:3]
        out.append("상시 무료는 %d곳(전체의 %d%%)이고, 주차면이 많은 곳은 %s입니다."
                   % (len(always), round(len(always) * 100 / len(rows)),
                      ", ".join("%s(%s면)" % (r["nm"], format(r["cp"], ",")) for r in big)))
    else:
        out.append("상시 무료로 신고된 주차장은 없습니다."
                   + (" 대신 %s 등 특정 요일에 무료로 풀리는 곳이 %d곳 있습니다."
                      % ("·".join(sorted({x for r in partly for x in r["fl"]})), len(partly)) if partly else ""))
    if priced:
        ps = sorted(r["p30"] for r in priced)
        cheap = min(priced, key=lambda r: (r["p30"], -r["cp"]))
        if ps[0] == ps[-1]:
            out.append("요금을 신고한 %d곳의 30분 요금은 모두 %s입니다." % (len(priced), won(ps[0])))
        else:
            out.append("요금을 신고한 %d곳의 30분 요금은 %s~%s이고 중간값은 %s입니다. 가장 싼 곳은 %s(30분 %s)입니다."
                       % (len(priced), won(ps[0]), won(ps[-1]), won(statistics.median(ps)), cheap["nm"], won(cheap["p30"])))
    allday = sum(1 for r in rows if "24시간" in (r["tm"] or ""))
    if allday:
        out.append("24시간 운영으로 신고된 곳은 %d곳입니다." % allday)
    return "".join("<p>%s</p>" % e(x) for x in out)


def region_faq(sido, sigungu, rows):
    always, partly, paid, priced = split(rows)
    faq = []
    if always:
        top = sorted(always, key=lambda r: -r["cp"])[:3]
        faq.append(("%s에 무료주차장이 있나요?" % sigungu,
                    "네. 지자체가 무료로 신고한 주차장이 %d곳 있습니다. 주차면이 많은 곳은 %s입니다. 운영시간과 이용 대상은 현장 안내판을 확인하세요."
                    % (len(always), ", ".join(r["nm"] for r in top))))
    else:
        faq.append(("%s에 무료주차장이 있나요?" % sigungu,
                    "상시 무료로 신고된 주차장은 없습니다."
                    + (" 다만 %d곳은 특정 요일(%s)에 무료입니다." % (len(partly), "·".join(sorted({x for r in partly for x in r["fl"]}))) if partly else "")
                    + " 유료 주차장의 30분 요금은 아래 표에서 비교할 수 있습니다."))
    if priced:
        cheap = sorted(priced, key=lambda r: (r["p30"], -r["cp"]))[:3]
        faq.append(("%s에서 가장 싼 주차장은 어디인가요?" % sigungu,
                    "30분 요금 기준으로 %s 순입니다. 요금은 지자체 신고 자료라 현장과 다를 수 있습니다."
                    % ", ".join("%s(%s)" % (r["nm"], won(r["p30"])) for r in cheap)))
    if partly:
        ex = partly[:3]
        faq.append(("%s에 토요일·공휴일에 무료인 주차장이 있나요?" % sigungu,
                    "요일별 무료로 신고된 곳이 %d곳 있습니다. 예: %s. 평일에는 요금을 받으니 방문 요일을 확인하세요."
                    % (len(partly), ", ".join("%s(%s)" % (r["nm"], "·".join(r["fl"])) for r in ex))))
    big = max(rows, key=lambda r: r["cp"])
    if big["cp"]:
        faq.append(("%s에서 가장 큰 주차장은 어디인가요?" % sigungu,
                    "등록 주차면 기준으로 %s(%s면, %s)입니다." % (big["nm"], format(big["cp"], ","), kind_label(big))))
    return faq


def faq_block(title, faq):
    return ("<h2>%s</h2>" % e(title)
            + "".join('<details class="faq"><summary>%s</summary><p>%s</p></details>' % (e(q), e(a)) for q, a in faq))


def faq_ld(faq):
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}


def region_table(sido, sigungu, rows, updated):
    """주차장 표 — 무료 먼저, 유료는 30분 요금 싼 순(빌드가 이미 그 순서로 정렬해 넘긴다)."""
    shown = rows[:TABLE_LIMIT]
    body = "".join(
        "<tr><th scope=\"row\">%s</th><td class=\"l\">%s</td><td>%s</td><td>%s</td><td class=\"l\">%s</td><td>%s</td></tr>"
        % (e(r["nm"]), e(r["ad"]), e(kind_label(r)),
           "무료" if r["fr"] else (won(r["p30"]) if r["p30"] else "미신고"),
           e(r["tm"] or "-"), (format(r["cp"], ",") + "면") if r["cp"] else "-")
        for r in shown)
    more = ("<p class=\"note\">표에는 %d곳까지 실었습니다. 나머지 %d곳은 위 지도와 목록에서 볼 수 있습니다.</p>"
            % (len(shown), len(rows) - len(shown)) if len(rows) > len(shown) else "")
    return ("<h2>%s 주차장 목록 표</h2>" % e(sigungu)
            + '<div class="table-wrap"><table class="sido-table lot-table">'
            + "<caption>%s %s 주차장 %d곳 · 무료 먼저, 유료는 30분 요금이 싼 순 · 마지막 갱신 %s</caption>"
              % (e(sido), e(sigungu), len(rows), e(updated))
            + '<thead><tr><th scope="col">주차장</th><th scope="col">주소</th><th scope="col">구분</th>'
              '<th scope="col">30분 요금</th><th scope="col">운영시간</th><th scope="col">주차면</th></tr></thead>'
            + "<tbody>%s</tbody></table></div>" % body + more)


def sido_table(sido, items):
    """시·도 페이지 — 시군구별 전체·상시 무료·요일별 무료·30분 요금 중간값. items = [(시군구, rows)]"""
    trs = []
    for name, rows in items:
        always, partly, _paid, priced = split(rows)
        med = won(statistics.median(r["p30"] for r in priced)) if priced else "-"
        trs.append('<tr><th scope="row"><a href="%s/">%s</a></th><td>%d곳</td><td>%d곳</td><td>%d곳</td><td>%s</td></tr>'
                   % (e(name), e(name), len(rows), len(always), len(partly), med))
    return ("<h2>%s 시군구별 무료주차장·요금 비교</h2>" % e(sido)
            + '<div class="table-wrap"><table class="sido-table"><thead><tr><th scope="col">시군구</th>'
              '<th scope="col">전체</th><th scope="col">상시 무료</th><th scope="col">요일별 무료</th>'
              '<th scope="col">30분 요금 중간값</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(trs))


def sido_facts(sido, items):
    allrows = [r for _n, rows in items for r in rows]
    always, partly, _paid, priced = split(allrows)
    best = max(items, key=lambda x: sum(1 for r in x[1] if r["fr"]))
    out = ["%s에는 주차장 %s곳이 등록돼 있고, 이 가운데 상시 무료는 %s곳(%d%%)입니다."
           % (sido, format(len(allrows), ","), format(len(always), ","), round(len(always) * 100 / max(1, len(allrows))))]
    n_best = sum(1 for r in best[1] if r["fr"])
    if n_best:
        out.append("무료주차장이 가장 많은 곳은 %s(%d곳)입니다." % (best[0], n_best))
    if priced:
        out.append("요금을 신고한 %s곳의 30분 요금 중간값은 %s입니다." % (format(len(priced), ","), won(statistics.median(r["p30"] for r in priced))))
    if partly:
        out.append("토요일·공휴일 등 특정 요일에만 무료인 곳은 %d곳입니다." % len(partly))
    return "".join("<p>%s</p>" % e(x) for x in out)


def sido_faq(sido, items):
    allrows = [r for _n, rows in items for r in rows]
    always, _partly, _paid, priced = split(allrows)
    ranked = sorted(items, key=lambda x: -sum(1 for r in x[1] if r["fr"]))[:3]
    faq = [("%s에서 무료주차장이 많은 지역은 어디인가요?" % sido,
            "상시 무료 주차장 수는 %s 순입니다." % ", ".join("%s %d곳" % (n, sum(1 for r in rows if r["fr"])) for n, rows in ranked))]
    if priced:
        cheap = sorted(((n, statistics.median([r["p30"] for r in rows if r["p30"]])) for n, rows in items
                        if sum(1 for r in rows if r["p30"]) >= 5), key=lambda x: x[1])[:3]
        if cheap:
            faq.append(("%s에서 주차요금이 싼 지역은 어디인가요?" % sido,
                        "요금 신고가 5곳 이상인 지역 가운데 30분 요금 중간값이 낮은 곳은 %s입니다."
                        % ", ".join("%s(%s)" % (n, won(m)) for n, m in cheap)))
    return faq


# ── 가이드 글 ────────────────────────────────────────────────────────────
def guides(rows, by_sido, updated):
    """[(slug, title, desc, body_html, faq)] — 본문 숫자는 전부 원자료에서 센 값."""
    always, partly, paid, priced = split(rows)
    total = len(rows)
    med = statistics.median(r["p30"] for r in priced) if priced else 0
    places = {k: sum(1 for r in rows if r["se"] == k) for k in ("노상", "노외", "부설")}
    free_by_place = {k: sum(1 for r in always if r["se"] == k) for k in ("노상", "노외", "부설")}
    owners = {k: sum(1 for r in rows if r["kd"] == k) for k in ("공영", "민영")}
    day_labels = {}
    for r in partly:
        for x in r["fl"]:
            day_labels[x] = day_labels.get(x, 0) + 1
    stat = []
    for sido, items in by_sido:
        rs = [r for _n, b in items for r in b]
        a, p, _pd, pr = split(rs)
        stat.append((sido, len(rs), len(a), len(p), statistics.median(r["p30"] for r in pr) if pr else 0))

    def table(head, trs):
        return ('<div class="table-wrap"><table class="sido-table"><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
                % ("".join('<th scope="col">%s</th>' % e(h) for h in head), "".join(trs)))

    rank_free = table(["시·도", "전체", "상시 무료", "무료 비율"], [
        '<tr><th scope="row"><a href="../../%s/">%s</a></th><td>%s곳</td><td>%s곳</td><td>%d%%</td></tr>'
        % (e(s), e(s), format(t, ","), format(a, ","), round(a * 100 / max(1, t)))
        for s, t, a, _p, _m in sorted(stat, key=lambda x: -x[2])])
    rank_fee = table(["시·도", "30분 요금 중간값", "요일별 무료"], [
        '<tr><th scope="row"><a href="../../%s/">%s</a></th><td>%s</td><td>%d곳</td></tr>' % (e(s), e(s), won(m) if m else "-", p)
        for s, _t, _a, p, m in sorted(stat, key=lambda x: (x[4] == 0, x[4]))])
    note = '<p class="note">숫자는 공공데이터를 %s 에 다시 받아 센 값입니다. 요금과 운영시간은 현장과 다를 수 있습니다.</p>' % e(updated)

    out = []
    out.append(("free-parking-by-region", "시·도별 무료주차장 수 순위 | 무료 비율·지역 비교",
                "전국 주차장 %s곳 가운데 상시 무료 %s곳을 시·도별로 세어 순위와 무료 비율을 표로 정리했습니다." % (format(total, ","), format(len(always), ",")),
                "<h1>시·도별 무료주차장 수 순위</h1>"
                + '<p class="lead">전국 주차장 %s곳 가운데 지자체가 무료로 신고한 곳은 %s곳(%d%%)입니다. 무료주차장이 많은 시·도부터 정리했습니다.</p>'
                  % (format(total, ","), format(len(always), ","), round(len(always) * 100 / max(1, total)))
                + "<h2>무료주차장이 많은 시·도</h2>" + rank_free
                + "<h2>표를 읽을 때 알아 둘 점</h2><p>무료 비율이 높은 지역은 대체로 군 단위와 관광지가 많은 곳입니다. "
                  "대도시는 공영주차장 대부분이 유료라 무료 비율이 낮게 나옵니다. 시·도 이름을 누르면 시군구별 표로 이어집니다.</p>" + note,
                [("무료주차장이 가장 많은 시·도는 어디인가요?",
                  "상시 무료 주차장 수는 %s 순입니다." % ", ".join("%s %s곳" % (s, format(a, ",")) for s, _t, a, _p, _m in sorted(stat, key=lambda x: -x[2])[:3]))]))
    out.append(("parking-fee-30min", "공영주차장 요금 30분 기준 비교 | 시·도별 중간값과 계산법",
                "기본요금 단위가 제각각인 주차요금을 30분 기준으로 환산하는 방법과 시·도별 30분 요금 중간값을 표로 정리했습니다.",
                "<h1>공영주차장 요금, 30분 기준으로 비교하기</h1>"
                + '<p class="lead">요금을 신고한 주차장 %s곳의 30분 요금 중간값은 %s입니다. 주차장마다 “10분 300원”, “30분 600원”처럼 단위가 달라 30분으로 환산해 비교했습니다.</p>'
                  % (format(len(priced), ","), won(med))
                + "<h2>30분 요금 계산법</h2><p>기본요금을 기본시간으로 나눠 30분을 곱합니다. 예를 들어 기본 10분에 300원이면 30분은 900원, "
                  "기본 60분에 1,000원이면 30분은 500원입니다. 추가요금 단위가 다른 주차장은 실제 정산 금액이 달라질 수 있습니다.</p>"
                + "<h2>시·도별 30분 요금 중간값</h2>" + rank_fee + note,
                [("주차요금을 30분 기준으로 어떻게 환산하나요?", "기본요금 ÷ 기본시간(분) × 30 으로 계산합니다. 기본 10분 300원이면 30분 900원입니다.")]))
    out.append(("weekend-holiday-free-parking", "토요일·공휴일 무료 주차장 찾는 법 | 요일별 무료 %d곳" % len(partly),
                "평일에는 유료지만 토요일·공휴일 등 특정 요일에 무료로 풀리는 주차장 %d곳을 찾는 방법과 주의할 점을 정리했습니다." % len(partly),
                "<h1>토요일·공휴일 무료 주차장 찾는 법</h1>"
                + '<p class="lead">자료에 요일별 무료로 신고된 주차장은 %d곳입니다(%s). 평일에는 요금을 받으니 방문 요일을 먼저 확인하세요.</p>'
                  % (len(partly), ", ".join("%s %d곳" % (k, v) for k, v in sorted(day_labels.items(), key=lambda x: -x[1])) or "요일 정보 없음")
                + "<h2>지도에서 찾는 순서</h2><p>지역 페이지를 열면 지도에 무료·요일별 무료·유료가 서로 다른 색 점으로 표시됩니다. "
                  "목록의 카드와 표의 ‘구분’ 칸에 ‘토요일 무료’, ‘공휴일 무료’처럼 무료인 요일이 적혀 있습니다.</p>"
                + "<h2>주의할 점</h2><p>요일별 무료 정보는 현재 서울 열린데이터광장 자료에만 들어 있습니다. 다른 지역은 지자체 조례에 따라 주말·공휴일에 "
                  "무료로 개방하는 곳이 있어도 자료에 표시되지 않을 수 있으니, 현장 안내판을 확인하세요.</p>"
                + "<h2>요일별 무료가 있는 시·도</h2>" + table(["시·도", "요일별 무료"], [
                    '<tr><th scope="row"><a href="../../%s/">%s</a></th><td>%d곳</td></tr>' % (e(s), e(s), p)
                    for s, _t, _a, p, _m in sorted(stat, key=lambda x: -x[3]) if p]) + note,
                [("토요일에 무료인 공영주차장은 어떻게 찾나요?", "지역 페이지의 표에서 ‘구분’ 칸에 ‘토요일 무료’라고 적힌 곳을 찾으면 됩니다. 평일에는 요금을 받습니다.")]))
    out.append(("street-offstreet-attached-parking", "노상·노외·부설 주차장 차이 | 종류별 개수와 무료 비율",
                "노상·노외·부설 주차장의 뜻과 차이를 설명하고, 전국 자료에서 종류별 개수와 무료 비율을 정리했습니다.",
                "<h1>노상·노외·부설 주차장, 무엇이 다른가요</h1>"
                + '<p class="lead">노상주차장은 도로 위나 교통광장에 선을 그어 만든 주차면이고, 노외주차장은 도로 밖 별도 부지에 만든 주차장, '
                  "부설주차장은 건물이나 시설에 딸린 주차장입니다.</p>"
                + "<h2>종류별 개수와 무료 비율</h2>" + table(["종류", "전체", "상시 무료", "무료 비율"], [
                    '<tr><th scope="row">%s</th><td>%s곳</td><td>%s곳</td><td>%d%%</td></tr>'
                    % (k, format(places[k], ","), format(free_by_place[k], ","), round(free_by_place[k] * 100 / max(1, places[k])))
                    for k in ("노상", "노외", "부설")])
                + "<h2>공영과 민영</h2><p>자료에는 공영 %s곳, 민영 %s곳이 들어 있습니다. 공영은 지자체나 공공기관이 운영하고, 민영은 개인이나 회사가 운영합니다.</p>"
                  % (format(owners["공영"], ","), format(owners["민영"], ","))
                + "<h2>이용할 때 차이</h2><p>노상주차장은 길가라 찾기 쉽지만 운영시간 밖에는 주차 단속 대상이 될 수 있습니다. "
                  "부설주차장은 그 시설 이용자만 쓸 수 있는 경우가 있으니 안내판을 확인하세요.</p>" + note,
                [("노상주차장과 노외주차장의 차이는 무엇인가요?", "노상주차장은 도로 위나 교통광장에 설치한 주차장이고, 노외주차장은 도로 밖 별도 부지에 설치한 주차장입니다.")]))
    return out

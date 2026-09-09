/* 공짜맵 - 전국 무료주차장 지도
   데이터는 /data/{시도}/{시군구}.json 을 필요할 때만 내려받는다. */
(function () {
  "use strict";

  var CFG = window.FREEMAP || {};
  var state = { all: [], rows: [], map: null, layer: null,
              origin: null, adPlaced: false, onlyFree: false,
              // 홈 첫 화면 둘러보기 모드
              browse: false, clusters: null, clustersWide: null, clusterLayer: null,
              browseCache: {}, browseLoading: false, popupOpen: false,
              escapeShown: false };

  /* ---------- 유틸 ---------- */

  function el(sel) { return document.querySelector(sel); }

  function expand(block) {
    if (!block || !block.d) return [];
    var f = block.f;
    return block.d.map(function (row) {
      var o = {};
      for (var i = 0; i < f.length; i++) o[f[i]] = row[i];
      return o;
    });
  }

  function distanceKm(a, b, c, d) {
    var R = 6371, toRad = Math.PI / 180;
    var dLat = (c - a) * toRad, dLon = (d - b) * toRad;
    var s = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(a * toRad) * Math.cos(c * toRad) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1 - s));
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function getJSON(url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(url + " " + r.status);
      return r.json();
    });
  }

  /* ---------- 렌더 ---------- */

  /* 길찾기·전화 링크. 카드와 지도 팝업이 같은 걸 쓴다.
     현재 창에서 연다. 전면광고(Vignette)가 클릭을 가로채도, 같은 탭 이동이면
     광고를 닫는 순간 브라우저가 원래 이동을 이어서 수행하기 때문이다.
     새 탭으로 열면 광고에 가로채인 탭이 사라져 목적지로 가지 못한다. */
  function actionsHTML(row, index) {
    // 네이버는 좌표 링크 규격이 자주 바뀌어 주소 검색으로 보낸다.
    // 이름으로 보내면 '한류월드 제4' 처럼 지자체가 줄여 신고한 이름이
    // 검색에 안 걸려 빈 화면이 뜬다. 주소는 지번·도로명 모두 정확히 잡힌다.
    var naver = "https://map.naver.com/p/search/" +
      encodeURIComponent(row.ad || row.nm);
    var google = "https://www.google.com/maps/dir/?api=1&destination=" + row.la + "," + row.lo;
    // 카카오맵은 앱 스킴으로 보내면 경로 안내가 바로 뜬다. 앱이 없으면
    // 아무 일도 안 일어나므로 href 에는 웹 링크를 남겨두고(bindKakaoApp)
    // 일정 시간 안에 앱이 안 열리면 웹으로 되돌린다.
    // link/to 는 카카오에 등록된 장소가 아니면 도착지가 비므로 link/map 을 쓴다.
    var kakaoWeb = "https://map.kakao.com/link/map/" +
      encodeURIComponent(row.nm) + "," + row.la + "," + row.lo;
    var kakaoApp = "kakaomap://route?ep=" + row.la + "," + row.lo + "&by=CAR";
    // 카카오 계열은 브랜드 노란색(.kakao)으로 구분한다.
    return '<a class="act" href="' + naver + '">네이버지도 길찾기</a>' +
      '<a class="act" href="' + google + '">구글맵 길찾기</a>' +
      '<a class="act kakao" href="' + kakaoWeb + '" data-app="' + esc(kakaoApp) +
      '">카카오맵 길찾기</a>' +
      (row.tel ? '<a class="act" href="tel:' + esc(row.tel) + '">전화 ' + esc(row.tel) + "</a>" : "") +
      (index != null ? '<button type="button" class="act" data-goto="' + index + '">목록에서 보기</button>' : "");
  }

  function won(n) { return Number(n).toLocaleString() + "원"; }

  /* fr=1 상시무료 / fl 있으면 그 요일만 무료 / p30 있으면 유료 / 셋 다 없으면 요금 미상 */
  function kindOf(row) {
    if (row.fr) return "free";
    if (row.fl && row.fl.length) return "partly";
    if (row.p30) return "paid";
    return "unknown";
  }

  /* 요금 상세. 기본 30분 600원 / 추가 10분 300원 / 일 최대 12,000원 */
  function feeChips(row) {
    var out = [];
    if (row.bc && row.bt) out.push(row.bt + "분 " + won(row.bc));
    if (row.ac && row.at) out.push("추가 " + row.at + "분 " + won(row.ac));
    if (row.dm) out.push("일 최대 " + won(row.dm));
    return out;
  }

  function itemHTML(row, index) {
    var kind = kindOf(row);
    var chips = [];

    if (kind === "free") {
      chips.push('<span class="chip">무료</span>');
    } else if (kind === "partly") {
      row.fl.forEach(function (label) {
        chips.push('<span class="chip warn">' + esc(label) + "</span>");
      });
    } else if (kind === "paid") {
      chips.push('<span class="chip pay">30분 ' + esc(won(row.p30)) + "</span>");
    } else {
      chips.push('<span class="chip plain">유료 · 요금 미표기</span>');
    }
    feeChips(row).forEach(function (t) {
      chips.push('<span class="chip plain">' + esc(t) + "</span>");
    });

    if (row.kd) chips.push('<span class="chip plain">' + esc(row.kd) + "</span>");
    if (row.se) chips.push('<span class="chip plain">' + esc(row.se) + "</span>");
    if (row.cp) chips.push('<span class="chip plain">' + esc(row.cp) + "면</span>");
    if (row.tm) chips.push('<span class="chip plain">' + esc(row.tm) + "</span>");
    if (row._km != null) chips.push('<span class="chip plain">' + row._km.toFixed(1) + "km</span>");

    return '<article class="item" id="spot-' + index + '">' +
      '<h3><button class="spot-focus" data-focus="' + index + '" aria-label="' + esc(row.nm) + ' 지도에서 보기">' + esc(row.nm) + '</button></h3>' +
      '<p class="addr">' + esc(row.ad) + "</p>" +
      '<div class="meta">' + chips.join("") + "</div>" +
      (kind === "partly" ? '<p class="warn-note">평일에는 요금을 받습니다</p>' : "") +
      '<div class="links">' + actionsHTML(row, null) + "</div>" +
      "</article>";
  }

  /* '무료만' 필터. 유료와 요일별(평일 유료)을 모두 걸러 상시 무료만 남긴다. */
  function applyFilter(keepView) {
    state.rows = state.onlyFree
      ? state.all.filter(function (r) { return r.fr; })
      : state.all;

    var label = el("#list-count");
    if (label) {
      label.textContent = state.onlyFree
        ? "무료 " + state.rows.length.toLocaleString() + "곳만 보는 중"
        : "전체 " + state.all.length.toLocaleString() + "곳";
    }
    renderList(keepView);
  }

  function bindFilter() {
    var btn = el("#only-free");
    if (!btn) return;
    btn.addEventListener("click", function () {
      state.onlyFree = !state.onlyFree;
      track("filter_free", { on: state.onlyFree ? 1 : 0 });
      btn.setAttribute("aria-pressed", String(state.onlyFree));
      btn.textContent = "상시 무료만";
      applyFilter(true);
    });
  }

  function renderList(keepView) {
    var rows = state.rows;
    var box = el("#list");
    if (!box) return;

    if (!rows.length) {
      box.innerHTML = '<p class="empty">' + (state.onlyFree ? '조건에 맞는 상시 무료 주차장이 없습니다. 전체 주차장도 확인해보세요.' : '이 주변에서 등록된 주차장을 찾지 못했습니다.') + '</p>';
    } else {
      box.innerHTML = rows.slice(0, 300).map(function (r, i) {
        return itemHTML(r, i);
      }).join("");
    }

    var more = el("#more");
    if (more) {
      more.textContent = rows.length > 300
        ? "총 " + rows.length.toLocaleString() + "곳 중 300곳까지 표시했습니다."
        : "";
    }
    placeFeedAd(rows.length);
    if (!keepView) fitAll();
    renderMarkers();
  }

  /* 목록 중간 광고. 페이지당 한 번만 넣는다. */
  function placeFeedAd(count) {
    if (state.adPlaced || !CFG.ad || count < 6) return;
    var anchor = document.querySelectorAll("#list .item")[4];
    if (!anchor) return;

    var box = document.createElement("aside");
    box.className = "ad-slot ad-feed";
    box.innerHTML = '<span class="ad-label">광고</span>' +
      '<ins class="adsbygoogle" style="display:block"' +
      ' data-ad-client="' + CFG.ad.client + '"' +
      ' data-ad-slot="' + CFG.ad.slot + '"' +
      ' data-ad-format="auto" data-full-width-responsive="true"></ins>';
    anchor.insertAdjacentElement("afterend", box);
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
      state.adPlaced = true;
    } catch (err) {
      box.remove();
    }
  }

  /* 도심은 한 화면에 수백 곳이 몰려 라벨이 서로 덮어버린다.
     화면 안에 있는 것만, 이미 놓인 라벨과 겹치지 않는 것만 골라 그린다.
     state.rows 가 이미 무료 → 요일별 → 싼 유료 순으로 정렬돼 있어서
     자리를 먼저 차지하는 쪽이 자연스럽게 무료와 저렴한 곳이 된다. */
  var LABEL_MAX = 260;   // 한 화면에 그릴 글자 라벨 상한

  function declutter() {
    var bounds = state.map.getBounds();
    var placed = [], labeled = [], dots = [];

    for (var i = 0; i < state.rows.length; i++) {
      var r = state.rows[i];
      if (!bounds.hasLatLng(new naver.maps.LatLng(r.la, r.lo))) continue;
      // 화면 안에 있으면 하나도 빼지 않는다. 라벨 자리가 없으면 점으로 남긴다.
      if (labeled.length + dots.length >= 3000) break;

      var pt = state.map.getProjection().fromCoordToOffset(new naver.maps.LatLng(r.la, r.lo));

      // state.rows 가 무료 → 요일별 → 싼 유료 순이라, 앞에서부터 자리를
      // 채우면 무료가 언제나 먼저 라벨을 가져간다. 유료에 밀리는 일은 없다.
      // 겹치는 것까지 전부 글자로 그리면 제주처럼 무료가 1,300곳인 곳에서
      // 글자가 뭉쳐 읽히지도 않고 지도가 버벅인다. 겹치면 점으로 남기고,
      // 확대해서 자리가 생기면 그때 글자로 바뀐다.
      var clear = labeled.length < LABEL_MAX;
      for (var j = 0; clear && j < placed.length; j++) {
        if (Math.abs(placed[j].x - pt.x) < 56 && Math.abs(placed[j].y - pt.y) < 22) {
          clear = false;
        }
      }
      if (clear) {
        placed.push(pt);
        labeled.push({ row: r, idx: i });
      } else {
        // 자리가 없다고 지워버리면 "여기 주차장이 몰려 있다"는 정보가 사라진다.
        // 라벨 대신 점으로 남겨두고, 확대하면 라벨로 바뀐다.
        dots.push({ row: r, idx: i });
      }
    }
    return { labeled: labeled, dots: dots };
  }

  // 점 수백 개를 DOM 으로 그리면 느리다. 캔버스 한 장에 그린다.


  var DOT_COLOR = {
    free: "#1a7a5c", partly: "#c2820a", paid: "#2f5fb8", unknown: "#6b7280"
  };

  /* 마커를 누르면 길찾기·전화까지 여기서 바로 되게 한다. 점과 라벨이 같이 쓴다. */
  function popupHTML(r, i) {
    var kind = kindOf(r);
    var when =
      kind === "free" ? '<span class="pop-free">상시 무료</span>' :
      kind === "partly" ? '<span class="pop-warn">' + esc(r.fl.join(", ")) + " · 평일 유료</span>" :
      kind === "paid" ? '<span class="pop-pay">30분 ' + esc(won(r.p30)) + "</span>" :
      '<span class="pop-ad">유료 · 요금 미표기</span>';
    var extra = feeChips(r);
    if (r.cp) extra.push(esc(r.cp) + "면");
    if (r.tm) extra.push(esc(r.tm));

    return '<div class="pop">' +
      '<b class="pop-nm">' + esc(r.nm) + "</b>" +
      '<span class="pop-ad">' + esc(r.ad) + "</span>" +
      when +
      (extra.length ? '<span class="pop-ad">' + extra.join(" · ") + "</span>" : "") +
      '<span class="pop-acts">' + actionsHTML(r, i < 300 ? i : null) + "</span>" +
      "</div>";
  }

  function clearMarkers(markers) {
    (markers || []).forEach(function (marker) {
      naver.maps.Event.clearInstanceListeners(marker);
      marker.setMap(null);
    });
  }

  function closePopup() {
    if (state.infoWindow) state.infoWindow.close();
    state.popupOpen = false;
  }

  function renderMarkers() {
    if (!state.map) return;
    clearMarkers(state.layer);
    state.layer = [];
    if (!state.rows.length) return;
    var picked = declutter();
    picked.labeled.concat(picked.dots).forEach(function (item, idx) {
      var r = item.row, kind = kindOf(r);
      var label = kind === "free" ? "무료" : kind === "partly"
        ? r.fl[0].replace(" 무료개방", "").replace(" 무료", "")
        : kind === "paid" ? won(r.p30) : "유료";
      var isDot = idx >= picked.labeled.length;
      var marker = new naver.maps.Marker({
        position: new naver.maps.LatLng(r.la, r.lo), map: state.map,
        title: r.nm + " · " + label,
        icon: { content: isDot
          ? '<button class="map-dot" aria-label="' + esc(r.nm + " " + label) + '" style="background:' + DOT_COLOR[kind] + '"></button>'
          : '<button class="pin pin-' + kind + '"><span>' + esc(label) + '</span></button>',
          anchor: new naver.maps.Point(isDot ? 5 : 24, isDot ? 5 : 12) }
      });
      naver.maps.Event.addListener(marker, "click", function () {
        closePopup();
        state.infoWindow = new naver.maps.InfoWindow({
          content: '<div class="naver-popup"><button class="popup-close" aria-label="상세 닫기" type="button">×</button>' + popupHTML(r, item.idx) + '</div>',
          // 화면 가장자리에서 열리면 지도를 밀어 상세 내용이 다 보이게 한다.
          // idle 은 state.popupOpen 으로 막혀 있어 마커가 다시 그려지지 않는다.
          borderWidth: 0, backgroundColor: "transparent", disableAutoPan: false
        });
        state.popupOpen = true;
        state.infoWindow.open(state.map, marker);
        // 네이버 InfoWindow 안의 클릭은 document 까지 올라오지 않을 때가 있다.
        // 위임에 기대지 말고 닫기 버튼에 직접 건다.
        var content = state.infoWindow.getContentElement &&
          state.infoWindow.getContentElement();
        var closeBtn = content && content.querySelector(".popup-close");
        if (closeBtn) {
          closeBtn.addEventListener("click", function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            closePopup();
          });
        }
      });
      state.layer.push(marker);
    });
  }

  function fitAll() {
    if (!state.map || !state.rows.length) return;
    if (state.origin) {
      state.map.setCenter(new naver.maps.LatLng(state.origin[0], state.origin[1]));
      state.map.setZoom(15, false);
      return;
    }
    var first = new naver.maps.LatLng(state.rows[0].la, state.rows[0].lo);
    var bounds = new naver.maps.LatLngBounds(first, first);
    state.rows.forEach(function (r) { bounds.extend(new naver.maps.LatLng(r.la, r.lo)); });
    state.map.fitBounds(bounds, { top: 35, right: 35, bottom: 35, left: 35 });
    if (state.map.getZoom() > 16) state.map.setZoom(16, false);
  }

  function initMap() {
    var node = el("#map");
    if (!node) return;
    if (!window.naver || !naver.maps || !naver.maps.Map) {
      node.innerHTML = '<p class="map-unavailable" role="status">지도를 불러오지 못했습니다. 잠시 후 다시 시도해주세요. 지역별 주차장 목록은 계속 확인할 수 있습니다.</p>';
      return;
    }
    state.map = new naver.maps.Map(node, {
      center: new naver.maps.LatLng(36.5, 127.8), zoom: 7,
      minZoom: 6, maxZoom: 19, zoomControl: true,
      zoomControlOptions: { position: naver.maps.Position.BOTTOM_RIGHT }
    });
    naver.maps.Event.addListener(state.map, "idle", function () {
      if (state.popupOpen) return;
      if (state.browse) refreshBrowse(); else renderMarkers();
    });
    naver.maps.Event.addListener(state.map, "click", closePopup);
    document.addEventListener("click", function (event) {
      if (event.target.closest(".popup-close")) closePopup();
    });
  }

  /* ---------- 페이지별 진입 ---------- */

  function startRegionPage() {
    initMap();
    bindNearby();
    getJSON(CFG.dataUrl).then(function (data) {
      state.all = expand(data.p);
      applyFilter();
      setResultsContext("선택한 지역의 주차장입니다. 지도 중심으로 다시 찾을 수도 있어요.");
    }).catch(function (err) {
      el("#list").innerHTML = '<p class="empty">데이터를 불러오지 못했습니다. (' + esc(err.message) + ")</p>";
    });
  }

  /* ---------- 홈 첫 화면: 전국 둘러보기 ----------
     '내 주변 찾기'를 누르기 전에도 지도가 비어 있지 않게 한다.
     넓게 보면 시군구별 개수 풍선, 확대하면 그 지역 파일만 받아 낱개로 보여준다.
     18,843곳을 한 번에 받으면 몇 MB라 처음부터 다 내려받지는 않는다. */

  var WIDE_ZOOM = 9;         // 이 미만에서는 시도 단위로 묶는다
  var DETAIL_ZOOM = 11;      // 이 이상 확대하면 낱개 마커로 바꾼다
  var BROWSE_MAX_FILES = 8;  // 한 화면에서 받아올 지역 파일 수 상한

  function startBrowse() {
    state.browse = true;
    getJSON(CFG.indexUrl).then(function (index) {
      var cells = [], wide = [];
      index.sido.forEach(function (sido) {
        var sum = 0, free = 0, la = 0, lo = 0, w = 0;
        sido.sgg.forEach(function (sgg) {
          if (!sgg.c) return;
          cells.push({ sido: sido.nm, nm: sgg.nm, c: sgg.c, p: sgg.p, f: sgg.f || 0 });
          sum += sgg.p; free += sgg.f || 0;
          la += sgg.c[0] * sgg.p; lo += sgg.c[1] * sgg.p; w += sgg.p;
        });
        // 시도 풍선 자리는 주차장 수로 가중평균한 중심. 시청 위치보다
        // 실제로 주차장이 몰린 쪽에 붙는다.
        if (w) wide.push({ sido: sido.nm, nm: sido.nm, p: sum, f: free, c: [la / w, lo / w] });
      });
      state.clusters = cells;
      state.clustersWide = wide;
      refreshBrowse();
    }).catch(function () { /* 지도는 비어도 나머지 기능은 살아 있다 */ });
  }

  function clearClusters() {
    if (state.clusterLayer) {
      clearMarkers(state.clusterLayer);
      state.clusterLayer = null;
    }
  }

  function stopBrowse() {
    state.browse = false;
    clearClusters();
    // browseCache 는 비우지 않는다. 이미 받아둔 지역 파일을 '내 주변 찾기'가 재사용한다.
  }

  function drawClusters() {
    if (!state.clusters || !state.map) return;
    clearClusters();
    var zoom = state.map.getZoom();
    var cells = zoom < WIDE_ZOOM ? (state.clustersWide || []) : state.clusters;
    var bounds = state.map.getBounds();
    state.clusterLayer = [];
    cells.forEach(function (c) {
      var pos = new naver.maps.LatLng(c.c[0], c.c[1]);
      if (!bounds.hasLatLng(pos)) return;
      var count = c.f || c.p;
      var marker = new naver.maps.Marker({ position: pos, map: state.map,
        title: c.nm + " · 무료 " + c.f + "곳 / 전체 " + c.p + "곳",
        icon: { content: '<button class="cluster' + (c.f ? '' : ' cluster-pay') + '"><span>' + count.toLocaleString() + '</span></button>',
          anchor: new naver.maps.Point(24, 20) }
      });
      naver.maps.Event.addListener(marker, "click", function () {
        state.map.setCenter(pos);
        state.map.setZoom(zoom < WIDE_ZOOM ? WIDE_ZOOM + 1 : DETAIL_ZOOM + 1, false);
      });
      state.clusterLayer.push(marker);
    });
  }

  /* 화면 안 시군구 파일만 받아 낱개 마커로 보여준다. */
  function loadDetail() {
    if (!state.clusters || state.browseLoading) return;
    // 화면 안에 '중심점'이 든 시군구만 고르면, 많이 확대했을 때 화면이
    // 시군구 하나보다 작아져 아무것도 안 잡힌다. 화면 중심에서 가까운 순으로 고른다.
    var centre = state.map.getCenter();
    var near = state.clusters.map(function (c) {
      return { c: c, km: distanceKm(centre.lat(), centre.lng(), c.c[0], c.c[1]) };
    }).filter(function (x) { return x.km < 80; });
    near.sort(function (a, b) { return a.km - b.km; });
    near = near.slice(0, BROWSE_MAX_FILES).map(function (x) { return x.c; });

    var missing = near.filter(function (c) {
      return !state.browseCache[c.sido + "/" + c.nm];
    });

    function paint() {
      var rows = [];
      near.forEach(function (c) {
        var got = state.browseCache[c.sido + "/" + c.nm];
        if (got) rows = rows.concat(got);
      });
      if (!state.browse || state.map.getZoom() < DETAIL_ZOOM) return;
      var bounds = state.map.getBounds();
      var center = state.map.getCenter();
      state.all = rows.filter(function (r) {
        return bounds.hasLatLng(new naver.maps.LatLng(r.la, r.lo));
      }).map(function (r) {
        return Object.assign({}, r, { _km: distanceKm(center.lat(), center.lng(), r.la, r.lo) });
      }).sort(function (a, b) { return a._km - b._km; });
      applyFilter(true);
      setResultsContext("현재 지도 안의 주차장 · 지도 중심에서 가까운 순 (인근 지역 데이터 기준)");
    }

    if (!missing.length) { paint(); return; }

    state.browseLoading = true;
    Promise.all(missing.map(function (c) {
      return getJSON(CFG.dataBase + encodeURIComponent(c.sido) + "/" + encodeURIComponent(c.nm) + ".json")
        .then(function (file) { state.browseCache[c.sido + "/" + c.nm] = expand(file.p); })
        .catch(function () { state.browseCache[c.sido + "/" + c.nm] = []; });
    })).then(function () {
      state.browseLoading = false;
      if (state.browse && state.map.getCenter().toString() !== centre.toString()) refreshBrowse();
      else paint();
    });
  }

  function refreshBrowse() {
    if (!state.browse || !state.map || !state.clusters) return;
    if (state.map.getZoom() >= DETAIL_ZOOM) {
      clearClusters();
      loadDetail();
    } else {
      state.all = [];
      applyFilter(true);
      if (el("#list")) el("#list").innerHTML = '<p class="empty">지역의 숫자를 누르면<br>주차장 위치와 요금이 나타납니다.</p>';
      setResultsContext("목적지를 검색하거나 지도를 확대해 보세요.");
      drawClusters();
    }
  }

  /* ---------- 인앱 브라우저 ----------
     스레드·인스타·페북·카톡 안에서 링크를 열면 웹뷰가 뜨는데, 여기서는
     위치 권한 자체를 앱이 막아버려 사이트가 아무리 요청해도 실패한다.
     페이지에서 권한을 살릴 방법은 없다. 밖의 브라우저로 나가는 길만 안내한다. */

  function inAppBrowser() {
    var ua = navigator.userAgent || "";
    // Barcelona = 스레드 앱의 내부 이름
    return /Barcelona|Instagram|FBAN|FBAV|KAKAOTALK|NAVER\(inapp|Line\/|DaumApps|everytimeApp/i.test(ua);
  }

  function isIOSDevice() {
    return /iphone|ipad|ipod/i.test(navigator.userAgent);
  }

  /* 안드로이드는 intent 로 크롬을 직접 띄울 수 있으니 버튼 하나로 끝낸다.
     iOS 에는 그런 통로가 없어 사파리로 나가는 메뉴 위치를 글로 알려주고
     주소 복사를 남겨둔다. */
  /* 인앱 브라우저에서 밖의 브라우저로 내보낸다.
     안드로이드는 intent 로 크롬이 바로 뜬다.
     iOS 에는 공식 통로가 없어 x-safari-https 를 시도해보고, 아무 일도
     일어나지 않으면(메타 계열 앱은 대부분 막아둔다) 안내로 떨어진다. */
  function openInBrowser(reason, detail) {
    var target = location.host + location.pathname + location.search;
    track("inapp_escape", { os: isIOSDevice() ? "ios" : "android" });

    // 안내 예약을 먼저 건다. 스킴 이동이 예외를 던지는 브라우저가 있는데,
    // 나중에 걸면 그 자리에서 멈춰 아무 안내도 못 띄운다.
    var wait = isIOSDevice() ? 800 : 1500;
    setTimeout(function () {
      if (!document.hidden) showEscapeGuide(reason, detail);
    }, wait);

    var url = isIOSDevice()
      ? "x-safari-https://" + target
      : "intent://" + target + "#Intent;scheme=https;package=com.android.chrome;end";
    try {
      window.location.href = url;
    } catch (err) { /* 막힌 웹뷰. 위 안내로 떨어진다 */ }
  }

  function showEscapeGuide(reason, detail) {
    var box = el("#nearby-msg");
    if (!box) return;
    var ios = isIOSDevice();
    // 눌러야 할 대상은 크게 강조한다(.hl). 나머지는 escape 처리한 평문이다.
    var hl = function (text) { return '<b class="hl">' + esc(text) + "</b>"; };

    var hint = ios
      ? "오른쪽 아래 나침반 모양(사파리) 아이콘, 또는 오른쪽 위 ··· 를 눌러 " +
        esc("“") + hl("Safari에서 열기") + esc("”를 선택해주세요.")
      : "아래 " + esc("“") + hl("크롬으로 열기") + esc("”를 누르면 바로 이동합니다.");

    // 안내를 한 줄로 붙이면 길어서 읽히지 않는다. 사정과 해결책을 줄로 나눈다.
    var html = "<b>" + esc(reason) + "</b><br>" +
      esc(detail || "지금은 앱 안에서 열려 있어 위치 권한을 쓸 수 없습니다.") +
      "<br>" + hint;

    if (ios) {
      html += '<br><button type="button" class="btn" style="margin-top:8px" ' +
        'id="escape-copy">주소 복사</button>';
    } else {
      var url = "intent://" + location.host + location.pathname +
        "#Intent;scheme=https;package=com.android.chrome;end";
      html += '<br><a class="btn danger" style="margin-top:8px" href="' + esc(url) +
        '">크롬으로 열기</a>';
    }
    // 한 번 나가면 다시 앱 안에서 열 일이 없도록 설치까지 권한다.
    html += '<br><span class="note" style="display:block;margin-top:8px">' +
      (ios
        ? "사파리에서 연 뒤 " + esc("“") + hl("앱 설치 바로가기") +
          esc("”를 누르면 홈 화면에서 바로 열 수 있습니다.")
        : "크롬에서 " + esc("“") + hl("앱 설치 바로가기") +
          esc("”를 누르면 다음부터는 앱으로 바로 열립니다.")) +
      "</span>";
    box.innerHTML = html;
    state.escapeShown = true;
    // bindShare() 를 다시 부르면 기존 버튼에 리스너가 겹쳐 붙는다. 여기만 직접 건다.
    var copyBtn = el("#escape-copy");
    if (copyBtn) {
      copyBtn.addEventListener("click", function () {
        copyLink(decodeURI(location.href)).then(function () {
          toast("주소를 복사했습니다. 브라우저에 붙여넣어 주세요");
        }).catch(function () {
          toast("복사에 실패했습니다. 주소창을 직접 복사해주세요");
        });
      });
    }
    track("inapp_block", { os: isIOSDevice() ? "ios" : "android" });
  }

  function startHomePage() {
    initMap();
    startBrowse();
    bindNearby();
  }

  function bindNearby() {
    var btn = el("#nearby");
    if (!btn) return;

    btn.addEventListener("click", function () {
      track("nearby_search");
      // 인앱 브라우저는 위치 권한이 막혀 있다. 기다렸다 실패시키지 말고
      // 곧바로 밖의 브라우저로 내보낸다.
      if (inAppBrowser()) {
        state.escapeShown = false;
        openInBrowser("앱 안에서는 위치를 쓸 수 없습니다.",
          "스레드·인스타그램 같은 앱 안에서는 위치 권한이 막혀 있습니다.");
        return;
      }
      if (!navigator.geolocation) {
        el("#nearby-msg").textContent = "이 브라우저는 위치 확인을 지원하지 않습니다.";
        return;
      }
      btn.disabled = true;
      btn.textContent = "위치 확인 중…";

      // 여기까지 왔으면 인앱이 아니다. 일반 브라우저는 응답이 빠르다.
      navigator.geolocation.getCurrentPosition(function (pos) {
        state.origin = [pos.coords.latitude, pos.coords.longitude];
        loadNearby();
      }, function () {
        btn.disabled = false;
        btn.textContent = "내 주변 찾기";
        el("#nearby-msg").textContent =
          "위치 권한이 거부되었습니다. 아래에서 지역을 직접 골라주세요.";
      }, {
        // GPS 고정밀(enableHighAccuracy)은 위성을 잡느라 7~8초씩 걸린다.
        // 가까운 주차장을 고르는 데는 와이파이·기지국 기반 수백 m 정확도면 충분하다.
        // maximumAge 로 최근에 잡아둔 위치가 있으면 즉시 재사용한다.
        enableHighAccuracy: false,
        timeout: 6000,
        maximumAge: 300000
      });
    });
  }

  var nearbyRequest = 0;
  function loadNearby(destinationName) {
    var requestId = ++nearbyRequest;
    var origin = state.origin.slice();
    closePopup();
    stopBrowse();
    var btn = el("#nearby");
    var msg = destinationName ? el("#destination-status") : el("#nearby-msg");

    // 둘러보기 지도가 이미 받아둔 지역 목록을 그대로 쓴다. 같은 파일을
    // 다시 받으면 왕복 한 번이 통째로 더 붙는다.
    var ready = state.clusters
      ? Promise.resolve(state.clusters)
      : getJSON(CFG.indexUrl).then(function (index) {
        var out = [];
        index.sido.forEach(function (sido) {
          sido.sgg.forEach(function (sgg) {
            if (sgg.c) out.push({ sido: sido.nm, nm: sgg.nm, c: sgg.c });
          });
        });
        return out;
      });

    return ready.then(function (list) {
      if (requestId !== nearbyRequest) return;
      var cells = list.map(function (c) {
        return {
          sido: c.sido, sigungu: c.nm,
          km: distanceKm(origin[0], origin[1], c.c[0], c.c[1])
        };
      });
      cells.sort(function (a, b) { return a.km - b.km; });
      var picks = cells.slice(0, 8);
      if (!picks.length) throw new Error("지역 데이터가 없습니다.");
      msg.textContent = picks.map(function (c) { return c.sigungu; }).join(", ") + " 데이터를 불러오는 중…";

      return Promise.all(picks.map(function (c) {
        var key = c.sido + "/" + c.sigungu;
        if (state.browseCache[key]) return Promise.resolve(state.browseCache[key]);
        return getJSON(CFG.dataBase + encodeURIComponent(c.sido) + "/" +
          encodeURIComponent(c.sigungu) + ".json").then(function (file) {
          var rows = expand(file.p);
          state.browseCache[key] = rows;
          return rows;
        });
      })).then(function (files) {
        if (requestId !== nearbyRequest) return;
        var merged = [];
        files.forEach(function (rows) { merged = merged.concat(rows); });
        merged.forEach(function (r) {
          r._km = distanceKm(origin[0], origin[1], r.la, r.lo);
        });
        merged.sort(function (a, b) { return a._km - b._km; });
        state.all = merged.slice(0, 300);

        stopBrowse();   // 내 주변 결과로 전환한다
        if (el("#nearby-result")) el("#nearby-result").hidden = false;
        var bar = el("#listbar");
        if (bar) bar.hidden = false;   // 홈에서는 찾기 전까지 감춰둔다
        applyFilter();
        setResultsContext((destinationName || "현재 위치") + " 주변 · 직선거리 순 (인근 지역 데이터 기준)");
        var freeCount = state.all.filter(function (r) { return r.fr; }).length;
        msg.textContent = (destinationName || "현재 위치") + " 주변 " +
          state.rows.length.toLocaleString() + "곳을 직선거리 순으로 보여줍니다 (인근 지역 데이터 기준)" +
          (freeCount ? " (무료 " + freeCount.toLocaleString() + "곳)" : "") + ".";
        if (btn) { btn.textContent = "다시 찾기"; btn.disabled = false; }
        if (state.map) {
          if (state.originMarker) state.originMarker.setMap(null);
          state.originMarker = new naver.maps.Marker({ map: state.map,
            position: new naver.maps.LatLng(origin[0], origin[1]),
            title: destinationName || "현재 위치",
            icon: { content: '<span class="origin-pin">' + esc(destinationName ? "목적지" : "내 위치") + '</span>', anchor: new naver.maps.Point(25, 30) }
          });
        }
      });
    }).catch(function (err) {
      if (requestId !== nearbyRequest) return;
      if (btn) { btn.disabled = false; btn.textContent = "내 주변 찾기"; }
      msg.textContent = "불러오기 실패: " + err.message;
    });
  }

  /* 장소명은 서버의 지역 검색, 주소는 지도 Geocoder로 조회한다. */
  function geocodeAddress(query) {
    return new Promise(function (resolve) {
      if (!window.naver || !naver.maps || !naver.maps.Service) return resolve([]);
      var timer = setTimeout(function () { resolve([]); }, 6500);
      naver.maps.Service.geocode({ query: query }, function (status, response) {
        clearTimeout(timer);
        if (status !== naver.maps.Service.Status.OK) return resolve([]);
        resolve(((response.v2 || {}).addresses || []).slice(0, 5).map(function (r) {
          return { name: r.roadAddress || r.jibunAddress, address: r.jibunAddress,
            lat: Number(r.y), lng: Number(r.x) };
        }).filter(validDestination));
      });
    });
  }

  function validDestination(item) {
    return item && typeof item.name === "string" && Number.isFinite(item.lat) && Number.isFinite(item.lng) &&
      item.lat >= 33 && item.lat <= 39.5 && item.lng >= 124 && item.lng <= 132;
  }

  function bindDestinationSearch() {
    var form = el("#destination-form");
    if (!form) return;
    var input = el("#destination-query"), results = el("#destination-results"), msg = el("#destination-status");
    var searchId = 0, controller;
    input.addEventListener("input", function () {
      searchId++;
      if (controller) controller.abort();
      results.replaceChildren();
      msg.textContent = "";
      form.removeAttribute("aria-busy");
    });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var query = input.value.trim();
      if (query.length < 2 || query.length > 100) { msg.textContent = "검색어를 2~100자로 입력해주세요."; return; }
      var id = ++searchId;
      if (controller) controller.abort();
      controller = new AbortController();
      var thisController = controller;
      var timer = setTimeout(function () { thisController.abort(); }, 7000);
      results.replaceChildren();
      msg.textContent = "목적지를 찾고 있습니다…";
      form.setAttribute("aria-busy", "true");
      var unavailable = false;
      fetch("/api/places?q=" + encodeURIComponent(query), { signal: controller.signal, cache: "no-store" })
        .then(function (r) { if (!r.ok) throw new Error("unavailable"); return r.json(); })
        .then(function (data) { return (data.items || []).filter(validDestination); })
        .catch(function () { unavailable = true; return []; })
        .then(function (items) { clearTimeout(timer); if (id !== searchId) return []; return items.length ? items : geocodeAddress(query); })
        .then(function (items) {
          if (id !== searchId) return;
          form.removeAttribute("aria-busy");
          msg.textContent = items.length ? "목적지를 선택하면 주변 주차장을 보여드립니다."
            : unavailable ? "장소 검색을 지금 이용할 수 없습니다. 도로명 주소로 다시 검색하거나 지역 목록을 이용해주세요."
            : "검색 결과가 없습니다. 지역명을 함께 입력하거나 도로명 주소로 검색해주세요.";
          items.forEach(function (item) {
            var button = document.createElement("button");
            button.type = "button"; button.className = "destination-option";
            var title = document.createElement("strong"), address = document.createElement("span");
            title.textContent = item.name; address.textContent = item.address || "";
            button.append(title, address);
            button.addEventListener("click", function () {
              searchId++;
              state.origin = [item.lat, item.lng];
              results.replaceChildren();
              msg.textContent = item.name + " 주변 주차장을 불러옵니다…";
              loadNearby(item.name);
            });
            results.appendChild(button);
          });
        }).catch(function () {
          if (id !== searchId) return;
          form.removeAttribute("aria-busy");
          msg.textContent = "검색 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.";
        });
    });
  }

  /* ---------- 공유 ---------- */

  /* 구글 애널리틱스 이벤트. GA 가 없거나 차단돼도 조용히 넘어간다. */
  function track(name, params) {
    if (typeof window.gtag !== "function") return;
    try { window.gtag("event", name, params || {}); } catch (err) { /* 무시 */ }
  }

  function toast(message) {
    var box = el("#toast");
    if (!box) {
      box = document.createElement("div");
      box.id = "toast";
      document.body.appendChild(box);
    }
    box.textContent = message;
    box.classList.add("on");
    clearTimeout(box._timer);
    box._timer = setTimeout(function () { box.classList.remove("on"); }, 2200);
  }

  /* 구형 브라우저 / http 페이지 / 권한 거부 시의 폴백 */
  function legacyCopy(url) {
    return new Promise(function (resolve, reject) {
      var area = document.createElement("textarea");
      area.value = url;
      area.setAttribute("readonly", "");
      area.style.cssText = "position:fixed;top:-1000px;opacity:0";
      document.body.appendChild(area);
      area.select();
      area.setSelectionRange(0, url.length);
      var ok = false;
      try {
        ok = document.execCommand && document.execCommand("copy");
      } catch (err) {
        ok = false;
      }
      document.body.removeChild(area);
      ok ? resolve() : reject(new Error("copy failed"));
    });
  }

  function copyLink(url) {
    if (navigator.clipboard && window.isSecureContext) {
      // 권한이 거부되는 경우가 있어 실패하면 반드시 구형 방식으로 한 번 더 시도한다.
      return navigator.clipboard.writeText(url).catch(function () {
        return legacyCopy(url);
      });
    }
    return legacyCopy(url);
  }

  function openPopup(url) {
    window.open(url, "_blank", "noopener,noreferrer,width=600,height=540");
  }

  function bindShare() {
    var buttons = document.querySelectorAll("[data-share]");
    if (!buttons.length) return;

    // 카카오톡 공유는 SDK 와 앱 키가 둘 다 있어야 동작한다.
    // 준비되지 않으면 버튼을 계속 숨겨 눌러도 아무 일 없는 상황을 막는다.
    if (CFG.kakaoKey && window.Kakao) {
      try {
        if (!Kakao.isInitialized()) Kakao.init(CFG.kakaoKey);
        Array.prototype.forEach.call(
          document.querySelectorAll('[data-share="kakao"]'),
          function (btn) { btn.hidden = false; }
        );
      } catch (err) { /* 키가 잘못됐거나 도메인 미등록 - 버튼은 숨긴 채로 둔다 */ }
    }

    // 네이티브 공유 시트는 지원하는 기기(주로 모바일)에서만 노출한다.
    // 여기서 카카오톡·문자·인스타그램이 모두 잡히므로 별도 SDK가 필요 없다.
    if (navigator.share) {
      Array.prototype.forEach.call(
        document.querySelectorAll('[data-share="native"]'),
        function (btn) { btn.hidden = false; btn.classList.add("primary"); }
      );
    }

    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener("click", function () {
        track("share", { method: btn.getAttribute("data-share") });
        var url = location.href;
        // 주소가 한글이라 location.href 는 %EC%84%9C... 로 인코딩돼 있다.
        // 사람이 보는 곳(복사·공유 시트)에는 디코딩한 주소를 넘겨야 카톡에서도 깔끔하다.
        var prettyUrl = url;
        try { prettyUrl = decodeURI(url); } catch (err) { /* 그대로 둔다 */ }
        var title = document.title;

        switch (btn.dataset.share) {
          case "kakao":
            // 이미지가 없는 사이트라 text 템플릿을 쓴다. feed 는 썸네일이 필수다.
            try {
              Kakao.Share.sendDefault({
                objectType: "text",
                text: title,
                link: { mobileWebUrl: prettyUrl, webUrl: prettyUrl }
              });
            } catch (err) {
              copyLink(prettyUrl).then(function () {
                toast("카카오톡 공유에 실패해 주소를 복사했습니다");
              }).catch(function () { });
            }
            break;
          case "native":
            navigator.share({ title: title, url: prettyUrl }).catch(function () { });
            break;
          // 공유 시트가 되면 시트를, 안 되면 주소 복사로 넘어가는 만능 버튼
          case "quick":
            if (navigator.share) {
              navigator.share({ title: title, url: prettyUrl }).catch(function () { });
            } else {
              copyLink(prettyUrl).then(function () {
                toast("주소를 복사했습니다");
              }).catch(function () {
                toast("복사에 실패했습니다. 주소창을 직접 복사해주세요");
              });
            }
            break;
          case "copy":
            copyLink(prettyUrl).then(function () {
              toast("주소를 복사했습니다");
            }).catch(function () {
              toast("복사에 실패했습니다. 주소창을 직접 복사해주세요");
            });
            break;
          case "naver":
            openPopup("https://blog.naver.com/openapi/share?url=" +
              encodeURIComponent(url) + "&title=" + encodeURIComponent(title));
            break;
          case "x":
            openPopup("https://twitter.com/intent/tweet?url=" +
              encodeURIComponent(url) + "&text=" + encodeURIComponent(title));
            break;
          case "facebook":
            openPopup("https://www.facebook.com/sharer/sharer.php?u=" + encodeURIComponent(url));
            break;
          case "instagram":
            // 인스타그램은 외부 링크를 바로 올리는 공개 주소가 없다.
            // 주소를 복사해두고 앱(없으면 웹)을 열어 붙여넣게 한다.
            copyLink(prettyUrl).then(function () {
              toast("주소를 복사했습니다. 인스타그램에 붙여넣어 주세요");
            }).catch(function () {
              toast("인스타그램을 엽니다. 주소창의 주소를 복사해 붙여넣어 주세요");
            }).then(function () {
              setTimeout(function () {
                window.open("https://www.instagram.com/", "_blank", "noopener");
              }, 900);
            });
            break;
        }
      });
    });
  }

  /* 지도 팝업의 "목록에서 보기" — 해당 카드로 스크롤하고 잠깐 강조한다. */
  /* 어느 지도로 길찾기를 많이 쓰는지 본다. */
  function bindRouteTracking() {
    document.addEventListener("click", function (ev) {
      var a = ev.target.closest && ev.target.closest("a.act");
      if (!a) return;
      var href = a.getAttribute("href") || "";
      var provider = href.indexOf("kakao") > -1 ? "kakao"
        : href.indexOf("naver") > -1 ? "naver"
        : href.indexOf("google") > -1 ? "google"
        : href.indexOf("tel:") === 0 ? "tel" : "other";
      track("route", { provider: provider });
    });
  }

  function setResultsContext(text) {
    var node = el("#results-context");
    if (node) node.textContent = text;
  }

  function setSheet(expanded) {
    var panel = el(".map-results"), button = el("#sheet-toggle");
    if (!panel || !button) return;
    panel.classList.toggle("expanded", expanded);
    button.setAttribute("aria-expanded", String(expanded));
    el("#sheet-action").textContent = expanded ? "접기 ↓" : "펼치기 ↑";
  }

  function bindMapWorkspace() {
    var menu = el("#map-menu");
    if (!menu) return;
    el("[data-menu-open]").addEventListener("click", function () { menu.showModal(); });
    el("#menu-close").addEventListener("click", function () { menu.close(); });
    menu.addEventListener("click", function (event) { if (event.target === menu) {
      var rect = menu.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) menu.close();
    } });
    el("#sheet-toggle").addEventListener("click", function () {
      setSheet(this.getAttribute("aria-expanded") !== "true");
    });
    el("#map-research").addEventListener("click", function () {
      if (!state.map) return;
      var center = state.map.getCenter();
      state.origin = [center.lat(), center.lng()];
      loadNearby("지도 중심");
    });
    document.addEventListener("click", function (event) {
      var button = event.target.closest && event.target.closest("[data-focus]");
      if (!button || !state.map) return;
      var row = state.rows[Number(button.dataset.focus)];
      if (!row) return;
      closePopup();
      stopBrowse();
      state.map.setCenter(new naver.maps.LatLng(row.la, row.lo));
      state.map.setZoom(17, false);
      setSheet(false);
    });
  }

  function bindGoto() {
    document.addEventListener("click", function (ev) {
      var btn = ev.target.closest && ev.target.closest("[data-goto]");
      if (!btn) return;
      var card = document.getElementById("spot-" + btn.dataset.goto);
      if (!card) return;
      closePopup();
      setSheet(true);
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.classList.add("hit");
      setTimeout(function () { card.classList.remove("hit"); }, 2000);
    });
  }

  /* 카카오맵 길찾기 — 휴대폰에서는 앱 스킴으로 먼저 시도한다.
     앱이 열리면 페이지가 백그라운드로 넘어가므로 document.hidden 으로 판별하고,
     안 열렸으면 href 에 적힌 웹 지도로 이어서 이동한다. */
  function bindKakaoApp() {
    if (!/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) return;
    document.addEventListener("click", function (ev) {
      var a = ev.target.closest && ev.target.closest("a[data-app]");
      if (!a) return;
      ev.preventDefault();
      var web = a.getAttribute("href");
      window.location.href = a.getAttribute("data-app");
      setTimeout(function () {
        if (!document.hidden) window.location.href = web;
      }, 1200);
    });
  }

  /* 광고는 레이아웃이 잡힌 뒤에 요청한다. HTML 안에서 바로 push 하면
     폭이 0으로 잡혀 availableWidth=0 오류가 나고 지면이 비어버린다. */
  function pushAds() {
    var units = document.querySelectorAll("ins.adsbygoogle:not([data-adsbygoogle-status])");
    Array.prototype.forEach.call(units, function (ins) {
      if (!ins.getBoundingClientRect().width) return;
      try {
        (window.adsbygoogle = window.adsbygoogle || []).push({});
      } catch (err) { /* 광고 차단 등 - 무시 */ }
    });
  }

  /* ---------- 홈 화면에 추가 ---------- */

  var installPrompt = null;
  var promptDismissed = false;

  /* beforeinstallprompt 는 페이지가 뜨자마자 한 번만 날아온다.
     bindInstall() 은 DOM 이 준비된 뒤에 도는데, 그 사이에 이벤트가 지나가면
     영영 못 받는다. 그래서 구독만 스크립트 최상단에서 미리 해둔다. */
  window.addEventListener("beforeinstallprompt", function (ev) {
    ev.preventDefault();
    installPrompt = ev;
    promptDismissed = false;
  });

  function isStandalone() {
    return window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true;
  }

  /* 설치 여부를 기억해둔다. 브라우저 탭에서는 설치돼 있어도
     standalone 이 아니라서 그것만으로는 알 수 없다. */
  function markInstalled() {
    try { localStorage.setItem("installed", "1"); } catch (err) { /* 무시 */ }
  }

  function wasInstalled() {
    if (isStandalone()) return true;
    try { return localStorage.getItem("installed") === "1"; } catch (err) { return false; }
  }

  function bindInstall() {
    var btn = el("#install-app");
    if (!btn) return;

    var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
    btn.hidden = false;   // 버튼은 항상 살려두고, 상황은 눌렀을 때 알려준다

    btn.addEventListener("click", function () {
      if (installPrompt) {
        var ev = installPrompt;
        // 한 번 쓴 이벤트는 재사용할 수 없다. 먼저 비워야
        // 사용자가 닫았을 때 아래 안내로 정확히 떨어진다.
        installPrompt = null;
        ev.prompt();
        ev.userChoice.then(function (res) {
          if (res && res.outcome === "accepted") {
            markInstalled();
            track("app_install", { source: "prompt" });
          }
          else promptDismissed = true;
        });
        return;
      }
      if (inAppBrowser()) {
        // 웹뷰에는 설치 기능 자체가 없다. 브라우저로 나가야 설치가 뜬다.
        state.escapeShown = false;
        openInBrowser("앱 안에서는 설치할 수 없습니다.",
          "스레드·인스타그램 같은 앱 안에서는 설치 기능이 동작하지 않습니다.");
        return;
      }
      if (wasInstalled()) {
        toast("이미 앱이 설치되어 있습니다");
      } else if (promptDismissed) {
        // 설치 창을 한 번 닫으면 크롬이 같은 페이지에서 다시 주지 않는다.
        toast("설치 창을 닫으셨네요. 새로고침한 뒤 다시 눌러주세요");
      } else if (isIOS) {
        toast("공유 버튼 → '홈 화면에 추가' 를 눌러주세요");
      } else {
        // 설치 이벤트가 없다고 설치됐다고 단정할 수 없다. 조건을 아직 못 채운
        // 브라우저일 수도 있어서, 단정하지 말고 수동 설치 방법을 알려준다.
        toast("브라우저 메뉴에서 '홈 화면에 추가' 를 눌러 설치해주세요");
      }
    });

    window.addEventListener("appinstalled", function () {
      markInstalled();
      track("app_install", { source: "appinstalled" });
      installPrompt = null;
    });
  }

  /* 서비스워커. 내용을 캐시하진 않고, 설치 가능 조건을 채우는 용도다. */
  function registerSW() {
    if (!("serviceWorker" in navigator) || location.protocol !== "https:") return;
    navigator.serviceWorker.register("/sw.js").catch(function () { });
  }

  /* 이 방문이 설치된 앱에서 열린 것인지 기록한다.
     설치 수(app_install)는 한 번뿐이지만, 이 값은 매 방문마다 남아서
     "설치하고 실제로 쓰는지"를 볼 수 있다. */
  function reportDisplayMode() {
    // 값은 보고서에 그대로 찍히므로 한글로 보낸다.
    var mode = isStandalone() ? "앱" : "브라우저";
    if (typeof window.gtag === "function") {
      try {
        window.gtag("set", "user_properties", { display_mode: mode });
      } catch (err) { /* 무시 */ }
    }
    track("app_open", { display_mode: mode });
  }

  document.addEventListener("DOMContentLoaded", function () {
    reportDisplayMode();
    bindShare();
    bindGoto();
    bindKakaoApp();
    bindRouteTracking();
    bindFilter();
    bindDestinationSearch();   // 검색창이 없으면 아무 일도 하지 않는다
    bindMapWorkspace();
    bindInstall();
    registerSW();
    if (CFG.mode === "region") startRegionPage();
    else if (CFG.mode === "home") startHomePage();

    // 레이아웃이 안정된 뒤 광고 요청
    setTimeout(pushAds, 300);
  });
})();

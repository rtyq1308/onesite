/* 공짜맵 - 전국 무료주차장 지도
   데이터는 /data/{시도}/{시군구}.json 을 필요할 때만 내려받는다. */
(function () {
  "use strict";

  var CFG = window.FREEMAP || {};
  var state = { all: [], rows: [], map: null, layer: null,
              origin: null, adPlaced: false, onlyFree: false };

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
      "<h3>" + esc(row.nm) + "</h3>" +
      '<p class="addr">' + esc(row.ad) + "</p>" +
      '<div class="meta">' + chips.join("") + "</div>" +
      (kind === "partly" ? '<p class="warn-note">평일에는 요금을 받습니다</p>' : "") +
      '<div class="links">' + actionsHTML(row, null) + "</div>" +
      "</article>";
  }

  /* '무료만' 필터. 유료와 요일별(평일 유료)을 모두 걸러 상시 무료만 남긴다. */
  function applyFilter() {
    state.rows = state.onlyFree
      ? state.all.filter(function (r) { return r.fr; })
      : state.all;

    var label = el("#list-count");
    if (label) {
      label.textContent = state.onlyFree
        ? "무료 " + state.rows.length.toLocaleString() + "곳만 보는 중"
        : "전체 " + state.all.length.toLocaleString() + "곳";
    }
    renderList();
  }

  function bindFilter() {
    var btn = el("#only-free");
    if (!btn) return;
    btn.addEventListener("click", function () {
      state.onlyFree = !state.onlyFree;
      btn.setAttribute("aria-pressed", String(state.onlyFree));
      btn.textContent = state.onlyFree
        ? "전체 주차장 보기"
        : "가까운 무료 주차장 우선으로 확인하기";
      applyFilter();
    });
  }

  function renderList() {
    var rows = state.rows;
    var box = el("#list");
    if (!box) return;

    if (!rows.length) {
      box.innerHTML = '<p class="empty">이 지역에는 등록된 주차장이 없습니다.</p>';
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
    fitAll();
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
    var bounds = state.map.getBounds().pad(0.2);
    var placed = [], labeled = [], dots = [];

    for (var i = 0; i < state.rows.length; i++) {
      var r = state.rows[i];
      if (!bounds.contains([r.la, r.lo])) continue;
      // 화면 안에 있으면 하나도 빼지 않는다. 라벨 자리가 없으면 점으로 남긴다.
      if (labeled.length + dots.length >= 3000) break;

      var pt = state.map.latLngToLayerPoint([r.la, r.lo]);

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
  var dotRenderer = null;

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

  function renderMarkers() {
    if (!state.map) return;
    if (state.layer) state.map.removeLayer(state.layer);
    if (!state.rows.length) return;

    var picked = declutter();

    // 라벨에 밀린 곳은 점으로. 팝업은 라벨과 똑같이 붙여서 눌러볼 수 있게 한다.
    var markers = picked.dots.map(function (item) {
      var r = item.row, i = item.idx;
      var c = DOT_COLOR[kindOf(r)];
      return L.circleMarker([r.la, r.lo], {
        renderer: dotRenderer,
        radius: 4, weight: 1, color: "#fff", fillColor: c, fillOpacity: 0.95
      }).bindPopup(popupHTML(r, i), { minWidth: 210, maxWidth: 260 });
    });

    markers = markers.concat(picked.labeled.map(function (item) {
      var r = item.row, i = item.idx;
      // 무료는 초록 "무료", 요일별은 주황 요일, 유료는 파랑 30분 요금.
      var kind = kindOf(r);
      // 원 대신 글자 박스. 지도만 봐도 공짜인지 얼마인지 읽히게 한다.
      var label =
        kind === "free" ? "무료" :
        kind === "partly" ? r.fl[0].replace(" 무료개방", "").replace(" 무료", "") :
        kind === "paid" ? won(r.p30) :
        "유료";
      var icon = L.divIcon({
        className: "pin pin-" + kind,
        html: "<span>" + esc(label) + "</span>",
        iconSize: null
      });

      return L.marker([r.la, r.lo], { icon: icon, riseOnHover: true })
        .bindPopup(popupHTML(r, i), { minWidth: 210, maxWidth: 260 });
    }));
    state.layer = L.layerGroup(markers).addTo(state.map);
  }

  /* 전체 데이터가 다 보이도록 한 번만 맞춘다.
     animate:false 인 이유: 애니메이션 줌은 CSS 트랜지션 완료 이벤트에 의존하는데,
     백그라운드 탭처럼 트랜지션이 스로틀링되면 그 이벤트가 오지 않아 지도가 멈춘다.
     maxZoom 은 주차장이 한두 곳뿐인 지역에서 골목까지 확대되는 것을 막는다. */
  function fitAll() {
    if (!state.map || !state.rows.length) return;
    state.map.fitBounds(
      L.latLngBounds(state.rows.map(function (r) { return [r.la, r.lo]; })).pad(0.15),
      { animate: false, maxZoom: 15 }
    );
  }

  function initMap() {
    var node = el("#map");
    if (!node || typeof L === "undefined") return;
    state.map = L.map(node, { scrollWheelZoom: true, preferCanvas: true })
      .setView([36.5, 127.8], 7);
    dotRenderer = L.canvas({ padding: 0.3 });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(state.map);

    // Leaflet 은 만들어질 때의 크기를 기억한다. 휴대폰을 가로로 눕히면 그 값이
    // 어긋나 타일이 엉뚱하게 깔리므로, 크기가 바뀌면 다시 계산하게 한다.
    var resizeTimer;
    function refit() {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        if (!state.map) return;
        state.map.invalidateSize();
        fitAll();
      }, 200);
    }
    window.addEventListener("resize", refit);
    window.addEventListener("orientationchange", refit);

    // 확대하면 가려졌던 곳이 하나씩 드러난다.
    var drawTimer;
    state.map.on("moveend zoomend", function () {
      clearTimeout(drawTimer);
      drawTimer = setTimeout(renderMarkers, 120);
    });
  }

  /* ---------- 페이지별 진입 ---------- */

  function startRegionPage() {
    initMap();
    getJSON(CFG.dataUrl).then(function (data) {
      state.all = expand(data.p);
      applyFilter();
    }).catch(function (err) {
      el("#list").innerHTML = '<p class="empty">데이터를 불러오지 못했습니다. (' + esc(err.message) + ")</p>";
    });
  }

  function startHomePage() {
    var btn = el("#nearby");
    if (!btn) return;
    initMap();

    btn.addEventListener("click", function () {
      if (!navigator.geolocation) {
        el("#nearby-msg").textContent = "이 브라우저는 위치 확인을 지원하지 않습니다.";
        return;
      }
      btn.disabled = true;
      btn.textContent = "위치 확인 중…";
      navigator.geolocation.getCurrentPosition(function (pos) {
        state.origin = [pos.coords.latitude, pos.coords.longitude];
        loadNearby();
      }, function () {
        btn.disabled = false;
        btn.textContent = "내 주변 찾기";
        el("#nearby-msg").textContent = "위치 권한이 거부되었습니다. 아래에서 지역을 직접 골라주세요.";
      }, { enableHighAccuracy: true, timeout: 10000 });
    });
  }

  function loadNearby() {
    var btn = el("#nearby");
    var msg = el("#nearby-msg");
    getJSON(CFG.indexUrl).then(function (index) {
      var cells = [];
      index.sido.forEach(function (sido) {
        sido.sgg.forEach(function (sgg) {
          if (!sgg.c) return;
          cells.push({
            sido: sido.nm, sigungu: sgg.nm,
            km: distanceKm(state.origin[0], state.origin[1], sgg.c[0], sgg.c[1])
          });
        });
      });
      cells.sort(function (a, b) { return a.km - b.km; });
      var picks = cells.slice(0, 5);
      msg.textContent = picks.map(function (c) { return c.sigungu; }).join(", ") + " 데이터를 불러오는 중…";

      return Promise.all(picks.map(function (c) {
        return getJSON(CFG.dataBase + encodeURIComponent(c.sido) + "/" + encodeURIComponent(c.sigungu) + ".json");
      })).then(function (files) {
        var merged = [];
        files.forEach(function (f) { merged = merged.concat(expand(f.p)); });
        merged.forEach(function (r) {
          r._km = distanceKm(state.origin[0], state.origin[1], r.la, r.lo);
        });
        merged.sort(function (a, b) { return a._km - b._km; });
        state.all = merged.slice(0, 300);

        el("#nearby-result").hidden = false;
        applyFilter();
        var freeCount = state.all.filter(function (r) { return r.fr; }).length;
        msg.textContent = picks[0].sido + " " + picks[0].sigungu + " 부근 " +
          state.rows.length.toLocaleString() + "곳을 가까운 순으로 보여줍니다" +
          (freeCount ? " (무료 " + freeCount.toLocaleString() + "곳)" : "") + ".";
        btn.textContent = "다시 찾기";
        btn.disabled = false;
        if (state.map) {
          L.circleMarker(state.origin, {
            radius: 8, color: "#d94848", fillColor: "#d94848", fillOpacity: 0.9
          }).addTo(state.map).bindPopup("현재 위치");
        }
      });
    }).catch(function (err) {
      btn.disabled = false;
      btn.textContent = "내 주변 찾기";
      msg.textContent = "불러오기 실패: " + err.message;
    });
  }

  /* ---------- 공유 ---------- */

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
        }
      });
    });
  }

  /* 지도 팝업의 "목록에서 보기" — 해당 카드로 스크롤하고 잠깐 강조한다. */
  function bindGoto() {
    document.addEventListener("click", function (ev) {
      var btn = ev.target.closest && ev.target.closest("[data-goto]");
      if (!btn) return;
      var card = document.getElementById("spot-" + btn.dataset.goto);
      if (!card) return;
      if (state.map) state.map.closePopup();
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

  /* beforeinstallprompt 는 페이지가 뜨자마자 한 번만 날아온다.
     bindInstall() 은 DOM 이 준비된 뒤에 도는데, 그 사이에 이벤트가 지나가면
     영영 못 받는다. 그래서 구독만 스크립트 최상단에서 미리 해둔다. */
  window.addEventListener("beforeinstallprompt", function (ev) {
    ev.preventDefault();
    installPrompt = ev;
    var btn = el("#install-app");
    if (btn && !isStandalone()) btn.hidden = false;
  });

  function isStandalone() {
    return window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true;
  }

  function bindInstall() {
    var btn = el("#install-app");
    if (!btn || isStandalone()) return;   // 이미 설치했으면 권하지 않는다

    var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);

    // 위 구독이 이미 이벤트를 받아뒀을 수 있다.
    if (installPrompt) btn.hidden = false;

    // iOS 사파리에는 설치 API 가 없다. 방법을 알려주는 수밖에 없다.
    if (isIOS) btn.hidden = false;

    btn.addEventListener("click", function () {
      if (installPrompt) {
        var ev = installPrompt;
        // 한 번 쓴 이벤트는 재사용할 수 없다. 먼저 비워야
        // 사용자가 닫았을 때 아래 안내로 정확히 떨어진다.
        installPrompt = null;
        ev.prompt();
        ev.userChoice.then(function (res) {
          if (res && res.outcome === "accepted") btn.hidden = true;
        });
      } else if (isIOS) {
        toast("공유 버튼 → '홈 화면에 추가' 를 눌러주세요");
      } else {
        // 설치 창을 한 번 닫으면 크롬이 같은 페이지에서 다시 주지 않는다.
        toast("설치 창을 닫으셨네요. 새로고침한 뒤 다시 눌러주세요");
      }
    });

    window.addEventListener("appinstalled", function () {
      btn.hidden = true;
      installPrompt = null;
    });
  }

  /* 서비스워커. 내용을 캐시하진 않고, 설치 가능 조건을 채우는 용도다. */
  function registerSW() {
    if (!("serviceWorker" in navigator) || location.protocol !== "https:") return;
    navigator.serviceWorker.register("/sw.js").catch(function () { });
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindShare();
    bindGoto();
    bindKakaoApp();
    bindFilter();
    bindInstall();
    registerSW();
    if (CFG.mode === "region") startRegionPage();
    else if (CFG.mode === "home") startHomePage();

    // 레이아웃이 안정된 뒤 광고 요청
    setTimeout(pushAds, 300);
  });
})();

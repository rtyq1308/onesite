/* 공짜맵 - 전국 무료주차장 지도
   데이터는 /data/{시도}/{시군구}.json 을 필요할 때만 내려받는다. */
(function () {
  "use strict";

  var CFG = window.FREEMAP || {};
  var COLOR = "#1f7a5a";          // 상시 무료
  var COLOR_PARTLY = "#c2820a";   // 특정 요일만 무료

  var state = { rows: [], map: null, layer: null, origin: null, adPlaced: false };

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

  function itemHTML(row) {
    // fl 이 비어 있으면 상시 무료, 값이 있으면 그 요일에만 무료다.
    var partly = !!(row.fl && row.fl.length);
    var chips = [];
    if (partly) {
      row.fl.forEach(function (label) {
        chips.push('<span class="chip warn">' + esc(label) + "</span>");
      });
    } else {
      chips.push('<span class="chip">무료</span>');
    }
    if (row.kd) chips.push('<span class="chip plain">' + esc(row.kd) + "</span>");
    if (row.se) chips.push('<span class="chip plain">' + esc(row.se) + "</span>");
    if (row.cp) chips.push('<span class="chip plain">' + esc(row.cp) + "면</span>");
    if (row.tm) chips.push('<span class="chip plain">' + esc(row.tm) + "</span>");
    if (row._km != null) chips.push('<span class="chip plain">' + row._km.toFixed(1) + "km</span>");

    var kakao = "https://map.kakao.com/link/to/" +
      encodeURIComponent(row.nm) + "," + row.la + "," + row.lo;
    var google = "https://www.google.com/maps/dir/?api=1&destination=" + row.la + "," + row.lo;

    return '<article class="item">' +
      "<h3>" + esc(row.nm) + "</h3>" +
      '<p class="addr">' + esc(row.ad) + "</p>" +
      '<div class="meta">' + chips.join("") + "</div>" +
      (partly ? '<p class="warn-note">평일에는 요금을 받습니다</p>' : "") +
      '<div class="links">' +
      '<a href="' + kakao + '" target="_blank" rel="noopener">카카오맵 길찾기</a>' +
      '<a href="' + google + '" target="_blank" rel="noopener">구글맵</a>' +
      (row.tel ? '<a href="tel:' + esc(row.tel) + '">' + esc(row.tel) + "</a>" : "") +
      "</div></article>";
  }

  function renderList() {
    var rows = state.rows;
    var box = el("#list");
    if (!box) return;

    if (!rows.length) {
      box.innerHTML = '<p class="empty">이 지역에는 등록된 무료주차장이 없습니다.</p>';
    } else {
      box.innerHTML = rows.slice(0, 300).map(itemHTML).join("");
    }

    var more = el("#more");
    if (more) {
      more.textContent = rows.length > 300
        ? "총 " + rows.length.toLocaleString() + "곳 중 300곳까지 표시했습니다."
        : "";
    }
    placeFeedAd(rows.length);
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

  function renderMarkers() {
    if (!state.map) return;
    if (state.layer) state.map.removeLayer(state.layer);
    var rows = state.rows.slice(0, 500);
    if (!rows.length) return;

    var markers = rows.map(function (r) {
      // 상시 무료와 요일별 무료를 지도에서도 색으로 구분한다.
      var partly = !!(r.fl && r.fl.length);
      var color = partly ? COLOR_PARTLY : COLOR;
      var when = partly ? "<br>" + esc(r.fl.join(", ")) + " (평일 유료)" : "";
      return L.circleMarker([r.la, r.lo], {
        radius: 6, weight: 2, color: color, fillColor: color, fillOpacity: 0.55
      }).bindPopup("<b>" + esc(r.nm) + "</b><br>" + esc(r.ad) + when);
    });
    state.layer = L.layerGroup(markers).addTo(state.map);

    // animate:false 로 즉시 맞춘다. 애니메이션 줌은 CSS 트랜지션의 완료 이벤트에
    // 의존하는데, 백그라운드 탭처럼 트랜지션이 스로틀링되는 상황에서는 그 이벤트가
    // 오지 않아 지도가 초기 화면에 멈춰버린다. 첫 화면 맞춤에는 애니메이션이 필요 없다.
    // maxZoom 은 주차장이 한두 곳뿐인 지역에서 골목까지 확대되는 것을 막는다.
    state.map.fitBounds(
      L.latLngBounds(rows.map(function (r) { return [r.la, r.lo]; })).pad(0.15),
      { animate: false, maxZoom: 15 }
    );
  }

  function initMap() {
    var node = el("#map");
    if (!node || typeof L === "undefined") return;
    state.map = L.map(node, { scrollWheelZoom: true }).setView([36.5, 127.8], 7);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(state.map);
  }

  /* ---------- 페이지별 진입 ---------- */

  function startRegionPage() {
    initMap();
    getJSON(CFG.dataUrl).then(function (data) {
      state.rows = expand(data.p);
      renderList();
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
      var picks = cells.slice(0, 3);
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
        state.rows = merged.slice(0, 60);

        el("#nearby-result").hidden = false;
        msg.textContent = picks[0].sido + " " + picks[0].sigungu + " 부근 기준, 가까운 순 60곳입니다.";
        btn.textContent = "다시 찾기";
        btn.disabled = false;
        renderList();
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
          case "native":
            navigator.share({ title: title, url: prettyUrl }).catch(function () { });
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

  document.addEventListener("DOMContentLoaded", function () {
    bindShare();
    if (CFG.mode === "region") startRegionPage();
    else if (CFG.mode === "home") startHomePage();
  });
})();

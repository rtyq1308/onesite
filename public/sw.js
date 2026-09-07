/* 홈 화면 추가(설치)를 위해 필요한 최소 서비스워커.

   내용을 캐시하지 않는다. 주차장 요금·운영시간은 틀리면 사용자가 헛걸음하는
   정보라, 오래된 화면을 보여주느니 네트워크에서 매번 받는 편이 낫다.
   fetch 핸들러가 있어야 브라우저가 설치 가능한 앱으로 인정한다. */

self.addEventListener("install", function () {
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", function () {
  // respondWith 를 부르지 않으면 브라우저가 평소대로 네트워크로 처리한다.
});

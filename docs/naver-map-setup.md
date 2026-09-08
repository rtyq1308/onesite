# 네이버 지도와 목적지 검색 연결

구현일: 2026-09-09. 계정 생성·로그인·API 신청·인증정보 등록은 사용자 담당입니다. 인증값을 채팅이나 OneDrive 폴더에 저장하지 않습니다.

## 연결할 설정

| 용도 | 설정 이름 | 등록 위치 |
|---|---|---|
| 지도 및 주소 검색 | NAVER_MAP_CLIENT_ID | GitHub Actions Repository Variable 또는 빌드 프로세스 환경변수 |
| 장소명 검색 ID | NAVER_SEARCH_CLIENT_ID | Cloudflare Pages의 서버 환경변수/Secret |
| 장소명 검색 비밀키 | NAVER_SEARCH_CLIENT_SECRET | Cloudflare Pages의 Secret |

지도용과 검색용 인증은 서로 다른 서비스의 값입니다. 지도 공개 Client ID만 HTML의 SDK URL에 들어갑니다. 검색 비밀키는 `functions/api/places.js`가 서버에서만 읽으며 브라우저·생성 HTML·오류 본문에 전달하지 않습니다.

1. 네이버 클라우드 Maps 애플리케이션에 Web Dynamic Map과 Geocoding을 활성화하고 웹 서비스 URL에 `https://parking.itfinancelab.com`을 등록합니다. 로컬 실검증을 하려면 실제 사용하는 localhost/127.0.0.1 URL도 서비스의 등록 규칙에 맞게 허용합니다.
2. 네이버 개발자센터 애플리케이션에서 검색 API를 활성화하고 검색용 ID/Secret을 발급받아 Cloudflare Pages에 등록합니다. Production과 Preview는 필요한 환경에 각각 등록합니다.
3. 지도 ID를 빌드 환경에 설정한 후 `python scripts/build_site.py`로 dist를 생성합니다. 현재 설정이 없으면 기존 dist를 수정하기 전에 빌드를 중단합니다.
4. 저장소의 `functions/`와 생성된 `dist/`를 함께 사용하는 Pages Git 연동 또는 프로젝트 루트에서 Wrangler 배포를 사용합니다. 대시보드의 dist 파일 드래그 업로드만으로는 Functions가 배포되지 않습니다.
5. 배포 후 지도 타일·무료/요금 마커·팝업·지역 확대·장소명 검색·도로명 주소 검색·결과 선택·무료 필터를 실제 인증으로 확인합니다. 현재 이 단계는 미완료입니다.

## 로컬 점검

```powershell
node --test tests/maps-search.test.mjs
python scripts/build_site.py --preview
python -m http.server 8796 --bind 127.0.0.1 --directory .preview
```

`--preview`는 광고를 제거하고 `.preview/`에 생성합니다. 지도 ID가 없으면 지도 로딩 실패 안내가 나옵니다. 위 정적 서버에서는 `/api/places`가 실행되지 않으므로 실제 장소 검색은 동작하지 않습니다. 인증값 없이 성공 경로는 테스트의 모의 응답으로 검증합니다.

연결 후 Functions까지 로컬에서 실행할 때는 프로젝트 루트에서 Wrangler의 Pages 개발 서버를 사용하고, 검색 인증값은 OneDrive 밖의 환경 파일 경로를 명시하는 해당 버전의 `--env-file` 옵션을 확인해 전달하세요. 프로젝트 내부 `.dev.vars`나 `.env`는 사용하지 않습니다.

## 동작과 한계

- 홈과 시군구 페이지에 장소명/주소 검색창을 제공합니다. 네이버 지역 검색 결과 최대 5개 중 목적지를 선택합니다. 장소 결과가 없거나 검색 서버를 이용할 수 없으면 지도 Geocoder 주소 검색을 시도합니다.
- 선택 좌표와 지역 중심점이 가까운 8개 지역의 주차장 데이터를 가져오고 직선거리순 최대 300곳을 표시합니다. 전국 전체에 대한 정확한 최근접 탐색이나 도보 경로 거리는 아닙니다.
- 현재 위치/목적지 표시는 재검색 시 교체합니다. 사용자 검색어는 분석 이벤트로 보내지 않습니다.
- 기존 요금·요일별 무료 조건 데이터는 그대로 사용합니다. 실시간 빈자리나 특정 방문 시간의 무료 여부를 새로 판정하지 않습니다.
- 지도 재구성은 네이버 SDK로 교체했으며, 전체 화면 지도/사이드 메뉴 개편은 이번 범위에 포함하지 않았습니다.

공식 참고: [네이버 지도 Geocoder](https://navermaps.github.io/maps.js.ncp/docs/tutorial-Geocoder-Geocoding.html), [네이버 지역 검색 API](https://developers.naver.com/docs/serviceapi/search/local/local.md), [Cloudflare Pages Functions](https://developers.cloudflare.com/pages/functions/get-started/).

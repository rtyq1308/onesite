# 공짜맵 - 데이터 받고, 사이트 만들고, 브라우저로 열어보는 것까지 한 번에.
# 실행.bat 을 더블클릭하면 이 스크립트가 돈다.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host ""
Write-Host "=== 공짜맵 빌드 ===" -ForegroundColor Cyan
Write-Host ""

# 1) 인증키 - 한 번 입력하면 data\.key 에 저장되어 다음부터는 안 물어본다.
$keyFile = Join-Path $root "data\.key"
if (-not (Test-Path $keyFile)) {
    Write-Host "공공데이터포털 인증키가 필요합니다."
    Write-Host "  data.go.kr -> 마이페이지 -> 오픈API -> 인증키 발급현황 에서"
    Write-Host "  [인증키 복사(Decoding)] 버튼을 누르세요." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  버튼을 눌렀으면 여기서 그냥 Enter 만 치면 됩니다(클립보드에서 가져옵니다)."
    Write-Host "  직접 붙여넣으려면 붙여넣고 Enter."
    Write-Host ""
    $key = Read-Host "인증키"

    if ([string]::IsNullOrWhiteSpace($key)) {
        try { $key = Get-Clipboard -Raw } catch { $key = "" }
        if ([string]::IsNullOrWhiteSpace($key)) {
            Write-Host "클립보드가 비어 있습니다. 복사 버튼을 먼저 누르고 다시 실행하세요." -ForegroundColor Red
            exit 1
        }
        Write-Host "클립보드에서 인증키를 가져왔습니다." -ForegroundColor Green
    }

    # 포털 화면에서 키가 두 줄로 접혀 보여서, 긁어 복사하면 줄바꿈이 딸려온다.
    $key = ($key -replace '\s', '')

    if ($key.Length -lt 60) {
        Write-Host ""
        Write-Host "인증키가 $($key.Length)자밖에 안 됩니다. 복사하다 잘린 것 같습니다." -ForegroundColor Red
        Write-Host "[인증키 복사(Decoding)] 버튼으로 다시 복사한 뒤 실행해주세요." -ForegroundColor Red
        exit 1
    }

    [System.IO.File]::WriteAllText($keyFile, $key)
    Write-Host "인증키를 저장했습니다($($key.Length)자). 다음부터는 묻지 않습니다." -ForegroundColor Green
    Write-Host ""
}
$env:DATA_GO_KR_KEY = ([System.IO.File]::ReadAllText($keyFile) -replace '\s', '')
$env:PYTHONIOENCODING = "utf-8"

# 2) 공공데이터 수집 (약 1~3분)
Write-Host "[1/3] 공공데이터를 받는 중... 몇 분 걸립니다." -ForegroundColor Yellow
python scripts\fetch_data.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "수집에 실패했습니다. 인증키가 틀렸다면 data\.key 파일을 지우고 다시 실행하세요." -ForegroundColor Red
    exit 1
}

# 2-1) 서울은 표준데이터에 거의 없어서 열린데이터광장에서 따로 받는다.
$seoulFile = Join-Path $root "data\.seoul.key"
if (Test-Path $seoulFile) {
    $env:SEOUL_API_KEY = ([System.IO.File]::ReadAllText($seoulFile) -replace '\s', '')
    Write-Host ""
    Write-Host "[1-2/3] 서울 공영주차장을 받는 중..." -ForegroundColor Yellow
    python scripts/fetch_seoul.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "서울 데이터 수집에 실패했지만 나머지는 계속 진행합니다." -ForegroundColor Red
    }
}

# 3) 정적 사이트 생성
Write-Host ""
Write-Host "[2/3] 사이트를 만드는 중..." -ForegroundColor Yellow
python scripts\build_site.py
if ($LASTEXITCODE -ne 0) { exit 1 }

# 4) 미리보기
Write-Host ""
Write-Host "[3/3] 브라우저에서 열었습니다. 창을 닫거나 Ctrl+C 를 누르면 종료됩니다." -ForegroundColor Green
Write-Host "      주소: http://127.0.0.1:8788" -ForegroundColor Green
Write-Host ""
Start-Process "http://127.0.0.1:8788"
python -m http.server 8788 --directory dist --bind 127.0.0.1

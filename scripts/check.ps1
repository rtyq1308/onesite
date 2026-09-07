# 인증키가 왜 안 먹는지 진단한다. 진단.bat 을 더블클릭하면 실행된다.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$keyFile = Join-Path $root "data\.key"
if (-not (Test-Path $keyFile)) {
    Write-Host "저장된 인증키가 없습니다. 클립보드에서 가져옵니다..." -ForegroundColor Yellow
    try { $key = Get-Clipboard -Raw } catch { $key = "" }
    if ([string]::IsNullOrWhiteSpace($key)) {
        Write-Host "포털에서 [인증키 복사(Decoding)] 를 누른 뒤 다시 실행하세요." -ForegroundColor Red
        exit 1
    }
    $key = ($key -replace '\s', '')
} else {
    $key = ([System.IO.File]::ReadAllText($keyFile) -replace '\s', '')
}

$env:DATA_GO_KR_KEY = $key
$env:PYTHONIOENCODING = "utf-8"
python scripts\fetch_data.py --check

# ---------- 서울 열린데이터광장 ----------
$seoulFile = Join-Path $root "data\.seoul.key"
if (-not (Test-Path $seoulFile)) {
    Write-Host ""
    Write-Host "서울 열린데이터광장 인증키를 넣으면 서울 데이터도 점검합니다." -ForegroundColor Yellow
    Write-Host "  발급: https://data.seoul.go.kr/together/mypage/actkeyMain.do"
    Write-Host "  건너뛰려면 그냥 Enter 를 누르세요."
    Write-Host ""
    $sk = Read-Host "서울 인증키"
    if (-not [string]::IsNullOrWhiteSpace($sk)) {
        [System.IO.File]::WriteAllText($seoulFile, ($sk -replace '\s', ''))
        Write-Host "서울 인증키를 저장했습니다." -ForegroundColor Green
    }
}
if (Test-Path $seoulFile) {
    $env:SEOUL_API_KEY = ([System.IO.File]::ReadAllText($seoulFile) -replace '\s', '')
    Write-Host ""
    python scripts/fetch_seoul.py --check
}

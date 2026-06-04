# Nginx 리버스 프록시 자동 설정 스크립트
# 기존 Nginx에 Guacamole 프록시 추가

param(
    [string]$NginxDir = "C:\nginx",
    [string]$CertPath = "",
    [string]$KeyPath = "",
    [string]$Domain = "localhost"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Msg)
    Write-Host "`n>>> $Msg" -ForegroundColor Green
}

# Nginx 설치 확인
Write-Step "Nginx 확인..."
$nginxExe = "$NginxDir\nginx.exe"
if (-not (Test-Path $nginxExe)) {
    Write-Host "  Nginx가 설치되어 있지 않습니다." -ForegroundColor Yellow
    Write-Host "  https://nginx.org/en/download.html 에서 Windows 버전 다운로드" -ForegroundColor Yellow
    Write-Host "  다운로드 후 $NginxDir 에 압축 해제" -ForegroundColor Yellow
    exit 1
}

Write-Host "  Nginx 발견: $nginxExe"

# HTTPS 설정 (자체 인증서 또는 기존 인증서)
Write-Step "SSL 인증서 설정..."

if ($CertPath -and $KeyPath -and (Test-Path $CertPath) -and (Test-Path $KeyPath)) {
    Write-Host "  기존 인증서 사용: $CertPath"
} else {
    Write-Host "  자체 인증서 생성 중..."
    $certDir = "$NginxDir\ssl"
    New-Item -ItemType Directory -Force -Path $certDir | Out-Null

    # Windows 자기 인증서 생성
    $cert = New-SelfSignedCertificate -DnsName $Domain -CertStoreLocation "Cert:\LocalMachine\My" -NotAfter (Get-Date).AddYears(5)
    $certPath = "$certDir\guacamole.pfx"
    $keyPath = "$certDir\guacamole.key"
    $pwd = ConvertTo-SecureString -String "guacamole" -Force -AsPlainText
    Export-PfxCertificate -Cert $cert -FilePath $certPath -Password $pwd

    # PFX를 PEM으로 변환 (OpenSSL 필요)
    Write-Host "  자체 인증서 생성됨 (Windows 인증서 스토어)"
    Write-Host "  브라우저에서 경고가 뜨면 '계속' 클릭" -ForegroundColor Yellow

    # Nginx 설정에 PFX 사용
    $usePfx = $true
}

# 설정 파일 생성
Write-Step "Nginx 설정 파일 생성..."

$conf = @"
# Guacamole 리버스 프록시 설정
# 이 파일을 Nginx의 conf.d 폴더에 복사하거나
# nginx.conf의 http 블록 안에 include

upstream guacamole_backend {
    server 127.0.0.1:8080;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name $Domain;

    ssl_certificate     $certPath;
    ssl_certificate_key $keyPath;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Guacamole 리버스 프록시
    location /guacamole/ {
        proxy_pass http://guacamole_backend/guacamole/;
        proxy_buffering off;
        proxy_http_version 1.1;
        proxy_set_header Upgrade `$http_upgrade;
        proxy_set_header Connection `$http_connection;
        proxy_set_header Host `$host;
        proxy_set_header X-Real-IP `$remote_addr;
        proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto `$scheme;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    location /guacamole/websocket-tunnel {
        proxy_pass http://guacamole_backend/guacamole/websocket-tunnel;
        proxy_http_version 1.1;
        proxy_set_header Upgrade `$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host `$host;
        proxy_read_timeout 600s;
    }

    location / {
        return 301 /guacamole/;
    }
}

server {
    listen 80;
    server_name $Domain;
    return 301 https://`$host$request_uri;
}
"@

$confPath = "$NginxDir\conf\guacamole.conf"
$conf | Out-File -FilePath $confPath -Encoding UTF8 -Force
Write-Host "  설정 파일 생성: $confPath"

# Nginx 설정 테스트
Write-Step "Nginx 설정 테스트..."
$result = & $nginxExe -t 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  설정 테스트 통과"
} else {
    Write-Host "  설정 테스트 실패:" -ForegroundColor Red
    Write-Host "  $result" -ForegroundColor Red
    exit 1
}

# Nginx 재시작
Write-Step "Nginx 재시작..."
& $nginxExe -s reload 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Nginx 재시작 완료"
} else {
    # Try starting nginx
    Start-Process -FilePath $nginxExe -ArgumentList "-c", "$NginxDir\conf\nginx.conf"
    Write-Host "  Nginx 시작 완료"
}

# 완료
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "Link" }).IPAddress | Select-Object -First 1

Write-Host "`n=========================================" -ForegroundColor Cyan
Write-Host "  Nginx 리버스 프록시 설정 완료!" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "접속 주소:" -ForegroundColor White
Write-Host "  https://$Domain" -ForegroundColor Cyan
Write-Host "  https://$ip" -ForegroundColor Cyan
Write-Host ""
Write-Host "Guacamole:" -ForegroundColor White
Write-Host "  https://$Domain/guacamole/" -ForegroundColor Cyan
Write-Host "  사용자: guacadmin / guacadmin" -ForegroundColor Yellow
Write-Host "=========================================" -ForegroundColor Cyan

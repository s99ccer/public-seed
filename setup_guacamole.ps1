#Requires -RunAsAdministrator
param(
    [switch]$Uninstall,
    [switch]$SkipDocker,
    [string]$DbPass = "GuacPass123!",
    [string]$GuacUser = "guacadmin",
    [string]$GuacPass = "guacadmin"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "관리자 권한으로 실행해주세요." -ForegroundColor Red
    exit 1
}

$GuacDir = "C:\Guacamole"
$ComposeFile = "$GuacDir\docker-compose.yml"
$InitSql = "$GuacDir\initdb.sql"
$GuacPort = 8080

function Write-Step {
    param([string]$Msg)
    Write-Host "`n>>> $Msg" -ForegroundColor Green
}

function Test-Docker {
    try {
        $v = docker version --format "{{.Server.Version}}" 2>$null
        return [bool]$v
    } catch {
        return $false
    }
}

function Install-DockerDesktop {
    Write-Step "Docker Desktop 설치 중..."

    if (Test-Path "C:\Program Files\Docker\Docker\Docker Desktop.exe") {
        Write-Host "  Docker Desktop 이미 설치됨" -ForegroundColor Yellow
        return
    }

    Write-Host "  Docker Desktop 다운로드 중..."
    $url = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
    $installer = "$env:TEMP\DockerDesktopInstaller.exe"

    try {
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    } catch {
        Write-Host "  다운로드 실패. 수동 설치 필요:" -ForegroundColor Red
        Write-Host "  https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
        Write-Host "  설치 후 다시 실행해주세요." -ForegroundColor Yellow
        exit 1
    }

    Write-Host "  설치 중 (5~10분 소요)..."
    Start-Process -Wait -FilePath $installer -ArgumentList "install", "--quiet", "--accept-license", "--backend=wsl-2"
    Write-Host "  Docker Desktop 설치 완료"
    Write-Host "  재부팅이 필요할 수 있습니다." -ForegroundColor Yellow
}

function New-ComposeFile {
    Write-Step "docker-compose.yml 생성..."
    New-Item -ItemType Directory -Force -Path $GuacDir | Out-Null

    $yaml = @"
services:
  guacdb:
    container_name: guacamole-db
    image: mariadb:10.11
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: '$DbPass'
      MYSQL_DATABASE: 'guacamole_db'
      MYSQL_USER: 'guacamole_user'
      MYSQL_PASSWORD: '$DbPass'
    volumes:
      - guac-db-data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 10s
      timeout: 5s
      retries: 5

  guacd:
    container_name: guacamole-guacd
    image: guacamole/guacd:1.5.5
    restart: unless-stopped
    depends_on:
      guacdb:
        condition: service_healthy

  guacamole:
    container_name: guacamole-web
    image: guacamole/guacamole:1.5.5
    restart: unless-stopped
    ports:
      - "$GuacPort`:8080"
    environment:
      GUACD_HOSTNAME: "guacd"
      MYSQL_HOSTNAME: "guacdb"
      MYSQL_DATABASE: "guacamole_db"
      MYSQL_USER: "guacamole_user"
      MYSQL_PASSWORD: "$DbPass"
      WEBAPP_CONTEXT: "ROOT"
    depends_on:
      guacdb:
        condition: service_healthy
      guacd:
        condition: service_started

volumes:
  guac-db-data:
"@

    $yaml | Out-File -FilePath $ComposeFile -Encoding UTF8 -Force
    Write-Host "  생성 완료: $ComposeFile"
}

function Initialize-Database {
    Write-Step "데이터베이스 초기화..."

    # Generate init SQL
    Write-Host "  initdb.sh로 SQL 생성 중..."
    docker run --rm guacamole/guacd:1.5.5 cat /dev/null 2>$null | Out-Null
    docker run --rm guacamole/guacamole:1.5.5 /opt/guacamole/bin/initdb.sh --mysql > $InitSql 2>$null

    if (-not (Test-Path $InitSql) -or (Get-Item $InitSql).Length -eq 0) {
        Write-Host "  initdb.sh 실패, 대체 방법 사용..." -ForegroundColor Yellow
        docker run --rm guacamole/guacamole:1.5.5 /opt/guacamole/bin/initdb.sh --mysql 2>$null | Out-File -FilePath $InitSql -Encoding UTF8
    }

    if ((Test-Path $InitSql) -and (Get-Item $InitSql).Length -gt 0) {
        Write-Host "  SQL 스크립트 생성 완료 ($InitSql)"
    } else {
        Write-Host "  SQL 스크립트 생성 실패" -ForegroundColor Red
        Write-Host "  수동으로 초기화해야 합니다." -ForegroundColor Yellow
        return $false
    }
    return $true
}

function Start-Guacamole {
    Write-Step "Guacamole 시작..."

    # Start database first
    Write-Host "  데이터베이스 시작 중..."
    docker compose -f $ComposeFile up -d guacdb
    Start-Sleep -Seconds 15

    # Wait for database to be healthy
    Write-Host "  데이터베이스 준비 대기 중..."
    $retries = 0
    while ($retries -lt 30) {
        $health = docker inspect --format='{{.State.Health.Status}}' guacamole-db 2>$null
        if ($health -eq "healthy") {
            Write-Host "  데이터베이스 준비 완료"
            break
        }
        Start-Sleep -Seconds 3
        $retries++
        if ($retries % 5 -eq 0) {
            Write-Host "  대기 중... ($retries/30)"
        }
    }

    # Initialize database
    Write-Host "  데이터베이스 초기화 중..."
    docker exec -i guacamole-db mysql -u root -p"$DbPass" guacamole_db < $InitSql 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  SQL 초기화 실패, 수동 초기화 시도..." -ForegroundColor Yellow
        $sql = Get-Content $InitSql -Raw
        $sql | docker exec -i guacamole-db mysql -u root -p"$DbPass" guacamole_db 2>$null
    }

    # Start guacd and guacamole
    Write-Host "  Guacamole 서비스 시작 중..."
    docker compose -f $ComposeFile up -d

    # Wait for Guacamole to start
    Write-Host "  Guacamole 시작 대기 중..."
    $retries = 0
    while ($retries -lt 30) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:$GuacPort/guacamole/" -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) {
                Write-Host "  Guacamole 시작 완료!"
                return $true
            }
        } catch {}
        Start-Sleep -Seconds 3
        $retries++
    }

    Write-Host "  Guacamole 시작 시간 초과" -ForegroundColor Yellow
    return $false
}

function New-GuacAdmin {
    Write-Step "관리자 계정 생성..."

    # Wait a bit more for full initialization
    Start-Sleep -Seconds 10

    # Create user via guacamole API or database
    # Default admin: guacadmin / guacadmin (built-in)
    Write-Host "  기본 관리자 계정: guacadmin / guacadmin"
    Write-Host "  (로그인 후 반드시 비밀번호 변경!)" -ForegroundColor Yellow
}

function New-RdpConnection {
    Write-Step "RDP 연결 설정..."

    # Use MySQL to add a connection to localhost
    $sql = @"
INSERT INTO guacamole_connection (connection_name, protocol) VALUES ('Windows 11', 'RDP');
SET @connId = LAST_INSERT_ID();
INSERT INTO guacamole_connection_parameter (connection_id, parameter_name, parameter_value)
VALUES
    (@connId, 'hostname', '127.0.0.1'),
    (@connId, 'port', '3389'),
    (@connId, 'username', ''),
    (@connId, 'password', ''),
    (@connId, 'ignore-cert', 'true'),
    (@connId, 'enable-wallpaper', 'true'),
    (@connId, 'disable-audio', 'false');
INSERT INTO guacamole_connection_permission (connection_id, permission) VALUES (@connId, 'READ');
"@

    $sql | docker exec -i guacamole-db mysql -u root -p"$DbPass" guacamole_db 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  RDP 연결 'Windows 11' 추가 완료"
    } else {
        Write-Host "  RDP 연결 추가 실패 (수동으로 추가 필요)" -ForegroundColor Yellow
    }
}

function Enable-RDP {
    Write-Step "Windows RDP 활성화..."
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server" -Name "fDenyTSConnections" -Value 0
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" -Name "UserAuthentication" -Value 0
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop" 2>$null
    Write-Host "  RDP 활성화 완료"
}

function Configure-Firewall {
    Write-Step "방화벽 설정..."
    New-NetFirewallRule -DisplayName "Guacamole (8080)" -Direction Inbound -Protocol TCP -LocalPort $GuacPort -Action Allow -ErrorAction SilentlyContinue
    Write-Host "  방화벽 규칙 추가 (TCP $GuacPort)"
}

function Show-Info {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "Link" }).IPAddress | Select-Object -First 1

    Write-Host "`n=========================================" -ForegroundColor Cyan
    Write-Host "  Apache Guacamole 설치 완료!" -ForegroundColor Cyan
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "접속 주소:" -ForegroundColor White
    Write-Host "  http://localhost:$GuacPort" -ForegroundColor Cyan
    Write-Host "  http://$ip`:$GuacPort" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "로그인:" -ForegroundColor White
    Write-Host "  사용자: guacadmin" -ForegroundColor Yellow
    Write-Host "  비밀번호: guacadmin" -ForegroundColor Yellow
    Write-Host "  (로그인 후 반드시 비밀번호 변경!)" -ForegroundColor Red
    Write-Host ""
    Write-Host "RDP 연결:" -ForegroundColor White
    Write-Host "  'Windows 11' 연결 클릭 → 로그인" -ForegroundColor Gray
    Write-Host ""
    Write-Host "443 포트에 연결 (IIS 리버스 프록시):" -ForegroundColor White
    Write-Host "  1. IIS ARR + URL Rewrite 설치" -ForegroundColor Gray
    Write-Host "  2. /guacamole/ -> http://localhost:$GuacPort/guacamole/" -ForegroundColor Gray
    Write-Host "  3. WebSocket 지원 활성화" -ForegroundColor Gray
    Write-Host ""
    Write-Host "서비스 관리:" -ForegroundColor White
    Write-Host "  시작: docker compose -f $ComposeFile up -d" -ForegroundColor Gray
    Write-Host "  중지: docker compose -f $ComposeFile down" -ForegroundColor Gray
    Write-Host "  로그: docker compose -f $ComposeFile logs -f" -ForegroundColor Gray
    Write-Host ""
    Write-Host "제거:" -ForegroundColor White
    Write-Host "  .\setup_guacamole.ps1 -Uninstall" -ForegroundColor Gray
    Write-Host "=========================================" -ForegroundColor Cyan
}

function Uninstall-All {
    Write-Step "Guacamole 제거..."
    if (Test-Path $ComposeFile) {
        docker compose -f $ComposeFile down -v 2>$null
    }
    if (Test-Path $GuacDir) {
        Remove-Item -Recurse -Force $GuacDir -ErrorAction SilentlyContinue
    }
    Write-Host "제거 완료" -ForegroundColor Green
}

# ===== MAIN =====
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Apache Guacamole Docker Installer" -ForegroundColor Cyan
Write-Host "  Windows 11 원격 데스크톱 솔루션" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if ($Uninstall) {
    Uninstall-All
    exit
}

# Check Docker
if (-not $SkipDocker) {
    if (-not (Test-Docker)) {
        Install-DockerDesktop
        # Wait for Docker to be available
        Write-Host "  Docker 시작 대기 중..."
        $retries = 0
        while ($retries -lt 60) {
            if (Test-Docker) {
                Write-Host "  Docker 준비 완료"
                break
            }
            Start-Sleep -Seconds 5
            $retries++
            if ($retries % 6 -eq 0) {
                Write-Host "  대기 중... ($retries/60)"
            }
        }
    } else {
        Write-Host "  Docker 이미 설치됨" -ForegroundColor Yellow
    }
}

# Enable RDP
Enable-RDP

# Create docker-compose.yml
New-ComposeFile

# Initialize database
$dbReady = Initialize-Database

# Configure firewall
Configure-Firewall

# Start Guacamole
$started = Start-Guacamole

if ($started) {
    # Create default admin
    New-GuacAdmin

    # Add RDP connection
    New-RdpConnection
}

# Show info
Show-Info

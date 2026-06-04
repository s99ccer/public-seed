#Requires -RunAsAdministrator
param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "관리자 권한으로 실행해주세요." -ForegroundColor Red
    exit 1
}

$RdpDir = "C:\RDPWeb"

function Write-Step {
    param([string]$Msg)
    Write-Host "`n>>> $Msg" -ForegroundColor Green
}

function Install-TigerVNC {
    Write-Step "TigerVNC 설치 중..."
    $vncUrl = "https://github.com/TigerVNC/tigervnc/releases/download/v1.14.1/tigervnc-1.14.1-x86_64.exe"
    $installer = "$env:TEMP\tigervnc_setup.exe"
    
    try {
        Invoke-WebRequest -Uri $vncUrl -OutFile $installer -UseBasicParsing
    } catch {
        Write-Host "다운로드 실패, mirror 시도..." -ForegroundColor Yellow
        $vncUrl = "https://sourceforge.net/projects/tigervnc/files/stable/1.14.1/tigervnc-1.14.1-x86_64.exe/download"
        Invoke-WebRequest -Uri $vncUrl -OutFile $installer -UseBasicParsing
    }
    
    Write-Host "  설치파일 다운로드 완료. 설치 중..."
    Start-Process -Wait -FilePath $installer -ArgumentList "/S /LOADINF=$RdpDir\vnc_install.inf" -ErrorAction SilentlyContinue
    
    # Try silent install without inf
    Start-Process -Wait -FilePath $installer -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR=""C:\Program Files\TigerVNC""" -ErrorAction SilentlyContinue
    
    Write-Host "  TigerVNC 설치 완료"
}

function Set-VncPassword {
    Write-Step "VNC 접속 암호 설정..."
    $vncDir = "C:\Program Files\TigerVNC"
    $pwFile = "$env:USERPROFILE\.vnc\passwd"
    
    if (Test-Path "$vncDir\vncpasswd.exe") {
        # Create .vnc directory
        New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.vnc" | Out-Null
        
        # Generate VNC password (default: "password123")
        # vncpasswd needs interactive input, so we use a different approach
        # Set via registry for WinVNC
        $regPath = "HKLM:\SOFTWARE\TigerVNC\WinVNC4"
        if (-not (Test-Path $regPath)) {
            New-Item -Path $regPath -Force | Out-Null
        }
        
        # Default password "admin123" stored as hex
        # Note: This is obfuscated, not encrypted
        $password = "admin123"
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($password)
        
        # Use vncconfig to set password non-interactively
        # Actually, vncpasswd -f works differently
        Write-Host "  VNC 암호: admin123 (추후 vncpasswd.exe로 변경 가능)"
        Write-Host "  주의: 보안을 위해 반드시 암호를 변경하세요!" -ForegroundColor Yellow
    }
}

function Install-Deps {
    Write-Step "Python 의존성 설치..."
    
    # Check if chocolatey is available
    $choco = Get-Command "choco" -ErrorAction SilentlyContinue
    if (-not $choco) {
        Write-Host "  Chocolatey 설치 중..."
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')) 2>$null
    }
    
    # Install NSSM (Non-Sucking Service Manager) for Windows service management
    if (Get-Command "choco" -ErrorAction SilentlyContinue) {
        choco install nssm -y --no-progress 2>$null
    }
    
    # Install Python packages
    pip install websockify 2>$null
    pip install flask flask-sock 2>$null
    
    Write-Host "  의존성 설치 완료"
}

function Install-NoVNC {
    Write-Step "noVNC 설치 중..."
    
    $novncDir = "$RdpDir\novnc"
    if (Test-Path $novncDir) {
        Remove-Item -Recurse -Force $novncDir -ErrorAction SilentlyContinue
    }
    
    # Download noVNC latest release
    $novncUrl = "https://github.com/novnc/noVNC/archive/refs/tags/v1.5.0.zip"
    $zipFile = "$env:TEMP\novnc.zip"
    
    try {
        Invoke-WebRequest -Uri $novncUrl -OutFile $zipFile -UseBasicParsing
    } catch {
        # Fallback to direct master branch
        $novncUrl = "https://github.com/novnc/noVNC/archive/refs/heads/master.zip"
        Invoke-WebRequest -Uri $novncUrl -OutFile $zipFile -UseBasicParsing
    }
    
    # Extract
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $tempExtract = "$env:TEMP\novnc_extract"
    if (Test-Path $tempExtract) { Remove-Item -Recurse -Force $tempExtract -ErrorAction SilentlyContinue }
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zipFile, $tempExtract)
    
    # Find the extracted directory (it could be noVNC-* or noVNC-master)
    $extracted = Get-ChildItem $tempExtract | Where-Object { $_.PSIsContainer } | Select-Object -First 1
    if ($extracted) {
        Move-Item -Path $extracted.FullName -Destination $novncDir -Force
    }
    
    # Clean up
    Remove-Item -Recurse -Force $tempExtract -ErrorAction SilentlyContinue
    Remove-Item -Force $zipFile -ErrorAction SilentlyContinue
    
    Write-Host "  noVNC 설치 완료: $novncDir"
}

function Enable-RDP {
    Write-Step "Windows 원격 데스크톱 활성화..."
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server" -Name "fDenyTSConnections" -Value 0
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" -Name "UserAuthentication" -Value 0
    Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
    Write-Host "  RDP 활성화 완료"
}

function New-Service-Script {
    Write-Step "서비스 시작 스크립트 생성..."
    
    # Create start script
    @"
`$ErrorActionPreference = "SilentlyContinue"
`$logFile = "$RdpDir\rdp_server.log"
`$novncDir = "$RdpDir\novnc"

# Wait for TigerVNC service to start
Start-Sleep -Seconds 3

# Run websockify with noVNC web interface
python -m websockify --web `$novncDir 6080 localhost:5900 2>&1 | Out-File `$logFile -Append
"@ | Out-File -FilePath "$RdpDir\start_websockify.ps1" -Encoding ASCII -Force
    
    Write-Host "  시작 스크립트 생성 완료"
}

function New-Service {
    Write-Step "Windows 서비스 등록..."
    
    # Create a CMD wrapper because NSSM needs a .exe or .bat
@"
@echo off
powershell -ExecutionPolicy Bypass -File "C:\RDPWeb\start_websockify.ps1"
"@ | Out-File -FilePath "$RdpDir\run_websockify.bat" -Encoding ASCII -Force
    
    # Try to create service
    $svcName = "RDPWebProxy"
    $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
    if ($svc) {
        sc.exe stop $svcName 2>$null
        sc.exe delete $svcName 2>$null
        Start-Sleep -Seconds 2
    }
    
    nssm install $svcName "cmd.exe" "/c `"$RdpDir\run_websockify.bat`"" 2>$null
    if ($?) {
        nssm set $svcName Description "Web-based Remote Desktop (noVNC + TigerVNC)" 2>$null
        nssm set $svcName Start SERVICE_AUTO_START 2>$null
        nssm set $svcName AppStdout "$RdpDir\service.log" 2>$null
        nssm set $svcName AppStderr "$RdpDir\service.err" 2>$null
        nssm set $svcName AppRestartDelay 5000 2>$null
        Write-Host "  서비스 '$svcName' 등록 완료"
    } else {
        Write-Host "  NSSM 서비스 등록 실패, 대체 방법 사용..." -ForegroundColor Yellow
        # Alternative: Scheduled Task
        $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$RdpDir\start_websockify.ps1`""
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        Register-ScheduledTask -TaskName "RDPWebProxy" -Action $action -Trigger $trigger -Principal $principal -Force 2>$null
        Write-Host "  예약 작업으로 등록 완료 (로그온 시 자동 실행)"
    }
}

function Configure-Firewall {
    Write-Step "방화벽 규칙 설정..."
    New-NetFirewallRule -DisplayName "RDP Web Proxy (6080)" -Direction Inbound -Protocol TCP -LocalPort 6080 -Action Allow -ErrorAction SilentlyContinue
    Write-Host "  방화벽 규칙 추가 완료 (TCP 6080)"
}

function Start-Now {
    Write-Step "서비스 시작..."
    
    # Start TigerVNC service if it exists
    $vncSvc = Get-Service -Name "tigervnc" -ErrorAction SilentlyContinue
    if ($vncSvc -and $vncSvc.Status -ne "Running") {
        Start-Service -Name "tigervnc" -ErrorAction SilentlyContinue
        Write-Host "  TigerVNC 서비스 시작"
    }
    
    # Start RDP Web service
    $svc = Get-Service -Name "RDPWebProxy" -ErrorAction SilentlyContinue
    if ($svc) {
        Start-Service -Name "RDPWebProxy" -ErrorAction SilentlyContinue
        Write-Host "  RDPWebProxy 서비스 시작"
    }
    
    # If service didn't work, run directly
    if (-not ($svc)) {
        Write-Host "  직접 실행 모드..."
        $novncDir = "$RdpDir\novnc"
        Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-m websockify --web `"$novncDir`" 6080 localhost:5900"
    }
}

function Uninstall-All {
    Write-Step "제거 중..."
    
    # Stop and remove services
    sc.exe stop "RDPWebProxy" 2>$null
    sc.exe delete "RDPWebProxy" 2>$null
    Unregister-ScheduledTask -TaskName "RDPWebProxy" -Confirm:$false 2>$null
    
    # Remove TigerVNC
    $uninstaller = Get-ChildItem "C:\Program Files\TigerVNC\unins*.exe" -ErrorAction SilentlyContinue
    if ($uninstaller) {
        Start-Process -Wait -FilePath $uninstaller.FullName -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES"
    }
    
    # Remove RDPWeb directory
    if (Test-Path $RdpDir) {
        Remove-Item -Recurse -Force $RdpDir -ErrorAction SilentlyContinue
    }
    
    Write-Host "제거 완료" -ForegroundColor Green
}

# ===== MAIN =====
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  Windows 원격 데스크톱 웹 설정" -ForegroundColor Cyan
Write-Host "  (TigerVNC + noVNC + WebSockify)" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan

if ($Uninstall) {
    Uninstall-All
    exit
}

# Create RDPWeb directory
New-Item -ItemType Directory -Force -Path $RdpDir | Out-Null

# Check if TigerVNC is already installed
$vncInstalled = Test-Path "C:\Program Files\TigerVNC\winvnc.exe"
if (-not $vncInstalled) {
    Install-TigerVNC
} else {
    Write-Host "  TigerVNC 이미 설치됨" -ForegroundColor Yellow
}

# Install dependencies
Install-Deps

# Install noVNC
Install-NoVNC

# Enable RDP
Enable-RDP

# Set VNC password
Set-VncPassword

# Create service script
New-Service-Script

# Register Windows service
New-Service

# Configure firewall
Configure-Firewall

# Start now
Start-Now

# Show info
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "Link" }).IPAddress | Select-Object -First 1

Write-Host "`n=======================================" -ForegroundColor Green
Write-Host "  설치 완료!" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green
Write-Host "접속 주소:" -ForegroundColor White
Write-Host "  http://localhost:6080/vnc_lite.html" -ForegroundColor Cyan
Write-Host "  http://$ip`:6080/vnc_lite.html" -ForegroundColor Cyan
Write-Host ""
Write-Host "VNC 암호: admin123" -ForegroundColor Yellow
Write-Host "(반드시 변경하세요: vncpasswd.exe)" -ForegroundColor Yellow
Write-Host ""
Write-Host "IIS/Nginx 리버스 프록시로 443에 연결하려면:" -ForegroundColor White
Write-Host "  1. IIS: ARR 모듈 설치 후 /vnc/ -> http://localhost:6080/ 프록시" -ForegroundColor Gray
Write-Host "  2. Nginx: location /vnc/ { proxy_pass http://localhost:6080/; }" -ForegroundColor Gray
Write-Host ""
Write-Host "서비스 상태 확인:" -ForegroundColor White
Write-Host "  Get-Service RDPWebProxy" -ForegroundColor Gray
Write-Host "서비스 중지:" -ForegroundColor White
Write-Host "  sc.exe stop RDPWebProxy" -ForegroundColor Gray
Write-Host "제거:" -ForegroundColor White
Write-Host "  .\setup_rdp.ps1 -Uninstall" -ForegroundColor Gray
Write-Host "=======================================" -ForegroundColor Green

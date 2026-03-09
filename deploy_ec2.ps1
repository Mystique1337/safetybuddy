<#
.SYNOPSIS
    SafetyBuddy — AWS EC2 Deployment Script (PowerShell)
    Deploys via Docker on a single EC2 instance

.EXAMPLE
    .\deploy_ec2.ps1 -EC2Host "54.123.45.67" -KeyFile "C:\Users\you\.ssh\mykey.pem"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$EC2Host,

    [Parameter(Mandatory=$false)]
    [string]$KeyFile = "$env:USERPROFILE\.ssh\id_rsa",

    [Parameter(Mandatory=$false)]
    [string]$User = "ec2-user"
)

$APP_DIR = "/home/$User/safetybuddy"
$SSH = "ssh -o StrictHostKeyChecking=no -i `"$KeyFile`" $User@$EC2Host"
$SCP = "scp -o StrictHostKeyChecking=no -i `"$KeyFile`""

Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  SafetyBuddy — EC2 Docker Deploy" -ForegroundColor Cyan
Write-Host "  Target: $EC2Host" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan

# ── 1. Check SSH connectivity ─────────────────────────
Write-Host "`n[1/5] Testing SSH connection..." -ForegroundColor Yellow
$testCmd = "$SSH `"echo 'SSH OK'`""
Invoke-Expression $testCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Cannot SSH to $EC2Host. Check your key file and security group." -ForegroundColor Red
    exit 1
}

# ── 2. Install Docker on EC2 ──────────────────────────
Write-Host "`n[2/5] Ensuring Docker is installed..." -ForegroundColor Yellow
$dockerInstall = @"
if ! command -v docker &> /dev/null; then
    sudo yum update -y
    sudo yum install -y docker
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker `$USER
fi
docker --version
"@
Invoke-Expression "$SSH `"$dockerInstall`""

# ── 3. Sync project files ─────────────────────────────
Write-Host "`n[3/5] Syncing project files..." -ForegroundColor Yellow

# Create remote directory
Invoke-Expression "$SSH `"mkdir -p $APP_DIR`""

# Use scp for key files (rsync may not be available on Windows)
$excludes = @('.git', '__pycache__', 'venv', '.venv', 'data/processed/chroma_db', '*.pyc')

# Create a tar, excluding unwanted files, and pipe to EC2
$tarExcludes = ($excludes | ForEach-Object { "--exclude='$_'" }) -join " "
Write-Host "  Packing and uploading project..."

# Simpler approach: use scp with a zip
$zipPath = "$env:TEMP\safetybuddy_deploy.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath }
Compress-Archive -Path ".\*" -DestinationPath $zipPath -Force
Invoke-Expression "$SCP `"$zipPath`" $User@${EC2Host}:/tmp/safetybuddy.zip"
Invoke-Expression "$SSH `"cd $APP_DIR && unzip -o /tmp/safetybuddy.zip && rm /tmp/safetybuddy.zip`""

# ── 4. Build and run ──────────────────────────────────
Write-Host "`n[4/5] Building and starting Docker containers..." -ForegroundColor Yellow
$dockerRun = @"
cd $APP_DIR
docker compose down 2>/dev/null || true
docker compose up --build -d
sleep 5
curl -sf http://localhost:5000/api/health && echo 'Health: OK' || echo 'Health: pending...'
"@
Invoke-Expression "$SSH `"$dockerRun`""

# ── 5. Status ─────────────────────────────────────────
Write-Host "`n[5/5] Deployment status:" -ForegroundColor Yellow
Invoke-Expression "$SSH `"cd $APP_DIR && docker compose ps`""

Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✅ Deployed! Access at: http://${EC2Host}:5000" -ForegroundColor Green
Write-Host ""
Write-Host "  Don't forget:" -ForegroundColor Yellow
Write-Host "  1. Set OPENAI_API_KEY in $APP_DIR/.env" -ForegroundColor Yellow
Write-Host "  2. Open port 5000 (or 80) in EC2 Security Group" -ForegroundColor Yellow
Write-Host "  3. Consider adding an ALB or Nginx for HTTPS" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Green

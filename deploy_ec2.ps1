<#
.SYNOPSIS
    SafetyBuddy — AWS EC2 First-Time Setup + Deploy (PowerShell)
    After this, GitHub Actions handles auto-deploy on push.

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
$REPO_URL = "https://github.com/Mystique1337/safetybuddy.git"
$SSH = "ssh -o StrictHostKeyChecking=no -i `"$KeyFile`" $User@$EC2Host"
$SCP = "scp -o StrictHostKeyChecking=no -i `"$KeyFile`""

Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  SafetyBuddy — EC2 Setup & Deploy" -ForegroundColor Cyan
Write-Host "  Target: $EC2Host" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan

# ── 1. Check SSH connectivity ─────────────────────────
Write-Host "`n[1/5] Testing SSH connection..." -ForegroundColor Yellow
Invoke-Expression "$SSH `"echo 'SSH OK'`""
if ($LASTEXITCODE -ne 0) {
    Write-Host "Cannot SSH to $EC2Host. Check key file and security group." -ForegroundColor Red
    exit 1
}

# ── 2. Install Docker + Git on EC2 ────────────────────
Write-Host "`n[2/5] Ensuring Docker & Git are installed..." -ForegroundColor Yellow
$installCmd = @'
if ! command -v docker &> /dev/null; then
    sudo yum update -y
    sudo yum install -y docker git
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker $USER
fi
if ! docker compose version &> /dev/null; then
    sudo mkdir -p /usr/local/lib/docker/cli-plugins
    sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose
    sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
fi
docker --version && docker compose version
'@
Invoke-Expression "$SSH '$installCmd'"

# ── 3. Clone repo (or pull latest) + copy model ───────
Write-Host "`n[3/5] Cloning/updating repo + uploading model..." -ForegroundColor Yellow
$cloneCmd = "if [ ! -d '$APP_DIR/.git' ]; then git clone $REPO_URL $APP_DIR; else cd $APP_DIR && git fetch origin master && git reset --hard origin/master; fi"
Invoke-Expression "$SSH `"$cloneCmd`""

# Upload YOLO model (not in git)
if (Test-Path "data\models\ppe_yolo26n.pt") {
    Write-Host "  Uploading YOLO model..." -ForegroundColor Gray
    Invoke-Expression "$SSH `"mkdir -p $APP_DIR/data/models`""
    Invoke-Expression "$SCP `"data\models\ppe_yolo26n.pt`" ${User}@${EC2Host}:${APP_DIR}/data/models/"
} else {
    Write-Host "  No local YOLO model found — skipping" -ForegroundColor Gray
}

# Create .env if needed
$envCmd = "if [ ! -f '$APP_DIR/.env' ]; then cp '$APP_DIR/.env.example' '$APP_DIR/.env'; echo 'Created .env — set OPENAI_API_KEY!'; else echo '.env exists'; fi"
Invoke-Expression "$SSH `"$envCmd`""

# ── 4. Build and run ──────────────────────────────────
Write-Host "`n[4/5] Building and starting Docker containers..." -ForegroundColor Yellow
$dockerCmd = "cd $APP_DIR && docker compose down 2>/dev/null; docker compose up --build -d && sleep 8 && curl -sf http://localhost:5000/api/health && echo ' Healthy!' || echo ' Starting...'"
Invoke-Expression "$SSH `"$dockerCmd`""

# ── 5. Status ─────────────────────────────────────────
Write-Host "`n[5/5] Deployment status:" -ForegroundColor Yellow
Invoke-Expression "$SSH `"cd $APP_DIR && docker compose ps`""

Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Deployed! Access at: http://${EC2Host}:5000" -ForegroundColor Green
Write-Host ""
Write-Host "  NEXT STEPS:" -ForegroundColor Yellow
Write-Host "  1. SSH in and set OPENAI_API_KEY in .env" -ForegroundColor Yellow
Write-Host "  2. Open port 5000 in EC2 Security Group" -ForegroundColor Yellow
Write-Host "  3. Add these GitHub Secrets for auto-deploy:" -ForegroundColor Yellow
Write-Host "     EC2_HOST    = $EC2Host" -ForegroundColor White
Write-Host "     EC2_USER    = $User" -ForegroundColor White
Write-Host "     EC2_SSH_KEY = (paste your private key)" -ForegroundColor White
Write-Host ""
Write-Host "  After that, every 'git push' auto-deploys!" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Green

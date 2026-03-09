#!/bin/bash
# ═══════════════════════════════════════════════════════
#  SafetyBuddy — AWS EC2 Deployment Script
#  Deploys via Docker on a single EC2 instance
# ═══════════════════════════════════════════════════════
set -e

# ── CONFIGURATION ──────────────────────────────────────
EC2_HOST="${1:?Usage: ./deploy_ec2.sh <ec2-ip-or-dns> [key-file]}"
KEY_FILE="${2:-~/.ssh/id_rsa}"
APP_DIR="/home/ec2-user/safetybuddy"
SSH_OPTS="-o StrictHostKeyChecking=no -i $KEY_FILE"

echo "═══════════════════════════════════════════════"
echo "  SafetyBuddy — EC2 Docker Deploy"
echo "  Target: $EC2_HOST"
echo "═══════════════════════════════════════════════"

# ── 1. Install Docker on EC2 (idempotent) ─────────────
echo ""
echo "[1/5] Ensuring Docker is installed on EC2..."
ssh $SSH_OPTS ec2-user@$EC2_HOST << 'REMOTE_INSTALL'
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    sudo yum update -y
    sudo yum install -y docker
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker ec2-user
    echo "Docker installed. You may need to re-login for group change."
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "Installing Docker Compose plugin..."
    sudo mkdir -p /usr/local/lib/docker/cli-plugins
    sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose
    sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
fi

docker --version
docker compose version 2>/dev/null || docker-compose --version
REMOTE_INSTALL

# ── 2. Sync project files ─────────────────────────────
echo ""
echo "[2/5] Syncing project files to EC2..."
rsync -avz --progress \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'venv' \
    --exclude '.venv' \
    --exclude 'data/processed/chroma_db' \
    -e "ssh $SSH_OPTS" \
    ./ ec2-user@$EC2_HOST:$APP_DIR/

# ── 3. Set up environment file ────────────────────────
echo ""
echo "[3/5] Checking .env on EC2..."
ssh $SSH_OPTS ec2-user@$EC2_HOST << REMOTE_ENV
cd $APP_DIR
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating template..."
    cat > .env << 'EOF'
OPENAI_API_KEY=sk-REPLACE_WITH_YOUR_KEY
SECRET_KEY=$(openssl rand -hex 32)
FLASK_ENV=production
EOF
    echo "❌ IMPORTANT: Edit .env and set your OPENAI_API_KEY"
    echo "   nano $APP_DIR/.env"
else
    echo "✅ .env exists"
fi
REMOTE_ENV

# ── 4. Build and run with Docker ──────────────────────
echo ""
echo "[4/5] Building and starting containers..."
ssh $SSH_OPTS ec2-user@$EC2_HOST << REMOTE_DOCKER
cd $APP_DIR
docker compose down 2>/dev/null || true
docker compose up --build -d
echo ""
echo "Waiting for health check..."
sleep 5
curl -sf http://localhost:5000/api/health && echo "" && echo "✅ App is healthy!" || echo "⚠️  Health check pending..."
REMOTE_DOCKER

# ── 5. Show status ────────────────────────────────────
echo ""
echo "[5/5] Deployment status..."
ssh $SSH_OPTS ec2-user@$EC2_HOST "cd $APP_DIR && docker compose ps"

echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ Deployed! Access at: http://$EC2_HOST:5000"
echo ""
echo "  Useful commands (SSH into EC2):"
echo "    docker compose logs -f        # View logs"
echo "    docker compose restart        # Restart app"
echo "    docker compose down           # Stop app"
echo "    nano $APP_DIR/.env            # Edit config"
echo "═══════════════════════════════════════════════"

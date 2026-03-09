#!/bin/bash
# ═══════════════════════════════════════════════════════
#  SafetyBuddy — AWS EC2 First-Time Setup + Deploy
#  After this, GitHub Actions handles auto-deploy on push
# ═══════════════════════════════════════════════════════
set -e

EC2_HOST="${1:?Usage: ./deploy_ec2.sh <ec2-ip-or-dns> [key-file]}"
KEY_FILE="${2:-~/.ssh/id_rsa}"
APP_DIR="/home/ec2-user/safetybuddy"
REPO_URL="https://github.com/Mystique1337/safetybuddy.git"
SSH_OPTS="-o StrictHostKeyChecking=no -i $KEY_FILE"

echo "═══════════════════════════════════════════════"
echo "  SafetyBuddy — EC2 Setup & Deploy"
echo "  Target: $EC2_HOST"
echo "═══════════════════════════════════════════════"

# ── 1. Install Docker + Git ───────────────────────────
echo ""
echo "[1/5] Installing Docker & Git on EC2..."
ssh $SSH_OPTS ec2-user@$EC2_HOST << 'REMOTE_INSTALL'
if ! command -v docker &> /dev/null; then
    echo "Installing Docker & Git..."
    sudo dnf update -y
    sudo dnf install -y docker git
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker ec2-user
    # newgrp docker to apply group immediately
    echo "Docker installed — group applied"
fi

if ! docker compose version &> /dev/null; then
    echo "Installing Docker Compose plugin..."
    sudo mkdir -p /usr/local/lib/docker/cli-plugins
    sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose
    sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
fi

docker --version
docker compose version
REMOTE_INSTALL

# ── 2. Clone repo (or pull latest) ────────────────────
echo ""
echo "[2/5] Cloning/updating repo from GitHub..."
ssh $SSH_OPTS ec2-user@$EC2_HOST << REMOTE_CLONE
if [ ! -d "$APP_DIR/.git" ]; then
    git clone $REPO_URL $APP_DIR
else
    cd $APP_DIR
    git fetch origin master
    git reset --hard origin/master
fi
REMOTE_CLONE

# ── 3. Copy YOLO model + .env (not in git) ────────────
echo ""
echo "[3/5] Syncing model + .env to EC2..."

# Copy YOLO model if it exists locally
if [ -f "data/models/ppe_yolo26n.pt" ]; then
    echo "  Uploading YOLO model..."
    ssh $SSH_OPTS ec2-user@$EC2_HOST "mkdir -p $APP_DIR/data/models"
    scp $SSH_OPTS data/models/ppe_yolo26n.pt ec2-user@$EC2_HOST:$APP_DIR/data/models/
else
    echo "  ⚠️  No local YOLO model found — skipping"
fi

# Create .env if it doesn't exist on EC2
ssh $SSH_OPTS ec2-user@$EC2_HOST << 'REMOTE_ENV'
APP_DIR="/home/ec2-user/safetybuddy"
if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" << EOF
OPENAI_API_KEY=sk-REPLACE_WITH_YOUR_KEY
SECRET_KEY=$(openssl rand -hex 32)
FLASK_ENV=production
EOF
    echo "  ⚠️  Created .env — you MUST set OPENAI_API_KEY:"
    echo "     ssh into EC2 and run: nano $APP_DIR/.env"
else
    echo "  ✅ .env already exists"
fi
REMOTE_ENV

# ── 4. Build and run ──────────────────────────────────
echo ""
echo "[4/5] Building and starting Docker containers..."
ssh $SSH_OPTS ec2-user@$EC2_HOST << REMOTE_DOCKER
cd $APP_DIR
sudo docker compose down 2>/dev/null || true
sudo docker compose up --build -d
echo "Waiting for app to start..."
sleep 10
curl -sf http://localhost:5000/api/health && echo "" && echo "✅ App is healthy!" || echo "⚠️  Health check pending — check: sudo docker compose logs"
REMOTE_DOCKER

# ── 5. Status ─────────────────────────────────────────
echo ""
echo "[5/5] Deployment status..."
ssh $SSH_OPTS ec2-user@$EC2_HOST "cd $APP_DIR && sudo docker compose ps"

echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ Deployed! Access at: http://$EC2_HOST:5000"
echo ""
echo "  NEXT STEPS:"
echo "  1. SSH in and set OPENAI_API_KEY in .env"
echo "  2. Open port 5000 in EC2 Security Group"
echo "  3. Add these GitHub Secrets for auto-deploy:"
echo "     EC2_HOST     = $EC2_HOST"
echo "     EC2_USER     = ec2-user"
echo "     EC2_SSH_KEY  = (paste your private key)"
echo ""
echo "  After that, every 'git push' auto-deploys!"
echo "═══════════════════════════════════════════════"

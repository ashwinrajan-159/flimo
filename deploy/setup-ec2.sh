#!/bin/bash
# =============================================================================
# Flimo AI Platform — EC2 Deployment Script
# 
# Run this on a fresh Ubuntu 22.04 EC2 instance (t3.medium minimum)
#
# Usage:
#   chmod +x deploy/setup-ec2.sh
#   sudo ./deploy/setup-ec2.sh
# =============================================================================

set -e

DOMAIN="${1:-your-domain.com}"
APP_DIR="/home/ubuntu/flimo"
REPO_URL="https://github.com/ashwinrajan-159/flimo.git"

echo "=== Flimo EC2 Setup ==="
echo "Domain: $DOMAIN"
echo "App Dir: $APP_DIR"

# --- 1. System Updates ---
echo "[1/7] Updating system..."
apt-get update -y
apt-get upgrade -y

# --- 2. Install Docker ---
echo "[2/7] Installing Docker..."
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

usermod -aG docker ubuntu

# --- 3. Install Nginx ---
echo "[3/7] Installing Nginx..."
apt-get install -y nginx

# --- 4. Clone Repository ---
echo "[4/7] Cloning repository..."
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR"
    git pull
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# --- 5. Setup Environment ---
echo "[5/7] Setting up environment..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    # Generate a random JWT secret
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    sed -i "s|CHANGE_ME_TO_A_RANDOM_SECRET|$JWT_SECRET|g" "$APP_DIR/.env"
    echo ""
    echo "=========================================="
    echo "IMPORTANT: Edit $APP_DIR/.env with your actual values!"
    echo "=========================================="
    echo ""
fi

# Create data/logs dirs
mkdir -p "$APP_DIR/data" "$APP_DIR/logs"
chown -R ubuntu:ubuntu "$APP_DIR"

# --- 6. Configure Nginx ---
echo "[6/7] Configuring Nginx..."
cat > /etc/nginx/sites-available/flimo <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /static/ {
        alias $APP_DIR/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    client_max_body_size 10M;
}
EOF

ln -sf /etc/nginx/sites-available/flimo /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# --- 7. Build & Start ---
echo "[7/7] Building and starting Flimo..."
cd "$APP_DIR"
docker compose build
docker compose up -d

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Flimo is running at: http://$DOMAIN"
echo ""
echo "Next steps:"
echo "  1. Edit $APP_DIR/.env with your actual API keys and Cognito config"
echo "  2. Copy your data files (content.db, vectors.faiss, id_map.pkl) to $APP_DIR/data/"
echo "  3. Restart: cd $APP_DIR && docker compose restart"
echo "  4. For HTTPS: sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx -d $DOMAIN"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f     # View logs"
echo "  docker compose restart     # Restart app"
echo "  docker compose down        # Stop app"
echo ""

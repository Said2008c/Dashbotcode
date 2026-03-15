#!/bin/bash

# ═══════════════════════════════════════════════════════════════
#           ⚡ PteroDash — Auto Setup Script
# ═══════════════════════════════════════════════════════════════

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
err()     { echo -e "${RED}[ERR]${NC}   $1"; exit 1; }
step()    { echo -e "\n${PURPLE}${BOLD}━━━ $1 ━━━${NC}"; }

# ── Banner ──
clear
echo -e "${PURPLE}${BOLD}"
echo "  ██████╗ ████████╗███████╗██████╗  ██████╗ ██████╗  █████╗ ███████╗██╗  ██╗"
echo "  ██╔══██╗╚══██╔══╝██╔════╝██╔══██╗██╔═══██╗██╔══██╗██╔══██╗██╔════╝██║  ██║"
echo "  ██████╔╝   ██║   █████╗  ██████╔╝██║   ██║██║  ██║███████║███████╗███████║"
echo "  ██╔═══╝    ██║   ██╔══╝  ██╔══██╗██║   ██║██║  ██║██╔══██║╚════██║██╔══██║"
echo "  ██║        ██║   ███████╗██║  ██║╚██████╔╝██████╔╝██║  ██║███████║██║  ██║"
echo "  ╚═╝        ╚═╝   ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝"
echo -e "${NC}"
echo -e "${CYAN}         Auto Setup Script — installs everything you need${NC}"
echo -e "${PURPLE}         ─────────────────────────────────────────────────${NC}"
echo ""

# ── Root check ──
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERR]${NC}   Please run as root:  sudo bash setup.sh"
  exit 1
fi

# ── OS check ──
if [ -f /etc/debian_version ]; then
  OS="debian"
elif [ -f /etc/redhat-release ]; then
  OS="redhat"
else
  warn "Unknown OS — assuming Debian/Ubuntu"
  OS="debian"
fi

success "System: $(uname -s) $(uname -m)"
echo ""

# ═══════════════════════════════════════════════════════════════
step "1 / 7 — System Update"
# ═══════════════════════════════════════════════════════════════
if [ "$OS" = "debian" ]; then
  apt-get update -qq && apt-get upgrade -y -qq
else
  yum update -y -q
fi
success "System updated"

# ═══════════════════════════════════════════════════════════════
step "2 / 7 — System Dependencies"
# ═══════════════════════════════════════════════════════════════
info "Installing curl, git, wget, python3, pip, build tools..."
if [ "$OS" = "debian" ]; then
  apt-get install -y -qq \
    curl wget git \
    python3 python3-pip python3-venv \
    build-essential \
    ca-certificates gnupg lsb-release \
    2>/dev/null
else
  yum install -y -q curl wget git python3 python3-pip gcc gcc-c++ make
fi
success "System dependencies installed"

# ═══════════════════════════════════════════════════════════════
step "3 / 7 — Node.js 22"
# ═══════════════════════════════════════════════════════════════
if command -v node &>/dev/null; then
  CURRENT_NODE=$(node --version)
  if [[ "$CURRENT_NODE" == v22* ]]; then
    success "Node.js $CURRENT_NODE already installed"
  else
    warn "Found $CURRENT_NODE — upgrading to Node.js 22..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - 2>/dev/null
    apt-get install -y -qq nodejs 2>/dev/null
    success "Node.js $(node --version) installed"
  fi
else
  info "Installing Node.js 22..."
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - 2>/dev/null
  if [ "$OS" = "debian" ]; then
    apt-get install -y -qq nodejs 2>/dev/null
  else
    yum install -y -q nodejs 2>/dev/null
  fi
  command -v node &>/dev/null || err "Node.js installation failed!"
  success "Node.js $(node --version) installed"
  success "npm $(npm --version) installed"
fi

# ═══════════════════════════════════════════════════════════════
step "4 / 7 — PM2"
# ═══════════════════════════════════════════════════════════════
if command -v pm2 &>/dev/null; then
  success "PM2 $(pm2 --version) already installed"
else
  info "Installing PM2 globally..."
  npm install -g pm2 2>/dev/null
  command -v pm2 &>/dev/null || err "PM2 installation failed!"
  success "PM2 $(pm2 --version) installed"
fi

info "Configuring PM2 auto-start on reboot..."
env PATH=$PATH:/usr/bin pm2 startup systemd -u root --hp /root 2>/dev/null | grep "^sudo" | bash 2>/dev/null
success "PM2 startup configured"

# ═══════════════════════════════════════════════════════════════
step "5 / 7 — Python & Flask Dependencies"
# ═══════════════════════════════════════════════════════════════
info "Upgrading pip..."
python3 -m pip install --upgrade pip -q 2>/dev/null
success "pip $(python3 -m pip --version | cut -d' ' -f2)"

info "Installing Flask, requests, gunicorn, python-dotenv..."
python3 -m pip install -q \
  flask \
  requests \
  gunicorn \
  python-dotenv \
  2>/dev/null
success "Python packages installed (flask, requests, gunicorn, python-dotenv)"

# ═══════════════════════════════════════════════════════════════
step "6 / 7 — Clone Repository & Organize Files"
# ═══════════════════════════════════════════════════════════════

INSTALL_DIR="/opt/pterodash"
REPO_URL="https://github.com/Said2008c/Dashbotcode.git"
REPO_BRANCH="templates"

# Remove old install
if [ -d "$INSTALL_DIR" ]; then
  warn "Old install found — removing $INSTALL_DIR ..."
  rm -rf "$INSTALL_DIR"
fi

info "Cloning from GitHub (branch: $REPO_BRANCH)..."
git clone --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"

[ -d "$INSTALL_DIR" ] || err "Git clone failed! Check internet connection."
success "Cloned to $INSTALL_DIR"

cd "$INSTALL_DIR" || err "Cannot enter $INSTALL_DIR"

# ── Create templates/ folder ──
mkdir -p templates
success "Created templates/"

# ── Move dashboard.html ──
if [ -f "dashboard.html" ]; then
  mv dashboard.html templates/dashboard.html
  success "Moved  dashboard.html  →  templates/dashboard.html"
else
  warn "dashboard.html not found in repo root — skipping"
fi

# ── Rename index2.html → index.html and move ──
if [ -f "index2.html" ]; then
  mv index2.html templates/index.html
  success "Renamed  index2.html  →  templates/index.html"
elif [ -f "index.html" ]; then
  mv index.html templates/index.html
  success "Moved  index.html  →  templates/index.html"
else
  warn "No index2.html or index.html found in repo root"
fi

# ── Verify app.py ──
[ -f "app.py" ] || err "app.py not found in repository!"
success "app.py found ✓"

# ── Show final structure ──
echo ""
info "Final file structure:"
echo -e "  ${CYAN}$INSTALL_DIR/${NC}"
echo -e "  ├── ${GREEN}app.py${NC}"
[ -f ".env" ] && echo -e "  ├── ${GREEN}.env${NC}"
echo -e "  └── ${GREEN}templates/${NC}"
[ -f "templates/dashboard.html" ] && echo -e "      ├── ${GREEN}dashboard.html${NC}"
[ -f "templates/index.html" ]     && echo -e "      └── ${GREEN}index.html${NC}"
echo ""

# ── Generate .env ──
if [ ! -f .env ]; then
  info "Generating .env file..."
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  cat > .env <<EOF
# ─────────────────────────────────────────
#   PteroDash — Environment Configuration
# ─────────────────────────────────────────

# Pterodactyl Panel
PANEL_URL=https://your-panel.com
PTERO_API_KEY=your-application-api-key

# Flask
FLASK_SECRET_KEY=${SECRET}
FLASK_HOST=0.0.0.0
FLASK_PORT=9001
FLASK_DEBUG=False
EOF
  success ".env created — ${YELLOW}EDIT IT with your panel details!${NC}"
fi

# ═══════════════════════════════════════════════════════════════
step "7 / 8 — Cloudflare Tunnel (cloudflared)"
# ═══════════════════════════════════════════════════════════════

echo ""
echo -e "${PURPLE}${BOLD}  Do you want to set up a Cloudflare Tunnel?${NC}"
echo -e "  ${CYAN}This exposes your dashboard publicly via a cloudflare.com URL.${NC}"
echo -e "  ${YELLOW}You need to create a tunnel token from: https://one.dash.cloudflare.com${NC}"
echo ""
echo -e "  ${BOLD}Steps to get your token:${NC}"
echo -e "  ${CYAN}1.${NC} Go to https://one.dash.cloudflare.com"
echo -e "  ${CYAN}2.${NC} Networks → Tunnels → Create a Tunnel"
echo -e "  ${CYAN}3.${NC} Choose 'Cloudflared' → name it anything"
echo -e "  ${CYAN}4.${NC} Copy the token shown in the install command"
echo ""
echo -ne "${YELLOW}  Setup Cloudflare Tunnel? [y/N]: ${NC}"
read -r CF_ANSWER

CF_TOKEN=""
CF_ENABLED=false

if [[ "$CF_ANSWER" =~ ^[Yy]$ ]]; then
  echo ""
  echo -ne "${CYAN}  Paste your Cloudflare Tunnel token: ${NC}"
  read -r CF_TOKEN

  if [ -z "$CF_TOKEN" ]; then
    warn "No token entered — skipping Cloudflare Tunnel setup"
  else
    # Install cloudflared
    info "Installing cloudflared..."

    if [ "$OS" = "debian" ]; then
      # Download latest cloudflared deb
      ARCH=$(dpkg --print-architecture)
      curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb" \
        -o /tmp/cloudflared.deb 2>/dev/null
      if [ -f /tmp/cloudflared.deb ]; then
        dpkg -i /tmp/cloudflared.deb 2>/dev/null
        rm /tmp/cloudflared.deb
      else
        # Fallback: direct binary download
        ARCH2=$(uname -m)
        [ "$ARCH2" = "x86_64" ] && CF_ARCH="amd64" || CF_ARCH="arm64"
        curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}" \
          -o /usr/local/bin/cloudflared 2>/dev/null
        chmod +x /usr/local/bin/cloudflared
      fi
    else
      # RPM fallback
      ARCH2=$(uname -m)
      [ "$ARCH2" = "x86_64" ] && CF_ARCH="amd64" || CF_ARCH="arm64"
      curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}" \
        -o /usr/local/bin/cloudflared 2>/dev/null
      chmod +x /usr/local/bin/cloudflared
    fi

    if command -v cloudflared &>/dev/null; then
      success "cloudflared $(cloudflared --version 2>/dev/null | head -1) installed"

      # Save token to .env
      echo "" >> "$INSTALL_DIR/.env"
      echo "# Cloudflare Tunnel" >> "$INSTALL_DIR/.env"
      echo "CF_TUNNEL_TOKEN=${CF_TOKEN}" >> "$INSTALL_DIR/.env"

      # Start tunnel via PM2
      info "Starting Cloudflare Tunnel via PM2..."
      pm2 delete pterodash-tunnel 2>/dev/null
      pm2 start cloudflared \
        --name "pterodash-tunnel" \
        --no-autorestart \
        -- tunnel --no-autoupdate run --token "$CF_TOKEN"

      sleep 3

      if pm2 list | grep -q "pterodash-tunnel"; then
        success "Cloudflare Tunnel running via PM2 ✓"
        pm2 save 2>/dev/null
        CF_ENABLED=true
      else
        warn "Tunnel may have failed — check:  pm2 logs pterodash-tunnel"
      fi
    else
      warn "cloudflared install failed — skipping tunnel setup"
    fi
  fi
else
  info "Skipping Cloudflare Tunnel setup"
fi

# ═══════════════════════════════════════════════════════════════
step "8 / 8 — systemd Service & Start"
# ═══════════════════════════════════════════════════════════════

GUNICORN_BIN="$(which gunicorn)"
[ -z "$GUNICORN_BIN" ] && err "gunicorn not found — pip install may have failed"

info "Writing /etc/systemd/system/pterodash.service..."

cat > /etc/systemd/system/pterodash.service <<EOF
[Unit]
Description=PteroDash — Pterodactyl Web Dashboard
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${GUNICORN_BIN} --workers 2 --bind 0.0.0.0:9001 --timeout 120 app:app
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pterodash
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable pterodash 2>/dev/null
success "Service created and enabled"

info "Starting pterodash..."
systemctl start pterodash
sleep 2

if systemctl is-active --quiet pterodash; then
  success "PteroDash is RUNNING! 🚀"
else
  warn "Service didn't start — likely because .env needs to be configured first."
  warn "Edit .env then run:  systemctl start pterodash"
fi

# ═══════════════════════════════════════════════════════════════
# ── DONE ──
# ═══════════════════════════════════════════════════════════════
SERVER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${PURPLE}${BOLD}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅  Setup Complete!${NC}"
echo -e "${PURPLE}${BOLD}════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BOLD}  Versions:${NC}"
echo -e "  ${GREEN}✓${NC} Node.js  $(node --version)"
echo -e "  ${GREEN}✓${NC} npm      v$(npm --version)"
echo -e "  ${GREEN}✓${NC} PM2      v$(pm2 --version)"
echo -e "  ${GREEN}✓${NC} Python3  $(python3 --version | cut -d' ' -f2)"
echo -e "  ${GREEN}✓${NC} pip      $(python3 -m pip --version | cut -d' ' -f2)"
echo -e "  ${GREEN}✓${NC} Gunicorn $(gunicorn --version 2>/dev/null)"
echo ""
echo -e "${BOLD}  ${YELLOW}⚠️  Required — edit your config:${NC}"
echo -e "  ${CYAN}nano ${INSTALL_DIR}/.env${NC}"
echo -e "  ${YELLOW}→ Set PANEL_URL and PTERO_API_KEY${NC}"
echo ""
echo -e "${BOLD}  Then restart:${NC}"
echo -e "  ${CYAN}systemctl restart pterodash${NC}"
echo ""
echo -e "${BOLD}  Dashboard URL:${NC}"
echo -e "  ${GREEN}➜  http://${SERVER_IP}:9001${NC}"
if [ "$CF_ENABLED" = true ]; then
  echo -e "  ${GREEN}➜  Cloudflare Tunnel is active — check your Cloudflare dashboard for the public URL${NC}"
  echo -e "  ${CYAN}pm2 logs pterodash-tunnel${NC}    — see tunnel logs & URL"
fi
echo ""
echo -e "${BOLD}  Commands:${NC}"
echo -e "  ${CYAN}systemctl status pterodash${NC}      check status"
echo -e "  ${CYAN}systemctl restart pterodash${NC}     restart"
echo -e "  ${CYAN}systemctl stop pterodash${NC}        stop"
echo -e "  ${CYAN}journalctl -u pterodash -f${NC}      live logs"
if [ "$CF_ENABLED" = true ]; then
echo -e "  ${CYAN}pm2 status${NC}                      PM2 processes"
echo -e "  ${CYAN}pm2 logs pterodash-tunnel${NC}       tunnel logs"
echo -e "  ${CYAN}pm2 restart pterodash-tunnel${NC}    restart tunnel"
fi
echo ""
echo -e "${PURPLE}${BOLD}════════════════════════════════════════════════${NC}"
echo ""

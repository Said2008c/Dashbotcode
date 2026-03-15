#!/bin/bash

# ═══════════════════════════════════════════════════════════════
#           ⚡ PteroDash — Auto Setup Script
# ═══════════════════════════════════════════════════════════════

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Helpers ──
info()    { echo -e "${CYAN}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[✓]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[✗]${NC}    $1"; }
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
echo -e "${PURPLE}         ─────────────────────────────────────────────────${NC}\n"

# ── Root check ──
if [ "$EUID" -ne 0 ]; then
  error "Please run as root: sudo bash setup.sh"
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

success "Running on: $(uname -s) $(uname -m)"
info "Starting setup...\n"

# ═══════════════════════════════════════════════════════════════
step "1 / 6 — System Update"
# ═══════════════════════════════════════════════════════════════
info "Updating package lists..."
if [ "$OS" = "debian" ]; then
  apt-get update -qq && apt-get upgrade -y -qq
else
  yum update -y -q
fi
success "System updated"

# ═══════════════════════════════════════════════════════════════
step "2 / 6 — Installing System Dependencies"
# ═══════════════════════════════════════════════════════════════
info "Installing curl, git, wget, build-essential, python3, pip..."
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
step "3 / 6 — Installing Node.js 22"
# ═══════════════════════════════════════════════════════════════

# Check if already installed
if command -v node &>/dev/null; then
  CURRENT_NODE=$(node --version)
  info "Node.js already installed: $CURRENT_NODE"
  # If not v22, reinstall
  if [[ "$CURRENT_NODE" != v22* ]]; then
    warn "Not v22 — reinstalling Node.js 22..."
    INSTALL_NODE=true
  else
    success "Node.js 22 already installed ✓"
    INSTALL_NODE=false
  fi
else
  INSTALL_NODE=true
fi

if [ "$INSTALL_NODE" = true ]; then
  info "Adding NodeSource repository for Node.js 22..."
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - 2>/dev/null
  if [ "$OS" = "debian" ]; then
    apt-get install -y -qq nodejs
  else
    yum install -y -q nodejs
  fi

  if command -v node &>/dev/null; then
    success "Node.js $(node --version) installed"
    success "npm $(npm --version) installed"
  else
    error "Node.js installation failed!"
    exit 1
  fi
fi

# ═══════════════════════════════════════════════════════════════
step "4 / 6 — Installing PM2"
# ═══════════════════════════════════════════════════════════════

if command -v pm2 &>/dev/null; then
  success "PM2 already installed: $(pm2 --version)"
else
  info "Installing PM2 globally..."
  npm install -g pm2 2>/dev/null
  if command -v pm2 &>/dev/null; then
    success "PM2 $(pm2 --version) installed"
  else
    error "PM2 installation failed!"
    exit 1
  fi
fi

# Setup PM2 to start on reboot
info "Configuring PM2 startup on boot..."
pm2 startup systemd -u root --hp /root 2>/dev/null | tail -1 | bash 2>/dev/null
success "PM2 startup configured"

# ═══════════════════════════════════════════════════════════════
step "5 / 6 — Installing Python Dependencies (Dashboard)"
# ═══════════════════════════════════════════════════════════════

# Upgrade pip first
info "Upgrading pip..."
python3 -m pip install --upgrade pip -q 2>/dev/null
success "pip upgraded to $(python3 -m pip --version | cut -d' ' -f2)"

# Install Flask dashboard dependencies
info "Installing Flask and dashboard requirements..."
python3 -m pip install -q \
  flask \
  requests \
  gunicorn \
  python-dotenv \
  2>/dev/null

success "Python packages installed:"
info "  • Flask"
info "  • requests"
info "  • gunicorn"
info "  • python-dotenv"

# ═══════════════════════════════════════════════════════════════
step "6 / 6 — Setting Up Dashboard Service (systemctl)"
# ═══════════════════════════════════════════════════════════════

# Detect dashboard path
DASH_PATH="$(pwd)/app.py"
if [ ! -f "$DASH_PATH" ]; then
  warn "app.py not found in current directory — service will point to $(pwd)/app.py"
  warn "Make sure you place app.py here before starting the service."
fi

WORKING_DIR="$(pwd)"
PYTHON_BIN="$(which python3)"
GUNICORN_BIN="$(which gunicorn)"

info "Creating systemd service at /etc/systemd/system/pterodash.service..."

cat > /etc/systemd/system/pterodash.service <<EOF
[Unit]
Description=PteroDash — Pterodactyl Web Dashboard
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${WORKING_DIR}
ExecStart=${GUNICORN_BIN} --workers 2 --bind 0.0.0.0:9001 --timeout 120 app:app
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pterodash
Environment=FLASK_ENV=production
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload
systemctl enable pterodash 2>/dev/null

success "systemd service created: pterodash.service"
success "Service set to auto-start on boot"

# ── Create .env template if not exists ──
if [ ! -f .env ]; then
  info "Creating .env template..."
  cat > .env <<EOF
# ─── Pterodactyl Settings ───
PANEL_URL=https://your-panel.com
PTERO_API_KEY=your-application-api-key

# ─── Flask Settings ───
FLASK_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
FLASK_HOST=0.0.0.0
FLASK_PORT=9001
FLASK_DEBUG=False
EOF
  success ".env file created — EDIT IT before starting!"
fi

# ── Summary ──
echo ""
echo -e "${PURPLE}${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅  Setup Complete!${NC}"
echo -e "${PURPLE}${BOLD}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BOLD}  Installed:${NC}"
echo -e "  ${GREEN}✓${NC} Node.js  $(node --version)"
echo -e "  ${GREEN}✓${NC} npm      $(npm --version)"
echo -e "  ${GREEN}✓${NC} PM2      $(pm2 --version)"
echo -e "  ${GREEN}✓${NC} Python3  $(python3 --version)"
echo -e "  ${GREEN}✓${NC} pip      $(python3 -m pip --version | cut -d' ' -f2)"
echo -e "  ${GREEN}✓${NC} Flask    $(python3 -m flask --version 2>/dev/null | head -1)"
echo -e "  ${GREEN}✓${NC} Gunicorn $(gunicorn --version 2>/dev/null)"
echo ""
echo -e "${BOLD}  Next steps:${NC}"
echo -e "  ${YELLOW}1.${NC} Edit ${CYAN}.env${NC} with your Pterodactyl panel URL & API key"
echo -e "  ${YELLOW}2.${NC} Place your files: ${CYAN}app.py${NC}, ${CYAN}templates/${NC} in ${CYAN}$(pwd)${NC}"
echo -e "  ${YELLOW}3.${NC} Start the dashboard:"
echo ""
echo -e "     ${PURPLE}# Using systemctl (recommended):${NC}"
echo -e "     ${CYAN}systemctl start pterodash${NC}"
echo -e "     ${CYAN}systemctl status pterodash${NC}"
echo ""
echo -e "     ${PURPLE}# Using PM2:${NC}"
echo -e "     ${CYAN}pm2 start app.py --name pterodash --interpreter python3${NC}"
echo -e "     ${CYAN}pm2 save${NC}"
echo ""
echo -e "     ${PURPLE}# Quick test (no service):${NC}"
echo -e "     ${CYAN}python3 app.py${NC}"
echo ""
echo -e "  ${YELLOW}4.${NC} Access dashboard at: ${CYAN}http://YOUR_IP:9001${NC}"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo -e "  ${CYAN}systemctl status pterodash${NC}   — check status"
echo -e "  ${CYAN}systemctl restart pterodash${NC}  — restart"
echo -e "  ${CYAN}journalctl -u pterodash -f${NC}   — live logs"
echo -e "  ${CYAN}pm2 logs pterodash${NC}           — PM2 logs"
echo ""
echo -e "${PURPLE}${BOLD}═══════════════════════════════════════════════════════${NC}\n"

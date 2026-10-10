
################################################################################
# DEPLOY NOW - Complete AI Suite Package Creator
# Creates deployable package with all files
################################################################################

set -e

PACKAGE_NAME="ai-self-hosting-suite"
PACKAGE_VERSION="1.0.0"
BUILD_DIR="./build"
PACKAGE_DIR="$BUILD_DIR/$PACKAGE_NAME-$PACKAGE_VERSION"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Creating Deployment Package for AI Suite                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Clean previous builds
rm -rf "$BUILD_DIR"
mkdir -p "$PACKAGE_DIR"/{bin,config,modules,docs,scripts}

echo "✓ Build directory created"

################################################################################
# Copy AI Paging Manager
################################################################################

echo "▶ Packaging AI Paging Manager..."
cp ai_paging_manager.py "$PACKAGE_DIR/bin/"
chmod +x "$PACKAGE_DIR/bin/ai_paging_manager.py"
echo "✓ AI Paging Manager packaged"

################################################################################
# Copy Life First AI Modules
################################################################################

echo "▶ Packaging Life First AI..."
mkdir -p "$PACKAGE_DIR/modules/lifefirst"

# Copy all Life First modules
for module in module_*.{sql,php} lifefirst_setup.sh deploy_modules.sh; do
    if [ -f "$module" ]; then
        cp "$module" "$PACKAGE_DIR/modules/lifefirst/"
    fi
done

# Copy additional modules
for module in budget_keeper.php secure_settings.php; do
    if [ -f "$module" ]; then
        cp "$module" "$PACKAGE_DIR/modules/lifefirst/"
    fi
done

echo "✓ Life First AI packaged"

################################################################################
# Copy Documentation
################################################################################

echo "▶ Packaging documentation..."
for doc in README.md START_HERE.md INSTALLATION_GUIDE.md DEPLOYMENT_CHECKLIST.md; do
    if [ -f "$doc" ]; then
        cp "$doc" "$PACKAGE_DIR/docs/"
    fi
done
echo "✓ Documentation packaged"

################################################################################
# Create Master Installer
################################################################################

echo "▶ Creating master installer..."
cat > "$PACKAGE_DIR/install.sh" << 'INSTALLER_EOF'
#!/bin/bash
# AI Self-Hosting Suite - One-Command Installer
# Usage: sudo ./install.sh

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          AI SELF-HOSTING SUITE INSTALLER                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 
   exit 1
fi

INSTALL_DIR="/opt/ai-suite"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Create directories
echo "Creating directories..."
mkdir -p "$INSTALL_DIR"/{bin,config,modules,logs}
mkdir -p /var/ai-swap
mkdir -p /var/log/ai-suite

# Install system dependencies
echo "Installing dependencies..."
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv apache2 mysql-server php php-mysql curl

# Install Python packages
echo "Setting up Python environment..."
python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"
pip install --quiet psutil
deactivate

# Copy files
echo "Installing AI Paging Manager..."
cp "$SCRIPT_DIR/bin/ai_paging_manager.py" "$INSTALL_DIR/bin/"
chmod +x "$INSTALL_DIR/bin/ai_paging_manager.py"

# Create systemd service
cat > /etc/systemd/system/ai-paging-manager.service << EOF
[Unit]
Description=AI Paging Manager
After=network.target

[Service]
Type=simple
User=root
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/bin/ai_paging_manager.py
Restart=on-failure
StandardOutput=append:/var/log/ai-suite/paging.log
StandardError=append:/var/log/ai-suite/paging-error.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

# Install Life First AI
if [ -d "$SCRIPT_DIR/modules/lifefirst" ]; then
    echo "Installing Life First AI..."
    mkdir -p /var/www/html/lifefirst
    cp -r "$SCRIPT_DIR/modules/lifefirst/"* /var/www/html/lifefirst/
    chown -R www-data:www-data /var/www/html/lifefirst
fi

# Create health check
cat > "$INSTALL_DIR/bin/health-check.sh" << 'HEALTH_EOF'
#!/bin/bash
echo "AI Suite Health Check"
echo "===================="
systemctl is-active --quiet ai-paging-manager && echo "✓ Paging Manager: Running" || echo "✗ Paging Manager: Stopped"
systemctl is-active --quiet apache2 && echo "✓ Apache: Running" || echo "✗ Apache: Stopped"
systemctl is-active --quiet mysql && echo "✓ MySQL: Running" || echo "✗ MySQL: Stopped"
free -h | grep Mem
df -h / | grep -v Filesystem
HEALTH_EOF

chmod +x "$INSTALL_DIR/bin/health-check.sh"
ln -sf "$INSTALL_DIR/bin/health-check.sh" /usr/local/bin/ai-health

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║            INSTALLATION COMPLETE!                            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Next steps:"
echo "1. Start paging manager: sudo systemctl start ai-paging-manager"
echo "2. Check health: ai-health"
echo "3. View logs: sudo journalctl -u ai-paging-manager -f"
echo ""
echo "For Life First AI setup, run:"
echo "cd /var/www/html/lifefirst && sudo ./lifefirst_setup.sh"
echo ""
INSTALLER_EOF

chmod +x "$PACKAGE_DIR/install.sh"
echo "✓ Master installer created"

################################################################################
# Create Quick Start Guide
################################################################################

cat > "$PACKAGE_DIR/QUICKSTART.md" << 'QUICKSTART_EOF'
# 🚀 QUICK START GUIDE

## Installation (One Command)

```bash
sudo ./install.sh
```

## Verify Installation

```bash
ai-health
```

## Start Services

```bash
# Start AI Paging Manager
sudo systemctl start ai-paging-manager
sudo systemctl enable ai-paging-manager

# Watch it work
sudo journalctl -u ai-paging-manager -f
```

## Access Life First AI

```
http://YOUR_SERVER_IP/lifefirst/
```

## Complete Setup

```bash
cd /var/www/html/lifefirst
sudo ./lifefirst_setup.sh
sudo ./deploy_modules.sh
```

## Demo Commands

```bash
# System health
ai-health

# Watch paging manager
sudo journalctl -u ai-paging-manager -f

# Check swap usage
swapon --show

# System load
htop
```

## Support

Check logs: `/var/log/ai-suite/`
Documentation: `./docs/`
QUICKSTART_EOF

echo "✓ Quick start guide created"

################################################################################
# Create README for package
################################################################################

cat > "$PACKAGE_DIR/README.md" << 'README_EOF'
# AI Self-Hosting Suite

Complete AI infrastructure for self-hosting on Ubuntu Server.

## What's Included

- **AI Paging Manager**: Revolutionary memory management with self-replicating doppelgangers
- **Life First AI**: Complete application suite (budget, security, messaging)
- **Full Stack**: Apache, MySQL, PHP, Python environment
- **Monitoring**: Health checks and logging

## Installation

```bash
sudo ./install.sh
```

## Components

### AI Paging Manager
- Dynamic swap space management
- Self-replicating under load
- Automatic load balancing
- Optimized for AI workloads

### Life First AI
- Budget tracking (5 accountability levels)
- Fort Knox security (GPS + Bluetooth + WiFi)
- Cross-phone messaging
- Bill reminders
- AI-powered insights

## Requirements

- Ubuntu Server 24.04 LTS
- 16GB RAM (minimum 8GB)
- 100GB disk space
- Root access

## Documentation

See `docs/` directory for complete documentation.

## Support

- GitHub: [your-repo]
- Email: [your-email]
- Docs: `./docs/INSTALLATION_GUIDE.md`
README_EOF

echo "✓ Package README created"

################################################################################
# Create deployment configuration
################################################################################

cat > "$PACKAGE_DIR/config/deployment.conf" << 'CONFIG_EOF'
# AI Suite Deployment Configuration

# Installation paths
INSTALL_DIR=/opt/ai-suite
SWAP_DIR=/var/ai-swap
LOG_DIR=/var/log/ai-suite
WEB_DIR=/var/www/html/lifefirst

# AI Paging Manager
PAGING_ENABLED=true
MAX_DOPPELGANGERS=8
DOPPELGANGER_LIFESPAN_MINUTES=30
CLONE_THRESHOLD=0.7
KILL_THRESHOLD=0.3

# Life First AI
LIFEFIRST_ENABLED=true
MYSQL_ROOT_PASSWORD=LifeFirst2024!
DB_NAME=lifefirst
DB_USER=lifefirst_user
DB_PASSWORD=LifeFirst_DB_2024!

# Security
API_SECRET=change_this_secret_key_in_production
CONFIG_EOF

echo "✓ Configuration file created"

################################################################################
# Create tarball
################################################################################

echo "▶ Creating tarball..."
cd "$BUILD_DIR"
tar -czf "$PACKAGE_NAME-$PACKAGE_VERSION.tar.gz" "$PACKAGE_NAME-$PACKAGE_VERSION"
cd ..

FILE_SIZE=$(du -h "$BUILD_DIR/$PACKAGE_NAME-$PACKAGE_VERSION.tar.gz" | cut -f1)

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           PACKAGE CREATED SUCCESSFULLY!                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Package: $BUILD_DIR/$PACKAGE_NAME-$PACKAGE_VERSION.tar.gz"
echo "Size: $FILE_SIZE"
echo ""
echo "To deploy:"
echo "1. Upload tarball to your server"
echo "2. Extract: tar -xzf $PACKAGE_NAME-$PACKAGE_VERSION.tar.gz"
echo "3. Install: cd $PACKAGE_NAME-$PACKAGE_VERSION && sudo ./install.sh"
echo ""
echo "For beta testers, provide:"
echo "wget YOUR_URL/$PACKAGE_NAME-$PACKAGE_VERSION.tar.gz"
echo "tar -xzf $PACKAGE_NAME-$PACKAGE_VERSION.tar.gz"
echo "cd $PACKAGE_NAME-$PACKAGE_VERSION"
echo "sudo ./install.sh"
echo ""
echo "Contents:"
ls -lh "$PACKAGE_DIR"
echo ""
echo "✓ Ready for deployment!"

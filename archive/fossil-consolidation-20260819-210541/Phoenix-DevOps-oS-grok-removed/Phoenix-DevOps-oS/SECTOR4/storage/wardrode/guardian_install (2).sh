#!/bin/bash
# Guardian Installation Script
# Installs guardian security and conflict detection system

set -e

echo "🛡️  Guardian Installation Script"
echo "================================"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Please run as root (sudo)"
    exit 1
fi

# Configuration
INSTALL_DIR="/opt/guardian"
CONFIG_DIR="/etc/guardian"
SYSTEMD_DIR="/etc/systemd/system"
LOG_DIR="/var/log/guardian"
BIN_DIR="/usr/local/bin"

echo ""
echo "📂 Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"
chmod 755 "$INSTALL_DIR"
chmod 755 "$CONFIG_DIR"
chmod 755 "$LOG_DIR"

echo "✓ Directories created"

# Copy guardian files (assumes guardian.py is in current directory)
echo ""
echo "📦 Installing guardian files..."

if [ -f "guardian.py" ]; then
    cp guardian.py "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/guardian.py"
    echo "✓ guardian.py installed"
else
    echo "⚠️  guardian.py not found in current directory"
    echo "   Place guardian.py here and run again"
fi

# Create symlink for easy access
ln -sf "$INSTALL_DIR/guardian.py" "$BIN_DIR/guardian"
echo "✓ Created symlink: guardian command available"

# Create guardian.json config
echo ""
echo "⚙️  Creating configuration..."

cat > "$CONFIG_DIR/guardian.json" << 'EOF'
{
  "guardian_name": "port_config_guardian",
  "version": "1.0.0",
  "agent_id": "guardian_001",
  "role": "SecurityMonitor",
  "permissions": "read_write_modify",
  "scan_paths": [
    "/etc",
    "/opt",
    "/home",
    "/usr/local/etc"
  ],
  "port_range": {
    "min": 1,
    "max": 65535
  },
  "config_patterns": [
    "*.conf",
    "*.config",
    "*.json",
    "*.yaml",
    "*.yml",
    "*.toml",
    "*.ini"
  ],
  "exclude_paths": [
    "/etc/ssl",
    "/etc/security",
    "/etc/shadow"
  ],
  "monitoring": {
    "scan_interval": 300,
    "alert_on_conflict": true,
    "auto_resolve": false,
    "log_all_scans": true
  },
  "integrations": {
    "anglyene": true,
    "helix": true,
    "report_to": [
      "/var/log/guardian/conflicts.log",
      "/tmp/guardian_status.json"
    ]
  },
  "checksum": {
    "algorithm": "sha256",
    "config_hash": "",
    "auto_verify": true
  }
}
EOF

echo "✓ Configuration created: $CONFIG_DIR/guardian.json"

# Create systemd service file
echo ""
echo "🔧 Creating systemd service..."

cat > "$SYSTEMD_DIR/guardian.service" << EOF
[Unit]
Description=Guardian Security and Conflict Detection System
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/guardian.py --daemon --config $CONFIG_DIR/guardian.json
Restart=on-failure
RestartSec=10
StandardOutput=append:$LOG_DIR/guardian.log
StandardError=append:$LOG_DIR/guardian-error.log

# Security settings
NoNewPrivileges=false
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

echo "✓ Systemd service created"

# Create guardian control script
echo ""
echo "🎮 Creating control script..."

cat > "$BIN_DIR/guardian-ctl" << 'CTLEOF'
#!/bin/bash
# Guardian Control Script

GUARDIAN_SERVICE="guardian.service"
GUARDIAN_CONFIG="/etc/guardian/guardian.json"
GUARDIAN_LOG="/var/log/guardian/guardian.log"
CONFLICT_LOG="/var/log/guardian/conflicts.log"

case "$1" in
    start)
        echo "Starting Guardian..."
        systemctl start $GUARDIAN_SERVICE
        systemctl status $GUARDIAN_SERVICE --no-pager
        ;;
    stop)
        echo "Stopping Guardian..."
        systemctl stop $GUARDIAN_SERVICE
        ;;
    restart)
        echo "Restarting Guardian..."
        systemctl restart $GUARDIAN_SERVICE
        ;;
    status)
        systemctl status $GUARDIAN_SERVICE --no-pager
        ;;
    enable)
        echo "Enabling Guardian to start on boot..."
        systemctl enable $GUARDIAN_SERVICE
        ;;
    disable)
        echo "Disabling Guardian..."
        systemctl disable $GUARDIAN_SERVICE
        ;;
    scan)
        echo "Running manual scan..."
        guardian --scan
        ;;
    conflicts)
        echo "Recent conflicts:"
        if [ -f "$CONFLICT_LOG" ]; then
            tail -n 50 "$CONFLICT_LOG"
        else
            echo "No conflicts logged yet"
        fi
        ;;
    logs)
        echo "Guardian logs:"
        tail -f "$GUARDIAN_LOG"
        ;;
    config)
        nano "$GUARDIAN_CONFIG"
        ;;
    *)
        echo "Guardian Control Script"
        echo ""
        echo "Usage: guardian-ctl {start|stop|restart|status|enable|disable|scan|conflicts|logs|config}"
        echo ""
        echo "Commands:"
        echo "  start      - Start guardian service"
        echo "  stop       - Stop guardian service"
        echo "  restart    - Restart guardian service"
        echo "  status     - Check guardian status"
        echo "  enable     - Enable autostart on boot"
        echo "  disable    - Disable autostart"
        echo "  scan       - Run manual port/config scan"
        echo "  conflicts  - Show recent conflicts"
        echo "  logs       - View live logs"
        echo "  config     - Edit configuration"
        exit 1
        ;;
esac
CTLEOF

chmod +x "$BIN_DIR/guardian-ctl"
echo "✓ Control script created: guardian-ctl"

# Install Python dependencies
echo ""
echo "📚 Installing Python dependencies..."

pip3 install psutil PyYAML toml >/dev/null 2>&1 || {
    echo "⚠️  Installing dependencies..."
    apt-get update -qq && apt-get install -y python3-pip >/dev/null 2>&1
    pip3 install psutil PyYAML toml
}

echo "✓ Dependencies installed"

# Reload systemd
echo ""
echo "🔄 Reloading systemd..."
systemctl daemon-reload
echo "✓ Systemd reloaded"

# Calculate and store config checksum
echo ""
echo "🔒 Generating config checksum..."
CHECKSUM=$(sha256sum "$CONFIG_DIR/guardian.json" | awk '{print $1}')
# Update the config with its own checksum
sed -i "s/\"config_hash\": \"\"/\"config_hash\": \"$CHECKSUM\"/" "$CONFIG_DIR/guardian.json"
echo "✓ Checksum: ${CHECKSUM:0:16}..."

# Final summary
echo ""
echo "================================"
echo "✅ Guardian Installation Complete!"
echo "================================"
echo ""
echo "📍 Installation paths:"
echo "   Program: $INSTALL_DIR/guardian.py"
echo "   Config:  $CONFIG_DIR/guardian.json"
echo "   Logs:    $LOG_DIR/"
echo "   Service: $SYSTEMD_DIR/guardian.service"
echo ""
echo "🎮 Quick commands:"
echo "   guardian-ctl start    - Start guardian"
echo "   guardian-ctl status   - Check status"
echo "   guardian-ctl scan     - Run manual scan"
echo "   guardian-ctl conflicts - View conflicts"
echo "   guardian-ctl logs     - View live logs"
echo ""
echo "🚀 Next steps:"
echo "   1. Review config: nano $CONFIG_DIR/guardian.json"
echo "   2. Start service: guardian-ctl start"
echo "   3. Enable autostart: guardian-ctl enable"
echo ""
echo "💡 Guardian will monitor ports and configs to prevent conflicts"
echo "   before they cause problems for helix, anglyene, or other software."
echo ""
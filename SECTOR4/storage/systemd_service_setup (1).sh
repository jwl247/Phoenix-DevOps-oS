#!/bin/bash
################################################################################
# Integrated Guardian Systemd Service Setup
# Deploys Port Guardian + Installer Guardian as a system service
################################################################################

echo "🛡️  Setting up Integrated Guardian as systemd service..."
echo ""

# Configuration
INSTALL_DIR="/opt/integrated_guardian"
SERVICE_NAME="integrated_guardian"
PYTHON_BIN="/usr/bin/python3"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Please run as root (sudo)"
    exit 1
fi

################################################################################
# STEP 1: Create Installation Directory
################################################################################
echo "📁 Creating installation directory..."
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# Check if integrated_guardian.py exists
if [ ! -f "$INSTALL_DIR/integrated_guardian.py" ]; then
    echo "❌ integrated_guardian.py not found in $INSTALL_DIR"
    echo "   Please place integrated_guardian.py in $INSTALL_DIR first"
    exit 1
fi

chmod +x integrated_guardian.py
echo "✅ Installation directory ready"
echo ""

################################################################################
# STEP 2: Create Systemd Service File
################################################################################
echo "📝 Creating systemd service file..."

cat > /etc/systemd/system/${SERVICE_NAME}.service << 'EOFSERVICE'
[Unit]
Description=Integrated Guardian (Port Guardian + Installer Guardian)
Documentation=https://github.com/yourrepo/integrated-guardian
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/integrated_guardian

# Main service - runs in BCM mode (monitoring)
ExecStart=/usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py daemon

# Send heartbeat every 20 seconds to keep failsafe happy
ExecStartPost=/bin/bash -c 'while true; do sleep 20; /usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py heartbeat; done &'

# Graceful shutdown
ExecStop=/usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py shutdown
TimeoutStopSec=30

# Restart policy
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=false
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/integrated_guardian
ReadWritePaths=/var/log/integrated_guardian

# Resource limits
LimitNOFILE=65535
CPUQuota=50%
MemoryMax=512M

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=integrated-guardian

[Install]
WantedBy=multi-user.target
EOFSERVICE

echo "✅ Systemd service file created"
echo ""

################################################################################
# STEP 3: Create Daemon Mode in integrated_guardian.py
################################################################################
echo "🔧 Adding daemon mode to integrated_guardian.py..."

# Check if daemon mode already exists
if ! grep -q "elif cmd == 'daemon':" integrated_guardian.py; then
    # Add daemon mode before the final else
    sed -i "/else:$/i\\
\\        elif cmd == 'daemon':\\
            print(f\"🛡️  [{guardian.instance_id}] Starting in daemon mode...\")\\
            print(f\"   BCM Mode: {guardian.config.get('bcm_mode', False)}\")\\
            print(f\"   Autonomous: {guardian.config.get('autonomous_mode', True)}\")\\
            print(f\"   Press Ctrl+C to stop\")\\
            \\
            import time\\
            try:\\
                while True:\\
                    # Auto-scan for new configs every 5 minutes\\
                    guardian.installer.auto_scan()\\
                    \\
                    # Check for conflicts\\
                    conflicts = guardian.installer.resolve_conflicts()\\
                    if conflicts:\\
                        print(f\"⚠️  {len(conflicts)} conflicts detected\")\\
                    \\
                    # Send heartbeat\\
                    guardian.system_heartbeat()\\
                    \\
                    # Sleep\\
                    time.sleep(300)  # 5 minutes\\
            except KeyboardInterrupt:\\
                print(f\"\\n👋 [{guardian.instance_id}] Shutting down gracefully...\")\\
                guardian.save_config()\\
        \\
        elif cmd == 'shutdown':\\
            print(f\"👋 [{guardian.instance_id}] Shutdown signal received\")\\
            guardian.save_config()\\
            guardian.installer.save_registry()\\
            print(f\"✅ Shutdown complete\")\\
\\
" integrated_guardian.py
    
    echo "✅ Daemon mode added"
else
    echo "✅ Daemon mode already exists"
fi

echo ""

################################################################################
# STEP 4: Create Log Directory
################################################################################
echo "📋 Creating log directory..."
mkdir -p /var/log/integrated_guardian
chown root:root /var/log/integrated_guardian
chmod 755 /var/log/integrated_guardian
echo "✅ Log directory ready"
echo ""

################################################################################
# STEP 5: Create Helper Scripts
################################################################################
echo "🔧 Creating helper scripts..."

# Status script
cat > /usr/local/bin/guardian-status << 'EOFSTATUS'
#!/bin/bash
echo "🛡️  Integrated Guardian Status"
echo "═══════════════════════════════════════════════════════════"
systemctl status integrated_guardian.service --no-pager
echo ""
echo "📊 Guardian Details:"
/usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py status
EOFSTATUS
chmod +x /usr/local/bin/guardian-status

# Threats script
cat > /usr/local/bin/guardian-threats << 'EOFTHREATS'
#!/bin/bash
echo "⚠️  Current Threats"
echo "═══════════════════════════════════════════════════════════"
/usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py threats
EOFTHREATS
chmod +x /usr/local/bin/guardian-threats

# Violations script
cat > /usr/local/bin/guardian-violations << 'EOFVIOLS'
#!/bin/bash
echo "🚨 Recent Violations"
echo "═══════════════════════════════════════════════════════════"
/usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py violations
EOFVIOLS
chmod +x /usr/local/bin/guardian-violations

# Installer conflicts script
cat > /usr/local/bin/guardian-conflicts << 'EOFCONFLICTS'
#!/bin/bash
echo "💕 Installer Guardian - Config Conflicts"
echo "═══════════════════════════════════════════════════════════"
/usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py installer conflicts
EOFCONFLICTS
chmod +x /usr/local/bin/guardian-conflicts

# Ports script
cat > /usr/local/bin/guardian-ports << 'EOFPORTS'
#!/bin/bash
echo "🔌 Registered Ports"
echo "═══════════════════════════════════════════════════════════"
/usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py installer ports
EOFPORTS
chmod +x /usr/local/bin/guardian-ports

# Quick control script
cat > /usr/local/bin/guardian << 'EOFGUARDIAN'
#!/bin/bash
case "$1" in
    start)
        sudo systemctl start integrated_guardian.service
        ;;
    stop)
        sudo systemctl stop integrated_guardian.service
        ;;
    restart)
        sudo systemctl restart integrated_guardian.service
        ;;
    status)
        guardian-status
        ;;
    threats)
        guardian-threats
        ;;
    violations)
        guardian-violations
        ;;
    conflicts)
        guardian-conflicts
        ;;
    ports)
        guardian-ports
        ;;
    logs)
        sudo journalctl -u integrated_guardian.service -f
        ;;
    bcm)
        if [ "$2" == "on" ]; then
            /usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py bcm on
        elif [ "$2" == "off" ]; then
            /usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py bcm off
        else
            /usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py bcm
        fi
        ;;
    lockdown)
        /usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py lockdown
        ;;
    unlock)
        /usr/bin/python3 /opt/integrated_guardian/integrated_guardian.py unlock
        ;;
    *)
        echo "🛡️  Integrated Guardian Control"
        echo ""
        echo "Usage: guardian <command>"
        echo ""
        echo "Service Control:"
        echo "  start              - Start guardian service"
        echo "  stop               - Stop guardian service"
        echo "  restart            - Restart guardian service"
        echo "  status             - Show full status"
        echo "  logs               - Follow live logs"
        echo ""
        echo "Security:"
        echo "  threats            - Show current threats"
        echo "  violations         - Show recent violations"
        echo "  lockdown           - Enable lockdown mode"
        echo "  unlock             - Disable lockdown"
        echo "  bcm [on|off]       - BCM mode (monitor only)"
        echo ""
        echo "Installer:"
        echo "  conflicts          - Show config conflicts"
        echo "  ports              - Show registered ports"
        echo ""
        echo "Examples:"
        echo "  guardian start"
        echo "  guardian status"
        echo "  guardian threats"
        echo "  guardian bcm on"
        ;;
esac
EOFGUARDIAN
chmod +x /usr/local/bin/guardian

echo "✅ Helper scripts created:"
echo "   - guardian (main control)"
echo "   - guardian-status"
echo "   - guardian-threats"
echo "   - guardian-violations"
echo "   - guardian-conflicts"
echo "   - guardian-ports"
echo ""

################################################################################
# STEP 6: Enable and Start Service
################################################################################
echo "🚀 Enabling and starting service..."
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}.service

# Ask if user wants to start now
read -p "Start service now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl start ${SERVICE_NAME}.service
    sleep 2
    echo ""
    systemctl status ${SERVICE_NAME}.service --no-pager
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ INTEGRATED GUARDIAN INSTALLED!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📋 Service Details:"
echo "   Name: ${SERVICE_NAME}.service"
echo "   Install Dir: $INSTALL_DIR"
echo "   Logs: /var/log/integrated_guardian"
echo ""
echo "🎮 Quick Commands:"
echo "   guardian start       - Start service"
echo "   guardian stop        - Stop service"
echo "   guardian status      - Full status"
echo "   guardian threats     - Show threats"
echo "   guardian conflicts   - Check configs"
echo "   guardian logs        - Live logs"
echo ""
echo "🔍 Systemctl Commands:"
echo "   systemctl status integrated_guardian.service"
echo "   systemctl restart integrated_guardian.service"
echo "   journalctl -u integrated_guardian.service -f"
echo ""
echo "💡 Next Steps:"
echo "   1. Check status: guardian status"
echo "   2. Enable BCM mode: guardian bcm on"
echo "   3. Scan configs: python3 $INSTALL_DIR/integrated_guardian.py installer scan"
echo "   4. Make services friends: python3 $INSTALL_DIR/integrated_guardian.py installer friends Helix LifeFirst"
echo ""

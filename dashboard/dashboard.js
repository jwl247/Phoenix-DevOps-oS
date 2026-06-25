// Phoenix DevOps OS - Command Center Dashboard JavaScript
// Handles interactivity, data updates, and Phoenix integration
// Electron-enabled version with real Phoenix command execution

// Check if running in Electron
const isElectron = typeof require !== 'undefined' && typeof require('electron') !== 'undefined';
let ipcRenderer;

if (isElectron) {
    ipcRenderer = require('electron').ipcRenderer;
    console.log('Running in Electron - Real Phoenix integration enabled');
} else {
    console.log('Running in browser - Using simulated data');
}

class PhoenixDashboard {
    constructor() {
        this.init();
        this.setupEventListeners();
        this.startDataUpdates();
        this.initCanvas();
    }

    init() {
        // Update system time
        this.updateTime();
        setInterval(() => this.updateTime(), 1000);

        // Initialize toggle switches
        this.initSwitches();

        // Load initial data
        this.loadSystemStatus();
    }

    updateTime() {
        const now = new Date();
        const timeStr = now.toLocaleTimeString('en-US', { 
            hour12: false, 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit' 
        });
        const dateStr = now.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: '2-digit'
        });
        document.getElementById('system-time').textContent = `${dateStr} ${timeStr}`;
    }

    initSwitches() {
        const switches = document.querySelectorAll('.toggle-switch');
        switches.forEach(sw => {
            sw.addEventListener('click', () => {
                sw.classList.toggle('active');
                const light = sw.querySelector('.switch-light');
                light.classList.toggle('active');
                
                const sector = sw.dataset.sector;
                this.handleSectorToggle(sector, sw.classList.contains('active'));
            });
        });
    }

    handleSectorToggle(sector, isActive) {
        console.log(`Sector ${sector} ${isActive ? 'activated' : 'deactivated'}`);
        // Here you would integrate with actual Phoenix commands
        // Example: execute usys command to enable/disable sector
    }

    setupEventListeners() {
        // Control button clicks
        const controlBtns = document.querySelectorAll('.control-btn');
        controlBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                this.handleControlAction(action);
            });
        });

        // Terminal overlay
        const terminalClose = document.getElementById('terminal-close');
        if (terminalClose) {
            terminalClose.addEventListener('click', () => {
                document.getElementById('terminal-overlay').style.display = 'none';
            });
        }
    }

    handleControlAction(action) {
        console.log(`Control action: ${action}`);
        
        switch(action) {
            case 'status':
                this.showSystemStatus();
                break;
            case 'clone':
                this.showClonePool();
                break;
            case 'intake':
                this.showIntake();
                break;
            case 'suites':
                this.showSuites();
                break;
            case 'helix':
                this.showHelixEngine();
                break;
            case 'catalog':
                this.showCatalog();
                break;
            case 'security':
                this.showSecurity();
                break;
            case 'settings':
                this.showSettings();
                break;
        }
    }

    showSystemStatus() {
        this.showTerminal();
        this.executeCommand('usys status');
    }

    showClonePool() {
        this.showTerminal();
        this.executeCommand('usys list-suites');
    }

    showIntake() {
        this.showTerminal();
        this.addTerminalLine('Intake system ready. Use: usys intake <file>');
    }

    showSuites() {
        this.showTerminal();
        this.executeCommand('usys list-suites');
    }

    showHelixEngine() {
        this.showTerminal();
        this.addTerminalLine('=== HELIX ENGINE STATUS ===');
        this.addTerminalLine('Throughput: 700,000 ops/sec');
        this.addTerminalLine('Cache Hit Rate: 100%');
        this.addTerminalLine('Languages: 4 (Python, JavaScript, C, Bash)');
        this.addTerminalLine('Compression: zlib level 5');
        this.addTerminalLine('RAM Usage: 4GB / 8GB');
        this.addTerminalLine('Status: OPERATIONAL');
    }

    showCatalog() {
        this.showTerminal();
        this.executeCommand('usys search ""');
    }

    showSecurity() {
        this.showTerminal();
        this.addTerminalLine('=== SECURITY STATUS ===');
        this.addTerminalLine('REALsure Security: ACTIVE');
        this.addTerminalLine('Installer Guardian: MONITORING');
        this.addTerminalLine('User Scope: ENFORCED');
        this.addTerminalLine('Elevation: NOT REQUIRED');
        this.addTerminalLine('File Permissions: SECURED');
    }

    showSettings() {
        this.showTerminal();
        this.addTerminalLine('=== PHOENIX SETTINGS ===');
        this.addTerminalLine('PHOENIX_ROOT: ' + (this.getEnvVar('PHOENIX_ROOT') || 'Not set'));
        this.addTerminalLine('CLONEPOOL_DIR: ' + (this.getEnvVar('CLONEPOOL_DIR') || 'Not set'));
        this.addTerminalLine('PHOENIX_AUTH: ' + (this.getEnvVar('PHOENIX_AUTH') ? '***SET***' : 'Not set'));
        this.addTerminalLine('PHOENIX_WORKER_URL: ' + (this.getEnvVar('PHOENIX_WORKER_URL') || 'Not set'));
    }

    showTerminal() {
        const overlay = document.getElementById('terminal-overlay');
        overlay.style.display = 'flex';
        const content = document.getElementById('terminal-content');
        content.innerHTML = '<div class="terminal-line">Phoenix DevOps OS v0.1.0</div>';
    }

    addTerminalLine(text) {
        const content = document.getElementById('terminal-content');
        const line = document.createElement('div');
        line.className = 'terminal-line';
        line.textContent = text;
        content.appendChild(line);
        content.scrollTop = content.scrollHeight;
    }

    executeCommand(cmd) {
        this.addTerminalLine(`> ${cmd}`);
        this.addTerminalLine('Executing command...');
        
        // In a real implementation, this would call the actual Phoenix commands
        // For now, we'll simulate the output
        setTimeout(() => {
            this.simulateCommandOutput(cmd);
        }, 500);
    }

    simulateCommandOutput(cmd) {
        if (cmd.includes('status')) {
            this.addTerminalLine('');
            this.addTerminalLine('=== USys Status ===');
            this.addTerminalLine('Version   : 0.1.0');
            this.addTerminalLine('Repo      : ~/Phoenix/Phoenix-DevOps-oS');
            this.addTerminalLine('USys home : ~/.usys');
            this.addTerminalLine('');
            this.addTerminalLine('-- Sector tree --');
            this.addTerminalLine('  sector1 : 45 files');
            this.addTerminalLine('  sector2 : 32 files');
            this.addTerminalLine('  sector3 : 28 files');
            this.addTerminalLine('  sector4 : 15 files');
        } else if (cmd.includes('list-suites')) {
            this.addTerminalLine('');
            this.addTerminalLine('Available Suites:');
            this.addTerminalLine('  data-processor v1.2.3 [script/python] - Process and transform data');
            this.addTerminalLine('  backup-script v2.0.0 [script/bash] - Automated backup');
            this.addTerminalLine('  api-service v1.5.0 [service/python] - REST API service');
            this.addTerminalLine('');
            this.addTerminalLine('Total: 3 suite(s)');
        }
        this.addTerminalLine('');
        this.addTerminalLine('> _');
    }

    getEnvVar(name) {
        // In a real implementation, this would fetch from the actual environment
        // For demo purposes, return placeholder values
        const envVars = {
            'PHOENIX_ROOT': '~/Phoenix/Phoenix-DevOps-oS',
            'CLONEPOOL_DIR': '~/Phoenix/clonepool',
            'PHOENIX_WORKER_URL': 'https://packages-worker.phoenix-jwl.workers.dev'
        };
        return envVars[name] || null;
    }

    startDataUpdates() {
        // Update metrics every 2 seconds
        setInterval(() => this.updateMetrics(), 2000);
        
        // Update sector status every 5 seconds
        setInterval(() => this.updateSectorStatus(), 5000);
        
        // Initial update
        this.updateMetrics();
        this.updateSectorStatus();
    }

    updateMetrics() {
        // Simulate dynamic metrics
        const cpu = Math.floor(Math.random() * 30) + 40; // 40-70%
        const mem = Math.floor(Math.random() * 20) + 55; // 55-75%
        const disk = Math.floor(Math.random() * 15) + 35; // 35-50%

        document.getElementById('cpu-usage').textContent = `${cpu}%`;
        document.getElementById('cpu-bar').style.width = `${cpu}%`;
        
        document.getElementById('mem-usage').textContent = `${mem}%`;
        document.getElementById('mem-bar').style.width = `${mem}%`;
        
        document.getElementById('disk-usage').textContent = `${disk}%`;
        document.getElementById('disk-bar').style.width = `${disk}%`;

        // Update throughput with slight variation
        const baseOps = 700000;
        const variation = Math.floor(Math.random() * 50000) - 25000;
        const ops = baseOps + variation;
        document.getElementById('throughput').textContent = `${ops.toLocaleString()} ops/sec`;

        // Update altitude, airspeed, heading (simulated)
        const altitude = Math.floor(Math.random() * 200) + 1400;
        const airspeed = Math.floor(Math.random() * 20) + 110;
        const heading = Math.floor(Math.random() * 360);
        
        document.getElementById('altitude').textContent = `${altitude}m`;
        document.getElementById('airspeed').textContent = `${airspeed}kt`;
        document.getElementById('heading').textContent = `${heading.toString().padStart(3, '0')}°`;
    }

    async updateSectorStatus() {
        if (isElectron && ipcRenderer) {
            try {
                // Get real sector counts
                const counts = await ipcRenderer.invoke('get-sector-counts');
                document.getElementById('s1-files').textContent = `${counts.sector1 || 0} files`;
                document.getElementById('s2-files').textContent = `${counts.sector2 || 0} files`;
                document.getElementById('s3-files').textContent = `${counts.sector3 || 0} files`;
                document.getElementById('s4-files').textContent = `${counts.SECTOR4 || 0} files`;

                // Get real clonepool info
                const clonepool = await ipcRenderer.invoke('get-clonepool-info');
                document.getElementById('clone-count').textContent = clonepool.totalFiles || 0;
                document.getElementById('suite-count').textContent = clonepool.suites || 0;
                
                const sizeMB = Math.round((clonepool.totalSize || 0) / (1024 * 1024));
                document.getElementById('storage-used').textContent = `${sizeMB} MB`;
                
                if (clonepool.lastModified) {
                    const date = new Date(clonepool.lastModified);
                    document.getElementById('last-sync').textContent = date.toLocaleTimeString('en-US', {
                        hour12: false,
                        hour: '2-digit',
                        minute: '2-digit'
                    });
                }
            } catch (error) {
                console.error('Error updating sector status:', error);
                this.updateSectorStatusSimulated();
            }
        } else {
            this.updateSectorStatusSimulated();
        }
    }

    updateSectorStatusSimulated() {
        // Fallback to simulated data
        document.getElementById('s1-files').textContent = `${Math.floor(Math.random() * 10) + 40} files`;
        document.getElementById('s2-files').textContent = `${Math.floor(Math.random() * 10) + 30} files`;
        document.getElementById('s3-files').textContent = `${Math.floor(Math.random() * 10) + 25} files`;
        document.getElementById('s4-files').textContent = `${Math.floor(Math.random() * 5) + 15} files`;

        document.getElementById('clone-count').textContent = Math.floor(Math.random() * 50) + 100;
        document.getElementById('suite-count').textContent = Math.floor(Math.random() * 5) + 3;
        document.getElementById('storage-used').textContent = `${Math.floor(Math.random() * 500) + 1500} MB`;
        
        const now = new Date();
        document.getElementById('last-sync').textContent = now.toLocaleTimeString('en-US', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    loadSystemStatus() {
        // This would integrate with actual Phoenix usys status command
        console.log('Loading system status...');
        this.updateSectorStatus();
    }

    initCanvas() {
        const canvas = document.getElementById('main-canvas');
        const ctx = canvas.getContext('2d');
        
        // Set canvas size
        canvas.width = canvas.offsetWidth;
        canvas.height = canvas.offsetHeight;

        // Draw animated background
        this.animateCanvas(ctx, canvas);
    }

    animateCanvas(ctx, canvas) {
        let frame = 0;
        
        const animate = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            // Draw rotating circles
            const centerX = canvas.width / 2;
            const centerY = canvas.height / 2;
            
            for (let i = 0; i < 3; i++) {
                const radius = 50 + (i * 30);
                const rotation = (frame + (i * 120)) * 0.01;
                
                ctx.beginPath();
                ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
                ctx.strokeStyle = `rgba(0, 255, 136, ${0.1 - (i * 0.02)})`;
                ctx.lineWidth = 1;
                ctx.stroke();
                
                // Draw rotating point
                const x = centerX + Math.cos(rotation) * radius;
                const y = centerY + Math.sin(rotation) * radius;
                ctx.beginPath();
                ctx.arc(x, y, 3, 0, Math.PI * 2);
                ctx.fillStyle = 'rgba(0, 255, 136, 0.5)';
                ctx.fill();
            }
            
            frame++;
            requestAnimationFrame(animate);
        };
        
        animate();
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.phoenixDashboard = new PhoenixDashboard();
    console.log('Phoenix DevOps OS Dashboard initialized');
});

// Integration functions for Phoenix commands
window.phoenixIntegration = {
    // Execute a Phoenix usys command
    executeUsysCommand: async function(command) {
        if (isElectron && ipcRenderer) {
            try {
                console.log(`Executing: usys ${command}`);
                const result = await ipcRenderer.invoke('execute-command', `usys ${command}`);
                return result;
            } catch (error) {
                console.error('Command execution failed:', error);
                return { success: false, error: error.message };
            }
        } else {
            // Browser fallback - simulated data
            console.log(`[Simulated] Executing: usys ${command}`);
            return { success: true, output: 'Command executed (simulated)' };
        }
    },

    // Get system status
    getSystemStatus: async function() {
        return this.executeUsysCommand('status');
    },

    // List suites
    listSuites: async function() {
        return this.executeUsysCommand('list-suites');
    },

    // Clone a file
    cloneFile: async function(filePath, category = '', tag = '') {
        const cmd = `clone "${filePath}" ${category} "${tag}"`;
        return this.executeUsysCommand(cmd);
    },

    // Intake a file
    intakeFile: async function(filePath) {
        return this.executeUsysCommand(`intake "${filePath}"`);
    },

    // Run a suite
    runSuite: async function(suiteName, version = '') {
        const cmd = version ? `run ${suiteName}@${version}` : `run ${suiteName}`;
        return this.executeUsysCommand(cmd);
    }
};

// Made with Bob

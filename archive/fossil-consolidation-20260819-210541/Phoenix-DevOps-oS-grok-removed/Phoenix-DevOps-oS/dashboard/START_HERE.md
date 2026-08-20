# 🚀 Phoenix Dashboard - START HERE

## The Fastest Way to Get Started

### Option 1: Super Quick Start (Recommended)

```powershell
# In the dashboard directory, run:
.\start.ps1
```

That's it! The script will:
- ✅ Check if Node.js is installed
- ✅ Install dependencies automatically
- ✅ Launch the dashboard

---

### Option 2: Manual Start

```bash
# Step 1: Install dependencies (first time only)
npm install

# Step 2: Run the dashboard
npm start
```

---

## What You'll See

When the dashboard launches, you'll get:

✨ **A native desktop application** that looks like this:
- Left panel with red toggle switches for sectors
- Center holographic display with Phoenix logo
- Right panel with system metrics
- Control buttons for all Phoenix functions
- Real-time data from your Phoenix installation

---

## First Time Setup

### Install Node.js (if you don't have it)

**Windows:**
```powershell
winget install OpenJS.NodeJS
```

**Or download from:** https://nodejs.org (choose LTS version)

**Verify installation:**
```bash
node --version
npm --version
```

---

## What Works Right Now

### ✅ Real Phoenix Integration
- Executes actual `usys` commands
- Shows real sector file counts
- Displays actual clonepool data
- Live system metrics

### ✅ Interactive Features
- Click toggle switches to activate/deactivate sectors
- Click control buttons to execute commands
- Terminal overlay shows real command output
- Metrics update automatically

### ✅ All UI Elements
- Holographic effects and animations
- Sci-fi green theme
- Responsive layout
- Smooth transitions

---

## Quick Commands Reference

### Running the Dashboard

```bash
# Start the app
npm start

# Or use the PowerShell script
.\start.ps1
```

### Building an .exe

```bash
# Create Windows installer
npm run build-win

# Find it in: dist/Phoenix Dashboard Setup 1.0.0.exe
```

### Development

```bash
# Install dependencies
npm install

# Update dependencies
npm update

# Clean install
rm -rf node_modules
npm install
```

---

## File Overview

```
dashboard/
├── START_HERE.md           ← You are here!
├── ELECTRON_SETUP.md       ← Detailed setup guide
├── INTEGRATION_GUIDE.md    ← Integration options
├── README.md               ← Feature documentation
│
├── start.ps1               ← Quick start script
├── package.json            ← Node.js config
├── main.js                 ← Electron backend
│
├── index.html              ← Dashboard UI
├── styles.css              ← Styling
└── dashboard.js            ← Frontend logic
```

---

## Troubleshooting

### "node: command not found"
**Fix:** Install Node.js (see above)

### "Cannot find module 'electron'"
**Fix:** Run `npm install` in the dashboard directory

### Dashboard shows simulated data
**Fix:** Make sure Phoenix is installed and environment variables are set
- Check: `echo $env:PHOENIX_ROOT`
- If not set, run Phoenix's `install.ps1` first

### Window is too big/small
**Fix:** Edit `main.js` line 13-14 to change window size

---

## Next Steps

### After First Launch

1. **Test the buttons** - Click "System Status" to see real Phoenix data
2. **Toggle switches** - Activate/deactivate sectors
3. **Check metrics** - Watch real-time updates
4. **Open terminal** - Click any control button

### Customize

- **Change colors:** Edit `styles.css`
- **Add features:** See `INTEGRATION_GUIDE.md`
- **Build .exe:** Run `npm run build-win`

### Learn More

- **Full setup guide:** `ELECTRON_SETUP.md`
- **Integration options:** `INTEGRATION_GUIDE.md`
- **Feature list:** `README.md`

---

## Support

### Documentation
- 📖 ELECTRON_SETUP.md - Complete Electron guide
- 📖 INTEGRATION_GUIDE.md - Integration methods
- 📖 README.md - Feature documentation

### Phoenix Commands
```bash
usys status          # Check Phoenix status
usys list-suites     # List available suites
usys clone <file>    # Clone a file
usys intake <file>   # Intake to vault
```

### Need Help?
1. Check the console for errors (DevTools)
2. Verify Phoenix is installed: `usys status`
3. Check environment: `echo $env:PHOENIX_ROOT`
4. Open an issue on GitHub

---

## Summary

### To Start the Dashboard:

```powershell
cd dashboard
.\start.ps1
```

### What You Get:

✅ Native desktop app
✅ Real Phoenix integration  
✅ Beautiful sci-fi interface
✅ All features working
✅ Live data updates

### Build Time:

- First run: ~2 minutes (npm install)
- Subsequent runs: ~5 seconds

---

## That's It!

You're ready to use the Phoenix Command Center Dashboard!

**Run this now:**
```powershell
.\start.ps1
```

🚀 **Enjoy your Phoenix Dashboard!**
# Phoenix DevOps — Between-Session Tasks
# jwl247 / Jerry Leftwich
# Run these solo. Each one advances the real build.
# Paste status.sh output + what you tried when you come back to Claude.
# =============================================================================

## FIRST — always run this before anything else
```bash
bash ~/phoenix-devops/status.sh
```
Green = good. Red = something to fix. Paste the output at the start of every
Claude session so we pick up exactly where we left off.

---

## TIER 1 — 5 minutes each. Just checking what we built.

### T1-A: Verify the 3-node mesh
```bash
sudo wg show                          # should show 2 peers from WSL
ssh phx "sudo wg show"                # phoenix-ext should show 2 peers too
ssh windows-host "ipconfig"           # windows side (needs OpenSSH on Windows)
```
**What you're looking for:** Each node knows about the other two.
`ssh phx` working = mesh is live.

---

### T1-B: Trace the WireGuard path
```bash
traceroute 10.77.0.1                  # WSL → Windows (should be 1 hop)
traceroute 10.77.0.3                  # WSL → phoenix-ext (should be 1 hop, direct)
ssh phx "traceroute 10.77.0.2"        # ext → WSL (1 hop back)
```
**What you're looking for:** Each hop is exactly 1. If you see 2 hops to
phoenix-ext, traffic is still routing through Windows (hub-and-spoke).
1 hop = direct peer connection is working.

---

### T1-C: Verify intake is installed on phoenix-ext
```bash
ssh phoenix-lan "source ~/.phoenix_env && intake --help 2>&1 | head -5"
```
**What you're looking for:** Some output about intake. If it says
"No such file" — bootstrap needs re-running on ext.

---

### T1-D: Check what's in the clone pool
```bash
ls ~/Phoenix/clonepool/               # WSL side
ssh phoenix-lan "ls ~/Phoenix/clonepool/"  # ext side
```
**What you're looking for:** Should be empty or have a few .json files.
This is where intake deposits files. Empty is fine — nothing's been intaked yet.

---

## TIER 2 — 15 minutes each. Using the system.

### T2-A: Intake your first file
Pick any real file on phoenix-ext (a config, a script, anything).
```bash
# On phoenix-ext:
ssh phoenix-lan
source ~/.phoenix_env
intake ~/phoenix-devops/sector3/wireguard/wg0-phoenix-ext.conf
ls ~/Phoenix/clonepool/
```
**What you're looking for:** A new .json sidecar in clonepool.
Open it — you'll see the TAV address, hex identity, SHA3 hash, QR strings.
That's the file's permanent identity in Phoenix.

---

### T2-B: Run the bridge
```bash
bridge status                          # what does the bridge see?
bridge ext                             # SSH to phoenix-ext through bridge
```
If `bridge` isn't in PATH:
```bash
~/Phoenix/bin/bridge status
```
**What you're looking for:** Green checkmarks for WireGuard and SSH.
`bridge ext` should drop you into a shell on phoenix-ext.

---

### T2-C: Make WireGuard start automatically on WSL boot
WSL resets on restart — every time you open it, wg0-wsl is down.
Fix it by adding this to your WSL profile:
```bash
echo 'sudo wg-quick up /home/jwlef/phoenix-devops/sector3/wireguard/wg0-wsl.conf 2>/dev/null || true' >> ~/.bashrc
```
Then test: close WSL completely, reopen it, run `ip link show wg0-wsl`.
Should say UP without you doing anything.

**Note:** It'll ask for sudo password on first open. To skip that too:
```bash
echo 'jwlef ALL=(ALL) NOPASSWD: /usr/bin/wg-quick' | sudo tee /etc/sudoers.d/wg-quick
```

---

### T2-D: Explore what phoenix-ext has running
```bash
ssh phoenix-lan "systemctl list-units --state=running | grep -v systemd"
ssh phoenix-lan "df -h"                # disk space
ssh phoenix-lan "free -h"             # RAM
ssh phoenix-lan "uname -r"            # kernel version
```
**What you're looking for:** Getting familiar with the machine.
Note the disk space — this is the machine Phoenix will live on.
The kernel version tells you if HWE kernel is installed.

---

### T2-E: Check the D1 worker manually
The status.sh shows the worker returning 404. Let's see what it actually says:
```bash
source ~/.phoenix_env
curl -s "$PHOENIX_WORKER_URL/health" | head -20
curl -s "$PHOENIX_WORKER_URL/" | head -20
```
**What you're looking for:** Either a JSON response or an error message.
Paste whatever comes back when you come to the next Claude session.

---

## TIER 3 — 30 minutes. Advancing the build.

### T3-A: Set up passwordless sudo for Phoenix commands on phoenix-ext
Right now every sudo on phoenix-ext needs your password. This gets annoying fast.
```bash
ssh -t phoenix-lan "sudo bash -c 'echo \"jwlef ALL=(ALL) NOPASSWD: /usr/bin/wg-quick, /usr/bin/wg, /usr/bin/systemctl\" >> /etc/sudoers.d/phoenix'"
```
Test it:
```bash
ssh phoenix-lan "sudo wg show"        # should work without password prompt
```

---

### T3-B: Install Input Leap on phoenix-ext
Input Leap = shared mouse and keyboard between Windows (left) and phoenix-ext (right).
```bash
# Copy and run the installer:
scp ~/phoenix-devops/sector3/bridge/inputleap-install.sh phoenix-lan:/tmp/
ssh -t phoenix-lan "bash /tmp/inputleap-install.sh 192.168.1.100"
```
192.168.1.100 is the Windows LAN IP.

On Windows: download Input Leap from https://github.com/input-leap/input-leap/releases
Run as server. Config is already written at:
`~/phoenix-devops/sector3/bridge/inputleap-server.conf`
Copy it to wherever Input Leap on Windows expects its config.

**What you're looking for:** Mouse slides from Windows screen to Linux screen
at the right edge.

---

### T3-C: Intake a batch of real files
Find files you want in the Phoenix vault and intake them:
```bash
ssh phoenix-lan
source ~/.phoenix_env

# Intake anything in a directory:
for f in ~/phoenix-devops/sector4/frank/*.py; do
    intake "$f"
    echo "---"
done

ls ~/Phoenix/clonepool/ | wc -l       # how many files landed
```
**What you're looking for:** Each file gets its own sidecar JSON.
The clonepool count goes up. This is how the 80% of existing backup
files get placed — Frank registers them, intake tracks them.

---

### T3-D: Pull up the Ubuntu machine's GNOME desktop
phoenix-ext has GNOME (we saw it in the WireGuard install output).
If you have it connected to a monitor, try logging in graphically.
If not, you can set up VNC or just confirm the desktop is there:
```bash
ssh phoenix-lan "systemctl status gdm"
ssh phoenix-lan "echo \$XDG_SESSION_TYPE"
```
This matters for Input Leap — it needs a running display to hook into.

---

## QUICK REFERENCE — Commands you'll use constantly

```bash
# Health check
bash ~/phoenix-devops/status.sh

# WireGuard
sudo wg show                                          # see tunnel status
sudo wg-quick up /home/jwlef/phoenix-devops/sector3/wireguard/wg0-wsl.conf
sudo wg-quick down /home/jwlef/phoenix-devops/sector3/wireguard/wg0-wsl.conf

# SSH shortcuts (from WSL)
ssh phoenix-lan     # → phoenix-ext via LAN (192.168.1.133) — always works
ssh phx             # → phoenix-ext via WireGuard (10.77.0.3) — needs wg up
ssh windows-host    # → Windows via WireGuard (10.77.0.1) — needs OpenSSH on Windows

# Phoenix commands
source ~/.phoenix_env         # load Phoenix environment
intake <file>                 # register a file into the clone pool
bridge status                 # check mesh + SSH connectivity
bridge ext                    # jump to phoenix-ext

# Git (always both machines)
git -C ~/phoenix-devops pull                          # WSL: pull latest
ssh phoenix-lan 'git -C ~/phoenix-devops pull'        # ext: pull latest
```

---

## WHAT TO TELL CLAUDE NEXT SESSION

1. Paste `bash ~/phoenix-devops/status.sh` output
2. Which tasks you tried and what happened
3. Any errors or surprising output (paste the exact text)
4. What you want to work on next

That's it. Claude reads status.sh like a dashboard — 30 seconds and we're
back up to speed on every machine.

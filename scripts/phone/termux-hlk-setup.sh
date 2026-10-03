#!/data/data/com.termux/files/usr/bin/bash
# termux-hlk-setup.sh — put HLK (kernel + genie + radar, PowerShell 7) on an Android phone.
# UnitedSys — United Systems | jwl247 | GPL-3.0
#
# Run INSIDE Termux (install Termux from F-Droid, not the Play Store):
#   curl -fsSLO https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/claude/youthful-ritchie-f42a4a/scripts/phone/termux-hlk-setup.sh
#   bash termux-hlk-setup.sh
# Then type:  hlk
#
# What it does: a Debian userland in Termux (proot-distro), Microsoft's ARM PowerShell 7 in it,
# the three HLK scripts, and an `hlk` command. It asks for NO keys and stores none: until a key
# is added by hand (~/.phoenix/kernel.env, chmod 600, read-only key preferred), the genie and its
# library work offline and nothing can reach the pool. Re-running is safe (skips what's there).
set -euo pipefail

BRANCH="${HLK_BRANCH:-claude/youthful-ritchie-f42a4a}"
RAW="https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/${BRANCH}/scripts"
PWSH_VER="${HLK_PWSH_VER:-7.4.6}"

say() { printf '\n== %s\n' "$*"; }

say "Termux packages"
pkg update -y
pkg install -y proot-distro curl

if [ ! -d "${PREFIX}/var/lib/proot-distro/installed-rootfs/debian" ]; then
  say "Debian userland (one time, a few minutes)"
  proot-distro install debian
else
  say "Debian userland already here"
fi

say "PowerShell ${PWSH_VER} + HLK inside Debian"
proot-distro login debian -- env RAW="$RAW" PWSH_VER="$PWSH_VER" bash -eu -o pipefail -c '
  case "$(uname -m)" in
    aarch64|arm64) ARCH=arm64 ;;
    armv7l|armv8l|arm) ARCH=arm32 ;;
    *) echo "unsupported CPU: $(uname -m)"; exit 1 ;;
  esac
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq curl ca-certificates libicu72 less tzdata >/dev/null
  if ! command -v pwsh >/dev/null; then
    mkdir -p /opt/microsoft/powershell/7
    curl -fsSL "https://github.com/PowerShell/PowerShell/releases/download/v${PWSH_VER}/powershell-${PWSH_VER}-linux-${ARCH}.tar.gz" \
      | tar -xz -C /opt/microsoft/powershell/7
    chmod +x /opt/microsoft/powershell/7/pwsh
    ln -sf /opt/microsoft/powershell/7/pwsh /usr/bin/pwsh
  fi
  pwsh -NoLogo -NoProfile -Command "\$PSVersionTable.PSVersion.ToString()"
  mkdir -p ~/hlk && cd ~/hlk
  for f in phx-kernel.ps1 genie.ps1 radar.ps1; do curl -fsSLO "$RAW/$f"; done
  pwsh -NoLogo -NoProfile -File ~/hlk/phx-kernel.ps1 install
  pwsh -NoLogo -NoProfile -Command ". ~/hlk/genie.ps1; genie install"
'

say "The hlk command"
cat > "${PREFIX}/bin/hlk" <<'LAUNCH'
#!/data/data/com.termux/files/usr/bin/bash
exec proot-distro login debian -- pwsh -NoLogo "$@"
LAUNCH
chmod +x "${PREFIX}/bin/hlk"

say "Done. Type:  hlk     then try:  bingo     genie library"

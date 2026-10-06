# pbmiii-up.ps1 — finish pbmIII from PBMII after node-up.sh ran on it from the USB stick
# Phoenix DevOps OS | jwl247 | GPL v3
#
#   PBMII, PS7:  cd F:\Phoenix\Phoenix-DevOps-oS
#                pwsh scripts\pbmiii-up.ps1 -Ip 192.168.1.x
#
# 1. hosts.json pbmiii ssh -> a@<Ip> (if it changed)      2. key + passwordless admin check
# 3. Nebula mesh (phoenix_net.py install-ssh)              4. hardening --keep-services, confirmed only after a NEW SSH session gets in (else it rolls back in 120 s by itself)  5. SMB shares on the mesh (password from the
#    vault, sent over SSH stdin to a 0600 file, never argv)    6. checks from Windows
param([Parameter(Mandatory)][string]$Ip, [string]$Node = 'pbmiii')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot)
$hostsFile = 'sector3/mesh/hosts.json'
$vault = 'F:\Phoenix\Vault\secrets'

function Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
function Fail($t) { Write-Host "FAIL: $t" -ForegroundColor Red; exit 1 }

Step "1. hosts.json"
$h = python -c "import json;print(json.dumps(json.load(open('$hostsFile'))['hosts']['$Node']))" | ConvertFrom-Json
$user = $h.ssh.Split('@')[0]
if ($h.ssh -ne "$user@$Ip") {
    python -c "import json;p='$hostsFile';d=json.load(open(p));d['hosts']['$Node']['ssh']='$user@$Ip';s=json.dumps(d,indent=2)+'\n';open(p,'w',newline='\n').write(s)"
    Write-Host "  $Node ssh: $($h.ssh) -> $user@$Ip (commit hosts.json)"
} else { Write-Host "  unchanged: $($h.ssh)" }
$key = Join-Path $HOME ".ssh\$($h.ssh_key)"
$ssh = @('-i', $key, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=accept-new', "$user@$Ip")

Step "2. key + admin"
# a reinstalled box has a NEW host key: drop the old one for this address first
ssh-keygen -R $Ip 2>$null | Out-Null
ssh-keygen -R $h.ip 2>$null | Out-Null     # its mesh address too
$r = ssh @ssh 'sudo -n true && hostname'
if ($LASTEXITCODE) { Fail "no key login or no passwordless admin — did node-up.sh finish on $Node?" }
Write-Host "  in as $user on $r, admin OK"

Step "3. mesh"
python sector3/mesh/phoenix_net.py install-ssh $Node
if ($LASTEXITCODE) { Fail 'mesh install' }

Step "4. hardening (--keep-services)"
ssh @ssh 'sudo bash /opt/phoenix/scripts/hardening/phoenix-harden.sh apply --ssh-from 192.168.1.0/24 --keep-services'
if ($LASTEXITCODE) { Fail 'harden apply (firewall rolls back in 120 s by itself)' }
Start-Sleep 3
$lan = ssh @ssh 'echo lan-ok'
$mesh = ssh -i $key -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$user@$($h.ip)" 'echo mesh-ok'
if ($lan -ne 'lan-ok' -or $mesh -ne 'mesh-ok') { Fail "new SSH session failed (lan=$lan mesh=$mesh) — NOT confirming; firewall rolls back in 120 s" }
ssh @ssh 'sudo bash /opt/phoenix/scripts/hardening/phoenix-harden.sh confirm'

Step "5. shares (after hardening: it needs auditd)"
$envLines = Get-Content (Join-Path $vault "samba-$Node.env")
$smbUser = ($envLines | Where-Object { $_ -like 'SMB_PBMIII_USER=*' }) -replace '^[^=]+=', ''
$smbPass = ($envLines | Where-Object { $_ -like 'SMB_PBMIII_PASS=*' }) -replace '^[^=]+=', ''
if (-not $smbPass) { Fail "no SMB_PBMIII_PASS in the vault" }
$remote = "umask 077; f=`$(mktemp); tr -d '\r\n' > `$f; sudo SMB_PASS_FILE=`$f SHARE_USER=$smbUser bash /opt/phoenix/scripts/shares/phoenix-shares.sh apply; rc=`$?; rm -f `$f; exit `$rc"
$smbPass | ssh @ssh $remote
if ($LASTEXITCODE) { Fail 'shares apply' }
$smbPass = $null

Step "6. checks from Windows"
$smb = Test-NetConnection $h.ip -Port 445 -WarningAction SilentlyContinue
Write-Host "  ssh over LAN : $lan"
Write-Host "  ssh over mesh: $mesh"
Write-Host "  SMB $($h.ip):445 : $($smb.TcpTestSucceeded)"
ssh @ssh 'printf "  services kept: "; systemctl is-active cups bluetooth avahi-daemon 2>/dev/null | tr "\n" " "; echo; printf "  pwsh: "; pwsh -NoLogo -NoProfile -c "\$PSVersionTable.PSVersion.ToString()"; printf "  helix.ko: "; ls /opt/phoenix/sector1/kernels/helix.ko 2>/dev/null || echo "not built"'
Write-Host "`n  Map the share:  net use P: \\$($h.ip)\pbmIII /user:$smbUser *" -ForegroundColor Green

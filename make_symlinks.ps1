$base = "C:\Users\jwlef\PhoenixDevOps"
foreach ($s in 'sector1','sector2','sector3','sector4') {
    $link   = "$base\$s\propcoms"
    $target = "$base\$s\propcoms.py"
    if (Test-Path $link) { Remove-Item $link -Force }
    New-Item -ItemType SymbolicLink -Path $link -Target $target | Out-Null
    Write-Host "$s propcoms symlink: ok -> $target"
}

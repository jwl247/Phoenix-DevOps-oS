---
description: Screenshot Jerry's screen and look at it (/look [seconds] [what to look at])
argument-hint: "[seconds to wait] [what to look at]"
allowed-tools: PowerShell, Read
---
Jerry wants you to look at his screen right now. Arguments: "$ARGUMENTS"

1. If the first word of the arguments is a number, that is a delay in seconds (max 30) so he can bring the right window forward; otherwise the delay is 0.
2. Take the shot with PowerShell, exactly:
   `pwsh -NoProfile -Sta -ExecutionPolicy Bypass -File F:\Phoenix\Phoenix-DevOps-oS\scripts\snap-to-claude.ps1 -Quiet -Delay <delay>`
3. Read `C:\Users\jwlef\.phoenix\screenshots\latest.png` with the Read tool.
4. Answer what he asked about (the rest of the arguments). If he asked nothing specific, say briefly what's on screen that matters to the current work (HUD state, errors, dialogs) in a few lines. The shot stays local in his account-only folder; never send it anywhere else.

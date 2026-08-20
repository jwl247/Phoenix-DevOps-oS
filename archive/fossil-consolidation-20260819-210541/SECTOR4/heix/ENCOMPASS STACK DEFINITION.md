# 🧬 ENCOMPASS STACK DEFINITION (MAGNET-WHALE EDITION)
[meta]
name = "Helix-Magnet-RTS"
version = "4.0.0"

[services.agno]
name = "enco_agnoD"
desc = "Environment Worker"
layer = -1
auto = true

[services.whale]
name = "enco_whaleD"
desc = "Helix Whale (LVM Monitor)"
layer = 0
auto = true
path = "/etc/HEix7_3GIII/core/helix_complete.py"

[services.magnet]
name = "enco_magnetD"
desc = "Magnet FS Neural Indexer"
layer = 1
auto = true
path = "/etc/HEix7_3GIII/core/helix_whale_core.py"

[services.dash]
name = "enco_dashD"
desc = "Sacrifice Command Bridge"
layer = 2
auto = true

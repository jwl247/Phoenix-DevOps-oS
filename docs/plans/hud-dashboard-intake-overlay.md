# HUD/Dashboard — manual intake overlay (suits from dropped files)

**Status:** CAPTURED, not designed or built. Jerry's plan + research, 2026-10-06. Discuss before building.

## Jerry's plan (his words, lightly tidied)

Package-handler intake of **manual files** goes through the dashboard — especially for **making suits**.
It is an **overlay** on the dashboard:

- tkinter DnD (drag and drop)
- isolation
- async
- permission map
- metadata sanitizer
- shutil copy buffer
- host file bridge

That overlay is the front of intake. We repurpose it to **pull the config out as a manifest (.jsonc)**.
The reference below (Jerry's research, emailed to himself 2026-10-06 7:38 AM) shows the pattern:
read live config from the system, read-only, and serialize it as a commented JSONC manifest.

### What "overlay" means (Jerry, 2026-10-06, correcting Claude's reading)

Not a panel on top of the dashboard. The overlay is **the new HUD itself**:
- **see-through**: a transparent window over whatever is on screen
- **click-through**: clicks pass to the app underneath except where the HUD has a control
- **set up the way we want**: Jerry decides the layout, not a fixed panel

**Why an overlay (Jerry):** it gives the HUD **desktop functions**. You drag and drop straight from the
desktop or Explorer and work on the **same files, open or closed**. A file can be open in its own app
and the HUD still works on it.

Catch for the build: a file that's open in another app may be locked. Most apps let other programs
read the file while they have it open, but some lock it completely. The copy buffer must open files
for shared read rather than doing a plain `shutil.copy`. When a file is fully locked, it should take a
Volume Shadow Copy snapshot, or say "close it first". It should never fail without saying so. Writing
back to an open file is a separate, bigger question (the other app could overwrite it), so that belongs
behind a "deviation" permission prompt.

**Sight picture (Jerry, 2026-10-06, "hell or high water"):** Claude gets to SEE the workspace,
the way Copilot Vision can. The HUD captures the screen (whole desktop, one window, or the area under
the overlay) and hands it to Claude as an image. Claude already reads images, so the missing part is
the capture and the handoff.
- Ladder: (1) a hotkey/button that takes one screenshot and drops it into a known folder Claude reads.
  This works today, with no new model needed. (2) The HUD sends the frame with the question, so Claude
  sees what Jerry sees. (3) Low-rate continuous frames while Jerry asks for a watch.
- Permission tier: a screen image leaving the machine goes to the Anthropic API. On by Jerry's choice,
  never silent. Show a visible "Claude can see" indicator, a hotkey to stop, and skip windows marked
  private (vault, banking, Laurie's private screens).
- Fallback: a local Ollama vision model (llava-class) for small "what's on screen" jobs, matching the
  Ollama button.

**AI in the new HUD:**
- **Claude is primary.**
- **Ollama is a fallback called by a button.** It does minimal guide work, small tasks and chat.
  (This matches CLAUDE.md rule 14: Ollama-local stays a real, tested fallback.)

Note for the design talk: a see-through, click-through window is standard Win32 (`WS_EX_LAYERED` +
`WS_EX_TRANSPARENT`, switched off per control). WPF (the existing `hud/`) supports it directly.
tkinter on Windows can make a window transparent, but click-through only works with Win32 calls on
top. Ask Jerry which one to use.

## Reference code (verbatim)

```python
import os
import re
import json

class GraphicDriverExtractor:
    def __init__(self):
        self.sysfs_drm_path = "/sys/class/drm"
        self.modprobe_path = "/etc/modprobe.d"
        self.extracted_config = {
            "kernel_module": "unknown",
            "device_hardware": {},
            "power_profiles": {},
            "driver_overrides": {}
        }

    def run_extraction_pipeline(self):
        """Asynchronously audits the kernel hardware layer without modifying profiles."""
        if not os.path.exists(self.sysfs_drm_path):
            return self.fallback_windows_extraction()

        # 1. Detect Active Driver Substrate Boundary
        for card in os.listdir(self.sysfs_drm_path):
            if card.startswith("card") and not "-" in card:
                device_link = os.path.join(self.sysfs_drm_path, card, "device")
                if os.path.exists(device_link):
                    self.extract_linux_sysfs_metrics(device_link)
                    break
        
        # 2. Extract Static Blacklist and Modprobe Overrides
        self.extract_modprobe_parameters()
        return self.serialize_to_jsonc()

    def extract_linux_sysfs_metrics(self, device_path):
        """Maps live memory/power states directly out of the driver's active boundary."""
        # Read low-level PCI Vendor identity
        try:
            with open(os.path.join(device_path, "vendor"), "r") as f:
                vendor_id = f.read().strip()
                self.extracted_config["device_hardware"]["vendor_id"] = vendor_id
                self.extracted_config["kernel_module"] = "amdgpu" if "0x1002" in vendor_id else "nvidia"
        except IOError:
            pass

        # Parse live power optimization tables if running open-source trees
        pp_table = os.path.join(device_path, "pp_power_profile_mode")
        if os.path.exists(pp_table):
            try:
                with open(pp_table, "r") as f:
                    # Capture the active driver profile line marked with an asterisk
                    profiles = f.readlines()
                    self.extracted_config["power_profiles"]["raw_table"] = [p.strip() for p in profiles]
                    for profile in profiles:
                        if "*" in profile:
                            self.extracted_config["power_profiles"]["active_mode"] = profile.replace("*", "").split()[1]
            except IOError:
                pass

    def extract_modprobe_parameters(self):
        """Gathers injection overrides sitting in boot configuration files."""
        if os.path.exists(self.modprobe_path):
            for conf_file in os.listdir(self.modprobe_path):
                if conf_file.endswith(".conf"):
                    try:
                        with open(os.path.join(self.modprobe_path, conf_file), "r") as f:
                            for line in f:
                                # Track manual kernel parameters like modeset or blacklist rules
                                if line.strip().startswith("options") or line.strip().startswith("blacklist"):
                                    tokens = line.strip().split()
                                    self.extracted_config["driver_overrides"][tokens[1]] = tokens[2:]
                    except IOError:
                        pass

    def fallback_windows_extraction(self):
        """Fallback mechanism if running inside an un-tainted Windows PowerShell bridge."""
        self.extracted_config["kernel_module"] = "windows-dxgi"
        self.extracted_config["device_hardware"]["note"] = "Extracting execution flags via fallback matrix"
        return self.serialize_to_jsonc()

    def serialize_to_jsonc(self):
        """Converts extracted configuration parameters into a clean, commented template."""
        raw_json = json.dumps(self.extracted_config, indent=4)
        jsonc_output = (
            "// =========================================================\n"
            "// COPES AUTOMATED GRAPHICS DRIVER CONFIGURATION MANIFEST\n"
            "// DETECTED AND EXTRACTED AT RUNTIME IN VOLATILE USERSPACE\n"
            "// =========================================================\n"
            f"{raw_json}"
        )
        return jsonc_output

if __name__ == "__main__":
    extractor = GraphicDriverExtractor()
    manifest_payload = extractor.run_extraction_pipeline()
    print(manifest_payload)
```

## Claude's review notes (for the design talk — nothing decided)

**What carries over:** the pattern. Read the live config, read-only, and write a JSONC manifest
with comments. It only reads `/etc/modprobe.d`, never writes it, so it stays inside AI safety rule 4.

**Bugs, if this code itself gets used:**
- Any vendor that isn't AMD gets labeled `nvidia`. Intel `0x8086` is misnamed.
- `blacklist foo` has no `tokens[2]`, so it records `[]`. Several `options` lines for one module overwrite each other.
- The docstring says asynchronous, but the code is synchronous.
- The Windows fallback extracts nothing.
- `re` is imported but never used.
- The JSONC has a header comment only, with no comment per field.

**How it meets what exists today:**
- Suites already have a manifest, `.suite.json`, which `usys.ps1` reads (`Get-UsysSuiteManifest`).
  intake.sh auto-registers it at `clonepool/<name>/.suite.json`. Going to `.jsonc` means
  that reader has to skip comments. Decide: switch to .jsonc, or have the overlay output a plain `.suite.json`.
- The overlay is a front end to the import method (intake.sh: hex, then sidecar, then R2, then D1), not a second intake path.
- GPU drivers are blacklisted on Phoenix OS (rule 6). The GPU-specific part is a sample, not a target.
  It's still open whether a game client may use the player's GPU.

**Toolkit question:** the dashboard is Electron, and the real HUD is WPF (`hud/`). A tkinter overlay would be
a third GUI toolkit. Electron already has native drag and drop, and its context isolation and sandbox
cover the "isolation" item. The main process would do the copy, the sanitizing and the permission check.
Ask Jerry which of the three to use: tkinter, Electron or WPF.

**Pipeline order (draft):** drop, then permission map check, then metadata sanitizer, then copy buffer
(shutil.copy2 to staging + hash), then host file bridge, then config extraction to a manifest,
then intake.sh, then the suite is registered.

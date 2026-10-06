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

## Jerry's filled-out template, part 2 (2026-10-06, verbatim)

```
| Lightweight UI Overlay (Tkinter) |
| [ Drag-and-Drop Tree ] <--> [ Working Dir Dashboard ] |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+

| Isolation & Cloning Microkernel |
| - Async Thread Worker Pools - Metadata Sanitizer |
| - Permission Mapping Engine - Shutil Copy Buffers |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+

| Host File System Bridge |
| [ /mnt/c/ ] [ /home/user/ ] [ UUID Drives ] |
+-------------------------------------------------------------+
```

Step-by-Step implementation: a single executable application script named `virtual_desktop_kernel.py`.
It has a background thread pool built in, so operations never freeze the UI workspace, whatever the file size.

```python
import os
import shutil
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk


class VirtualDesktopKernel:

    def __init__(self, root, working_dir=None):
        self.root = root
        self.root.title("Agnostic Virtual Workspace v1.0")
        self.root.geometry("900x600")

        # Configure working workspace path (defaults to current execution directory)
        self.working_dir = (
            os.path.abspath(working_dir)
            if working_dir
            else os.path.join(os.getcwd(), "workspace_dir")
        )
        if not os.path.exists(self.working_dir):
            os.makedirs(self.working_dir)

        # Base filesystem exploration starting point
        # Works dynamically across Windows, WSL/Linux, or custom mounts
        self.host_root = "/" if os.name != "nt" else "C:\\"

        self.setup_styles()
        self.create_widgets()
        self.populate_tree(self.host_root, "")

    def setup_styles(self):
        """Builds a scannable high-contrast operational terminal scheme."""
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background="#1e1e24", foreground="#ffffff")
        style.configure(
            "Treeview",
            background="#2d2d34",
            fieldbackground="#2d2d34",
            foreground="#ffffff",
        )
        style.map("Treeview", background=[("selected", "#005f73")])
        style.configure("TButton", background="#005f73", foreground="#ffffff")

    def create_widgets(self):
        # Master Workspace Layout Split
        self.paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left Frame: Host Filesystem Map
        left_frame = ttk.Labelframe(self.paned_window, text="Host System Explorer")
        self.paned_window.add(left_frame, weight=1)

        self.tree = ttk.Treeview(left_frame, columns=("path"), show="tree")
        self.tree.heading("#0", text="Directory Structure", anchor="w")
        self.tree.column("path", width=0, stretch=tk.NO) # Hidden path payload

        tree_scroll = ttk.Scrollbar(
            left_frame, orient=tk.VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewOpen>>", self.on_node_expand)

        # Right Frame: Virtual Active Working Directory Output
        right_frame = ttk.Labelframe(
            self.paned_window, text=f"Target Working Dir: {self.working_dir}"
        )
        self.paned_window.add(right_frame, weight=1)

        self.workspace_list = tk.Listbox(
            right_frame, bg="#1a1a1a", fg="#a9def9", font=("Consolas", 10)
        )
        self.workspace_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Action Execution Control Console
        control_bar = ttk.Frame(right_frame)
        control_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)

        self.clone_btn = ttk.Button(
            control_bar, text="⚡ Clone Selected to Workspace", command=self.trigger_cloning
        )
        self.clone_btn.pack(side=tk.RIGHT, padx=5)

        self.refresh_workspace_view()

    def populate_tree(self, parent_path, node):
        """Discovers host resources and provisions dynamic directory nodes safely."""
        try:
            for item in os.listdir(parent_path):
                full_path = os.path.join(parent_path, item)
                is_dir = os.path.isdir(full_path)
                # Create a placeholder if it is a directory to allow expanding actions later
                child_node = self.tree.insert(
                    node,
                    "end",
                    text=item,
                    values=(full_path,),
                    open=False,
                )
                if is_dir:
                    self.tree.insert(child_node, "end", text="_dummy")
        except PermissionError:
            pass # Quietly bypass privileged system nodes

    def on_node_expand(self, event):
        """Asynchronously loads real directory metadata when tree nodes expand."""
        node = self.tree.focus()
        path = self.tree.item(node, "values")[0]

        # Flush dummy items out of the allocation channel
        children = self.tree.get_children(node)
        if children and self.tree.item(children[0], "text") == "_dummy":
            self.tree.delete(children[0])
            self.populate_tree(path, node)

    def refresh_workspace_view(self):
        """Re-scans the isolated sandbox target directory to audit files."""
        self.workspace_list.delete(0, tk.END)
        for item in os.listdir(self.working_dir):
            file_size = os.path.getsize(os.path.join(self.working_dir, item))
            self.workspace_list.insert(tk.END, f"📦 {item} ({file_size} bytes)")

    def trigger_cloning(self):
        """Delegates copy calls to background threading pipelines."""
        selected_node = self.tree.focus()
        if not selected_node:
            messagebox.showwarning("Selection Required", "Select an asset to copy.")
            return

        source_path = self.tree.item(selected_node, "values")[0]

        # Spawn asynchronous thread worker to keep the environment interactive
        worker = threading.Thread(
            target=self.async_clone_kernel, args=(source_path,), daemon=True
        )
        worker.start()

    def async_clone_kernel(self, src):
        """Core kernel engine that preserves absolute attributes and permissions."""
        base_name = os.path.basename(src)
        dest_path = os.path.join(self.working_dir, base_name)

        try:
            if os.path.isdir(src):
                # Copy entire structure keeping permissions and symlinks intact
                shutil.copytree(src, dest_path, symlinks=True, dirs_exist_ok=True)
            else:
                # copy2 preserves metadata, access records, and execution flags
                shutil.copy2(src, dest_path)

            # Re-index working directory upon safe system exit
            self.root.after(0, self.refresh_workspace_view)
        except Exception as e:
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Kernel Copy Interrupted", f"Failed file tracking operation:\n{str(e)}"
                ),
            )


if __name__ == "__main__":
```
(The paste ended here: the `__main__` body was cut off.)

**Claude's notes on part 2:**
- This is a normal two-pane window (tree on one side, workspace on the other), not yet the see-through,
  click-through overlay. The threaded copy and the working-dir view carry over.
- These boxes aren't built yet: the metadata sanitizer, the permission map and the "isolation" step.
  Today `async_clone_kernel` copies whatever is selected, straight in.
- The copy is plain `shutil.copy2`/`copytree`. A file that's open and locked fails with an error box
  (see the locked-file note above). There is no hash and no intake.sh handoff yet.
- `/mnt/c` in the bridge diagram is a WSL path. Phoenix has no WSL. On Windows the bridge is the
  drives themselves; on Linux it's the mounts.
- The `refresh_workspace_view` `getsize` call on a directory gives the directory entry's size, not
  its contents.
- The error lambda reads `e` after the except block ends, and Python clears `e` at that point, so it
  raises a NameError. Bind it as `lambda e=e:`.

## Build (Claude drives the how; Jerry 2026-10-06)
**Decisions (Jerry):** the Console is the launch pad: every human button and switch, and the old HUD's panels move
into it. The HUD is chat only, and it's Claude. The entire desktop is drag and drop, with a drop-down of file
actions. Paths to everything come from Atlas.

**Slice 1: DONE 2026-10-06** (`hud/`):
- `Desktop/FileActions.cs`: one engine for every door. Copy/move/rename/new folder/show/send to pbmIII/intake.
  Shared-read copies, so open files work. A plain sentence when a file is locked. Never overwrites ("name (2)").
  A cross-drive move is copy, then SHA-256 verify, then delete. Every action goes to
  `E:\Phoenix\hud-live-monitor\actions.log`. Tested by calling the compiled engine: copy-while-open,
  name collision, exclusive-lock message, folder move C:->D: verified, bad rename refused, new folder.
- `Desktop/AtlasClient.cs` + `ActionMenu.cs` place picker: "Copy/Move to Phoenix place…" asks Atlas
  (packages-worker `/connections?q=`) plus fixed places (pbmIII share, repo, Desktop, Downloads, clone pool)
  plus Browse. Atlas query verified live.
- `HudOverlay`: full work-area, see-through, click-through except the solid chat column and a 6 px drop
  shelf on the left edge. Drop gives the drop-down at the cursor. "Ask Claude about it" attaches the paths to
  the next message (images go as vision to the API tier). Ctrl+Alt+Space toggles it. Its log is
  `hud-chat-log.txt`.
- `App`: one process. Console (MainWindow, now a normal window titled "Phoenix Console") plus the HUD.
  They share `App.Ai`, so it's one conversation. `Hud.exe --hud` opens the HUD at start. The Console has
  a HUD switch.
- Seen live (screenshot): the HUD over Process Monitor, which stays usable underneath; the Console behind.
- NOT yet proven by a human hand: an actual mouse drag onto the shelf, and the picker UI. Jerry to try.

**Next:** slice 3, the Explorer right-click "Phoenix" menu (HKCU verbs, then `Hud.exe --action`, sent to the
running app). Slice 4, Console tabs: the web Console (portal) in WebView2, plus the CLI/voice/monitor panels
and switches. Then sight in the HUD, and the Ollama/OpenJarvis button.

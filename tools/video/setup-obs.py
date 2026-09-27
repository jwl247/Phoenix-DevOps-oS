#!/usr/bin/env python3
"""Set OBS Studio up for Phoenix/PBM videos. Run with OBS CLOSED.

UnitedSys — United Systems | jwl247 | GPL-3.0

Adds a "Phoenix" profile + scene collection (the existing ones are left alone):
  scenes   "Screen + face"  your screen, the webcam in the bottom-right corner
           "Face"           the webcam, full frame
  sound    the V8S mic (the good one) + the PC's own sound; the webcam's own
           mic is muted so the voice isn't doubled
  output   1920x1080 @ 30, MP4 (hybrid: safe if OBS crashes mid-take),
           x264 on the CPU (Phoenix's no-GPU rule), saved to
           E:\\Phoenix\\video\\raw\\screen-<date-time>.mp4 next to the voice files

Devices are picked by their real Windows IDs, never "default". Found live
2026-09-27: both mics are named just "Microphone"; the V8S is the endpoint whose
interface name is "V8S" (a name-based guess picked the webcam).

  python tools/video/setup-obs.py
"""
import json
import os
import shutil
import subprocess
import sys
import uuid
import winreg

OBS = os.path.join(os.environ["APPDATA"], "obs-studio")
OUT_DIR = r"E:\Phoenix\video\raw"
MIC_NAME, CAM_NAME = "V8S", "Streaming Camera"
W, H = 1920, 1080


def capture_endpoint(iface_name):
    """{0.0.1.00000000}.{guid} of the active capture endpoint whose interface name matches."""
    base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
        for i in range(winreg.QueryInfoKey(k)[0]):
            g = winreg.EnumKey(k, i)
            try:
                with winreg.OpenKey(k, g) as dk:
                    if winreg.QueryValueEx(dk, "DeviceState")[0] != 1:
                        continue
                with winreg.OpenKey(k, g + r"\Properties") as pk:
                    name = winreg.QueryValueEx(pk, "{b3f8fa53-0004-438e-9003-51a46e139bfc},6")[0]
            except OSError:
                continue
            if name == iface_name:
                return "{0.0.1.00000000}." + g
    return None


def camera_id(name):
    """OBS's 'Name:\\\\?\\usb#...\\global' id for a DirectShow camera (via ffmpeg's device list)."""
    # A shell opened before ffmpeg was installed doesn't have it on PATH yet;
    # winget's own link folder always does.
    ffmpeg = shutil.which("ffmpeg") or os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "WinGet", "Links", "ffmpeg.exe")
    r = subprocess.run([ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                       capture_output=True, text=True)
    lines = r.stderr.splitlines()
    for i, line in enumerate(lines):
        if f'"{name}" (video)' in line:
            for alt in lines[i + 1:i + 4]:
                if "@device_pnp_" in alt and "usb#" in alt:
                    path = alt.split('"')[1].replace("@device_pnp_", "")
                    return f"{name}:{path}"
    return None


def primary_monitor_id():
    """The primary monitor's interface path (a DISPLAY#...#{e6f07b5f...} device path). OBS needs it: with no id,
    monitor capture records black (found live 2026-09-27: 'display: (0x0)')."""
    import ctypes
    from ctypes import wintypes

    class DD(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32), ("DeviceString", wintypes.WCHAR * 128),
                    ("StateFlags", wintypes.DWORD), ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]
    u, i = ctypes.windll.user32, 0
    while True:
        a = DD(); a.cb = ctypes.sizeof(a)
        if not u.EnumDisplayDevicesW(None, i, ctypes.byref(a), 0):
            return None
        if a.StateFlags & 4:                                  # DISPLAY_DEVICE_PRIMARY_DEVICE
            m = DD(); m.cb = ctypes.sizeof(m)
            if u.EnumDisplayDevicesW(a.DeviceName, 0, ctypes.byref(m), 1):   # EDD_GET_DEVICE_INTERFACE_NAME
                return m.DeviceID
        i += 1


def source(sid, name, settings, **extra):
    s = {"prev_ver": 537001986, "name": name, "uuid": str(uuid.uuid4()), "id": sid, "versioned_id": sid,
         "settings": settings, "mixers": 255, "sync": 0, "flags": 0, "volume": 1.0, "balance": 0.5,
         "enabled": True, "muted": False, "push-to-mute": False, "push-to-mute-delay": 0,
         "push-to-talk": False, "push-to-talk-delay": 0, "hotkeys": {}, "deinterlace_mode": 0,
         "deinterlace_field_order": 0, "monitoring_type": 0, "private_settings": {}}
    s.update(extra)
    return s


def item(src, iid, x, y, bw, bh):
    """A scene item scaled to fit inside a bw x bh box at (x, y), whatever the source's own size."""
    return {"name": src["name"], "source_uuid": src["uuid"], "visible": True, "locked": False, "rot": 0.0,
            "pos": {"x": float(x), "y": float(y)}, "scale": {"x": 1.0, "y": 1.0}, "align": 5,
            "bounds_type": 2, "bounds_align": 0, "bounds_crop": False, "bounds": {"x": float(bw), "y": float(bh)},
            "crop_left": 0, "crop_top": 0, "crop_right": 0, "crop_bottom": 0, "id": iid,
            "group_item_backup": False, "scale_filter": "disable", "blend_method": "default",
            "blend_type": "normal", "show_transition": {"duration": 0}, "hide_transition": {"duration": 0},
            "private_settings": {}}


def scene(name, items):
    return source("scene", name, {"id_counter": len(items), "custom_size": False, "items": items},
                  mixers=0, canvas_uuid="6c69626f-6273-4c00-9d88-c5136d61696e")


def main():
    if subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe"], capture_output=True, text=True).stdout.count("obs64.exe"):
        sys.exit("Close OBS first (it rewrites these files when it exits).")
    mic, cam = capture_endpoint(MIC_NAME), camera_id(CAM_NAME)
    if not mic:
        sys.exit(f"No active '{MIC_NAME}' microphone. Is the V8S plugged in?")
    print(f"mic: {MIC_NAME} = {mic}\ncamera: {cam or 'not found (scene gets no webcam)'}")

    mon = primary_monitor_id()
    print(f"monitor: {mon or 'not found (screen capture will be black)'}")
    screen = source("monitor_capture", "Screen", {"method": 0, "monitor_id": mon or "", "capture_cursor": True})
    items_sf, items_f, extra_sources = [item(screen, 1, 0, 0, W, H)], [], []
    if cam:
        # Custom 1920x1080 MJPEG: the camera's default mode put a blue band across the
        # top (found live 2026-09-27); its own 1080p MJPEG frame is clean.
        webcam = source("dshow_input", "Webcam", {"video_device_id": cam, "active": True, "res_type": 1,
                                                  "resolution": "1920x1080", "video_format": 400,
                                                  "frame_interval": 333333}, muted=True)
        bw, bh, m = 448, 252, 24
        items_sf.append(item(webcam, 2, W - bw - m, H - bh - m, bw, bh))
        items_f.append(item(webcam, 1, 0, 0, W, H))
        extra_sources.append(webcam)
    sc_sf, sc_f = scene("Screen + face", items_sf), scene("Face", items_f)

    collection = {
        "name": "Phoenix",
        "DesktopAudioDevice1": source("wasapi_output_capture", "PC sound", {"device_id": "default"}),
        "AuxAudioDevice1": source("wasapi_input_capture", "Mic (V8S)", {"device_id": mic}),
        "sources": [sc_sf, sc_f, screen, *extra_sources],
        "groups": [], "scene_order": [{"name": "Screen + face"}, {"name": "Face"}],
        "current_scene": "Screen + face", "current_program_scene": "Screen + face",
        "current_transition": "Fade", "transition_duration": 300, "transitions": [], "quick_transitions": [],
        "saved_projectors": [], "preview_locked": False, "modules": {}, "version": 2,
    }
    os.makedirs(os.path.join(OBS, "basic", "scenes"), exist_ok=True)
    with open(os.path.join(OBS, "basic", "scenes", "Phoenix.json"), "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=4)

    prof = os.path.join(OBS, "basic", "profiles", "Phoenix")
    os.makedirs(prof, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(prof, "basic.ini"), "w", encoding="utf-8") as f:
        f.write(f"""[General]
Name=Phoenix

[Output]
Mode=Simple
FilenameFormatting=screen-%CCYY%MM%DD-%hh%mm%ss

[SimpleOutput]
FilePath={OUT_DIR.replace(chr(92), "/")}
RecFormat2=hybrid_mp4
RecQuality=Small
RecEncoder=x264
ABitrate=192
FileNameWithoutSpace=true

[Video]
BaseCX={W}
BaseCY={H}
OutputCX={W}
OutputCY={H}
FPSType=0
FPSCommon=30

[Audio]
SampleRate=48000
ChannelSetup=Stereo
""")

    ini = os.path.join(OBS, "user.ini")
    lines = open(ini, encoding="utf-8").read().splitlines()
    want = {"Profile": "Phoenix", "ProfileDir": "Phoenix", "SceneCollection": "Phoenix", "SceneCollectionFile": "Phoenix.json"}
    out, section = [], ""
    for line in lines:
        if line.startswith("["):
            section = line
        key = line.split("=", 1)[0]
        if section == "[Basic]" and key in want:
            line = f"{key}={want.pop(key)}"
        out.append(line)
    if want:
        idx = out.index("[Basic]") + 1 if "[Basic]" in out else len(out)
        if "[Basic]" not in out:
            out += ["", "[Basic]"]
            idx = len(out)
        for k, v in want.items():
            out.insert(idx, f"{k}={v}")
    with open(ini, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("OBS set up: profile + scenes 'Phoenix'. Open OBS and press Start Recording.")


if __name__ == "__main__":
    main()

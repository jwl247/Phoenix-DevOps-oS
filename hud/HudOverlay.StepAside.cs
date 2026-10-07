using System.Runtime.InteropServices;
using System.Text;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Threading;

namespace Hud;

/// <summary>
/// The eye steps aside (Jerry 2026-10-07: "your always on top im trying to use the compaq").
/// The overlay is a see-through window over the whole work area, pinned on top, so it sat over a
/// full-screen VNC/remote view of the Compaq, a game, a video. Like the Windows taskbar: while the
/// window in front fills its screen, the eye hides; it comes back when that window leaves the front.
/// "Hide the eye" in the tray hides it until "Show the eye".
/// </summary>
public partial class HudOverlay
{
    private DispatcherTimer? _asideTimer;
    private bool _userHidden, _asideHidden;

    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] private static extern IntPtr MonitorFromWindow(IntPtr h, uint flags);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern bool GetMonitorInfo(IntPtr m, ref MONITORINFO mi);
    [StructLayout(LayoutKind.Sequential)] private struct RECT { public int L, T, R, B; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct MONITORINFO { public int cbSize; public RECT rcMonitor, rcWork; public uint dwFlags; }

    // The desktop and the shell are never "a full-screen app".
    private static readonly HashSet<string> ShellClasses = new(StringComparer.Ordinal) { "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd" };

    public bool EyeHiddenByUser => _userHidden;

    /// <summary>The tray's Hide/Show the eye.</summary>
    public void SetEyeHidden(bool hidden) { _userHidden = hidden; ApplyAside(); }

    private void StartStepAside()
    {
        _asideTimer = new DispatcherTimer(DispatcherPriority.Background) { Interval = TimeSpan.FromMilliseconds(400) };
        _asideTimer.Tick += (_, _) =>
        {
            var full = ForegroundIsFullScreen();
            if (full != _asideHidden) { _asideHidden = full; ApplyAside(); }
        };
        _asideTimer.Start();
        Closed += (_, _) => _asideTimer.Stop();
    }

    private void ApplyAside() => Visibility = _userHidden || _asideHidden ? Visibility.Hidden : Visibility.Visible;

    private bool ForegroundIsFullScreen()
    {
        var fg = GetForegroundWindow();
        if (fg == IntPtr.Zero || fg == new WindowInteropHelper(this).Handle) return false;
        var cls = new StringBuilder(64);
        GetClassName(fg, cls, cls.Capacity);
        if (ShellClasses.Contains(cls.ToString())) return false;
        if (!GetWindowRect(fg, out var r)) return false;
        var mi = new MONITORINFO { cbSize = Marshal.SizeOf<MONITORINFO>() };
        if (!GetMonitorInfo(MonitorFromWindow(fg, 2 /* nearest */), ref mi)) return false;
        var m = mi.rcMonitor;
        return r.L <= m.L && r.T <= m.T && r.R >= m.R && r.B >= m.B;
    }
}

using System.Runtime.InteropServices;
using System.Windows.Input;
using System.Windows.Threading;

namespace Hud.Voice;

/// <summary>
/// System-wide push-to-talk via a WH_KEYBOARD_LL hook. RegisterHotKey only
/// delivers a single WM_HOTKEY message on activation (plus OS key-repeat
/// while held) — it has no clean key-up signal, which hold-to-talk genuinely
/// needs to know when to stop recording. A low-level keyboard hook gives
/// real key-down/key-up events system-wide regardless of window focus, the
/// same mechanism Discord/Mumble-style push-to-talk relies on.
/// </summary>
public sealed class PushToTalkHotkey : IDisposable
{
    private const int WH_KEYBOARD_LL = 13;
    private const int WM_KEYDOWN = 0x0100;
    private const int WM_SYSKEYDOWN = 0x0104;
    private const int WM_KEYUP = 0x0101;
    private const int WM_SYSKEYUP = 0x0105;

    private delegate IntPtr LowLevelKeyboardProc(int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int idHook, LowLevelKeyboardProc lpfn, IntPtr hMod, uint dwThreadId);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UnhookWindowsHookEx(IntPtr hhk);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr GetModuleHandle(string? lpModuleName);

    private readonly int _targetVkCode;
    private readonly Dispatcher _dispatcher;

    // Kept alive for the hook's lifetime — the GC would otherwise collect
    // this delegate while native code still holds a pointer into it.
    private readonly LowLevelKeyboardProc _proc;

    private IntPtr _hookHandle = IntPtr.Zero;
    private bool _isDown;

    public event Action? PressStart;
    public event Action? PressEnd;

    public PushToTalkHotkey(Key key, Dispatcher dispatcher)
    {
        _targetVkCode = KeyInterop.VirtualKeyFromKey(key);
        _dispatcher = dispatcher;
        _proc = HookCallback;
    }

    public void Start()
    {
        if (_hookHandle != IntPtr.Zero) return;
        using var curProcess = System.Diagnostics.Process.GetCurrentProcess();
        using var curModule = curProcess.MainModule!;
        _hookHandle = SetWindowsHookEx(WH_KEYBOARD_LL, _proc, GetModuleHandle(curModule.ModuleName), 0);
    }

    private IntPtr HookCallback(int nCode, IntPtr wParam, IntPtr lParam)
    {
        if (nCode >= 0)
        {
            var vkCode = Marshal.ReadInt32(lParam);
            if (vkCode == _targetVkCode)
            {
                var msg = (int)wParam;
                if ((msg == WM_KEYDOWN || msg == WM_SYSKEYDOWN) && !_isDown)
                {
                    _isDown = true;
                    // Hand off immediately — a slow LL keyboard hook callback
                    // gets Windows to silently unhook it, so no real work
                    // happens on this call stack.
                    _dispatcher.BeginInvoke(() => PressStart?.Invoke());
                }
                else if (msg == WM_KEYUP || msg == WM_SYSKEYUP)
                {
                    _isDown = false;
                    _dispatcher.BeginInvoke(() => PressEnd?.Invoke());
                }
            }
        }
        return CallNextHookEx(_hookHandle, nCode, wParam, lParam);
    }

    public void Dispose()
    {
        if (_hookHandle != IntPtr.Zero)
        {
            UnhookWindowsHookEx(_hookHandle);
            _hookHandle = IntPtr.Zero;
        }
    }
}

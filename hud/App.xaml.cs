using System.Windows;
using Hud.Voice;

namespace Hud;

/// <summary>
/// The HUD is the EYE (Jerry, 2026-10-07, docs/plans/hud-eye-and-docks.md): the only thing always on
/// screen is the scanner eye; voice is the main way to talk; the chat drops down from the eye; the
/// docks stay invisible until a file is dragged to an edge or they're called. Every button lives in
/// the Console (MainWindow), opened from the eye only when wanted. One conversation (App.Ai) and
/// one voice (App.Voice) whichever face you use.
///   Hud.exe --eye    the eye only (what logon starts)
///   Hud.exe          the eye + the Console
/// The app lives as long as the eye: quit from the eye's right-click menu.
/// </summary>
public partial class App : Application
{
    public static AiChatService Ai { get; } = new();
    public static VoiceController? Voice { get; private set; }
    public static HudOverlay? Overlay { get; private set; }
    private static TrayIcon? _tray;
    private static MainWindow? _console;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        // Claude Code must start as a clean top-level session even when the HUD itself was
        // launched from inside one (a dev testing it) - same reason as the Console's CLI pane.
        foreach (System.Collections.DictionaryEntry kv in Environment.GetEnvironmentVariables())
        {
            var name = (string)kv.Key;
            if (name.StartsWith("CLAUDE_CODE_", StringComparison.Ordinal) || name == "CLAUDECODE")
                Environment.SetEnvironmentVariable(name, null);
        }
        var root = Environment.GetEnvironmentVariable("PHOENIX_ROOT");
        if (!string.IsNullOrEmpty(root) && System.IO.Directory.Exists(root)) Environment.CurrentDirectory = root;

        // Voice belongs to the app, not a window: the eye listens and speaks with the Console closed.
        Voice = VoiceSetup.Create(Dispatcher);

        Overlay = new HudOverlay();
        Overlay.Show();
        _tray = new TrayIcon();                                         // the Console lives in the tray (Jerry 10/7)
        if (!e.Args.Contains("--eye")) OpenConsole();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _tray?.Dispose();
        Voice?.Dispose();
        base.OnExit(e);
    }

    /// <summary>The button panel. Built only when asked for (it runs the Live Monitor capture).</summary>
    public static void OpenConsole()
    {
        if (_console is null || !_console.IsLoaded)
        {
            _console = new MainWindow();
            _console.Closed += (_, _) => _console = null;
            _console.Show();
        }
        else
        {
            if (_console.WindowState == WindowState.Minimized) _console.WindowState = WindowState.Normal;
            _console.Show();
        }
        _console.Activate();
    }

    /// <summary>The Console's HUD switch: drop the chat down from the eye, or fold it away.</summary>
    public static void ToggleHud() => Overlay?.ToggleChat();
}

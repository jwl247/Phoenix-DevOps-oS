using System.Windows;

namespace Hud;

/// <summary>
/// One process, two faces (Jerry, 2026-10-06): the CONSOLE (MainWindow: every human
/// button and switch, the old HUD's panels) is the launch pad; the HUD (HudOverlay:
/// see-through, click-through, chat only, Claude) is launched from it or with
/// Ctrl+Alt+Space. Both share App.Ai, so it's one conversation whichever face you use.
///   Hud.exe          Console
///   Hud.exe --hud    Console + HUD shown
/// </summary>
public partial class App : Application
{
    public static AiChatService Ai { get; } = new();
    public static HudOverlay? Overlay { get; private set; }

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        var console = new MainWindow();
        MainWindow = console;
        console.Show();

        Overlay = new HudOverlay();
        // Create the window handle now (so Ctrl+Alt+Space works) without showing it.
        new System.Windows.Interop.WindowInteropHelper(Overlay).EnsureHandle();
        if (e.Args.Contains("--hud")) Overlay.Toggle();
        console.Closed += (_, _) => Shutdown();
    }

    /// <summary>The Console's LAUNCH HUD switch.</summary>
    public static void ToggleHud() => Overlay?.Toggle();
}

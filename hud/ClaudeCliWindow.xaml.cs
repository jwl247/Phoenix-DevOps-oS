using System.IO;
using System.Windows;
using System.Windows.Input;

namespace Hud;

/// <summary>
/// The real "H.L.K-10 can work, not just watch" pane: a genuine interactive
/// Claude Code CLI session in a real pseudo-console (ConPTY), giving the HUD
/// the same tool access (shell, file edit, everything) as any other Claude
/// Code session — not a plain PowerShell prompt.
///
/// Mirrors dashboard/terminal-pty.js's "claude hotline" pattern exactly:
/// spawn a normal PowerShell session, then type the `claude.cmd` command
/// into it shortly after startup (rather than invoking claude.cmd as the
/// process directly) — so if the CLI session exits, you land back at a
/// normal, still-useful shell instead of a dead pane.
/// </summary>
public partial class ClaudeCliWindow : Window
{
    public ClaudeCliWindow()
    {
        InitializeComponent();

        Term.StartupCommandLine = $"{ResolveShell()} -NoLogo";
        Loaded += (_, _) => LaunchClaudeSession();
    }

    private void LaunchClaudeSession()
    {
        StatusLabel.Text = "launching…";
        // Same 300ms grace period dashboard/terminal-pty.js uses — give the
        // shell a moment to finish its own startup/profile before typing
        // into it, or the command can arrive before the prompt is ready.
        var timer = new System.Windows.Threading.DispatcherTimer { Interval = TimeSpan.FromMilliseconds(300) };
        timer.Tick += (_, _) =>
        {
            timer.Stop();
            try
            {
                // PowerShell treats a bare quoted string as a string literal
                // to echo, not a command to run — needs the call operator.
                // Confirmed live 2026-09-21: without it, the path just got
                // echoed back and the prompt returned instantly, nothing
                // launched.
                Term.ConPTYTerm.WriteToTerm($"& {ResolveClaudeCli()}\r");
                StatusLabel.Text = "";
            }
            catch (Exception ex)
            {
                StatusLabel.Text = $"error: {ex.Message}";
            }
        };
        timer.Start();
    }

    // Bare "claude" / "claude.cmd" isn't reliably found in the freshly
    // spawned ConPTY child shell even when it resolves fine in an ordinary
    // interactive session — confirmed live 2026-09-21 ("not recognized"),
    // most likely the terminal control not passing through this process's
    // full PATH to the child. Sidestep the question entirely with an
    // absolute path. This machine's real install is a native binary at
    // ~/.local/bin/claude.exe, NOT the npm-global claude.cmd
    // dashboard/main.js assumes — check both, plus PATH, in that order.
    private static string ResolveClaudeCli()
    {
        string[] candidates =
        {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".local", "bin", "claude.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "npm", "claude.cmd"),
        };
        foreach (var c in candidates)
        {
            if (File.Exists(c)) return $"\"{c}\"";
        }
        return "claude";
    }

    // Same resolution order as dashboard/terminal-pty.js's resolveShell() —
    // prefer a real PowerShell 7 install, fall back to Windows PowerShell.
    private static string ResolveShell()
    {
        string[] candidates =
        {
            @"C:\Program Files\PowerShell\7\pwsh.exe",
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Microsoft", "WindowsApps", "pwsh.exe"),
        };
        foreach (var c in candidates)
        {
            if (File.Exists(c)) return $"\"{c}\"";
        }
        return "powershell.exe";
    }

    private void Restart_Click(object sender, RoutedEventArgs e)
    {
        Term.RestartTerm();
        LaunchClaudeSession();
    }

    private void TitleBar_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        // No native title bar (WindowStyle=None) and this window's position
        // is owner-synced by MainWindow, so dragging here is deliberately a
        // no-op rather than fighting the sync loop — drag the main HUD
        // window's title strip instead, this one follows.
    }
}

using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using WinForms = System.Windows.Forms;

namespace Hud;

/// <summary>
/// The Console lives in the system tray (Jerry 2026-10-07: "the console can be system tray only-ish",
/// "use our asset bird"). Click the Phoenix bird = the Console; right-click = the quick buttons.
/// Every item respects the edition (HudProfile): a game edition never lists Jerry's tools.
/// </summary>
public sealed class TrayIcon : IDisposable
{
    private readonly WinForms.NotifyIcon _icon;

    public TrayIcon()
    {
        var p = HudProfile.Current;
        _icon = new WinForms.NotifyIcon
        {
            Icon = LoadBird(),
            Text = p.Edition == "full" ? "Phoenix - click for the Console" : "Phoenix",
            Visible = true,
            ContextMenuStrip = new WinForms.ContextMenuStrip(),
        };
        var m = _icon.ContextMenuStrip;
        void item(string text, Action act) => m.Items.Add(text, null, (_, _) => Application.Current.Dispatcher.Invoke(act));

        if (p.Console) item("Open the Console", App.OpenConsole);
        item("Run…", RunBox.Open);
        if (p.Intake) item("Suit look-up…", () => SuitLookup.Open());
        item("Chat (drop it down from the eye)", App.ToggleHud);
        if (p.Jarvis) item("Ask Jarvis…", () => App.Overlay?.StartJarvisAsk());
        item("Screenshot for Claude", SnapForClaude);
        m.Items.Add(new WinForms.ToolStripSeparator());
        item("Quit the HUD", () => Application.Current.Shutdown());

        _icon.MouseClick += (_, e) =>
        {
            if (e.Button == WinForms.MouseButtons.Left)
                Application.Current.Dispatcher.Invoke(() => { if (p.Console) App.OpenConsole(); else App.ToggleHud(); });
        };
    }

    private static System.Drawing.Icon LoadBird()
    {
        var f = Path.Combine(AppContext.BaseDirectory, "phoenix.ico");
        try { if (File.Exists(f)) return new System.Drawing.Icon(f, 32, 32); } catch { }
        return System.Drawing.SystemIcons.Application;
    }

    private static void SnapForClaude()
    {
        var repo = Environment.GetEnvironmentVariable("PHOENIX_ROOT") ?? @"F:\Phoenix\Phoenix-DevOps-oS";
        var psi = new ProcessStartInfo("pwsh") { UseShellExecute = false, CreateNoWindow = true };
        foreach (var a in new[] { "-NoProfile", "-Sta", "-ExecutionPolicy", "Bypass", "-File", Path.Combine(repo, "scripts", "snap-to-claude.ps1") })
            psi.ArgumentList.Add(a);
        try { Process.Start(psi); } catch { }
    }

    public void Dispose() { _icon.Visible = false; _icon.Dispose(); }
}

/// <summary>A Run box like Windows' Win+R (Jerry 10/7): a program, a path, a URL or a command line.</summary>
public sealed class RunBox : Window
{
    private static RunBox? _open;
    private readonly TextBox _input;
    private readonly TextBlock _note;
    private static readonly List<string> History = new();

    public static void Open()
    {
        if (_open is { IsLoaded: true }) { _open.Activate(); return; }
        _open = new RunBox();
        _open.Show();
        _open.Activate();
    }

    private RunBox()
    {
        Title = "Run"; Width = 460; SizeToContent = SizeToContent.Height; ResizeMode = ResizeMode.NoResize;
        WindowStartupLocation = WindowStartupLocation.CenterScreen; Topmost = true;
        Background = new SolidColorBrush(Color.FromRgb(0x0A, 0x0D, 0x10));
        var amber = new SolidColorBrush(Color.FromRgb(0xFF, 0xCC, 0x00));
        var panel = new StackPanel { Margin = new Thickness(14) };
        panel.Children.Add(new TextBlock { Text = "Type a program, folder, file, web address or command, and Phoenix opens it.",
                                           Foreground = amber, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 8) });
        _input = new TextBox { FontFamily = new FontFamily("Consolas"), FontSize = 14, Padding = new Thickness(6, 4, 6, 4),
                               Background = new SolidColorBrush(Color.FromRgb(0x14, 0x18, 0x1C)), Foreground = amber, CaretBrush = amber };
        if (History.Count > 0) { _input.Text = History[^1]; _input.SelectAll(); }
        _input.KeyDown += (_, e) =>
        {
            if (e.Key == Key.Enter) Go();
            else if (e.Key == Key.Escape) Close();
        };
        panel.Children.Add(_input);
        _note = new TextBlock { Foreground = Brushes.IndianRed, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 6, 0, 0) };
        panel.Children.Add(_note);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 10, 0, 0) };
        var ok = new Button { Content = "Run", Width = 80, Margin = new Thickness(0, 0, 8, 0), IsDefault = true };
        ok.Click += (_, _) => Go();
        var cancel = new Button { Content = "Cancel", Width = 80, IsCancel = true };
        buttons.Children.Add(ok); buttons.Children.Add(cancel);
        panel.Children.Add(buttons);
        Content = panel;
        Loaded += (_, _) => _input.Focus();
        Closed += (_, _) => _open = null;
    }

    private void Go()
    {
        var text = _input.Text.Trim();
        if (text.Length == 0) return;
        var (ok, why) = Launch(text);
        if (!ok) { _note.Text = why; return; }
        History.Remove(text); History.Add(text);
        Close();
    }

    /// <summary>Win+R semantics: a whole path or URL first, else "program arguments".</summary>
    internal static (bool Ok, string Why) Launch(string text)
    {
        var whole = Environment.ExpandEnvironmentVariables(text.Trim().Trim('"'));
        try
        {
            if (File.Exists(whole) || Directory.Exists(whole) || Uri.TryCreate(whole, UriKind.Absolute, out var u) && u.Scheme is "http" or "https")
            {
                Process.Start(new ProcessStartInfo(whole) { UseShellExecute = true });
                return (true, "");
            }
            string program, args;
            if (text.StartsWith('"')) { var end = text.IndexOf('"', 1); program = end > 0 ? text[1..end] : text.Trim('"'); args = end > 0 ? text[(end + 1)..].Trim() : ""; }
            else { var sp = text.IndexOf(' '); program = sp > 0 ? text[..sp] : text; args = sp > 0 ? text[(sp + 1)..].Trim() : ""; }
            Process.Start(new ProcessStartInfo(Environment.ExpandEnvironmentVariables(program), args) { UseShellExecute = true });
            return (true, "");
        }
        catch (Exception e) { return (false, $"Windows can't find '{text}'. ({e.Message})"); }
    }
}

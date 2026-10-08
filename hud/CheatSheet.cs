using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using Hud.Desktop;

namespace Hud;

/// <summary>
/// The commands cheat sheet (Jerry 10/8: "there needs to be a commands cheat sheet" ... "button" ...
/// "not everyone is going to have my desktop"). Its own window, so it doesn't depend on anyone's Desktop:
/// the aliases + docs\COMMANDS.md from the repo when this machine has it, else COMMANDS.md from the pool
/// (custody-checked, same as the Glossary). Type to filter; Esc closes.
/// </summary>
public sealed class CheatSheet : Window
{
    private static CheatSheet? _open;
    private static readonly Brush Bg = new SolidColorBrush(Color.FromRgb(0x0A, 0x0D, 0x10));
    private static readonly Brush Panel = new SolidColorBrush(Color.FromRgb(0x14, 0x18, 0x1C));
    private static readonly Brush Fg = new SolidColorBrush(Color.FromRgb(0x7F, 0xFF, 0xD4));
    private static readonly Brush Amber = new SolidColorBrush(Color.FromRgb(0xFF, 0xCC, 0x00));
    private static readonly Brush Dim = new SolidColorBrush(Color.FromRgb(0x5A, 0x7A, 0x70));

    private readonly TextBox _filter, _text;
    private readonly TextBlock _source;
    private string[] _lines = Array.Empty<string>();

    public static void Open()
    {
        if (_open is not { IsLoaded: true }) { _open = new CheatSheet(); _open.Show(); }
        _open.Activate();
    }

    private CheatSheet()
    {
        Title = "Phoenix commands"; Width = 1000; Height = 700; Background = Bg;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        var mono = new FontFamily("Consolas");
        var root = new DockPanel { Margin = new Thickness(12) };

        var top = new DockPanel { Margin = new Thickness(0, 0, 0, 8) };
        top.Children.Add(new TextBlock { Text = "Filter:", Foreground = Fg, FontFamily = mono, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 8, 0) });
        _filter = new TextBox { FontFamily = mono, FontSize = 14, Padding = new Thickness(6, 3, 6, 3), Background = Panel, Foreground = Amber, CaretBrush = Amber };
        _filter.TextChanged += (_, _) => Show(_filter.Text.Trim());
        _filter.KeyDown += (_, e) => { if (e.Key == Key.Escape) Close(); };
        top.Children.Add(_filter);
        DockPanel.SetDock(top, Dock.Top);
        root.Children.Add(top);

        _source = new TextBlock { Foreground = Dim, FontFamily = mono, Margin = new Thickness(0, 6, 0, 0) };
        DockPanel.SetDock(_source, Dock.Bottom);
        root.Children.Add(_source);

        _text = new TextBox { IsReadOnly = true, FontFamily = mono, FontSize = 12, Background = Panel, Foreground = Fg, BorderThickness = new Thickness(0),
                              TextWrapping = TextWrapping.NoWrap, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto };
        root.Children.Add(_text);
        Content = root;
        Loaded += async (_, _) => { _filter.Focus(); await Load(); };
        Closed += (_, _) => _open = null;
    }

    private async Task Load()
    {
        _source.Text = "loading…";
        var repo = FileActions.RepoRoot;
        var md = Path.Combine(repo, "docs", "COMMANDS.md");
        var aliases = Path.Combine(repo, "scripts", "phoenix-aliases.ps1");
        string text, from;
        // First choice: `usys help` itself - the easy one-word commands, never out of step with usys.
        if (await UsysHelpAsync() is { Length: > 200 } help)
        {
            text = help;
            from = "from usys help (this machine's Phoenix)";
        }
        else if (File.Exists(md))
        {
            var card = File.Exists(aliases)
                ? File.ReadLines(aliases).Take(40).Where(l => l.StartsWith("#   ") && l.Length > 4 && l[4] != ' ')
                      .Select(l => "  " + l.TrimStart('#').Trim())
                : Enumerable.Empty<string>();
            text = "QUICK CARD - aliases\n" + string.Join("\n", card) + "\n\n" + await File.ReadAllTextAsync(md);
            from = $"from this machine's Phoenix: {md}";
        }
        else
        {
            // No repo here: the pool's copy, custody-checked (PoolClient refuses a mismatch).
            var (hits, err) = await PoolClient.SearchAsync("COMMANDS.md", suitsOnly: false);
            var row = hits.FirstOrDefault(h => h.InPool && h.Name.EndsWith("COMMANDS.md", StringComparison.OrdinalIgnoreCase));
            if (row is null) { _source.Text = err ?? "COMMANDS.md isn't on this machine or in the pool."; return; }
            var (code, note) = await PoolClient.FetchCodeAsync(row);
            if (code is null) { _source.Text = note; return; }
            text = code; from = $"from the pool: {row.Name} {row.Version} - {note}";
        }
        _lines = text.Replace("\r\n", "\n").Split('\n');
        _source.Text = from + "   (type to filter, Esc closes)";
        Show(_filter.Text.Trim());
    }

    private static async Task<string?> UsysHelpAsync()
    {
        try
        {
            var psi = new System.Diagnostics.ProcessStartInfo("pwsh")
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            foreach (var a in new[] { "-NoProfile", "-NoLogo", "-File", UsysButtons.UsysScript, "help" }) psi.ArgumentList.Add(a);
            using var p = System.Diagnostics.Process.Start(psi)!;
            var outTask = p.StandardOutput.ReadToEndAsync();
            _ = p.StandardError.ReadToEndAsync();
            if (!p.WaitForExit(20_000)) { try { p.Kill(); } catch { } return null; }
            return await outTask;
        }
        catch { return null; }
    }

    private void Show(string word) =>
        _text.Text = word.Length == 0 ? string.Join("\n", _lines)
            : string.Join("\n", _lines.Where(l => l.Contains(word, StringComparison.OrdinalIgnoreCase)));
}

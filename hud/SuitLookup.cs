using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using Hud.Desktop;

namespace Hud;

/// <summary>
/// Suit look-up (Console list item 1, Jerry 2026-10-07; replaces the dashboard's clone pool look-up).
/// Type a name or what it does; pick a suit; read its code (read-only, custody-checked) or Import it,
/// which is `genie import` (custody -> RAM -> run) in a PS7 window so the answer stays on screen.
/// Full edition only: a game build never lists Jerry's pool.
/// </summary>
public sealed class SuitLookup : Window
{
    private static SuitLookup? _open, _glossary;
    private readonly bool _isGlossary;   // the Glossary: every file in the pool, read-only, no Import
    private static readonly Brush Bg = new SolidColorBrush(Color.FromRgb(0x0A, 0x0D, 0x10));
    private static readonly Brush Panel = new SolidColorBrush(Color.FromRgb(0x14, 0x18, 0x1C));
    private static readonly Brush Fg = new SolidColorBrush(Color.FromRgb(0x7F, 0xFF, 0xD4));
    private static readonly Brush Amber = new SolidColorBrush(Color.FromRgb(0xFF, 0xCC, 0x00));
    private static readonly Brush Dim = new SolidColorBrush(Color.FromRgb(0x5A, 0x7A, 0x70));

    private readonly TextBox _query;
    private readonly ListBox _list;
    private readonly TextBlock _status, _what, _note;
    private readonly TextBox _code;
    private readonly Button _import;
    private int _searchGen, _codeGen;

    public static void Open(string? word = null)
    {
        if (!HudProfile.Current.Intake) return;
        if (_open is not { IsLoaded: true }) { _open = new SuitLookup(false); _open.Show(); }
        _open.Activate();
        if (!string.IsNullOrWhiteSpace(word)) { _open._query.Text = word; _ = _open.Search(); }
    }

    /// <summary>The Glossary (Console list item 2, Jerry 10/8: "glossary needs to show code"): any file in
    /// the pool or Atlas by name or what it does, its code shown read-only and custody-checked.</summary>
    public static void OpenGlossary(string? word = null)
    {
        if (!HudProfile.Current.Intake) return;
        if (_glossary is not { IsLoaded: true }) { _glossary = new SuitLookup(true); _glossary.Show(); }
        _glossary.Activate();
        if (!string.IsNullOrWhiteSpace(word)) { _glossary._query.Text = word; _ = _glossary.Search(); }
    }

    private SuitLookup(bool glossary)
    {
        _isGlossary = glossary;
        Title = glossary ? "Glossary" : "Suit look-up"; Width = 980; Height = 640; Background = Bg; Topmost = false;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        var mono = new FontFamily("Consolas");

        var root = new DockPanel { Margin = new Thickness(12) };
        var top = new DockPanel { Margin = new Thickness(0, 0, 0, 8) };
        top.Children.Add(new TextBlock { Text = glossary ? "Find anything in Phoenix (name or what it does):" : "Find a suit (name or what it does):", Foreground = Fg, FontFamily = mono,
                                         VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 8, 0) });
        _query = new TextBox { FontFamily = mono, FontSize = 14, Padding = new Thickness(6, 3, 6, 3), Background = Panel, Foreground = Amber, CaretBrush = Amber };
        _query.KeyDown += (_, e) => { if (e.Key == Key.Enter) _ = Search(); else if (e.Key == Key.Escape) Close(); };
        top.Children.Add(_query);
        DockPanel.SetDock(top, Dock.Top);
        root.Children.Add(top);

        _status = new TextBlock { Foreground = Dim, FontFamily = mono, Margin = new Thickness(0, 6, 0, 0), TextWrapping = TextWrapping.Wrap,
                                  Text = "Enter searches the pool by name and Atlas by description." };
        DockPanel.SetDock(_status, Dock.Bottom);
        root.Children.Add(_status);

        var grid = new Grid();
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(360) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

        _list = new ListBox { Background = Panel, Foreground = Fg, FontFamily = mono, BorderThickness = new Thickness(0) };
        _list.SelectionChanged += (_, _) => _ = ShowSelected();
        _list.MouseDoubleClick += (_, _) => { if (!_isGlossary) Import(); };
        grid.Children.Add(_list);

        var right = new DockPanel { Margin = new Thickness(10, 0, 0, 0) };
        Grid.SetColumn(right, 1);
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 6) };
        _import = new Button { Content = "Import (run)", Padding = new Thickness(10, 3, 10, 3), Margin = new Thickness(0, 0, 8, 0), IsEnabled = false,
                               ToolTip = "genie import: pulled from R2 into RAM, SHA3-checked against custody, run once" };
        _import.Click += (_, _) => Import();
        var copy = new Button { Content = "Copy name", Padding = new Thickness(10, 3, 10, 3) };
        copy.Click += (_, _) => { if (_list.SelectedItem is ListBoxItem { Tag: PoolClient.Suit s }) Clipboard.SetText(s.Name); };
        if (!glossary) actions.Children.Add(_import);
        actions.Children.Add(copy);
        DockPanel.SetDock(actions, Dock.Top);
        right.Children.Add(actions);
        _what = new TextBlock { Foreground = Amber, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 6), MaxHeight = 120 };
        DockPanel.SetDock(_what, Dock.Top);
        right.Children.Add(_what);
        _note = new TextBlock { Foreground = Dim, FontFamily = mono, Margin = new Thickness(0, 0, 0, 4) };
        DockPanel.SetDock(_note, Dock.Top);
        right.Children.Add(_note);
        _code = new TextBox { IsReadOnly = true, IsReadOnlyCaretVisible = true, FontFamily = mono, FontSize = 12, Background = Panel, Foreground = Fg,
                              BorderThickness = new Thickness(0), AcceptsReturn = true, TextWrapping = TextWrapping.NoWrap,
                              VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto };
        right.Children.Add(_code);
        grid.Children.Add(right);
        root.Children.Add(grid);

        Content = root;
        Loaded += (_, _) => _query.Focus();
        Closed += (_, _) => { if (_isGlossary) _glossary = null; else _open = null; };
    }

    private async Task Search()
    {
        var word = _query.Text.Trim();
        if (word.Length < 2) { _status.Text = "Type at least 2 letters."; return; }
        var gen = ++_searchGen;
        _status.Text = $"searching the pool and Atlas for \"{word}\"…";
        var (suits, error) = await PoolClient.SearchAsync(word, suitsOnly: !_isGlossary);
        if (gen != _searchGen) return;   // a newer search is running
        _list.Items.Clear();
        foreach (var s in suits)
        {
            var item = new StackPanel();
            item.Children.Add(new TextBlock { Text = s.Line, Foreground = (_isGlossary ? s.InPool : s.Importable) ? Fg : Dim });
            if (s.What.Length > 0)
                item.Children.Add(new TextBlock { Text = s.What.Length > 70 ? s.What[..70] + "…" : s.What, Foreground = Dim, FontSize = 11 });
            _list.Items.Add(new ListBoxItem { Content = item, Tag = s, Padding = new Thickness(2, 3, 2, 3) });
        }
        var count = _isGlossary
            ? (suits.Count == 0 ? $"nothing for \"{word}\"" : $"{suits.Count} file(s) for \"{word}\" - pick one to read its code")
            : (suits.Count == 0 ? $"no suits for \"{word}\"" : $"{suits.Count} suit(s) for \"{word}\" - double-click or Import to run one");
        _status.Text = error is null ? count : suits.Count == 0 ? error : $"{count}  ({error})";
        if (_list.Items.Count > 0) _list.SelectedIndex = 0;
    }

    private async Task ShowSelected()
    {
        if (_list.SelectedItem is not ListBoxItem { Tag: PoolClient.Suit s }) { _import.IsEnabled = false; return; }
        var gen = ++_codeGen;
        _import.IsEnabled = s.Importable && !_isGlossary;
        _what.Text = (s.What.Length > 0 ? s.What : "No description yet (Atlas has no entry for it).")
                     + (s.RepoPath.Length > 0 ? $"\n{s.RepoPath}" : "")
                     + (_isGlossary ? (s.InPool ? "" : "\nNot in the pool yet: the repo copy is shown.")
                        : s.Importable ? "" : !s.InPool ? "\nNot in the pool yet: intake it, then it can be imported."
                                                      : "\nRead-only here: in-RAM import is Python-only.");
        _note.Text = "fetching the code…";
        _code.Text = "";
        var (code, note) = await PoolClient.FetchCodeAsync(s);
        if (gen != _codeGen) return;
        _note.Text = note;
        _code.Text = code ?? "";
    }

    private void Import()
    {
        if (_list.SelectedItem is not ListBoxItem { Tag: PoolClient.Suit s } || !s.Importable || !PoolClient.IsHex(s.Hex)) return;
        var (ok, why) = RunGenie("import", s.Hex);
        _status.Text = ok ? $"importing {s.Name} - the answer shows in the PS7 window" : why;
    }

    /// <summary>
    /// A genie command in its own PS7 window that stays open. Arguments are hex ids only (checked by the caller),
    /// never free text, so nothing typed here reaches a shell.
    /// </summary>
    internal static (bool ok, string why) RunGenie(string verb, string hex)
    {
        var genie = Path.Combine(FileActions.RepoRoot, "sector1", "kernel", "genie", "genie.ps1");
        if (!File.Exists(genie)) return (false, $"genie isn't at {genie}");
        var psi = new ProcessStartInfo("pwsh") { UseShellExecute = false, CreateNoWindow = false };   // its own console window
        foreach (var a in new[] { "-NoExit", "-NoProfile", "-Command", $". '{genie}'; genie {verb} {hex}" })
            psi.ArgumentList.Add(a);
        try { Process.Start(psi); return (true, ""); }
        catch (Exception e) { return (false, $"couldn't start PS7: {e.Message}"); }
    }
}

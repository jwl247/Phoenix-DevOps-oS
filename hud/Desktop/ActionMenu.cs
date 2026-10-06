using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace Hud.Desktop;

/// <summary>
/// The drop-down: what you can do with whatever was dropped (or right-clicked in Explorer).
/// One menu for every door, all actions through FileActions. "Ask Claude" hands the paths
/// to the HUD chat instead of acting, so a question about a file never moves it.
/// </summary>
public static class ActionMenu
{
    private static readonly Brush Bg = new SolidColorBrush(Color.FromRgb(0x0A, 0x0D, 0x10));
    private static readonly Brush Fg = new SolidColorBrush(Color.FromRgb(0x7F, 0xFF, 0xD4));

    /// <param name="paths">files/folders dropped</param>
    /// <param name="report">one line per result, shown in the HUD chat</param>
    /// <param name="askClaude">puts the paths into the chat input</param>
    public static ContextMenu Build(IReadOnlyList<string> paths, Action<string> report, Action<IReadOnlyList<string>> askClaude)
    {
        var what = paths.Count == 1 ? Path.GetFileName(paths[0].TrimEnd('\\')) : $"{paths.Count} items";
        var m = new ContextMenu { Background = Bg, Foreground = Fg, FontFamily = new FontFamily("Consolas") };
        m.Items.Add(new MenuItem { Header = what, IsEnabled = false, FontWeight = FontWeights.Bold });
        m.Items.Add(new Separator());

        Add(m, "Ask Claude about it", () => askClaude(paths));
        Add(m, "Copy to Phoenix place…", () => Pick("Copy", dest => Each(paths, p => FileActions.CopyTo(p, dest), report)));
        Add(m, "Move to Phoenix place…", () => Pick("Move", dest => Each(paths, p => FileActions.MoveTo(p, dest), report)));
        Add(m, "Send to pbmIII", () => Each(paths, FileActions.SendToThirdBox, report));
        Add(m, "Intake to the clone pool", async () =>
        {
            foreach (var p in paths)
            {
                report($"[ACT] intaking {Path.GetFileName(p.TrimEnd('\\'))}…");
                var r = await FileActions.IntakeAsync(p);
                report((r.Ok ? "[ACT] " : "[ACT FAILED] ") + r.Message);
            }
        });
        m.Items.Add(new Separator());
        if (paths.Count == 1)
            Add(m, "Rename…", () =>
            {
                var name = Ask("Rename", "New name:", Path.GetFileName(paths[0].TrimEnd('\\')));
                if (name is not null) Show(FileActions.Rename(paths[0], name), report);
            });
        Add(m, "New folder here…", () =>
        {
            var name = Ask("New folder", "Folder name:", "New folder");
            if (name is not null) Show(FileActions.NewFolder(paths[0], name), report);
        });
        Add(m, "Show in Explorer", () => Show(FileActions.ShowInExplorer(paths[0]), report));
        return m;
    }

    private static void Add(ContextMenu m, string header, Action act)
    {
        var item = new MenuItem { Header = header, Background = Bg, Foreground = Fg };
        item.Click += (_, _) => act();
        m.Items.Add(item);
    }

    private static void Each(IReadOnlyList<string> paths, Func<string, FileActions.Result> act, Action<string> report)
    {
        foreach (var p in paths) Show(act(p), report);
    }

    private static void Show(FileActions.Result r, Action<string> report) =>
        report((r.Ok ? "[ACT] " : "[ACT FAILED] ") + r.Message);

    private static void Pick(string verb, Action<string> then)
    {
        var dest = PlacePicker.Show(verb);
        if (dest is not null) then(dest);
    }

    /// <summary>A one-line prompt; null on cancel.</summary>
    internal static string? Ask(string title, string label, string initial)
    {
        var box = new TextBox { Text = initial, Margin = new Thickness(0, 6, 0, 10), Background = Bg, Foreground = Fg,
                                CaretBrush = Fg, FontFamily = new FontFamily("Consolas"), Padding = new Thickness(4) };
        var ok = new Button { Content = "OK", IsDefault = true, Width = 70, Margin = new Thickness(0, 0, 8, 0) };
        var cancel = new Button { Content = "Cancel", IsCancel = true, Width = 70 };
        var w = new Window
        {
            Title = title, Width = 380, SizeToContent = SizeToContent.Height, WindowStartupLocation = WindowStartupLocation.CenterScreen,
            Topmost = true, ResizeMode = ResizeMode.NoResize, Background = Bg,
            Content = new StackPanel
            {
                Margin = new Thickness(14),
                Children =
                {
                    new TextBlock { Text = label, Foreground = Fg, FontFamily = new FontFamily("Consolas") }, box,
                    new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Children = { ok, cancel } },
                },
            },
        };
        ok.Click += (_, _) => w.DialogResult = true;
        w.Loaded += (_, _) => { box.Focus(); box.SelectAll(); };
        return w.ShowDialog() == true ? box.Text : null;
    }
}

/// <summary>Where should it go? Atlas search + the fixed places + Browse.</summary>
public static class PlacePicker
{
    private static readonly Brush Bg = new SolidColorBrush(Color.FromRgb(0x0A, 0x0D, 0x10));
    private static readonly Brush Fg = new SolidColorBrush(Color.FromRgb(0x7F, 0xFF, 0xD4));
    private static readonly Brush Dim = new SolidColorBrush(Color.FromRgb(0x5A, 0x7A, 0x70));

    public static string? Show(string verb)
    {
        string? chosen = null;
        var search = new TextBox { Background = Bg, Foreground = Fg, CaretBrush = Fg, FontFamily = new FontFamily("Consolas"), Padding = new Thickness(4) };
        var list = new ListBox { Background = Bg, Foreground = Fg, Height = 320, FontFamily = new FontFamily("Consolas"), BorderBrush = Dim };
        var status = new TextBlock { Foreground = Dim, FontFamily = new FontFamily("Consolas"), Margin = new Thickness(0, 4, 0, 4) };
        var browse = new Button { Content = "Browse…", Width = 90, Margin = new Thickness(0, 0, 8, 0) };
        var ok = new Button { Content = verb, IsDefault = true, Width = 90, Margin = new Thickness(0, 0, 8, 0) };
        var cancel = new Button { Content = "Cancel", IsCancel = true, Width = 90 };
        var w = new Window
        {
            Title = $"{verb} to… (type to ask Atlas)", Width = 620, SizeToContent = SizeToContent.Height,
            WindowStartupLocation = WindowStartupLocation.CenterScreen, Topmost = true, Background = Bg,
            Content = new StackPanel
            {
                Margin = new Thickness(14),
                Children =
                {
                    new TextBlock { Text = "Search Phoenix (Atlas):", Foreground = Fg, FontFamily = new FontFamily("Consolas") },
                    search, status, list,
                    new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right,
                                     Margin = new Thickness(0, 10, 0, 0), Children = { browse, ok, cancel } },
                },
            },
        };

        void Fill(IEnumerable<AtlasClient.Place> places)
        {
            list.Items.Clear();
            foreach (var p in places)
            {
                var row = new StackPanel { Tag = p.FullPath, Margin = new Thickness(0, 2, 0, 2) };
                row.Children.Add(new TextBlock { Text = $"{p.Name}   [{p.Area}]", Foreground = Fg });
                row.Children.Add(new TextBlock { Text = p.FullPath + (p.Note.Length > 0 ? "  —  " + p.Note : ""), Foreground = Dim, FontSize = 11 });
                list.Items.Add(row);
            }
            if (list.Items.Count > 0) list.SelectedIndex = 0;
        }
        Fill(AtlasClient.FixedPlaces());
        status.Text = "Fixed places. Type a word (sector2, mesh, game…) for Atlas.";

        var gen = 0;
        search.TextChanged += async (_, _) =>
        {
            var my = ++gen;
            var word = search.Text.Trim();
            if (word.Length < 2) { Fill(AtlasClient.FixedPlaces()); return; }
            await Task.Delay(250);                       // typing pause before asking
            if (my != gen) return;
            status.Text = "asking Atlas…";
            var (places, error) = await AtlasClient.SearchAsync(word);
            if (my != gen) return;
            var fixedHits = AtlasClient.FixedPlaces().Where(p => p.Name.Contains(word, StringComparison.OrdinalIgnoreCase));
            Fill(fixedHits.Concat(places));
            status.Text = error ?? $"{places.Count} Atlas place(s) for \"{word}\"";
        };
        void Accept()
        {
            if (list.SelectedItem is StackPanel { Tag: string path }) { chosen = path; w.DialogResult = true; }
        }
        ok.Click += (_, _) => Accept();
        list.MouseDoubleClick += (_, _) => Accept();
        browse.Click += (_, _) =>
        {
            var d = new Microsoft.Win32.OpenFolderDialog { Title = $"{verb} to…" };
            if (d.ShowDialog(w) == true) { chosen = d.FolderName; w.DialogResult = true; }
        };
        search.KeyDown += (_, e) => { if (e.Key == Key.Down && list.Items.Count > 0) { list.Focus(); } };
        w.Loaded += (_, _) => search.Focus();
        return w.ShowDialog() == true ? chosen : null;
    }
}

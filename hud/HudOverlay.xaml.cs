using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using Hud.Desktop;
using Hud.Voice;

namespace Hud;

/// <summary>
/// The HUD (Jerry, 2026-10-07, docs/plans/hud-eye-and-docks.md): the EYE is the only thing always on
/// screen and voice is the main way to talk. Click the eye and the chat drops down; right-click it for
/// Jarvis and the Console. The docks are NOT PRESENT until you ask for them ("open the dock", "expose
/// the right dock", "close the dock" - spoken or typed): a second lock, nothing on screen reacts to a
/// stray drag (Jerry 10/7, like "turn on the radar" in the game). Each dock is a drop-down tree of
/// places - drag out of it to anywhere, drop onto it to intake or ask. Everything else is transparent, so the desktop works underneath.
/// What this edition may use comes from HudProfile (Jerry's tools vs a game's).
/// Ctrl+Alt+Space drops the chat down / folds it away.
/// </summary>
public partial class HudOverlay : Window
{
    private readonly List<string> _lines = new();
    private readonly List<string> _attached = new();
    private readonly HudProfile _profile = HudProfile.Current;
    private static readonly string LogPath = Path.Combine(@"E:\", "Phoenix", "hud-live-monitor", "hud-chat-log.txt");

    private const int HotkeyId = 0x5048;            // "PH"
    private const uint MOD_ALT = 0x1, MOD_CONTROL = 0x2, MOD_NOREPEAT = 0x4000, VK_SPACE = 0x20;
    [DllImport("user32.dll")] private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint mods, uint vk);
    [DllImport("user32.dll")] private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    private const double DockOpenWidth = 330;

    // Security's lock over the docks (Jerry 10/7: "lockable by security"): set by `security lock-hud`
    // (the sensor, CLI-only, chained as an alert). While it exists no dock opens, and any open dock
    // closes the moment it appears.
    private static readonly string SecurityDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".phoenix", "security");
    private static readonly string HudLockFile = Path.Combine(SecurityDir, "hud-locked");
    private FileSystemWatcher? _lockWatch;
    internal static bool DocksLocked => File.Exists(HudLockFile);
    private Point _dragStart;
    private TreeViewItem? _dragItem;

    public HudOverlay()
    {
        InitializeComponent();
        var work = SystemParameters.WorkArea;
        Left = work.Left; Top = work.Top; Width = work.Width; Height = work.Height;
        Header.Text = _profile.Edition == "full" ? $"CLAUDE · {App.Ai.Config.Provider}" : "PHOENIX";
        _lines.Add("[SYS] Hold Right Ctrl to talk. Click the eye for this chat, right-click it for the docks"
                   + (_profile.Jarvis ? ", Jarvis" : "") + (_profile.Console ? " and the Console" : "")
                   + ". Say \"open the dock\" (or left/right dock) to bring the docks out; \"close the dock\" puts them away.");
        if (_profile.Jarvis) _lines.Add("[SYS] Start a message with \"Jarvis\" (typed or spoken) to ask him instead.");
        App.Ai.Note += line => Dispatcher.BeginInvoke(() => Add(line));
        WireVoice();
        FillTree(TreeLeft, _profile.LeftPlaces);                        // home on the left
        FillTree(TreeRight, _profile.RightPlaces);                      // the roots on the right
        Bar.SetState(VoiceState.Idle);
        WatchSecurityLock();
        Refresh();
        SourceInitialized += (_, _) =>
        {
            var h = new WindowInteropHelper(this).Handle;
            if (!RegisterHotKey(h, HotkeyId, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_SPACE))
                Add("[SYS] Ctrl+Alt+Space is taken by another program; click the eye instead.");
            HwndSource.FromHwnd(h).AddHook(WndProc);
        };
        Closed += (_, _) => UnregisterHotKey(new WindowInteropHelper(this).Handle, HotkeyId);
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == 0x0312 && wParam.ToInt32() == HotkeyId) { ToggleChat(); handled = true; }   // WM_HOTKEY
        return IntPtr.Zero;
    }

    // ------------------------------------------------------------ voice: the main way in
    private void WireVoice()
    {
        var v = App.Voice;
        if (v is null) { Add("[SYS] Voice isn't available; type in the chat."); return; }
        v.StateChanged += s => Dispatcher.Invoke(() => Bar.SetState(s));
        v.TranscriptReady += t => Dispatcher.Invoke(() => _ = AskAsync(t, speak: true));
        v.Note += line => Dispatcher.BeginInvoke(() => Add($"[SYS] {line}"));
        Add(v.UnavailableReason is null ? $"[SYS] {v.ArmedLine}" : $"[SYS] {v.UnavailableReason}");
    }

    // ------------------------------------------------------------ the eye
    private void Eye_Click(object sender, MouseButtonEventArgs e) => ToggleChat();

    private void Eye_RightClick(object sender, MouseButtonEventArgs e)
    {
        var m = new ContextMenu { Background = new SolidColorBrush(Color.FromRgb(0x0A, 0x0D, 0x10)),
                                  Foreground = (Brush)FindResource("Amber"), FontFamily = new FontFamily("Consolas") };
        void item(string header, Action act) { var i = new MenuItem { Header = header }; i.Click += (_, _) => act(); m.Items.Add(i); }
        item(ChatPanel.IsVisible ? "Fold the chat away" : "Open the chat", ToggleChat);
        if (_profile.Jarvis) item("Ask Jarvis…", StartJarvisAsk);
        if (_profile.Console) item("Open the Console", App.OpenConsole);
        m.Items.Add(new Separator());
        item("Quit the HUD", () => Application.Current.Shutdown());
        m.PlacementTarget = EyeFrame;
        m.IsOpen = true;
        e.Handled = true;
    }

    /// <summary>Opens the chat with "Jarvis, " ready to finish (tray + eye menus).</summary>
    public void StartJarvisAsk()
    {
        OpenChat();
        ChatInput.Text = "Jarvis, ";
        ChatInput.CaretIndex = ChatInput.Text.Length;
    }

    // ------------------------------------------------------------ the chat (drop-down)
    public void ToggleChat() { if (ChatPanel.IsVisible) FoldChat(); else OpenChat(); }

    private void OpenChat()
    {
        ChatPanel.Visibility = Visibility.Visible;
        Activate();
        ChatInput.Focus();
        Refresh();
    }

    private void FoldChat() => ChatPanel.Visibility = Visibility.Collapsed;

    private void Hide_Click(object sender, RoutedEventArgs e) => FoldChat();

    private void ChatInput_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) { Send_Click(sender, e); e.Handled = true; }
        else if (e.Key == Key.Escape) FoldChat();
    }

    private async void Send_Click(object sender, RoutedEventArgs e)
    {
        var text = ChatInput.Text.Trim();
        if (text.Length == 0 && _attached.Count == 0) return;
        ChatInput.Clear();
        await AskAsync(text, speak: false);
    }

    /// <summary>One way in for typed and spoken questions. "Jarvis, ..." goes to Jarvis; the rest to Claude.</summary>
    private async Task AskAsync(string text, bool speak)
    {
        var files = _attached.ToList();
        _attached.Clear();
        Attached.Visibility = Visibility.Collapsed;

        // The docks only come out when asked (second lock): handled here, no round trip to the AI.
        if (DockCommand(text) is { } cmd)
        {
            Add($"[YOU] {text}");
            var docks = cmd.Which switch { "left" => new[] { Shelf }, "right" => new[] { ShelfRight }, _ => new[] { Shelf, ShelfRight } };
            if (cmd.Open && DocksLocked)
            {
                Add("[SECURITY] The docks are locked by security. Unlock them from a terminal: security unlock-hud");
                await Finish("The docks are locked by security.", speak);
                return;
            }
            foreach (var d in docks) { if (cmd.Open) OpenDock(d); else CloseDock(d); }
            var said = (cmd.Open ? "Dock open" : "Dock closed") + (cmd.Which is "left" or "right" ? $", {cmd.Which}." : ".");
            Add($"[SYS] {said}");
            await Finish(said, speak);
            return;
        }

        if (_profile.Jarvis && IsForJarvis(text, out var forJarvis))
        {
            Add($"[YOU → JARVIS] {forJarvis}");
            Bar.SetState(VoiceState.Thinking);
            var answer = await AskJarvisAsync(forJarvis);
            Add(answer.Ok ? $"[JARVIS] {answer.Text}" : $"[JARVIS · not answering] {answer.Text}");
            await Finish(answer.Ok ? answer.Text : "Jarvis isn't answering.", speak);
            return;
        }

        if (!_profile.ClaudeCodeTools)
        {
            Add("[SYS] This edition's companion isn't wired yet.");
            await Finish("", speak);
            return;
        }

        // Files go as exact paths; every Claude tier can Read them.
        var message = files.Count == 0 ? text
            : $"{(text.Length > 0 ? text : "Look at this.")}\n\nFiles (read them by path):\n" + string.Join("\n", files);
        var image = files.FirstOrDefault(f => new[] { ".png", ".jpg", ".jpeg", ".gif", ".webp" }
            .Contains(Path.GetExtension(f).ToLowerInvariant()));

        Add($"[YOU] {text}{(files.Count > 0 ? $"  (+{files.Count} file{(files.Count > 1 ? "s" : "")})" : "")}");
        var at = _lines.Count;
        Add("[CLAUDE] …");
        Bar.SetState(VoiceState.Thinking);
        var result = await App.Ai.SendAsync(message, image, chunk => Dispatcher.Invoke(() =>
        {
            _lines[at] = _lines[at] == "[CLAUDE] …" ? "[CLAUDE] " + chunk : _lines[at] + chunk;
            Refresh();
        }));
        if (result.Steps.Count > 0) { _lines.InsertRange(at, result.Steps.Select(s => $"[HANDS] {s}")); at += result.Steps.Count; }
        _lines[at] = result.Success
            ? (_lines[at] == "[CLAUDE] …" ? $"[CLAUDE · {result.Provider}] {result.Reply}" : _lines[at])
            : $"[ERROR · {result.Provider}] {result.Error}";
        Refresh();
        await Finish(result.Success ? result.Reply ?? "" : "", speak);
    }

    /// <summary>Back to idle, speaking the answer first when the question was spoken.</summary>
    private async Task Finish(string spoken, bool speak)
    {
        if (speak && App.Voice is not null) await App.Voice.SpeakReplyAsync(spoken);   // drives Speaking -> Idle
        else Bar.SetState(VoiceState.Idle);
    }

    /// <summary>"open the dock", "expose the right dock", "close both docks", "put the dock away"...</summary>
    internal static (bool Open, string Which)? DockCommand(string text)
    {
        var t = " " + text.ToLowerInvariant().Replace(",", " ").Replace(".", " ").Replace("!", " ") + " ";
        // speech-to-text hears "dock" as "door" (seen live 10/7) - take both
        if (!new[] { " dock ", " docks ", " door ", " doors " }.Any(t.Contains)) return null;
        if (t.Split(' ', StringSplitOptions.RemoveEmptyEntries).Length > 8) return null;   // a sentence ABOUT docks goes to the AI
        bool open = new[] { " open ", " expose ", " show ", " bring ", " turn on ", " pull " }.Any(t.Contains);
        bool close = new[] { " close ", " hide ", " away ", " turn off ", " shut " }.Any(t.Contains);
        if (open == close) return null;
        var which = t.Contains(" left ") ? "left" : t.Contains(" right ") ? "right" : "both";
        return (open, which);
    }

    internal static bool IsForJarvis(string text, out string rest)
    {
        var t = text.TrimStart();
        if (t.StartsWith("jarvis", StringComparison.OrdinalIgnoreCase) &&
            (t.Length == 6 || !char.IsLetterOrDigit(t[6])))
        {
            rest = t[6..].TrimStart(' ', ',', ':', '.', '!').Trim();
            return rest.Length > 0;
        }
        rest = "";
        return false;
    }

    /// <summary>Jarvis on pbmIII through his gate, with the same command any terminal uses (bin/jarvis).</summary>
    internal static async Task<(bool Ok, string Text)> AskJarvisAsync(string question)
    {
        var repo = Environment.GetEnvironmentVariable("PHOENIX_ROOT") ?? @"F:\Phoenix\Phoenix-DevOps-oS";
        var psi = new ProcessStartInfo("python") { RedirectStandardOutput = true, RedirectStandardError = true,
                                                   RedirectStandardInput = true, UseShellExecute = false, CreateNoWindow = true };
        psi.ArgumentList.Add(Path.Combine(repo, "bin", "jarvis"));
        try
        {
            using var p = Process.Start(psi)!;
            await p.StandardInput.WriteAsync(question);                 // on stdin: never on a command line
            p.StandardInput.Close();
            var outTask = p.StandardOutput.ReadToEndAsync();
            var errTask = p.StandardError.ReadToEndAsync();
            if (!p.WaitForExit(160_000)) { try { p.Kill(); } catch { } return (false, "no answer in 160 s"); }
            var output = (await outTask).Trim();
            var err = (await errTask).Trim();
            return p.ExitCode == 0 ? (true, output) : (false, err.Length > 0 ? err : $"exit {p.ExitCode}");
        }
        catch (Exception e) { return (false, e.Message); }
    }

    // ------------------------------------------------------------ the docks
    // A dock exists only while opened by a command; there is nothing at the edges otherwise.
    private void Shelf_DragEnter(object sender, DragEventArgs e) { }
    private void Shelf_DragLeave(object sender, DragEventArgs e) { }

    private void WatchSecurityLock()
    {
        try
        {
            Directory.CreateDirectory(SecurityDir);
            _lockWatch = new FileSystemWatcher(SecurityDir, "hud-locked") { EnableRaisingEvents = true };
            _lockWatch.Created += (_, _) => Dispatcher.BeginInvoke(() =>
            {
                CloseDock(Shelf); CloseDock(ShelfRight);
                Add("[SECURITY] Security locked the docks; they're closed.");
            });
            _lockWatch.Deleted += (_, _) => Dispatcher.BeginInvoke(() => Add("[SECURITY] Security unlocked the docks."));
            Closed += (_, _) => _lockWatch?.Dispose();
        }
        catch (Exception e) { Add($"[SYS] can't watch the security lock ({e.Message}); docks stay closed"); }
        if (DocksLocked) Add("[SECURITY] The docks are locked by security.");
    }

    private void OpenDock(Border dock)
    {
        if (DocksLocked) return;                                       // checked at the door, every time
        dock.Width = DockOpenWidth;
        dock.Background = new SolidColorBrush(Color.FromArgb(0xE0, 0x0A, 0x0D, 0x10));
        BodyOf(dock).Visibility = Visibility.Visible;
        dock.Visibility = Visibility.Visible;
    }

    private void CloseDock(Border dock)
    {
        dock.Visibility = Visibility.Collapsed;
        BodyOf(dock).Visibility = Visibility.Collapsed;
    }

    private void CloseDock_Click(object sender, RoutedEventArgs e)
    {
        var dock = (sender as DependencyObject) is { } d && IsInside(d, Shelf) ? Shelf : ShelfRight;
        CloseDock(dock);
    }

    private static bool IsInside(DependencyObject d, DependencyObject parent)
    {
        for (var x = d; x is not null; x = VisualTreeHelper.GetParent(x)) if (x == parent) return true;
        return false;
    }

    private FrameworkElement BodyOf(Border dock) => dock == Shelf ? ShelfBody : ShelfRightBody;

    private void FillTree(TreeView tree, IReadOnlyList<(string Name, string Path)> places)
    {
        tree.Items.Clear();
        foreach (var (name, path) in places) tree.Items.Add(Node(path, name));
        if (places.Count == 1 && tree.Items[0] is TreeViewItem only) only.IsExpanded = true;   // a single root opens straight away
        tree.PreviewMouseLeftButtonDown += (_, e) => { _dragStart = e.GetPosition(null); _dragItem = ItemAt(e.OriginalSource); };
        tree.PreviewMouseMove += Tree_PreviewMouseMove;
        tree.MouseDoubleClick += (_, e) =>
        {
            if (ItemAt(e.OriginalSource)?.Tag is string p && File.Exists(p))
                try { Process.Start(new ProcessStartInfo(p) { UseShellExecute = true }); } catch (Exception x) { Add($"[SYS] can't open it: {x.Message}"); }
        };
    }

    private TreeViewItem Node(string path, string? label = null)
    {
        var isDir = Directory.Exists(path);
        var n = new TreeViewItem
        {
            Header = (isDir ? "▸ " : "  ") + (label ?? Path.GetFileName(path.TrimEnd('\\'))),
            Tag = path, Foreground = (Brush)FindResource(isDir ? "Amber" : "AmberDim"), ToolTip = path,
        };
        if (isDir)
        {
            n.Items.Add("…");                                          // lazy: filled on first expand
            n.Expanded += (_, e) =>
            {
                if (n.Items.Count != 1 || n.Items[0] is not string) return;
                n.Items.Clear();
                try
                {
                    var di = new DirectoryInfo(path);
                    foreach (var d in di.EnumerateDirectories().Where(Shown).OrderBy(d => d.Name).Take(300)) n.Items.Add(Node(d.FullName));
                    foreach (var f in di.EnumerateFiles().Where(Shown).OrderByDescending(f => f.LastWriteTime).Take(300)) n.Items.Add(Node(f.FullName));
                }
                catch (Exception x) { n.Items.Add(new TreeViewItem { Header = $"  (can't open: {x.Message})", IsEnabled = false }); }
                e.Handled = true;
            };
        }
        return n;
    }

    private static bool Shown(FileSystemInfo i) => (i.Attributes & (FileAttributes.Hidden | FileAttributes.System)) == 0;

    private static TreeViewItem? ItemAt(object source)
    {
        for (var d = source as DependencyObject; d is not null; d = VisualTreeHelper.GetParent(d))
            if (d is TreeViewItem t) return t;
        return null;
    }

    /// <summary>Drag a file or folder out of a dock onto the desktop, Explorer, an app - anywhere.</summary>
    private void Tree_PreviewMouseMove(object sender, MouseEventArgs e)
    {
        if (e.LeftButton != MouseButtonState.Pressed || _dragItem?.Tag is not string path) return;
        var d = e.GetPosition(null) - _dragStart;
        if (Math.Abs(d.X) < SystemParameters.MinimumHorizontalDragDistance &&
            Math.Abs(d.Y) < SystemParameters.MinimumVerticalDragDistance) return;
        var item = _dragItem;
        _dragItem = null;
        var data = new DataObject(DataFormats.FileDrop, new[] { path });
        DragDrop.DoDragDrop(item, data, DragDropEffects.Copy | DragDropEffects.Move | DragDropEffects.Link);
    }

    // ------------------------------------------------------------ drops (dock, eye, chat)
    private void Any_DragOver(object sender, DragEventArgs e)
    {
        e.Effects = e.Data.GetDataPresent(DataFormats.FileDrop) ? DragDropEffects.Copy : DragDropEffects.None;
        e.Handled = true;
    }

    private void Any_Drop(object sender, DragEventArgs e)
    {
        if (e.Data.GetData(DataFormats.FileDrop) is not string[] paths || paths.Length == 0) return;
        Activate();
        var menu = ActionMenu.Build(paths, line => Dispatcher.Invoke(() => Add(line)), AttachToChat);
        menu.Placement = System.Windows.Controls.Primitives.PlacementMode.MousePoint;
        menu.IsOpen = true;
        e.Handled = true;
    }

    /// <summary>"Ask Claude about it": the paths ride along with the next message.</summary>
    public void AttachToChat(IReadOnlyList<string> paths)
    {
        foreach (var p in paths) if (!_attached.Contains(p)) _attached.Add(p);
        Attached.Text = "attached: " + string.Join(", ", _attached.Select(p => Path.GetFileName(p.TrimEnd('\\'))));
        Attached.Visibility = Visibility.Visible;
        OpenChat();
    }

    private void Add(string line) { _lines.Add(line); Refresh(); }

    private void Refresh()
    {
        var text = string.Join(Environment.NewLine + Environment.NewLine, _lines);
        ChatLog.Text = text;
        ChatLog.CaretIndex = text.Length;
        Dispatcher.BeginInvoke(() => ChatLog.ScrollToEnd(), System.Windows.Threading.DispatcherPriority.Loaded);
        try { Directory.CreateDirectory(Path.GetDirectoryName(LogPath)!); File.WriteAllText(LogPath, text); } catch { }
    }
}

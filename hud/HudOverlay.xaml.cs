using System.IO;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using Hud.Desktop;

namespace Hud;

/// <summary>
/// The HUD: chat only, and it's Claude (Jerry, 2026-10-06: "chat only hud is you"). Every
/// human button and switch lives in the Console, which launches this. See-through and
/// click-through everywhere except the chat column and the drop shelf; the whole desktop
/// stays usable underneath. Shares App.Ai with the Console, so it's one conversation.
/// Toggle anywhere: Ctrl+Alt+Space.
/// </summary>
public partial class HudOverlay : Window
{
    private readonly List<string> _lines = new();
    private readonly List<string> _attached = new();
    private static readonly string LogPath = Path.Combine(@"E:\", "Phoenix", "hud-live-monitor", "hud-chat-log.txt");

    private const int HotkeyId = 0x5048;            // "PH"
    private const uint MOD_ALT = 0x1, MOD_CONTROL = 0x2, MOD_NOREPEAT = 0x4000, VK_SPACE = 0x20;
    [DllImport("user32.dll")] private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint mods, uint vk);
    [DllImport("user32.dll")] private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    public HudOverlay()
    {
        InitializeComponent();
        var work = SystemParameters.WorkArea;
        Left = work.Left; Top = work.Top; Width = work.Width; Height = work.Height;
        Header.Text = $"CLAUDE · {App.Ai.Config.Provider}";
        _lines.Add("[SYS] HUD up. Drag anything to the left screen edge, or onto this panel. Ctrl+Alt+Space hides/shows.");
        App.Ai.Note += line => Dispatcher.BeginInvoke(() => Add(line));
        Refresh();
        SourceInitialized += (_, _) =>
        {
            var h = new WindowInteropHelper(this).Handle;
            if (!RegisterHotKey(h, HotkeyId, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_SPACE))
                Add("[SYS] Ctrl+Alt+Space is taken by another program; use the Console's HUD switch.");
            HwndSource.FromHwnd(h).AddHook(WndProc);
        };
        Closed += (_, _) => UnregisterHotKey(new WindowInteropHelper(this).Handle, HotkeyId);
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == 0x0312 && wParam.ToInt32() == HotkeyId)       // WM_HOTKEY
        {
            Toggle();
            handled = true;
        }
        return IntPtr.Zero;
    }

    public void Toggle()
    {
        if (IsVisible) Hide();
        else { Show(); Activate(); ChatInput.Focus(); }
    }

    private void Hide_Click(object sender, RoutedEventArgs e) => Hide();

    // ------------------------------------------------------------ drag and drop
    private void Shelf_DragEnter(object sender, DragEventArgs e)
    {
        Shelf.Width = 150;
        Shelf.Background = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromArgb(0xC0, 0x0A, 0x0D, 0x10));
        ShelfText.Visibility = Visibility.Visible;
    }

    private void Shelf_DragLeave(object sender, DragEventArgs e) => CloseShelf();

    private void CloseShelf()
    {
        Shelf.Width = 6;
        Shelf.Background = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromArgb(0x01, 0, 0, 0));
        ShelfText.Visibility = Visibility.Collapsed;
    }

    private void Any_DragOver(object sender, DragEventArgs e)
    {
        e.Effects = e.Data.GetDataPresent(DataFormats.FileDrop) ? DragDropEffects.Copy : DragDropEffects.None;
        e.Handled = true;
    }

    private void Any_Drop(object sender, DragEventArgs e)
    {
        CloseShelf();
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
        if (!IsVisible) Show();
        Activate();
        ChatInput.Focus();
    }

    // ------------------------------------------------------------ chat
    private void ChatInput_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) { Send_Click(sender, e); e.Handled = true; }
        else if (e.Key == Key.Escape) Hide();
    }

    private async void Send_Click(object sender, RoutedEventArgs e)
    {
        var text = ChatInput.Text.Trim();
        if (text.Length == 0 && _attached.Count == 0) return;
        ChatInput.Clear();
        var files = _attached.ToList();
        _attached.Clear();
        Attached.Visibility = Visibility.Collapsed;

        // Files go as exact paths; every Claude tier can Read them (the CLI tiers by path,
        // the API tier gets an image attached when one is a picture).
        var message = files.Count == 0 ? text
            : $"{(text.Length > 0 ? text : "Look at this.")}\n\nFiles (read them by path):\n" + string.Join("\n", files);
        var image = files.FirstOrDefault(f => new[] { ".png", ".jpg", ".jpeg", ".gif", ".webp" }
            .Contains(Path.GetExtension(f).ToLowerInvariant()));

        Add($"[YOU] {text}{(files.Count > 0 ? $"  (+{files.Count} file{(files.Count > 1 ? "s" : "")})" : "")}");
        var at = _lines.Count;
        Add("[CLAUDE] …");
        Bar.SetState(Voice.VoiceState.Thinking);
        var result = await App.Ai.SendAsync(message, image, chunk => Dispatcher.Invoke(() =>
        {
            _lines[at] = _lines[at] == "[CLAUDE] …" ? "[CLAUDE] " + chunk : _lines[at] + chunk;
            Refresh();
        }));
        if (result.Steps.Count > 0) { _lines.InsertRange(at, result.Steps.Select(s => $"[HANDS] {s}")); at += result.Steps.Count; }
        _lines[at] = result.Success
            ? (_lines[at] == "[CLAUDE] …" ? $"[CLAUDE · {result.Provider}] {result.Reply}" : _lines[at])
            : $"[ERROR · {result.Provider}] {result.Error}";
        Bar.SetState(Voice.VoiceState.Idle);
        Refresh();
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

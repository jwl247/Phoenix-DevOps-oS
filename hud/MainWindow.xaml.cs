using System.Collections.ObjectModel;
using System.IO;
using System.Windows;
using System.Windows.Input;

namespace Hud;

public partial class MainWindow : Window
{
    private readonly AiChatService _ai = new();
    private readonly ScreenCaptureService _capture = new(TimeSpan.FromMilliseconds(1000));
    private readonly ObservableCollection<string> _lines = new();
    private ClaudeCliWindow? _claudeCli;

    public MainWindow()
    {
        InitializeComponent();

        ChatLog.ItemsSource = _lines;
        ProviderLabel.Text = $"provider: {_ai.Config.Provider}";
        _lines.Add($"[SYS] H.L.K-10 online. provider={_ai.Config.Provider}. Config read from ~/.phoenix/ai_auth.json.");

        _capture.FrameCaptured += frame => Dispatcher.Invoke(() => LiveMonitorImage.Source = frame);
        _capture.Start();

        // Rooted here so the CLAUDE CLI pane's spawned shell inherits it as
        // its working directory (EasyWindowsTerminalControl exposes no
        // per-process working-directory API — see ClaudeCliWindow.xaml's
        // note — so the whole HUD process's cwd is what the child inherits).
        var root = Environment.GetEnvironmentVariable("PHOENIX_ROOT");
        if (!string.IsNullOrEmpty(root) && Directory.Exists(root)) Environment.CurrentDirectory = root;

        // 1/3 of screen height, not a hardcoded pixel value — same
        // resolution-independence reasoning as the full-screen MainWindow
        // sizing fix (SystemParameters, not a fixed number that only looks
        // right on the one screen it was tuned against).
        ClaudeCliDockAnchor.Height = SystemParameters.PrimaryScreenHeight / 3;

        // Same reason dashboard/terminal-pty.js's cleanEnv() strips these:
        // if Hud.exe itself ever gets launched from inside a running Claude
        // Code session (e.g. a dev testing it from a Claude Code terminal —
        // confirmed live 2026-09-21, is exactly how this surfaced), the
        // spawned CLAUDE CLI pane inherits CLAUDE_CODE_CHILD_SESSION and
        // starts as a nested session with transcript saving off instead of
        // a clean top-level one.
        foreach (System.Collections.DictionaryEntry kv in Environment.GetEnvironmentVariables())
        {
            var name = (string)kv.Key;
            if (name.StartsWith("CLAUDE_CODE_", StringComparison.Ordinal) || name == "CLAUDECODE")
                Environment.SetEnvironmentVariable(name, null);
        }

        // WPF refuses Owner = a window that hasn't been shown yet, and this
        // constructor runs before MainWindow itself is shown — so creating/
        // showing the docked companion has to wait for Loaded, not happen
        // here. Confirmed the hard way: this threw XamlParseException /
        // InvalidOperationException on first launch.
        Loaded += (_, _) =>
        {
            _claudeCli = new ClaudeCliWindow { Owner = this };
            _claudeCli.Show();
            SyncClaudeCliDock();
        };
        LocationChanged += (_, _) => SyncClaudeCliDock();
        SizeChanged += (_, _) => SyncClaudeCliDock();
        StateChanged += (_, _) =>
        {
            if (_claudeCli is null) return;
            _claudeCli.Visibility = WindowState == WindowState.Minimized ? Visibility.Hidden : Visibility.Visible;
        };
        ClaudeCliDockAnchor.SizeChanged += (_, _) => SyncClaudeCliDock();

        Closed += (_, _) =>
        {
            _capture.Dispose();
            _claudeCli?.Close();
            _claudeCli = null;
        };
    }

    // Keeps the separate, opaque ClaudeCliWindow pixel-aligned to the
    // invisible ClaudeCliDockAnchor placeholder in this (transparent)
    // window, so the two windows read as one seamless HUD pane. Staying in
    // WPF device-independent coordinates throughout (TransformToAncestor +
    // Window.Left/Top, never raw screen pixels) keeps this correct without
    // needing a separate DPI conversion step.
    private void SyncClaudeCliDock()
    {
        if (_claudeCli is null || !IsLoaded) return;
        var topLeft = ClaudeCliDockAnchor.TransformToAncestor(this).Transform(new Point(0, 0));
        _claudeCli.Left = Left + topLeft.X;
        _claudeCli.Top = Top + topLeft.Y;
        _claudeCli.Width = ClaudeCliDockAnchor.ActualWidth;
        _claudeCli.Height = ClaudeCliDockAnchor.ActualHeight;
    }

    private void TitleBar_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ButtonState == MouseButtonState.Pressed) DragMove();
    }

    private void Close_Click(object sender, RoutedEventArgs e) => Close();

    private void ChatInput_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) _ = SendAsync();
    }

    private void Send_Click(object sender, RoutedEventArgs e) => _ = SendAsync();

    private async Task SendAsync()
    {
        var message = ChatInput.Text.Trim();
        if (message.Length == 0) return;
        ChatInput.Text = "";
        _lines.Add($"[YOU] {message}");
        ScrollToEnd();

        var placeholderIndex = _lines.Count;
        _lines.Add("[H.L.K-10] …");
        ScrollToEnd();

        var result = await _ai.SendAsync(message, chunk =>
        {
            Dispatcher.Invoke(() =>
            {
                if (_lines[placeholderIndex] == "[H.L.K-10] …") _lines[placeholderIndex] = "[H.L.K-10] " + chunk;
                else _lines[placeholderIndex] += chunk;
                ScrollToEnd();
            });
        });

        if (result.Success)
        {
            if (_lines[placeholderIndex] == "[H.L.K-10] …")
                _lines[placeholderIndex] = $"[H.L.K-10 · {result.Provider}] {result.Reply}";
        }
        else
        {
            _lines[placeholderIndex] = $"[ERROR · {result.Provider}] {result.Error}";
        }
        ScrollToEnd();
    }

    private void ScrollToEnd() => ChatScroll.ScrollToEnd();
}

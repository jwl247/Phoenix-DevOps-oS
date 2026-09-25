using System.IO;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media.Imaging;
using Hud.Voice;

namespace Hud;

public partial class MainWindow : Window
{
    private readonly AiChatService _ai = new();
    private readonly ScreenCaptureService _capture = new(TimeSpan.FromMilliseconds(1000));
    private readonly List<string> _lines = new();
    private ClaudeCliWindow? _claudeCli;
    private VoiceController? _voice;
    private int _frameSaveCounter;

    // Live Monitor previously only ever painted this into the on-screen Image
    // control — nothing else could see it. Saved to disk here too so ANY
    // Claude Code session can Read it directly: H.L.K-10's own chat/voice
    // replies (via AiChatService's imagePath param below), the HUD's own
    // CLAUDE CLI pane, or a dev session working on the HUD from outside it.
    // Jerry, 2026-09-22: "they have to tie together" / "specifficly you" /
    // "claude code in the hud" — the Live Monitor pane was decorative until
    // this existed.
    private static readonly string LiveMonitorFramePath =
        Path.Combine(@"E:\", "Phoenix", "hud-live-monitor", "current.png");

    // Same reasoning, but for the AI Chat pane's actual text instead of a
    // screenshot of it. Jerry, 2026-09-22: "you need to be able to see and
    // use the data in the claude box main screen" — a screenshot only gives
    // pixels to squint at; the real H.L.K-10 transcript (what was asked, what
    // it replied, any error text) needs to be readable as exact text by any
    // Claude Code session, not OCR'd off an image.
    private static readonly string ChatLogPath =
        Path.Combine(@"E:\", "Phoenix", "hud-live-monitor", "chat-log.txt");

    public MainWindow()
    {
        InitializeComponent();

        ProviderLabel.Text = $"provider: {_ai.Config.Provider}";
        _lines.Add($"[SYS] H.L.K-10 online. provider={_ai.Config.Provider}. Config read from ~/.phoenix/ai_auth.json.");

        _capture.FrameCaptured += frame => Dispatcher.Invoke(() =>
        {
            LiveMonitorImage.Source = frame;
            // Throttled to every 3rd tick (~3s) — a full-desktop PNG
            // encode+write on every 1s capture tick is wasted work for
            // something a Read call only ever needs fresh to a few seconds.
            if (++_frameSaveCounter % 3 == 0) SaveFrameToDisk(frame);
        });
        _capture.Start();

        // Milestone 3: voice. Built as its own controller rather than inline
        // here so hotkey/mic/STT/TTS have one home — see hud/Voice/. Degrades
        // to an armed-but-inert hotkey with a status line (never a crash)
        // when the local Whisper/Piper files from hud/VOICE_SETUP.md aren't
        // installed yet.
        _voice = VoiceSetup.Create(Dispatcher);
        _voice.StateChanged += state => Dispatcher.Invoke(() => VoiceIndicator.SetState(state));
        _voice.TranscriptReady += transcript => _ = SendMessageAsync(transcript, speak: true);
        _lines.Add(_voice.UnavailableReason is null
            ? "[SYS] Voice armed — hold the hotkey to talk."
            : $"[SYS] {_voice.UnavailableReason}");
        RefreshChatLog();

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
            _voice?.Dispose();
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

    private void ToggleCli_Click(object sender, RoutedEventArgs e)
    {
        if (_claudeCli is null) return;
        _claudeCli.Visibility = _claudeCli.Visibility == Visibility.Visible ? Visibility.Hidden : Visibility.Visible;
    }

    private void ChatInput_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) _ = SendAsync();
    }

    private void Send_Click(object sender, RoutedEventArgs e) => _ = SendAsync();

    private Task SendAsync()
    {
        var message = ChatInput.Text.Trim();
        ChatInput.Text = "";
        // Typed input is never spoken back — only a voice-originated
        // question gets a spoken reply, so typing doesn't unexpectedly
        // start narrating at you.
        return SendMessageAsync(message, speak: false);
    }

    /// <summary>
    /// The one path both typed chat and voice transcripts go through, so
    /// they share one history and one append/streaming behavior instead of
    /// diverging into two copies of the same logic.
    /// </summary>
    private async Task SendMessageAsync(string message, bool speak)
    {
        if (message.Length == 0) return;
        _lines.Add($"[YOU] {message}");
        RefreshChatLog();

        var placeholderIndex = _lines.Count;
        _lines.Add("[H.L.K-10] …");
        RefreshChatLog();

        var imagePath = File.Exists(LiveMonitorFramePath) ? LiveMonitorFramePath : null;
        var result = await _ai.SendAsync(message, imagePath, chunk =>
        {
            Dispatcher.Invoke(() =>
            {
                if (_lines[placeholderIndex] == "[H.L.K-10] …") _lines[placeholderIndex] = "[H.L.K-10] " + chunk;
                else _lines[placeholderIndex] += chunk;
                RefreshChatLog();
            });
        });

        string? finalReply = null;
        if (result.Success)
        {
            if (_lines[placeholderIndex] == "[H.L.K-10] …")
                _lines[placeholderIndex] = $"[H.L.K-10 · {result.Provider}] {result.Reply}";
            finalReply = result.Reply;
        }
        else
        {
            _lines[placeholderIndex] = $"[ERROR · {result.Provider}] {result.Error}";
        }
        RefreshChatLog();

        if (speak && !string.IsNullOrWhiteSpace(finalReply) && _voice is not null)
            await _voice.SpeakReplyAsync(finalReply);
    }

    // Renders _lines into the read-only TextBox and scrolls to the bottom —
    // TextBox.ScrollToEnd() handles both text-length and caret-position
    // scrolling in one call, no separate ScrollViewer needed.
    private void RefreshChatLog()
    {
        var text = string.Join("\n\n", _lines);
        ChatLog.Text = text;
        ChatLog.CaretIndex = text.Length;
        ChatLog.ScrollToEnd();

        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(ChatLogPath)!);
            File.WriteAllText(ChatLogPath, text);
        }
        catch
        {
            // Transient (e.g. a reader has it open) — next refresh retries.
        }
    }

    private static void SaveFrameToDisk(BitmapSource frame)
    {
        try
        {
            var dir = Path.GetDirectoryName(LiveMonitorFramePath)!;
            Directory.CreateDirectory(dir);
            var encoder = new PngBitmapEncoder();
            encoder.Frames.Add(BitmapFrame.Create(frame));
            using var fs = new FileStream(LiveMonitorFramePath, FileMode.Create, FileAccess.Write);
            encoder.Save(fs);
        }
        catch
        {
            // Transient (e.g. file locked by a reader mid-write) — next tick retries.
        }
    }
}

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
    private ClaudeCodeSession? _claudeCode;
    private readonly List<string> _codeLines = new();
    private System.Windows.Threading.DispatcherTimer? _codeTimer;
    private DateTime _codeStarted;
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

    // The CLAUDE CODE pane's transcript, same idea: readable as exact text.
    private static readonly string ClaudeCodeLogPath =
        Path.Combine(@"E:\", "Phoenix", "hud-live-monitor", "claude-code-log.txt");

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
        _voice.Note += line => { _lines.Add($"[SYS] {line}"); RefreshChatLog(); };
        _lines.Add(_voice.UnavailableReason is null
            ? $"[SYS] {_voice.ArmedLine}"
            : $"[SYS] {_voice.UnavailableReason}");
        // [HANDS] catalog / [SYS] ollama lines from H.L.K-10 (HUD-F03, HUD-F04).
        // They arrive on background threads; subscribing starts the hands refresh.
        _ai.Note += line => Dispatcher.BeginInvoke(() => { _lines.Add(line); RefreshChatLog(); });
        if (ClaudeCodeSession.InstalledPath() is null)
            _lines.Add("[SYS] Claude Code isn't installed here (no ~/.local/bin/claude.exe or npm claude.cmd): " +
                       "the CLAUDE CODE pane and the subscription tier won't answer. Ollama and the API tier still work.");
        RefreshChatLog();

        // The CLAUDE CODE pane works in the Phoenix repo.
        var root = Environment.GetEnvironmentVariable("PHOENIX_ROOT");
        if (!string.IsNullOrEmpty(root) && Directory.Exists(root)) Environment.CurrentDirectory = root;

        // CLAUDE CODE pane height comes from its XAML margins now — it
        // stretches to fill the right column between LIVE MONITOR and H.L.K-10.

        // Fill the work area, not the whole screen — at full screen height the
        // bottom-anchored H.L.K-10 panel's input row sat behind the taskbar.
        var work = SystemParameters.WorkArea;
        Left = work.Left;
        Top = work.Top;
        Width = work.Width;
        Height = work.Height;

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

        _claudeCode = new ClaudeCodeSession(Environment.CurrentDirectory);
        _claudeCode.Said += text => Dispatcher.Invoke(() => AddCode($"[CLAUDE] {text}"));
        _claudeCode.UsedTool += what => Dispatcher.Invoke(() => AddCode($"  > {what}"));
        _claudeCode.ToolFailed += why => Dispatcher.Invoke(() => AddCode($"  ! {why}"));
        _claudeCode.Finished += (ok, error, secs) => Dispatcher.Invoke(() =>
        {
            _codeTimer?.Stop();
            AddCode(ok ? $"[DONE · {secs:0}s]" : $"[STOPPED · {secs:0}s] {error}");
            SetCodeBusy(false);
        });
        _codeLines.Add($"[SYS] Claude Code online, working in {Environment.CurrentDirectory}. Type below and press Enter.");
        RefreshCodeLog();

        Closed += (_, _) =>
        {
            _capture.Dispose();
            _voice?.Dispose();
            _claudeCode?.Stop();
        };
    }

    private void TitleBar_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ButtonState == MouseButtonState.Pressed) DragMove();
    }

    private void Close_Click(object sender, RoutedEventArgs e) => Close();

    private void ToggleCli_Click(object sender, RoutedEventArgs e) =>
        ClaudeCodePane.Visibility = ClaudeCodePane.Visibility == Visibility.Visible ? Visibility.Collapsed : Visibility.Visible;

    // ---- CLAUDE CODE pane ----------------------------------------------

    private void ClaudeCodeInput_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && (Keyboard.Modifiers & ModifierKeys.Shift) == 0)
        {
            e.Handled = true;
            SendToClaudeCode();
        }
    }

    private void ClaudeCodeSend_Click(object sender, RoutedEventArgs e) => SendToClaudeCode();

    private void ClaudeCodeStop_Click(object sender, RoutedEventArgs e) => _claudeCode?.Stop();

    private void ClaudeCodeNew_Click(object sender, RoutedEventArgs e)
    {
        if (_claudeCode is null || _claudeCode.IsRunning) return;
        _claudeCode.NewSession();
        _codeLines.Clear();
        _codeLines.Add("[SYS] New conversation.");
        RefreshCodeLog();
    }

    private void SendToClaudeCode()
    {
        var message = ClaudeCodeInput.Text.Trim();
        if (message.Length == 0 || _claudeCode is null || _claudeCode.IsRunning) return;
        ClaudeCodeInput.Text = "";
        AddCode($"[YOU] {message}");
        SetCodeBusy(true);
        try
        {
            _claudeCode.Send(message);
        }
        catch (Exception ex)
        {
            AddCode($"[ERROR] couldn't start Claude Code: {ex.Message}");
            SetCodeBusy(false);
        }
    }

    private void SetCodeBusy(bool busy)
    {
        ClaudeCodeStopButton.IsEnabled = busy;
        if (busy)
        {
            _codeStarted = DateTime.UtcNow;
            _codeTimer ??= new System.Windows.Threading.DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
            _codeTimer.Tick -= CodeTimerTick;
            _codeTimer.Tick += CodeTimerTick;
            _codeTimer.Start();
            ClaudeCodeStatus.Text = "working… 0s";
        }
        else ClaudeCodeStatus.Text = "ready";
    }

    private void CodeTimerTick(object? sender, EventArgs e) =>
        ClaudeCodeStatus.Text = $"working… {(DateTime.UtcNow - _codeStarted).TotalSeconds:0}s";

    private void AddCode(string line)
    {
        _codeLines.Add(line);
        RefreshCodeLog();
    }

    private void RefreshCodeLog()
    {
        var text = string.Join("\n\n", _codeLines);
        ClaudeCodeLog.Text = text;
        ClaudeCodeLog.CaretIndex = text.Length;
        ScrollToEndAfterLayout(ClaudeCodeLog);
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(ClaudeCodeLogPath)!);
            File.WriteAllText(ClaudeCodeLogPath, text);
        }
        catch
        {
            // Transient (a reader has it open) — next refresh retries.
        }
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

        // What the hands did on the way (open Office, status of the Compaq…),
        // one line each, above the reply, so "what did you just do" is always
        // on screen and in chat-log.txt.
        if (result.Steps.Count > 0)
        {
            _lines.InsertRange(placeholderIndex, result.Steps.Select(s => $"[HANDS] {s}"));
            placeholderIndex += result.Steps.Count;
        }

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

        // Always hand back to voice when the question came from voice: an
        // empty reply (or an error) resets it to idle instead of leaving it
        // stuck on "thinking".
        if (speak && _voice is not null)
            await _voice.SpeakReplyAsync(finalReply ?? "");
    }

    // Scrolling right after setting Text scrolls to the OLD extent — the new
    // wrapped lines aren't measured yet, so the last line or two of a long
    // reply sat below the visible area (Jerry, 2026-09-27: "i cant see the
    // bottom row of text"). Scroll again once layout has run.
    private static void ScrollToEndAfterLayout(System.Windows.Controls.TextBox box)
    {
        box.ScrollToEnd();
        box.Dispatcher.BeginInvoke(box.ScrollToEnd, System.Windows.Threading.DispatcherPriority.Loaded);
    }

    // Renders _lines into the read-only TextBox and scrolls to the bottom.
    private void RefreshChatLog()
    {
        var text = string.Join("\n\n", _lines);
        ChatLog.Text = text;
        ChatLog.CaretIndex = text.Length;
        ScrollToEndAfterLayout(ChatLog);

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

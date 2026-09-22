using System.IO;
using System.Windows.Input;
using System.Windows.Threading;

namespace Hud.Voice;

public enum VoiceState { Idle, Listening, Thinking, Speaking }

/// <summary>
/// Wires push-to-talk -> mic capture -> local Whisper STT into one state
/// machine. Deliberately does NOT talk to AiChatService itself — the caller
/// (MainWindow) owns the actual Claude request + chat-log append, exactly
/// the same path typed chat already uses, so voice and typed input share
/// one history instead of two divergent code paths. This class only ever
/// hands back a transcript (TranscriptReady) and, later, speaks whatever
/// final reply text the caller gives it (SpeakReplyAsync).
/// </summary>
public sealed class VoiceController : IDisposable
{
    private readonly PushToTalkHotkey _hotkey;
    private readonly MicrophoneCapture _mic = new();
    private readonly WhisperTranscriber? _whisper;
    private readonly PiperTextToSpeech? _tts;
    private readonly Dispatcher _dispatcher;

    public VoiceState State { get; private set; } = VoiceState.Idle;
    public event Action<VoiceState>? StateChanged;
    public event Action<string>? TranscriptReady;

    /// <summary>Non-null when voice is armed but not fully usable yet (e.g. no local model installed) — surfaced as a status line, not a crash.</summary>
    public string? UnavailableReason { get; }

    public VoiceController(Dispatcher dispatcher, Key hotkeyKey, WhisperTranscriber? whisper, PiperTextToSpeech? tts)
    {
        _dispatcher = dispatcher;
        _whisper = whisper;
        _tts = tts;

        UnavailableReason = _whisper is null
            ? "Voice hotkey armed, but no local Whisper model found — see hud/VOICE_SETUP.md."
            : _tts is null
                ? "Voice input is live, but no local Piper voice found — replies won't be spoken. See hud/VOICE_SETUP.md."
                : null;

        _hotkey = new PushToTalkHotkey(hotkeyKey, dispatcher);
        _hotkey.PressStart += OnPressStart;
        _hotkey.PressEnd += OnPressEnd;
        _hotkey.Start();
    }

    private void OnPressStart()
    {
        if (_whisper is null) return;

        // Barge-in: pressing the hotkey again while Claude is still talking
        // cancels playback immediately instead of waiting it out.
        if (State == VoiceState.Speaking) _tts?.Stop();

        _mic.Start();
        SetState(VoiceState.Listening);
    }

    private async void OnPressEnd()
    {
        if (_whisper is null || State != VoiceState.Listening) return;

        SetState(VoiceState.Thinking);

        Stream? wav;
        try
        {
            wav = await _mic.StopAsync();
        }
        catch
        {
            SetState(VoiceState.Idle);
            return;
        }

        if (wav is null) { SetState(VoiceState.Idle); return; }

        string transcript;
        using (wav)
        {
            try
            {
                transcript = await _whisper.TranscribeAsync(wav);
            }
            catch
            {
                SetState(VoiceState.Idle);
                return;
            }
        }

        if (string.IsNullOrWhiteSpace(transcript)) { SetState(VoiceState.Idle); return; }

        // Stays in Thinking until the caller's Claude round-trip finishes and
        // calls SpeakReplyAsync (or decides not to speak at all) — this
        // event is the hand-off seam between the two.
        TranscriptReady?.Invoke(transcript);
    }

    // Serializes playback across overlapping SpeakReplyAsync calls. MainWindow
    // fires TranscriptReady handling as fire-and-forget, so barge-in can let a
    // SECOND full reply-and-speak cycle start before the FIRST one's WaveOut
    // player has actually finished disposing — _tts.Stop() only asks it to
    // stop, it doesn't block until torn down. Without this, both players can
    // briefly be alive at once (confirmed live 2026-09-22: "its talking over
    // itself now" — this is the next bug the barge-in fix above surfaced).
    private Task _speakTask = Task.CompletedTask;

    public Task SpeakReplyAsync(string text)
    {
        var previous = _speakTask;
        var task = SpeakAfterAsync(previous, text);
        _speakTask = task;
        return task;
    }

    private async Task SpeakAfterAsync(Task previous, string text)
    {
        await previous; // wait for any still-unwinding prior playback to fully dispose first

        if (_tts is null || string.IsNullOrWhiteSpace(text)) { SetState(VoiceState.Idle); return; }

        SetState(VoiceState.Speaking);
        try
        {
            await _tts.SpeakAsync(SpeechTextSanitizer.ForSpeech(text));
        }
        catch
        {
            // A TTS failure shouldn't crash the HUD — the reply is already
            // visible as text in the chat pane regardless.
        }
        finally
        {
            // Barge-in race: _tts.Stop() (called from OnPressStart) makes
            // SpeakAsync's await above return, but that happens on a queued
            // dispatcher continuation — it can land AFTER OnPressStart has
            // already moved State to Listening for the new recording. Only
            // reset to Idle if nothing has already moved state on since,
            // otherwise this clobbers the barge-in and the new recording
            // silently never gets processed (confirmed live 2026-09-22:
            // "barge stopped the voice but has not resumed yet").
            if (State == VoiceState.Speaking) SetState(VoiceState.Idle);
        }
    }

    private void SetState(VoiceState state)
    {
        State = state;
        _dispatcher.Invoke(() => StateChanged?.Invoke(state));
    }

    public void Dispose()
    {
        _hotkey.PressStart -= OnPressStart;
        _hotkey.PressEnd -= OnPressEnd;
        _hotkey.Dispose();
        _mic.Dispose();
        _tts?.Dispose();
        _whisper?.Dispose();
    }
}

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
    private readonly MicrophoneCapture _mic;
    private readonly string _keyName;
    private readonly WhisperTranscriber? _whisper;
    private readonly PiperTextToSpeech? _tts;
    private readonly Dispatcher _dispatcher;

    public VoiceState State { get; private set; } = VoiceState.Idle;
    public event Action<VoiceState>? StateChanged;
    public event Action<string>? TranscriptReady;

    /// <summary>
    /// A plain-words line for H.L.K-10's pane whenever voice can't finish a
    /// step. Before 2026-09-27 every failure here returned to Idle silently,
    /// so "nothing happened" could mean any of five different problems.
    /// </summary>
    public event Action<string>? Note;

    /// <summary>What's armed: key + mic, shown once at startup.</summary>
    public string ArmedLine => $"Voice armed — hold {_keyName} to talk. Mic: {_mic.DeviceName}.";

    /// <summary>Non-null when voice is armed but not fully usable yet (e.g. no local model installed) — surfaced as a status line, not a crash.</summary>
    public string? UnavailableReason { get; private set; }

    public VoiceController(Dispatcher dispatcher, Key hotkeyKey, WhisperTranscriber? whisper, PiperTextToSpeech? tts, string? micName = null)
    {
        _dispatcher = dispatcher;
        _mic = new MicrophoneCapture(micName);
        _keyName = hotkeyKey switch { Key.RightCtrl => "Right Ctrl", Key.LeftCtrl => "Left Ctrl", Key.RightAlt => "Right Alt", _ => hotkeyKey.ToString() };
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
        if (_hotkey.Error is not null) UnavailableReason = $"{_hotkey.Error}. Voice can't hear the talk key.";
    }

    private void Tell(string line) => _dispatcher.BeginInvoke(() => Note?.Invoke(line));

    private void OnPressStart()
    {
        if (_whisper is null) return;

        // Barge-in: pressing the hotkey again while Claude is still talking
        // cancels playback immediately instead of waiting it out.
        if (State == VoiceState.Speaking) _tts?.Stop();

        try
        {
            _mic.Start();
        }
        catch (Exception ex)
        {
            Tell($"voice: the mic ({_mic.DeviceName}) wouldn't start: {ex.Message}");
            SetState(VoiceState.Idle);
            return;
        }
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
        catch (Exception ex)
        {
            Tell($"voice: the mic didn't stop cleanly: {ex.Message}");
            SetState(VoiceState.Idle);
            return;
        }

        if (wav is null)
        {
            Tell($"voice: nothing was recorded from {_mic.DeviceName}.");
            SetState(VoiceState.Idle);
            return;
        }
        // A tap, not a hold: ignore quietly.
        if (_mic.LastSeconds < 0.4) { wav.Dispose(); SetState(VoiceState.Idle); return; }

        string transcript;
        using (wav)
        {
            try
            {
                transcript = await _whisper.TranscribeAsync(wav);
            }
            catch (Exception ex)
            {
                Tell($"voice: speech recognition failed: {ex.Message}");
                SetState(VoiceState.Idle);
                return;
            }
        }

        if (string.IsNullOrWhiteSpace(transcript) || IsSilenceGuess(transcript))
        {
            var level = _mic.LastPeakDb < -45
                ? $"the mic sounded nearly silent (loudest {_mic.LastPeakDb:0} dB) — check {_mic.DeviceName} is on, unmuted and the gain is up"
                : $"loudest {_mic.LastPeakDb:0} dB, so sound came in but no words were recognized";
            Tell($"voice: didn't catch anything ({_mic.LastSeconds:0.0} s recorded; {level}).");
            SetState(VoiceState.Idle);
            return;
        }

        // Stays in Thinking until the caller's Claude round-trip finishes and
        // calls SpeakReplyAsync (or decides not to speak at all) — this
        // event is the hand-off seam between the two.
        TranscriptReady?.Invoke(transcript);
    }

    // What Whisper famously "hears" in near-silence (room noise, a held key
    // with nobody talking). Seen live 2026-09-27: a silent 2 s hold came back
    // as "you" and got sent to H.L.K-10 as a question.
    private static readonly HashSet<string> SilenceGuesses = new(StringComparer.OrdinalIgnoreCase)
    {
        "you", "thank you", "thanks", "thanks for watching", "thank you for watching", "bye", "okay",
        "[blank_audio]", "[silence]", "(silence)", "[music]", "(music)", "[no speech]",
    };

    private static bool IsSilenceGuess(string transcript)
    {
        var t = transcript.Trim().Trim('.', '!', '?', ',', ' ').Trim();
        return t.Length == 0 || SilenceGuesses.Contains(t);
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
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // A TTS failure shouldn't crash the HUD — the reply is already
            // visible as text in the chat pane regardless. Say so, though.
            Tell($"voice: couldn't speak the reply: {ex.Message}");
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

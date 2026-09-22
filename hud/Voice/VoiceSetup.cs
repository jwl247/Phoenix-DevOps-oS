using System.IO;
using System.Windows.Input;
using System.Windows.Threading;

namespace Hud.Voice;

/// <summary>
/// Resolves voice config the same way AiChatService resolves AI config:
/// ~/.phoenix/phoenix.env overrides, sane defaults otherwise. Whisper/Piper
/// files are a one-time manual local install (see hud/VOICE_SETUP.md), not
/// committed to the repo — same treatment as Ollama's local models — so
/// this must degrade gracefully (a null engine + a status line, never a
/// crash) when they aren't present yet.
/// </summary>
public static class VoiceSetup
{
    public static VoiceController Create(Dispatcher dispatcher)
    {
        var env = ReadPhoenixEnv();

        var hotkey = Key.RightCtrl;
        if (env.TryGetValue("PHOENIX_VOICE_HOTKEY", out var hkName) && Enum.TryParse<Key>(hkName, true, out var parsed))
            hotkey = parsed;

        var whisperModelPath = env.GetValueOrDefault("PHOENIX_WHISPER_MODEL_PATH")
                                ?? @"E:\Phoenix\voice-models\whisper\ggml-base.en.bin";
        WhisperTranscriber? whisper = null;
        try
        {
            if (File.Exists(whisperModelPath)) whisper = new WhisperTranscriber(whisperModelPath);
        }
        catch
        {
            whisper = null;
        }

        var piperDir = env.GetValueOrDefault("PHOENIX_PIPER_DIR") ?? @"E:\Phoenix\voice-models\piper";
        var piperVoice = env.GetValueOrDefault("PHOENIX_PIPER_VOICE") ?? "en_US-lessac-medium.onnx";
        var piper = new PiperTextToSpeech(piperDir, piperVoice);

        return new VoiceController(dispatcher, hotkey, whisper, piper.IsAvailable ? piper : null);
    }

    private static Dictionary<string, string> ReadPhoenixEnv()
    {
        var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".phoenix", "phoenix.env");
        try
        {
            if (!File.Exists(path)) return result;
            foreach (var raw in File.ReadAllLines(path))
            {
                var line = raw.Trim();
                if (line.Length == 0 || line.StartsWith('#')) continue;
                var eq = line.IndexOf('=');
                if (eq < 1) continue;
                var key = line[..eq].Trim();
                var val = line[(eq + 1)..].Trim().Trim('"', '\'');
                result[key] = val;
            }
        }
        catch { /* same tolerant behavior as AiChatService.LoadConfig */ }
        return result;
    }
}

using System.Diagnostics;
using System.IO;
using NAudio.Wave;

namespace Hud.Voice;

/// <summary>
/// Local-only text-to-speech via Piper (github.com/rhasspy/piper) — a small,
/// open-source, ONNX-based neural TTS that runs CPU-only with genuinely
/// listenable voices, a real step up from Windows SAPI's robotic built-in
/// voices. Invoked as an external process, the same pattern AiChatService
/// already uses to shell out to the `claude` CLI, so no native binding is
/// needed. The binary + a voice model are a one-time manual local install
/// (see hud/VOICE_SETUP.md) — not committed to the repo, same treatment as
/// Ollama's local models.
/// </summary>
public sealed class PiperTextToSpeech : IDisposable
{
    private readonly string _piperExe;
    private readonly string _voiceModelPath;
    private WaveOut? _player;

    public PiperTextToSpeech(string piperDir, string voiceModelFileName)
    {
        _piperExe = Path.Combine(piperDir, "piper.exe");
        _voiceModelPath = Path.Combine(piperDir, voiceModelFileName);
    }

    public bool IsAvailable => File.Exists(_piperExe) && File.Exists(_voiceModelPath);

    public async Task SpeakAsync(string text, CancellationToken ct = default)
    {
        if (!IsAvailable || string.IsNullOrWhiteSpace(text)) return;

        var tempWav = Path.Combine(Path.GetTempPath(), $"phoenix-voice-{Guid.NewGuid():N}.wav");
        try
        {
            await RunPiperAsync(text, tempWav, ct);
            ct.ThrowIfCancellationRequested();
            if (!File.Exists(tempWav)) return;
            await PlayAsync(tempWav, ct);
        }
        finally
        {
            try { if (File.Exists(tempWav)) File.Delete(tempWav); } catch { /* best-effort cleanup */ }
        }
    }

    private async Task RunPiperAsync(string text, string outputWavPath, CancellationToken ct)
    {
        var psi = new ProcessStartInfo
        {
            FileName = _piperExe,
            Arguments = $"--model \"{_voiceModelPath}\" --output_file \"{outputWavPath}\"",
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        using var proc = Process.Start(psi) ?? throw new InvalidOperationException("Failed to start piper.exe");
        await using (proc.StandardInput)
        {
            await proc.StandardInput.WriteAsync(text.AsMemory(), ct);
        }

        using (ct.Register(() => { try { if (!proc.HasExited) proc.Kill(true); } catch { } }))
        {
            await proc.WaitForExitAsync(ct);
        }
    }

    private async Task PlayAsync(string wavPath, CancellationToken ct)
    {
        using var reader = new AudioFileReader(wavPath);
        using var player = new WaveOut();
        _player = player;

        var tcs = new TaskCompletionSource();
        player.PlaybackStopped += (_, _) => tcs.TrySetResult();
        player.Init(reader);
        player.Play();

        using (ct.Register(() => player.Stop()))
        {
            await tcs.Task;
        }
        _player = null;
    }

    /// <summary>Barge-in: called when the user starts talking over a reply.</summary>
    public void Stop() => _player?.Stop();

    public void Dispose() => _player?.Dispose();
}

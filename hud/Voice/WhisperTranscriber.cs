using System.IO;
using Whisper.net;
using Whisper.net.LibraryLoader;

namespace Hud.Voice;

/// <summary>
/// Local-only speech-to-text via Whisper.net (whisper.cpp bindings). GPU
/// drivers are blacklisted for Phoenix (root CLAUDE.md, Critical Rule #6) —
/// the static constructor forces whisper.cpp's native loader to the CPU
/// runtime instead of letting it auto-probe Vulkan/CUDA/CoreML if any
/// happen to be present on the machine.
/// </summary>
public sealed class WhisperTranscriber : IDisposable
{
    static WhisperTranscriber()
    {
        RuntimeOptions.RuntimeLibraryOrder = [RuntimeLibrary.Cpu];
    }

    private readonly WhisperFactory _factory;
    private readonly WhisperProcessor _processor;

    public WhisperTranscriber(string modelPath)
    {
        if (!File.Exists(modelPath))
            throw new FileNotFoundException(
                $"Whisper model not found at '{modelPath}'. See hud/VOICE_SETUP.md to download one.", modelPath);

        _factory = WhisperFactory.FromPath(modelPath);
        _processor = _factory.CreateBuilder().WithLanguage("en").Build();
    }

    public async Task<string> TranscribeAsync(Stream wavStream)
    {
        var text = new System.Text.StringBuilder();
        await foreach (var segment in _processor.ProcessAsync(wavStream))
        {
            text.Append(segment.Text);
        }
        return text.ToString().Trim();
    }

    public void Dispose()
    {
        _processor.Dispose();
        _factory.Dispose();
    }
}

using System.IO;
using NAudio.Wave;

namespace Hud.Voice;

/// <summary>
/// Captures 16 kHz mono PCM — Whisper's native input format — directly, so
/// no resampling step is needed between mic and transcription.
/// </summary>
public sealed class MicrophoneCapture : IDisposable
{
    private WaveIn? _waveIn;
    private MemoryStream? _buffer;
    private WaveFileWriter? _writer;

    public bool IsCapturing { get; private set; }

    public void Start()
    {
        if (IsCapturing) return;

        _buffer = new MemoryStream();
        _waveIn = new WaveIn
        {
            WaveFormat = new WaveFormat(16000, 16, 1),
            BufferMilliseconds = 50
        };
        _writer = new WaveFileWriter(_buffer, _waveIn.WaveFormat);
        _waveIn.DataAvailable += OnDataAvailable;
        _waveIn.StartRecording();
        IsCapturing = true;
    }

    private void OnDataAvailable(object? sender, WaveInEventArgs e) => _writer?.Write(e.Buffer, 0, e.BytesRecorded);

    /// <summary>
    /// Waits for NAudio's own RecordingStopped signal rather than returning
    /// the instant StopRecording() is called — a few more DataAvailable
    /// callbacks can still land after StopRecording() returns but before
    /// recording has actually finished, and losing that tail would clip the
    /// end of whatever was just said.
    /// </summary>
    public async Task<Stream?> StopAsync()
    {
        if (!IsCapturing || _waveIn is null || _writer is null || _buffer is null) return null;
        IsCapturing = false;

        var tcs = new TaskCompletionSource();
        void OnStopped(object? s, StoppedEventArgs e) => tcs.TrySetResult();
        _waveIn.RecordingStopped += OnStopped;
        _waveIn.StopRecording();
        await tcs.Task;
        _waveIn.RecordingStopped -= OnStopped;
        _waveIn.DataAvailable -= OnDataAvailable;

        // Patches the RIFF header's size fields in place with the real
        // length now that recording is done, without closing the stream —
        // Dispose() would do the same patch but also closes _buffer, and we
        // still need to read it back out below.
        _writer.Flush();
        var bytes = _buffer.ToArray();

        _waveIn.Dispose();
        _writer.Dispose();
        _waveIn = null;
        _writer = null;
        _buffer = null;

        return bytes.Length == 0 ? null : new MemoryStream(bytes);
    }

    public void Dispose()
    {
        _waveIn?.Dispose();
        _writer?.Dispose();
        _buffer?.Dispose();
    }
}

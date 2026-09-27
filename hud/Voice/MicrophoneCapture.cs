using System.IO;
using NAudio.Wave;

namespace Hud.Voice;

/// <summary>
/// Captures 16 kHz mono PCM — Whisper's native input format — directly, so
/// no resampling step is needed between mic and transcription.
///
/// Which mic: PHOENIX_VOICE_MIC (any part of the device name, e.g. "V8S")
/// picks one by name; otherwise the first input device. DeviceName says which
/// one it actually is, so the HUD can show it instead of leaving it a guess
/// (2026-09-27: the recording gear added the night before made "which mic is
/// voice using?" a real question).
/// </summary>
public sealed class MicrophoneCapture : IDisposable
{
    private WaveIn? _waveIn;
    private MemoryStream? _buffer;
    private WaveFileWriter? _writer;
    private int _peak;          // loudest 16-bit sample this recording
    private long _samples;

    public bool IsCapturing { get; private set; }
    public int DeviceNumber { get; }
    public string DeviceName { get; }

    /// <summary>Length of the last recording, in seconds.</summary>
    public double LastSeconds { get; private set; }

    /// <summary>Loudest point of the last recording in dBFS (0 = max, -90 ≈ nothing).</summary>
    public double LastPeakDb { get; private set; }

    public MicrophoneCapture(string? preferredName = null)
    {
        DeviceNumber = 0;
        DeviceName = "no microphone found";
        var count = WaveIn.DeviceCount;
        if (count == 0) return;
        for (var i = 0; i < count; i++)
        {
            var name = WaveIn.GetCapabilities(i).ProductName;
            if (!string.IsNullOrWhiteSpace(preferredName) && name.Contains(preferredName, StringComparison.OrdinalIgnoreCase))
            {
                DeviceNumber = i;
                DeviceName = name;
                return;
            }
        }
        DeviceName = WaveIn.GetCapabilities(0).ProductName;
    }

    public void Start()
    {
        if (IsCapturing) return;

        _peak = 0;
        _samples = 0;
        _buffer = new MemoryStream();
        _waveIn = new WaveIn
        {
            DeviceNumber = DeviceNumber,
            WaveFormat = new WaveFormat(16000, 16, 1),
            BufferMilliseconds = 50
        };
        _writer = new WaveFileWriter(_buffer, _waveIn.WaveFormat);
        _waveIn.DataAvailable += OnDataAvailable;
        _waveIn.StartRecording();
        IsCapturing = true;
    }

    private void OnDataAvailable(object? sender, WaveInEventArgs e)
    {
        _writer?.Write(e.Buffer, 0, e.BytesRecorded);
        for (var i = 0; i + 1 < e.BytesRecorded; i += 2)
        {
            var s = Math.Abs((int)BitConverter.ToInt16(e.Buffer, i));
            if (s > _peak) _peak = s;
        }
        _samples += e.BytesRecorded / 2;
    }

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

        LastSeconds = _samples / 16000.0;
        LastPeakDb = _peak == 0 ? -90 : 20 * Math.Log10(_peak / 32768.0);

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

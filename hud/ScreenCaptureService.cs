using System.Drawing;
using System.Drawing.Imaging;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using DrawingRectangle = System.Drawing.Rectangle;
using DrawingSize = System.Drawing.Size;
using DrawingPixelFormat = System.Drawing.Imaging.PixelFormat;

namespace Hud;

/// <summary>
/// Continuous desktop capture — the "see what I'm doing" half of the HUD's
/// purpose. Runs on a timer so it is actually continuous, per the explicit
/// requirement.
///
/// 2026-09-28: the frame now comes from DXGI Desktop Duplication
/// (DesktopDuplicationCapture) — the GPU's composed frame, no flicker — and
/// GDI CopyFromScreen is only the fallback when duplication is unavailable
/// (a locked/RDP session, a display change mid-run). The GDI path is the one
/// that flashed the HUD on every grab (Jerry: "it flashes on my screen every
/// time"). Which path is live is reported through <see cref="Mode"/>.
/// </summary>
public class ScreenCaptureService : IDisposable
{
    private readonly DispatcherTimer _timer;
    private DesktopDuplicationCapture? _dup;
    private int _dupFailures;
    private DateTime _nextDupRetry = DateTime.MinValue;
    private BitmapSource? _last;

    public event Action<BitmapSource>? FrameCaptured;
    /// <summary>"duplication" | "gdi" | "none" — for the H.L.K-10 status line.</summary>
    public string Mode { get; private set; } = "none";
    public event Action<string>? ModeChanged;

    public ScreenCaptureService(TimeSpan? interval = null)
    {
        _timer = new DispatcherTimer { Interval = interval ?? TimeSpan.FromMilliseconds(1000) };
        _timer.Tick += (_, _) => CaptureOnce();
    }

    public void Start() => _timer.Start();
    public void Stop() => _timer.Stop();

    private void SetMode(string m)
    {
        if (m == Mode) return;
        Mode = m;
        ModeChanged?.Invoke(m);
    }

    private void CaptureOnce()
    {
        var frame = CaptureViaDuplication() ?? CaptureViaGdi();
        if (frame is null) return;
        _last = frame;
        FrameCaptured?.Invoke(frame);
    }

    // Duplication reports only changes: a null from CaptureFrame() means
    // "nothing moved", so the last frame is re-published. A thrown error
    // (access lost, device removed) tears the duplication down; it is retried
    // after a short back-off, GDI carries the picture meanwhile.
    private BitmapSource? CaptureViaDuplication()
    {
        try
        {
            if (_dup is null)
            {
                if (DateTime.UtcNow < _nextDupRetry) return null;
                _dup = new DesktopDuplicationCapture();
                _dupFailures = 0;
                SetMode("duplication");
            }
            var frame = _dup.CaptureFrame();
            return frame ?? _last;
        }
        catch
        {
            _dup?.Dispose();
            _dup = null;
            _dupFailures++;
            _nextDupRetry = DateTime.UtcNow + TimeSpan.FromSeconds(Math.Min(60, 5 * _dupFailures));
            return null;
        }
    }

    private BitmapSource? CaptureViaGdi()
    {
        try
        {
            var left = (int)SystemParameters.VirtualScreenLeft;
            var top = (int)SystemParameters.VirtualScreenTop;
            var width = (int)SystemParameters.VirtualScreenWidth;
            var height = (int)SystemParameters.VirtualScreenHeight;
            using var bmp = new Bitmap(width, height, DrawingPixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(bmp))
            {
                g.CopyFromScreen(left, top, 0, 0, new DrawingSize(width, height), CopyPixelOperation.SourceCopy);
            }
            var bitmapSource = ToBitmapSource(bmp);
            bitmapSource.Freeze();
            SetMode("gdi");
            return bitmapSource;
        }
        catch
        {
            // A transient capture failure (e.g. display mode changing) shouldn't
            // kill the loop — just skip this tick, the next one will retry.
            return null;
        }
    }

    private static BitmapSource ToBitmapSource(Bitmap bmp)
    {
        var rect = new DrawingRectangle(0, 0, bmp.Width, bmp.Height);
        var data = bmp.LockBits(rect, ImageLockMode.ReadOnly, DrawingPixelFormat.Format32bppArgb);
        try
        {
            return BitmapSource.Create(
                bmp.Width, bmp.Height, 96, 96, PixelFormats.Bgra32, null,
                data.Scan0, data.Stride * bmp.Height, data.Stride);
        }
        finally
        {
            bmp.UnlockBits(data);
        }
    }

    public void Dispose()
    {
        _timer.Stop();
        _dup?.Dispose();
        _dup = null;
    }
}

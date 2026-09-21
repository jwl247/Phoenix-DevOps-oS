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
/// purpose. The Electron dashboard's Live Monitor panel captures on demand
/// (button click); this runs on a timer so it's actually continuous, per
/// the explicit requirement.
/// </summary>
public class ScreenCaptureService : IDisposable
{
    private readonly DispatcherTimer _timer;
    public event Action<BitmapSource>? FrameCaptured;

    public ScreenCaptureService(TimeSpan? interval = null)
    {
        _timer = new DispatcherTimer { Interval = interval ?? TimeSpan.FromMilliseconds(1000) };
        _timer.Tick += (_, _) => CaptureOnce();
    }

    public void Start() => _timer.Start();
    public void Stop() => _timer.Stop();

    private void CaptureOnce()
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
            FrameCaptured?.Invoke(bitmapSource);
        }
        catch
        {
            // A transient capture failure (e.g. display mode changing) shouldn't
            // kill the loop — just skip this tick, the next one will retry.
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

    public void Dispose() => _timer.Stop();
}

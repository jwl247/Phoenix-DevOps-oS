using System.Runtime.InteropServices;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;

namespace Hud;

/// <summary>
/// Desktop capture through DXGI Desktop Duplication (Windows 8+), one
/// duplication per monitor, composed into one virtual-screen frame.
///
/// Why this exists (Jerry, 2026-09-28: "it flashes on my screen every time"):
/// the previous GDI CopyFromScreen forces the compositor to re-render the
/// HUD's own topmost transparent window on every grab, which is the flash.
/// Duplication reads the composed frame the GPU already has: no flicker, a
/// fraction of the CPU, and the HUD keeps itself out of the picture with
/// WDA_EXCLUDEFROMCAPTURE (MainWindow). ScreenCaptureService falls back to
/// GDI if this cannot start or dies mid-run (RDP session, display change).
/// </summary>
public sealed class DesktopDuplicationCapture : IDisposable
{
    private sealed class Output : IDisposable
    {
        public required IDXGIOutputDuplication Duplication;
        public required ID3D11Texture2D Staging;
        public required int Left, Top, Width, Height;   // desktop coordinates
        public byte[]? LastPixels;                       // duplication only reports CHANGES; keep the last frame
        public void Dispose() { Duplication.Dispose(); Staging.Dispose(); }
    }

    private readonly ID3D11Device _device;
    private readonly ID3D11DeviceContext _context;
    private readonly List<Output> _outputs = new();
    private readonly int _vLeft, _vTop, _vWidth, _vHeight;
    private readonly byte[] _frame;                      // BGRA, virtual screen
    private bool _disposed;

    public int Width => _vWidth;
    public int Height => _vHeight;

    /// <summary>Throws when duplication is unavailable (no D3D11, session locked, etc.).</summary>
    public DesktopDuplicationCapture()
    {
        using var factory = DXGI.CreateDXGIFactory1<IDXGIFactory1>();
        if (factory.EnumAdapters1(0, out IDXGIAdapter1 adapter).Failure) throw new InvalidOperationException("no DXGI adapter");
        using (adapter)
        {
            var levels = new[] { FeatureLevel.Level_11_1, FeatureLevel.Level_11_0, FeatureLevel.Level_10_1, FeatureLevel.Level_10_0 };
            D3D11.D3D11CreateDevice(adapter, DriverType.Unknown, DeviceCreationFlags.BgraSupport, levels, out _device!, out _context!).CheckError();

            int minL = int.MaxValue, minT = int.MaxValue, maxR = int.MinValue, maxB = int.MinValue;
            for (uint i = 0; adapter.EnumOutputs(i, out IDXGIOutput output).Success; i++)
            {
                using (output)
                {
                    var desc = output.Description;
                    if (!desc.AttachedToDesktop) continue;
                    var r = desc.DesktopCoordinates;
                    int w = r.Right - r.Left, h = r.Bottom - r.Top;
                    using var output1 = output.QueryInterface<IDXGIOutput1>();
                    var dup = output1.DuplicateOutput(_device);
                    var staging = _device.CreateTexture2D(new Texture2DDescription
                    {
                        Width = (uint)w, Height = (uint)h, MipLevels = 1, ArraySize = 1,
                        Format = Format.B8G8R8A8_UNorm, SampleDescription = new SampleDescription(1, 0),
                        Usage = ResourceUsage.Staging, BindFlags = BindFlags.None, CPUAccessFlags = CpuAccessFlags.Read,
                    });
                    _outputs.Add(new Output { Duplication = dup, Staging = staging, Left = r.Left, Top = r.Top, Width = w, Height = h });
                    minL = Math.Min(minL, r.Left); minT = Math.Min(minT, r.Top); maxR = Math.Max(maxR, r.Right); maxB = Math.Max(maxB, r.Bottom);
                }
            }
        }
        if (_outputs.Count == 0) throw new InvalidOperationException("no attached outputs to duplicate");
        _vLeft = minL; _vTop = minT; _vWidth = maxR - minL; _vHeight = maxB - minT;
        _frame = new byte[_vWidth * _vHeight * 4];
    }

    /// <summary>
    /// One composed frame of the whole desktop. Returns null when no output
    /// changed since the last call (the caller keeps its previous frame).
    /// Throws on a lost duplication (caller recreates or falls back).
    /// </summary>
    public BitmapSource? CaptureFrame()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        bool any = false;
        foreach (var o in _outputs)
        {
            var hr = o.Duplication.AcquireNextFrame(0, out OutduplFrameInfo info, out IDXGIResource resource);
            if (hr == ResultCode.WaitTimeout) continue;               // nothing new on this monitor
            hr.CheckError();                                           // AccessLost etc. -> caller recreates
            try
            {
                if (info.LastPresentTime != 0 || o.LastPixels is null)
                {
                    using var tex = resource.QueryInterface<ID3D11Texture2D>();
                    _context.CopyResource(o.Staging, tex);
                    var map = _context.Map(o.Staging, 0, MapMode.Read, MapFlags.None);
                    try
                    {
                        o.LastPixels ??= new byte[o.Width * o.Height * 4];
                        int rowBytes = o.Width * 4;
                        for (int y = 0; y < o.Height; y++)
                            Marshal.Copy(map.DataPointer + (nint)(y * (long)map.RowPitch), o.LastPixels, y * rowBytes, rowBytes);
                    }
                    finally { _context.Unmap(o.Staging, 0); }
                    any = true;
                }
            }
            finally
            {
                resource.Dispose();
                o.Duplication.ReleaseFrame();
            }
        }
        if (!any) return null;

        // compose every monitor's last frame into the virtual screen
        int vRow = _vWidth * 4;
        foreach (var o in _outputs)
        {
            if (o.LastPixels is null) continue;
            int rowBytes = o.Width * 4;
            int x0 = (o.Left - _vLeft) * 4, y0 = o.Top - _vTop;
            for (int y = 0; y < o.Height; y++)
                Buffer.BlockCopy(o.LastPixels, y * rowBytes, _frame, (y0 + y) * vRow + x0, rowBytes);
        }
        var bmp = BitmapSource.Create(_vWidth, _vHeight, 96, 96, PixelFormats.Bgra32, null, _frame, vRow);
        bmp.Freeze();
        return bmp;
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        foreach (var o in _outputs) o.Dispose();
        _outputs.Clear();
        _context.Dispose();
        _device.Dispose();
    }
}

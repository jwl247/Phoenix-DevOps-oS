using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using Hud.Desktop;

namespace Hud;

/// <summary>
/// The Console's easy buttons (Jerry 10/8: "everything gets an easy button ... usys is the new common
/// command"). Each one runs ONE usys command in its own PS7 window that stays open, so the answer is on
/// screen. Arguments go to usys.ps1 as separate argv items (-File, never -Command): nothing typed here
/// is ever parsed as PowerShell.
/// </summary>
public static class UsysButtons
{
    public static string UsysScript => Path.Combine(FileActions.RepoRoot, "scripts", "usys.ps1");

    /// <summary>Run `usys verb args...` in a PS7 window that stays open.</summary>
    public static (bool ok, string why) Run(string verb, string? workDir = null, params string[] args)
    {
        if (!File.Exists(UsysScript)) return (false, $"usys isn't at {UsysScript}");
        var dir = workDir is { Length: > 0 } && Directory.Exists(workDir) ? workDir : FileActions.RepoRoot;
        var psi = new ProcessStartInfo("pwsh") { UseShellExecute = false, CreateNoWindow = false, WorkingDirectory = dir };
        foreach (var a in new[] { "-NoExit", "-NoLogo", "-File", UsysScript, verb }) psi.ArgumentList.Add(a);
        foreach (var a in args) psi.ArgumentList.Add(a);
        try { Process.Start(psi); return (true, ""); }
        catch (Exception e) { return (false, $"couldn't start PS7: {e.Message}"); }
    }

    public static string? PickFile(string title)
    {
        var d = new Microsoft.Win32.OpenFileDialog { Title = title, CheckFileExists = true };
        return d.ShowDialog() == true ? d.FileName : null;
    }

    public static string? PickFolder(string title)
    {
        var d = new Microsoft.Win32.OpenFolderDialog { Title = title };
        return d.ShowDialog() == true ? d.FolderName : null;
    }

    /// <summary>A one-line ask: type a name, or Browse… for a file. Returns null on cancel.</summary>
    public static string? Ask(string title, string prompt, bool allowBrowse)
    {
        var w = new Window { Title = title, Width = 560, SizeToContent = SizeToContent.Height, ResizeMode = ResizeMode.NoResize,
                             WindowStartupLocation = WindowStartupLocation.CenterScreen, Background = new SolidColorBrush(Color.FromRgb(0x0A, 0x0D, 0x10)) };
        var fg = new SolidColorBrush(Color.FromRgb(0x7F, 0xFF, 0xD4));
        var root = new StackPanel { Margin = new Thickness(14) };
        root.Children.Add(new TextBlock { Text = prompt, Foreground = fg, FontFamily = new FontFamily("Consolas"), Margin = new Thickness(0, 0, 0, 8), TextWrapping = TextWrapping.Wrap });
        var box = new TextBox { FontFamily = new FontFamily("Consolas"), FontSize = 14, Padding = new Thickness(6, 3, 6, 3) };
        root.Children.Add(box);
        var row = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 10, 0, 0) };
        string? result = null;
        if (allowBrowse)
        {
            var browse = new Button { Content = "Browse…", Padding = new Thickness(12, 4, 12, 4), Margin = new Thickness(0, 0, 8, 0) };
            browse.Click += (_, _) => { if (PickFile(title) is { } f) box.Text = f; };
            row.Children.Add(browse);
        }
        var ok = new Button { Content = "OK", IsDefault = true, Padding = new Thickness(18, 4, 18, 4), Margin = new Thickness(0, 0, 8, 0) };
        ok.Click += (_, _) => { if (box.Text.Trim().Length > 0) { result = box.Text.Trim(); w.Close(); } };
        var cancel = new Button { Content = "Cancel", IsCancel = true, Padding = new Thickness(12, 4, 12, 4) };
        row.Children.Add(ok); row.Children.Add(cancel);
        root.Children.Add(row);
        w.Content = root;
        w.Loaded += (_, _) => box.Focus();
        w.ShowDialog();
        return result;
    }
}

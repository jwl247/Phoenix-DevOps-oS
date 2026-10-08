using System.Diagnostics;
using System.IO;
using Hud.Desktop;

namespace Hud;

/// <summary>
/// The Console's one-click buttons transplanted from the Electron dashboard (Jerry 2026-10-08:
/// "open file explorer, open terminal, glossary needs to show code"). Each one is also in the tray menu.
/// </summary>
public static class ConsoleActions
{
    /// <summary>Phoenix's home folder, as the dashboard's OPEN FILE EXPLORER did (dirs.phoenix, else the repo).</summary>
    public static string PhoenixHome
    {
        get
        {
            var up = Path.GetDirectoryName(FileActions.RepoRoot);
            return up is not null && Directory.Exists(up) ? up : FileActions.RepoRoot;
        }
    }

    public static void OpenExplorer(string? folder = null)
    {
        var dir = folder is { Length: > 0 } && Directory.Exists(folder) ? folder : PhoenixHome;
        try { Process.Start(new ProcessStartInfo("explorer.exe", $"\"{dir}\"") { UseShellExecute = true }); }
        catch (Exception e) { FileActions.Log($"explorer failed: {e.Message}"); }
    }

    /// <summary>PS7 in the Phoenix repo: a Windows Terminal tab when wt is there, else a PS7 window.</summary>
    public static void OpenTerminal(string? folder = null)
    {
        var dir = folder is { Length: > 0 } && Directory.Exists(folder) ? folder : FileActions.RepoRoot;
        try
        {
            var wt = new ProcessStartInfo("wt.exe") { UseShellExecute = false };
            foreach (var a in new[] { "-d", dir, "pwsh", "-NoLogo" }) wt.ArgumentList.Add(a);
            Process.Start(wt);
        }
        catch
        {
            try { Process.Start(new ProcessStartInfo("pwsh", "-NoLogo") { UseShellExecute = true, WorkingDirectory = dir }); }
            catch (Exception e) { FileActions.Log($"terminal failed: {e.Message}"); }
        }
    }
}

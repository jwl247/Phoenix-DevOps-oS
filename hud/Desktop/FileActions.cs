using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;

namespace Hud.Desktop;

/// <summary>
/// The one engine behind every desktop file action: the HUD's drop shelf, the
/// Console, and Explorer's right-click "Phoenix" menu all call this, so a file
/// behaves the same whichever door it came through (Jerry, 2026-10-06: "the
/// entire desk top is drag and drop … move folder edit folders etc").
///
/// Rules it keeps:
/// - Works on files that are OPEN in another app: reads use FileShare.ReadWrite |
///   Delete, so Word/Excel/editors holding a file don't block a copy. A file
///   something has locked outright fails with a plain sentence, never silently.
/// - Never overwrites: a name that's taken becomes "name (2).ext".
/// - A move across drives is copy → SHA-256 verify → delete source; the source
///   is only removed once the copy is proven identical.
/// - Every action lands in actions.log (one line, timestamped), so "what did you
///   just do" always has an exact answer (CLAUDE.md: seamless, never un-auditable).
/// </summary>
public static class FileActions
{
    public static readonly string LogPath =
        Path.Combine(@"E:\", "Phoenix", "hud-live-monitor", "actions.log");

    /// <summary>The Phoenix repo (for intake); PHOENIX_ROOT wins, else the known home.</summary>
    public static string RepoRoot =>
        Environment.GetEnvironmentVariable("PHOENIX_ROOT") is { Length: > 0 } r && Directory.Exists(r)
            ? r : @"F:\Phoenix\Phoenix-DevOps-oS";

    /// <summary>pbmIII's read-write share: the mapped P: drive, else its mesh path.</summary>
    public static string ThirdBoxShare => Directory.Exists(@"P:\") ? @"P:\" : @"\\10.42.0.10\pbmIII";

    public record Result(bool Ok, string Message);

    public static void Log(string line)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(LogPath)!);
            File.AppendAllText(LogPath, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {line}{Environment.NewLine}");
        }
        catch { /* the action itself already happened; a full log disk must not undo it */ }
    }

    private static Result Done(bool ok, string message)
    {
        Log((ok ? "OK   " : "FAIL ") + message);
        return new Result(ok, message);
    }

    // ------------------------------------------------------------ copy / move
    public static Result CopyTo(string source, string destDir)
    {
        try
        {
            var dest = FreeName(Path.Combine(destDir, Path.GetFileName(source.TrimEnd('\\'))));
            if (Directory.Exists(source)) CopyDir(source, dest); else CopyFile(source, dest);
            return Done(true, $"copied {source} -> {dest}");
        }
        catch (Exception e) { return Done(false, $"copy {source}: {Plain(e)}"); }
    }

    public static Result MoveTo(string source, string destDir)
    {
        try
        {
            var dest = FreeName(Path.Combine(destDir, Path.GetFileName(source.TrimEnd('\\'))));
            var sameDrive = string.Equals(Path.GetPathRoot(Path.GetFullPath(source)),
                                          Path.GetPathRoot(Path.GetFullPath(destDir)), StringComparison.OrdinalIgnoreCase);
            if (sameDrive)
            {
                if (Directory.Exists(source)) Directory.Move(source, dest); else File.Move(source, dest);
            }
            else
            {
                if (Directory.Exists(source)) CopyDir(source, dest); else CopyFile(source, dest);
                if (!SameContent(source, dest))
                    return Done(false, $"move {source}: the copy at {dest} did not verify; source left in place");
                if (Directory.Exists(source)) Directory.Delete(source, recursive: true); else File.Delete(source);
            }
            return Done(true, $"moved {source} -> {dest}");
        }
        catch (Exception e) { return Done(false, $"move {source}: {Plain(e)}"); }
    }

    public static Result Rename(string source, string newName)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(newName) || newName.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
                return Done(false, $"rename {source}: \"{newName}\" isn't a valid name");
            var dest = Path.Combine(Path.GetDirectoryName(source.TrimEnd('\\'))!, newName.Trim());
            if (File.Exists(dest) || Directory.Exists(dest))
                return Done(false, $"rename {source}: {newName} already exists there");
            if (Directory.Exists(source)) Directory.Move(source, dest); else File.Move(source, dest);
            return Done(true, $"renamed {source} -> {dest}");
        }
        catch (Exception e) { return Done(false, $"rename {source}: {Plain(e)}"); }
    }

    public static Result NewFolder(string where, string name)
    {
        try
        {
            var parent = Directory.Exists(where) ? where : Path.GetDirectoryName(where)!;
            var dest = FreeName(Path.Combine(parent, string.IsNullOrWhiteSpace(name) ? "New folder" : name.Trim()));
            Directory.CreateDirectory(dest);
            return Done(true, $"new folder {dest}");
        }
        catch (Exception e) { return Done(false, $"new folder in {where}: {Plain(e)}"); }
    }

    public static Result ShowInExplorer(string path)
    {
        try
        {
            Process.Start(new ProcessStartInfo("explorer.exe", $"/select,\"{path}\"") { UseShellExecute = true });
            return Done(true, $"shown in Explorer: {path}");
        }
        catch (Exception e) { return Done(false, $"show {path}: {Plain(e)}"); }
    }

    public static Result SendToThirdBox(string source) => CopyTo(source, ThirdBoxShare);

    // ------------------------------------------------------------ intake
    /// <summary>Through Frank's import method (scripts/hsf-intake.sh): hex, sidecar, R2, D1.</summary>
    public static async Task<Result> IntakeAsync(string source)
    {
        var bash = new[] { @"C:\Program Files\Git\bin\bash.exe", @"C:\Program Files\Git\usr\bin\bash.exe" }
            .FirstOrDefault(File.Exists);
        if (bash is null) return Done(false, $"intake {source}: Git Bash not found");
        var script = Path.Combine(RepoRoot, "scripts", "hsf-intake.sh");
        if (!File.Exists(script)) return Done(false, $"intake {source}: {script} not found");
        var psi = new ProcessStartInfo(bash)
        {
            RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false,
            CreateNoWindow = true, WorkingDirectory = RepoRoot,
        };
        psi.ArgumentList.Add(ToBashPath(script));
        psi.ArgumentList.Add(ToBashPath(source));
        try
        {
            using var p = Process.Start(psi)!;
            var outTask = p.StandardOutput.ReadToEndAsync();
            var errTask = p.StandardError.ReadToEndAsync();
            await p.WaitForExitAsync();
            var all = (await outTask) + (await errTask);
            var ok = p.ExitCode == 0 && all.Contains("intake:OK", StringComparison.Ordinal)
                     || all.Contains("Version   :", StringComparison.Ordinal);
            var tail = string.Join(" | ", all.Split('\n').Select(l => l.Trim())
                .Where(l => l.StartsWith("[intake:OK]") || l.StartsWith("Version") || l.Contains("ERROR")).Take(3));
            return Done(ok, $"intake {source}: {(tail.Length > 0 ? tail : $"exit {p.ExitCode}")}");
        }
        catch (Exception e) { return Done(false, $"intake {source}: {Plain(e)}"); }
    }

    internal static string ToBashPath(string win)
    {
        var full = Path.GetFullPath(win);
        return full.Length > 1 && full[1] == ':'
            ? "/" + char.ToLowerInvariant(full[0]) + full[2..].Replace('\\', '/')
            : full.Replace('\\', '/');
    }

    // ------------------------------------------------------------ helpers
    /// <summary>"name.ext" if free, else "name (2).ext", "name (3).ext" …</summary>
    internal static string FreeName(string wanted)
    {
        if (!File.Exists(wanted) && !Directory.Exists(wanted)) return wanted;
        var dir = Path.GetDirectoryName(wanted)!;
        var stem = Path.GetFileNameWithoutExtension(wanted);
        var ext = Directory.Exists(wanted) ? "" : Path.GetExtension(wanted);
        if (Directory.Exists(wanted)) stem = Path.GetFileName(wanted);
        for (var i = 2; ; i++)
        {
            var c = Path.Combine(dir, $"{stem} ({i}){ext}");
            if (!File.Exists(c) && !Directory.Exists(c)) return c;
        }
    }

    /// <summary>Shared-read copy: works while another app has the file open.</summary>
    internal static void CopyFile(string src, string dest)
    {
        using (var input = new FileStream(src, FileMode.Open, FileAccess.Read,
                                          FileShare.ReadWrite | FileShare.Delete, 1 << 20))
        using (var output = new FileStream(dest, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1 << 20))
            input.CopyTo(output, 1 << 20);
        File.SetLastWriteTimeUtc(dest, File.GetLastWriteTimeUtc(src));
    }

    internal static void CopyDir(string src, string dest)
    {
        Directory.CreateDirectory(dest);
        foreach (var f in Directory.EnumerateFiles(src)) CopyFile(f, Path.Combine(dest, Path.GetFileName(f)));
        foreach (var d in Directory.EnumerateDirectories(src))
        {
            // a junction/symlink is copied as a link target would be dangerous (loops); skip it, say so
            if (new DirectoryInfo(d).Attributes.HasFlag(FileAttributes.ReparsePoint))
            {
                Log($"SKIP link {d} (not followed)");
                continue;
            }
            CopyDir(d, Path.Combine(dest, Path.GetFileName(d)));
        }
    }

    internal static bool SameContent(string a, string b)
    {
        if (File.Exists(a)) return File.Exists(b) && Hash(a).SequenceEqual(Hash(b));
        if (!Directory.Exists(b)) return false;
        var fa = Directory.EnumerateFiles(a, "*", SearchOption.AllDirectories)
            .Select(f => Path.GetRelativePath(a, f)).OrderBy(x => x, StringComparer.OrdinalIgnoreCase).ToList();
        var fb = Directory.EnumerateFiles(b, "*", SearchOption.AllDirectories)
            .Select(f => Path.GetRelativePath(b, f)).OrderBy(x => x, StringComparer.OrdinalIgnoreCase).ToList();
        return fa.SequenceEqual(fb, StringComparer.OrdinalIgnoreCase)
               && fa.All(rel => Hash(Path.Combine(a, rel)).SequenceEqual(Hash(Path.Combine(b, rel))));
    }

    private static byte[] Hash(string path)
    {
        using var s = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 1 << 20);
        return SHA256.HashData(s);
    }

    /// <summary>Exceptions in words Jerry and Laurie can act on.</summary>
    internal static string Plain(Exception e) => e switch
    {
        IOException io when (io.HResult & 0xFFFF) is 32 or 33 =>
            "another program has it locked. Close it there and try again",
        UnauthorizedAccessException => "Windows says no permission for that location",
        FileNotFoundException or DirectoryNotFoundException => "it isn't there anymore",
        _ => e.Message,
    };
}

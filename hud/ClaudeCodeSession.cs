using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;

namespace Hud;

/// <summary>
/// Full Claude Code (every tool, working in the repo) driven the same way
/// H.L.K-10's chat is: one background `claude -p` run per message, no
/// terminal window. Replaces the old ConPTY companion window (ClaudeCliWindow),
/// which was a separate opaque window stuck on top of the HUD and died to
/// "Session Terminated" (Jerry, 2026-09-27: "if you make claude cli like the
/// hlk10's it'd work, being clear").
///
/// Conversation memory: the first run's session_id is kept and every later
/// message runs with --resume, so it's one continuing conversation until
/// NewSession() is called.
///
/// Output is --output-format stream-json: one JSON object per line. We turn
/// the ones that matter into plain events (what it said, which tool it used
/// on what, the final result) and ignore the rest (hooks, thinking, rate limits).
/// </summary>
public sealed class ClaudeCodeSession
{
    public event Action<string>? Said;                 // a block of Claude's text
    public event Action<string>? UsedTool;             // "Bash: git status", "Edit: hud/MainWindow.xaml"
    public event Action<string>? ToolFailed;           // a tool result that came back as an error
    public event Action<bool, string, double>? Finished; // ok, error text (if any), seconds

    public string? SessionId { get; private set; }
    public bool IsRunning => _proc is { HasExited: false };

    private Process? _proc;
    private readonly string _workingDir;

    public ClaudeCodeSession(string workingDir) => _workingDir = workingDir;

    public void NewSession() => SessionId = null;

    public void Stop()
    {
        try { if (_proc is { HasExited: false }) _proc.Kill(entireProcessTree: true); }
        catch { /* already gone */ }
    }

    public void Send(string message)
    {
        if (IsRunning) throw new InvalidOperationException("still working on the last message");
        var started = DateTime.UtcNow;

        var args = new StringBuilder("-p --output-format stream-json --verbose --dangerously-skip-permissions");
        if (SessionId is not null) args.Append(" --resume ").Append(SessionId);

        var psi = new ProcessStartInfo
        {
            FileName = FindClaudeExe(),
            Arguments = args.ToString(),
            WorkingDirectory = _workingDir,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false),
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        // Subscription only: never fall back to pay-per-token API billing
        // (same rule as AiChatService's CLI path), and never start as a
        // nested child of whatever Claude Code session launched the HUD.
        psi.EnvironmentVariables.Remove("ANTHROPIC_API_KEY");
        psi.EnvironmentVariables.Remove("ANTHROPIC_AUTH_TOKEN");
        foreach (var key in psi.EnvironmentVariables.Keys.Cast<string>().ToList())
            if (key.StartsWith("CLAUDE_CODE_", StringComparison.Ordinal) || key == "CLAUDECODE")
                psi.EnvironmentVariables.Remove(key);

        var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        var stderr = new StringBuilder();
        string? resultError = null;
        bool sawResult = false;

        proc.OutputDataReceived += (_, e) =>
        {
            if (string.IsNullOrWhiteSpace(e.Data)) return;
            try { Handle(e.Data, ref sawResult, ref resultError); }
            catch (JsonException) { /* a non-JSON line; ignore */ }
        };
        proc.ErrorDataReceived += (_, e) => { if (e.Data != null) stderr.AppendLine(e.Data); };
        proc.Exited += (_, _) =>
        {
            // Let the async readers drain before deciding how it went.
            try { proc.WaitForExit(); } catch { }
            var secs = (DateTime.UtcNow - started).TotalSeconds;
            if (!sawResult)
            {
                var why = stderr.Length > 0 ? stderr.ToString().Trim() : $"stopped (exit {SafeExitCode(proc)})";
                Finished?.Invoke(false, why, secs);
            }
            else Finished?.Invoke(resultError is null, resultError ?? "", secs);
            _proc = null;
        };

        _proc = proc;
        proc.Start();
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();
        proc.StandardInput.Write(message);
        proc.StandardInput.Close();
    }

    private void Handle(string line, ref bool sawResult, ref string? resultError)
    {
        using var doc = JsonDocument.Parse(line);
        var root = doc.RootElement;
        var type = Str(root, "type");

        if (type == "system" && Str(root, "subtype") == "init")
        {
            SessionId = Str(root, "session_id") ?? SessionId;
            return;
        }
        if (type == "assistant" && root.TryGetProperty("message", out var msg) && msg.TryGetProperty("content", out var content))
        {
            foreach (var c in content.EnumerateArray())
            {
                var ct = Str(c, "type");
                if (ct == "text")
                {
                    var text = Str(c, "text");
                    if (!string.IsNullOrWhiteSpace(text)) Said?.Invoke(text.Trim());
                }
                else if (ct == "tool_use")
                {
                    UsedTool?.Invoke(DescribeTool(Str(c, "name") ?? "tool", c.TryGetProperty("input", out var inp) ? inp : default));
                }
            }
            return;
        }
        if (type == "user" && root.TryGetProperty("message", out var umsg) && umsg.TryGetProperty("content", out var ucontent)
            && ucontent.ValueKind == JsonValueKind.Array)
        {
            foreach (var c in ucontent.EnumerateArray())
            {
                if (Str(c, "type") == "tool_result" && c.TryGetProperty("is_error", out var isErr) && isErr.ValueKind == JsonValueKind.True)
                {
                    var body = c.TryGetProperty("content", out var b) ? (b.ValueKind == JsonValueKind.String ? b.GetString() : b.ToString()) : "";
                    ToolFailed?.Invoke(Shorten(body ?? "", 200));
                }
            }
            return;
        }
        if (type == "result")
        {
            sawResult = true;
            SessionId = Str(root, "session_id") ?? SessionId;
            var isError = root.TryGetProperty("is_error", out var ie) && ie.ValueKind == JsonValueKind.True;
            if (isError) resultError = Str(root, "result") ?? Str(root, "subtype") ?? "failed";
        }
    }

    // One short line per tool call: what it did, on what.
    private static string DescribeTool(string name, JsonElement input)
    {
        string? pick(params string[] keys)
        {
            if (input.ValueKind != JsonValueKind.Object) return null;
            foreach (var k in keys)
                if (input.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String) return v.GetString();
            return null;
        }
        var detail = name switch
        {
            "Bash" or "PowerShell" => pick("description", "command"),
            "Read" or "Write" or "Edit" or "NotebookEdit" => RelPath(pick("file_path", "notebook_path")),
            "Glob" or "Grep" => pick("pattern"),
            "WebFetch" => pick("url"),
            "WebSearch" => pick("query"),
            "Agent" or "Task" => pick("description"),
            _ => null,
        };
        return detail is null ? name : $"{name}: {Shorten(detail, 140)}";
    }

    private static string? RelPath(string? p)
    {
        if (p is null) return null;
        var root = Environment.CurrentDirectory.TrimEnd('\\', '/') + Path.DirectorySeparatorChar;
        return p.StartsWith(root, StringComparison.OrdinalIgnoreCase) ? p[root.Length..] : p;
    }

    private static string Shorten(string s, int max)
    {
        s = s.Replace("\r", " ").Replace("\n", " ").Trim();
        return s.Length <= max ? s : s[..(max - 1)] + "…";
    }

    private static string? Str(JsonElement e, string name) =>
        e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    private static int SafeExitCode(Process p)
    {
        try { return p.ExitCode; } catch { return -1; }
    }

    // This machine's real install is the native ~/.local/bin/claude.exe (not
    // the npm claude.cmd older code assumed — the bug that silenced H.L.K-10
    // on 2026-09-22). Running the .exe directly also skips a cmd.exe layer.
    private static string FindClaudeExe()
    {
        var native = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".local", "bin", "claude.exe");
        if (File.Exists(native)) return native;
        var npm = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "npm", "claude.cmd");
        return File.Exists(npm) ? npm : "claude";
    }
}

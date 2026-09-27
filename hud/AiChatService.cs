using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Hud;

/// <summary>
/// Ported from dashboard/main.js's real ai-chat IPC handler — same config file,
/// same provider chain (helpdesk -> ollama -> claude -> subscription, with the
/// same Ollama-failure-falls-back-to-restricted-Claude-CLI safety net), so the
/// HUD shares whatever auth the existing dashboard already has configured
/// instead of requiring its own separate setup.
/// </summary>
public class AiChatResult
{
    public bool Success { get; set; }
    public string Provider { get; set; } = "";
    public string Reply { get; set; } = "";
    public string? Error { get; set; }
    /// <summary>What H.L.K's hands did on the way to this reply, one line each.</summary>
    public List<string> Steps { get; set; } = new();
}

public class AiAuthConfig
{
    public string Provider { get; set; } = "helpdesk";
    public string? Key { get; set; }
    public string? Model { get; set; }
    public string? OllamaUrl { get; set; }
}

public class AiChatService
{
    private static readonly string PhoenixConfDir =
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".phoenix");
    private static readonly string AuthFile = Path.Combine(PhoenixConfDir, "ai_auth.json");
    private static readonly string EnvFile = Path.Combine(PhoenixConfDir, "phoenix.env");

    private readonly HttpClient _http = new HttpClient { Timeout = TimeSpan.FromSeconds(120) };
    private readonly List<(string role, string content)> _history = new();

    public AiAuthConfig Config { get; private set; } = new();

    public AiChatService()
    {
        LoadConfig();
    }

    public void LoadConfig()
    {
        var cfg = new AiAuthConfig();
        try
        {
            if (File.Exists(AuthFile))
            {
                var json = File.ReadAllText(AuthFile);
                var doc = JsonSerializer.Deserialize<JsonElement>(json);
                if (doc.TryGetProperty("provider", out var p)) cfg.Provider = p.GetString() ?? "helpdesk";
                if (doc.TryGetProperty("key", out var k)) cfg.Key = k.GetString();
                if (doc.TryGetProperty("model", out var m)) cfg.Model = m.GetString();
                if (doc.TryGetProperty("ollamaUrl", out var o)) cfg.OllamaUrl = o.GetString();
            }
        }
        catch { /* same tolerant behavior as main.js: bad/missing file just falls back to defaults */ }

        // phoenix.env can override boot-relevant keys, same precedence as loadPhoenixEnv() in main.js
        try
        {
            if (File.Exists(EnvFile))
            {
                foreach (var raw in File.ReadAllLines(EnvFile))
                {
                    var line = raw.Trim();
                    if (line.Length == 0 || line.StartsWith("#")) continue;
                    var eq = line.IndexOf('=');
                    if (eq < 1) continue;
                    var key = line[..eq].Trim();
                    var val = line[(eq + 1)..].Trim().Trim('"', '\'');
                    if (key == "PHOENIX_AI_PROVIDER") cfg.Provider = val;
                    if (key == "PHOENIX_OLLAMA_URL") cfg.OllamaUrl = val;
                }
            }
        }
        catch { }

        var envKey = Environment.GetEnvironmentVariable("PHOENIX_AI_KEY")
                     ?? Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY");
        if (!string.IsNullOrEmpty(envKey)) cfg.Key ??= envKey;

        Config = cfg;
    }

    /// <param name="imagePath">
    /// Current Live Monitor frame, saved to disk by MainWindow just before this
    /// call — ties the HUD's "see" half (ScreenCaptureService) to its "act" half
    /// (this chat/voice loop), which previously sat side by side with no wiring
    /// between them (Jerry, 2026-09-22: "they have to tie together"). The Claude
    /// API path attaches it as a real vision content block; the CLI paths point
    /// Claude at the file path (Read is never in the disallowed-tools list, so
    /// even the restricted CLI can open it). Ollama's configured model
    /// (llama3.2, text-only) gets no image — silently skipped there.
    /// </param>
    public async Task<AiChatResult> SendAsync(string message, string? imagePath = null, Action<string>? onChunk = null)
    {
        var steps = new List<string>();

        // A tool that "asks first" is waiting: THIS message is the user's answer.
        // The HUD decides yes/no itself from the user's own words; the model is
        // never asked and can never say yes on the user's behalf.
        if (_pending is { } p)
        {
            _pending = null;
            if (!IsYes(message))
            {
                _history.Add(("user", message));
                _history.Add(("assistant", "Okay, I won't."));
                steps.Add($"{p.Machine} · {p.Label} · you said no, nothing was done");
                return new AiChatResult { Success = true, Provider = "hands", Reply = "Okay, I won't.", Steps = steps };
            }
            var (st, body) = await _hands.RunAsync(p.Machine, p.Tool, p.Args, confirm: true);
            steps.Add(StepLine(p.Machine, p.Label, st, body, confirmed: true));
            _history.Add(("user", $"{message}\n\n{ToolResultText(p.Machine, p.Tool, st, body)}"));
            return await ModelLoopAsync(null, onChunk, steps);
        }

        _history.Add(("user", message));
        return await ModelLoopAsync(imagePath, onChunk, steps);
    }

    // ── H.L.K's hands: the fixed tool list, driven by any model ─────────────
    // CLAUDE.md, "THE INTERACTION MODEL": Phoenix's own abilities as declared,
    // callable tools with permission tiers, not a raw shell to improvise with.
    // The protocol is one plain line (ACTION {json}) on purpose: a small local
    // Ollama model can drive it too, so the fallback story holds.
    private readonly HandsClient _hands = new();
    private PendingAction? _pending;
    private const int MaxSteps = 4;

    private sealed record PendingAction(string Machine, string Tool, string Label, JsonElement Args);

    private const string BasePrompt =
        "You are H.L.K-10, the onboard AI running inside Phoenix's own HUD — Jerry's platform, " +
        "not a demo. Be direct, useful, and concise.";

    private async Task<AiChatResult> ModelLoopAsync(string? imagePath, Action<string>? onChunk, List<string> steps)
    {
        var catalog = await _hands.DescribeAsync();
        var systemPrompt = catalog.Length == 0 ? BasePrompt : BasePrompt + "\n\n" +
            "You can act on Phoenix machines through H.L.K's hands. The tools available right now:\n" + catalog +
            "\nTo use one, reply with ONLY this single line and nothing else:\n" +
            "ACTION {\"machine\": \"compaq\", \"tool\": \"status\", \"args\": {}}\n" +
            "The HUD runs it and gives you the result; then answer the user in plain words (no raw JSON). " +
            "Use a tool only when the user asks for something a tool does. Never say you did something " +
            "unless a result came back saying it was done. Tools marked [asks the user first]: request them " +
            "normally; the HUD asks the user and only the user's own yes runs them. Never ask for, assume or " +
            "claim that yes yourself.";

        string provider = "";
        for (var i = 0; i < MaxSteps; i++)
        {
            var filter = new ActionAwareStream(onChunk);
            var call = await CallProviderAsync(systemPrompt, i == 0 ? imagePath : null, filter.Push);
            if (!call.ok)
                return new AiChatResult { Success = false, Provider = call.provider, Error = call.error, Steps = steps };
            provider = call.provider;

            var action = ParseAction(call.reply);
            if (action is null)
            {
                _history.Add(("assistant", call.reply));
                return new AiChatResult { Success = true, Provider = provider, Reply = call.reply, Steps = steps };
            }

            _history.Add(("assistant", action.Value.raw));
            var (st, body) = await _hands.RunAsync(action.Value.machine, action.Value.tool, action.Value.args, confirm: false);
            var label = ToolLabel(action.Value.tool, action.Value.args);

            if (st == 409 && body.TryGetProperty("needs_confirm", out var nc) && nc.ValueKind == JsonValueKind.True)
            {
                var question = (body.TryGetProperty("question", out var q) ? q.GetString() : null)
                               ?? $"{label} on {action.Value.machine}?";
                _pending = new PendingAction(action.Value.machine, action.Value.tool, label, action.Value.args);
                var ask = $"{question} Say yes to go ahead, or no.";
                _history.Add(("assistant", ask));
                steps.Add($"{action.Value.machine} · {label} · waiting for your yes");
                return new AiChatResult { Success = true, Provider = provider, Reply = ask, Steps = steps };
            }

            steps.Add(StepLine(action.Value.machine, label, st, body, confirmed: false));
            _history.Add(("user", ToolResultText(action.Value.machine, action.Value.tool, st, body)));
        }

        const string stopped = "I stopped after four steps without a final answer. Tell me what you want next.";
        _history.Add(("assistant", stopped));
        return new AiChatResult { Success = true, Provider = provider, Reply = stopped, Steps = steps };
    }

    /// <summary>One model call on the configured provider chain. Doesn't touch history.</summary>
    private async Task<(bool ok, string provider, string reply, string? error)> CallProviderAsync(
        string systemPrompt, string? imagePath, Action<string>? onChunk)
    {
        var provider = (Config.Provider ?? "helpdesk").ToLowerInvariant();

        if (provider is "helpdesk" or "ollama")
        {
            try
            {
                return (true, "ollama", await ChatOllamaAsync(systemPrompt), null);
            }
            catch (Exception e)
            {
                if (provider == "ollama") return (false, "ollama", "", e.Message);
                // helpdesk: fall through to restricted Claude CLI safety net, same as main.js
            }
        }

        if (provider == "claude")
        {
            try
            {
                return (true, $"claude/{Config.Model ?? "claude-sonnet-5"}", await ChatClaudeApiStreamAsync(systemPrompt, imagePath, onChunk), null);
            }
            catch (Exception e)
            {
                return (false, "claude", "", e.Message);
            }
        }

        if (provider == "subscription")
        {
            try
            {
                return (true, "claude/subscription", await RunClaudeCliAsync(BuildFullPrompt(systemPrompt, imagePath), fullTools: true, onChunk), null);
            }
            catch (Exception e)
            {
                return (false, "claude/subscription", "", e.Message);
            }
        }

        // Ollama-failure fallback — restricted-tool Claude CLI, same safety net as main.js
        try
        {
            return (true, "claude/subscription", await RunClaudeCliAsync(BuildFullPrompt(systemPrompt, imagePath), fullTools: false, onChunk: null), null);
        }
        catch (Exception e)
        {
            return (false, "helpdesk", "",
                $"All Help Desk providers unavailable. {e.Message}\nStart Ollama (ollama serve) or set ANTHROPIC_API_KEY for Claude.");
        }
    }

    /// <summary>
    /// Finds an "ACTION {json}" line. Only machine, tool and args are read: a
    /// "confirm" the model writes is dropped, so it can never approve its own
    /// ask-first action.
    /// </summary>
    internal static (string machine, string tool, JsonElement args, string raw)? ParseAction(string reply)
    {
        foreach (var rawLine in reply.Split('\n'))
        {
            var line = rawLine.Trim().Trim('`').Trim();
            if (!line.StartsWith("ACTION", StringComparison.Ordinal)) continue;
            var brace = line.IndexOf('{');
            if (brace < 0) continue;
            try
            {
                var j = JsonSerializer.Deserialize<JsonElement>(line[brace..]);
                var machine = j.TryGetProperty("machine", out var m) ? m.GetString() : null;
                var tool = j.TryGetProperty("tool", out var t) ? t.GetString() : null;
                if (string.IsNullOrWhiteSpace(machine) || string.IsNullOrWhiteSpace(tool)) continue;
                machine = machine.ToLowerInvariant().Replace(".phx", "");
                var args = j.TryGetProperty("args", out var a) && a.ValueKind == JsonValueKind.Object
                    ? a : JsonSerializer.Deserialize<JsonElement>("{}");
                return (machine, tool, args, line);
            }
            catch (JsonException)
            {
                // not a real action line; keep looking
            }
        }
        return null;
    }

    private static readonly HashSet<string> YesWords = new(StringComparer.OrdinalIgnoreCase)
        { "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed", "affirmative", "go", "proceed" };
    private static readonly string[] NoWords = { "no", "nope", "don't", "dont", "not", "wait", "stop", "cancel", "hold" };

    /// <summary>The user's own words decide; anything unclear counts as no.</summary>
    internal static bool IsYes(string message)
    {
        var words = new string(message.ToLowerInvariant().Select(c => char.IsLetter(c) || c == '\'' || c == ' ' ? c : ' ').ToArray())
            .Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (words.Length == 0 || words.Length > 6) return false;
        if (words.Any(w => NoWords.Contains(w))) return false;
        var text = string.Join(' ', words);
        return YesWords.Contains(words[0]) || text.StartsWith("do it") || text.StartsWith("go ahead");
    }

    private static string ToolLabel(string tool, JsonElement args)
    {
        string? arg(string k) => args.ValueKind == JsonValueKind.Object && args.TryGetProperty(k, out var v) ? v.GetString() : null;
        return tool switch
        {
            "open_app" => $"open {arg("app") ?? "an app"}",
            "restart_service" => $"restart {arg("service") ?? "a service"}",
            "restart_pc" => "restart the machine",
            "cancel_restart" => "cancel the restart",
            _ => tool.Replace('_', ' '),
        };
    }

    private static string StepLine(string machine, string label, int status, JsonElement body, bool confirmed)
    {
        var ok = status == 200 && body.TryGetProperty("ok", out var o) && o.ValueKind == JsonValueKind.True;
        var err = body.TryGetProperty("error", out var e) ? e.GetString() : $"HTTP {status}";
        return $"{machine} · {label} · {(ok ? (confirmed ? "done, you said yes" : "done") : $"not done: {err}")}";
    }

    private static string ToolResultText(string machine, string tool, int status, JsonElement body)
    {
        var json = body.GetRawText();
        if (json.Length > 1500) json = json[..1500] + "…";
        return $"[hands result: {machine} / {tool}, HTTP {status}] {json}\n" +
               "Answer the user now in plain words from this result. Only use another ACTION if one more step is really needed.";
    }

    /// <summary>
    /// Streams the reply to the screen, except an ACTION line: that is held
    /// back (it's for the HUD, not the user). Text that clearly isn't an
    /// ACTION flows through as it arrives.
    /// </summary>
    private sealed class ActionAwareStream(Action<string>? sink)
    {
        private readonly StringBuilder _held = new();
        private bool _decided, _isAction;

        public void Push(string chunk)
        {
            if (sink is null) return;
            if (_decided)
            {
                if (!_isAction) sink(chunk);
                return;
            }
            _held.Append(chunk);
            var start = _held.ToString().TrimStart().TrimStart('`');
            if (start.Length < "ACTION".Length && "ACTION".StartsWith(start, StringComparison.Ordinal)) return;
            _decided = true;
            _isAction = start.StartsWith("ACTION", StringComparison.Ordinal);
            if (!_isAction) sink(_held.ToString());
        }
    }

    private string BuildFullPrompt(string systemPrompt, string? imagePath)
    {
        var historyText = string.Join("\n", _history.SkipLast(1).Select(t => $"{(t.role == "user" ? "User" : "Assistant")}: {t.content}"));
        var last = _history.Last().content;
        var imageNote = imagePath is not null && File.Exists(imagePath)
            ? $"\n\n[Live Monitor screenshot of the current desktop is saved at: {imagePath} — Read it if it's relevant to answering.]"
            : "";
        return $"{systemPrompt}{imageNote}\n\n{(historyText.Length > 0 ? historyText + "\n\n" : "")}User: {last}";
    }

    // A small local model, left to write prose, ignored the ACTION protocol and
    // made up a machine's status (live 2026-09-26: "8 GB, up 2 hours" for a
    // 15.5 GB box it never asked). With the hands in play it now has to answer
    // in a fixed shape Ollama enforces: {"say": ...} or {"action": {...}}.
    private static readonly object OllamaReplyShape = new
    {
        type = "object",
        properties = new
        {
            say = new { type = "string" },
            action = new
            {
                type = "object",
                properties = new
                {
                    machine = new { type = "string" },
                    tool = new { type = "string" },
                    args = new { type = "object" },
                },
                required = new[] { "machine", "tool" },
            },
        },
    };

    private const string OllamaShapeRules =
        "\n\nReply ONLY with JSON. To use a tool: {\"action\": {\"machine\": \"compaq\", \"tool\": \"status\", \"args\": {}}}. " +
        "To answer the user: {\"say\": \"your answer\"}. You know NOTHING about any machine's memory, disks, load, " +
        "services or state unless a [hands result] in this conversation told you; if the user asks about a machine, " +
        "use a tool first. Never say an action was sent, done or cancelled unless a [hands result] says so.";

    private async Task<string> ChatOllamaAsync(string systemPrompt)
    {
        var url = (Config.OllamaUrl ?? "http://localhost:11434").TrimEnd('/') + "/api/chat";
        var tools = systemPrompt.Contains("ACTION {", StringComparison.Ordinal);
        var messages = new List<object> { new { role = "system", content = tools ? systemPrompt + OllamaShapeRules : systemPrompt } };
        messages.AddRange(_history.Select(t => (object)new { role = t.role, content = t.content }));
        var body = tools
            ? JsonSerializer.Serialize(new { model = "llama3", messages, stream = false, format = OllamaReplyShape, options = new { temperature = 0 } })
            : JsonSerializer.Serialize(new { model = "llama3", messages, stream = false });
        var res = await _http.PostAsync(url, new StringContent(body, Encoding.UTF8, "application/json"));
        if (!res.IsSuccessStatusCode) throw new Exception($"Ollama {(int)res.StatusCode}");
        var json = await res.Content.ReadAsStringAsync();
        var doc = JsonSerializer.Deserialize<JsonElement>(json);
        var reply = doc.GetProperty("message").GetProperty("content").GetString() ?? "";
        if (reply.Length == 0) throw new Exception("Ollama returned empty response");
        return tools ? FromOllamaShape(reply) : reply;
    }

    /// <summary>{"action":...} -> an ACTION line for the loop; {"say":...} -> the answer.</summary>
    internal static string FromOllamaShape(string reply)
    {
        try
        {
            var j = JsonSerializer.Deserialize<JsonElement>(reply);
            if (j.TryGetProperty("action", out var a) && a.ValueKind == JsonValueKind.Object
                && a.TryGetProperty("machine", out _) && a.TryGetProperty("tool", out _))
                return "ACTION " + a.GetRawText();
            if (j.TryGetProperty("say", out var s) && s.GetString() is { Length: > 0 } say) return say;
        }
        catch (JsonException) { }
        return reply;
    }

    private async Task<string> ChatClaudeApiStreamAsync(string systemPrompt, string? imagePath, Action<string>? onChunk)
    {
        var apiKey = Config.Key ?? Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY");
        if (string.IsNullOrEmpty(apiKey)) throw new Exception("No Anthropic API key");
        var model = Config.Model ?? "claude-sonnet-5";

        // Real vision, not a file-path hint — only the last (current) user
        // turn gets the image, so history doesn't re-send stale screenshots.
        // Tool results can put two turns from the same side back to back; the
        // API wants them alternating, so they're merged first.
        var merged = new List<(string role, string content)>();
        foreach (var h in _history)
        {
            if (merged.Count > 0 && merged[^1].role == h.role)
                merged[^1] = (h.role, merged[^1].content + "\n\n" + h.content);
            else merged.Add(h);
        }
        var messages = new List<object>();
        for (var i = 0; i < merged.Count; i++)
        {
            var t = merged[i];
            var isCurrentUserTurn = i == merged.Count - 1 && t.role == "user";
            if (isCurrentUserTurn && imagePath is not null && File.Exists(imagePath))
            {
                var b64 = Convert.ToBase64String(File.ReadAllBytes(imagePath));
                messages.Add(new
                {
                    role = "user",
                    content = new object[]
                    {
                        new { type = "image", source = new { type = "base64", media_type = "image/png", data = b64 } },
                        new { type = "text", text = t.content }
                    }
                });
            }
            else
            {
                messages.Add(new { role = t.role, content = t.content });
            }
        }
        var payload = JsonSerializer.Serialize(new { model, max_tokens = 1024, system = systemPrompt, messages, stream = true });

        using var req = new HttpRequestMessage(HttpMethod.Post, "https://api.anthropic.com/v1/messages");
        req.Headers.Add("x-api-key", apiKey);
        req.Headers.Add("anthropic-version", "2023-06-01");
        req.Content = new StringContent(payload, Encoding.UTF8, "application/json");

        using var res = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead);
        if (!res.IsSuccessStatusCode)
        {
            var err = await res.Content.ReadAsStringAsync();
            throw new Exception($"Claude API {(int)res.StatusCode}: {err[..Math.Min(200, err.Length)]}");
        }

        await using var stream = await res.Content.ReadAsStreamAsync();
        using var reader = new StreamReader(stream);
        var full = new StringBuilder();
        string? line;
        while ((line = await reader.ReadLineAsync()) != null)
        {
            if (!line.StartsWith("data:")) continue;
            var jsonStr = line[5..].Trim();
            if (jsonStr.Length == 0) continue;
            try
            {
                var evt = JsonSerializer.Deserialize<JsonElement>(jsonStr);
                if (evt.TryGetProperty("type", out var t) && t.GetString() == "content_block_delta"
                    && evt.TryGetProperty("delta", out var d) && d.TryGetProperty("text", out var txt))
                {
                    var chunk = txt.GetString() ?? "";
                    full.Append(chunk);
                    onChunk?.Invoke(chunk);
                }
            }
            catch { }
        }
        if (full.Length == 0) throw new Exception("Claude API returned empty response");
        return full.ToString();
    }

    // Same fix as ClaudeCliWindow.xaml.cs's ResolveClaudeCli() (2026-09-21) —
    // this machine's real install is a native binary at ~/.local/bin/claude.exe,
    // not the npm-global claude.cmd this used to assume. That mismatch silently
    // broke the "helpdesk" provider's Ollama-down fallback (confirmed live
    // 2026-09-22: Ollama not running -> falls through to this CLI path -> cmd.exe
    // can't find claude.cmd -> voice/chat gets no reply at all).
    private static string FindClaudeCli()
    {
        string[] candidates =
        {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".local", "bin", "claude.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "npm", "claude.cmd"),
        };
        foreach (var c in candidates)
        {
            if (File.Exists(c)) return $"\"{c}\"";
        }
        return "claude.cmd";
    }

    private static Task<string> RunClaudeCliAsync(string prompt, bool fullTools, Action<string>? onChunk)
    {
        var tcs = new TaskCompletionSource<string>();
        var cli = FindClaudeCli();
        var args = fullTools
            ? "--print --dangerously-skip-permissions"
            : "--print --disallowedTools Bash,Write,Edit,WebFetch,WebSearch";

        var psi = new ProcessStartInfo
        {
            FileName = "cmd.exe",
            Arguments = $"/c {cli} {args}",
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        // Same reasoning as main.js: strip API-key auth so a CLI-tier call
        // can't silently fall back to pay-per-token billing.
        psi.EnvironmentVariables.Remove("ANTHROPIC_API_KEY");
        psi.EnvironmentVariables.Remove("ANTHROPIC_AUTH_TOKEN");

        var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        var stdout = new StringBuilder();
        var stderr = new StringBuilder();
        proc.OutputDataReceived += (_, e) =>
        {
            if (e.Data == null) return;
            stdout.AppendLine(e.Data);
            onChunk?.Invoke(e.Data + "\n");
        };
        proc.ErrorDataReceived += (_, e) => { if (e.Data != null) stderr.AppendLine(e.Data); };
        proc.Exited += (_, _) =>
        {
            if (proc.ExitCode != 0) tcs.TrySetException(new Exception(stderr.Length > 0 ? stderr.ToString() : $"claude exited {proc.ExitCode}"));
            else tcs.TrySetResult(stdout.ToString().Trim());
        };

        proc.Start();
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();
        proc.StandardInput.Write(prompt);
        proc.StandardInput.Close();

        return tcs.Task;
    }
}

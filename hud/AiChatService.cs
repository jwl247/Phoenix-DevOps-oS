using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

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

    // HUD-F04: the whole transcript is re-sent on every model call (and, on
    // the subscription tier, re-spawned into a fresh `claude -p` each turn),
    // so it is capped to the last 20 turns — 40 entries — like the dashboard.
    private const int MaxHistoryEntries = 40;

    private void Remember(string role, string content)
    {
        _history.Add((role, content));
        if (_history.Count > MaxHistoryEntries) _history.RemoveRange(0, _history.Count - MaxHistoryEntries);
    }

    public AiAuthConfig Config { get; private set; } = new();

    /// <summary>
    /// Plain-words lines for the pane that aren't a reply: "[HANDS] catalog: …"
    /// when the reachable hands change, "[SYS] ollama: …" when the configured
    /// model isn't the one that ends up running. Subscribing starts the
    /// background hands refresh (HUD-F03), so no line can fire before anyone
    /// is listening.
    /// </summary>
    public event Action<string>? Note
    {
        add { _note += value; EnsureHandsStarted(); }
        remove { _note -= value; }
    }
    private Action<string>? _note;

    public AiChatService()
    {
        LoadConfig();
        _hands.CatalogChanged += line => _note?.Invoke("[HANDS] " + line);
    }

    /// <summary>What the last hands fetch found, or null before the first one lands.</summary>
    public string? HandsCatalogLine => _hands.CatalogLine is { } l ? "[HANDS] " + l : null;

    private void EnsureHandsStarted() => _hands.StartBackgroundRefresh(TimeSpan.FromMinutes(1));

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
                    if (key == "PHOENIX_AI_MODEL" && val.Length > 0) cfg.Model = val;   // same key the dashboard honours
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
    /// even the restricted CLI can open it). Ollama's model (text-only) gets
    /// no image — silently skipped there.
    /// </param>
    public async Task<AiChatResult> SendAsync(string message, string? imagePath = null, Action<string>? onChunk = null)
    {
        var steps = new List<string>();
        EnsureHandsStarted();

        // A tool that "asks first" is waiting: THIS message is the user's answer.
        // The HUD decides yes/no itself from the user's own words; the model is
        // never asked and can never say yes on the user's behalf.
        if (_pending is { } p)
        {
            _pending = null;
            if (!IsYes(message))
            {
                Remember("user", message);
                Remember("assistant", "Okay, I won't.");
                steps.Add($"{p.Machine} · {p.Label} · you said no, nothing was done");
                return new AiChatResult { Success = true, Provider = "hands", Reply = "Okay, I won't.", Steps = steps };
            }
            var (st, body) = await _hands.RunAsync(p.Machine, p.Tool, p.Args, confirm: true);
            steps.Add(StepLine(p.Machine, p.Label, st, body, confirmed: true));
            Remember("user", $"{message}\n\n{ToolResultText(p.Machine, p.Tool, st, body)}");
            return await ModelLoopAsync(null, onChunk, steps);
        }

        Remember("user", message);
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
                Remember("assistant", call.reply);
                return new AiChatResult { Success = true, Provider = provider, Reply = call.reply, Steps = steps };
            }

            Remember("assistant", action.Value.raw);
            var (st, body) = await _hands.RunAsync(action.Value.machine, action.Value.tool, action.Value.args, confirm: false);
            var label = ToolLabel(action.Value.tool, action.Value.args);

            if (st == 409 && body.TryGetProperty("needs_confirm", out var nc) && nc.ValueKind == JsonValueKind.True)
            {
                var question = (body.TryGetProperty("question", out var q) ? q.GetString() : null)
                               ?? $"{label} on {action.Value.machine}?";
                _pending = new PendingAction(action.Value.machine, action.Value.tool, label, action.Value.args);
                var ask = $"{question} Say yes to go ahead, or no.";
                Remember("assistant", ask);
                steps.Add($"{action.Value.machine} · {label} · waiting for your yes");
                return new AiChatResult { Success = true, Provider = provider, Reply = ask, Steps = steps };
            }

            steps.Add(StepLine(action.Value.machine, label, st, body, confirmed: false));
            Remember("user", ToolResultText(action.Value.machine, action.Value.tool, st, body));
        }

        const string stopped = "I stopped after four steps without a final answer. Tell me what you want next.";
        Remember("assistant", stopped);
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

    // HUD-F01 (2026-09-28 audit): the old gate took any short message whose
    // FIRST word was a yes-word and that had none of nine no-words in it — so
    // "okay, what will that restart?" ran the restart. Now the WHOLE message
    // has to be a yes phrase (or a run of them: "Yeah, do it."), and anything
    // with a question mark is never a yes. CLAUDE.md, THE INTERACTION MODEL:
    // tier 2 runs on the user's own yes, only.
    private static readonly Regex YesPhrase = new(
        @"^(yes|yeah|yep|yup|ok|okay|sure|confirm(ed)?|affirmative|go|proceed|do it|go ahead)( please)?$",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    /// <summary>The user's own words decide; anything unclear counts as no.</summary>
    internal static bool IsYes(string message)
    {
        if (string.IsNullOrWhiteSpace(message) || message.Contains('?')) return false;
        // "Yeah, do it." / "OK!" / "yes, please": every comma- or
        // period-separated piece must itself be a yes phrase. One stray clause
        // ("yes if it's safe", "sure but which one") and it is not a yes.
        var pieces = message
            .Split(new[] { ',', '.', '!', ';' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(p => Regex.Replace(p, @"\s+", " "))
            .ToArray();
        if (pieces.Length == 0) return false;
        for (var i = 0; i < pieces.Length; i++)
        {
            if (YesPhrase.IsMatch(pieces[i])) continue;
            if (i > 0 && pieces[i].Equals("please", StringComparison.OrdinalIgnoreCase)) continue;
            return false;
        }
        return true;
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
    /// Streams the reply to the screen, except ACTION lines (and bare code
    /// fences around them): those are for the HUD, not the user, and are held
    /// back wherever they appear. Before HUD-F07 the decision was made once on
    /// the first chunk, so "Sure.\n```\nACTION {…}\n```" — the shape a CLI tier
    /// streams line by line — leaked the raw JSON into the chat. Now it works
    /// per line: a line goes out as soon as it clearly isn't an ACTION line,
    /// or when it ends.
    /// </summary>
    private sealed class ActionAwareStream(Action<string>? sink)
    {
        private readonly StringBuilder _line = new();   // the current, unfinished line
        private bool _passing;                          // this line already went out as it arrived

        public void Push(string chunk)
        {
            if (sink is null || chunk.Length == 0) return;
            var start = 0;
            while (start < chunk.Length)
            {
                var nl = chunk.IndexOf('\n', start);
                if (nl < 0) { Take(chunk[start..], endOfLine: false); return; }
                Take(chunk[start..(nl + 1)], endOfLine: true);
                start = nl + 1;
            }
        }

        private void Take(string piece, bool endOfLine)
        {
            if (_passing)
            {
                sink!(piece);
                if (endOfLine) _passing = false;
                return;
            }
            _line.Append(piece);
            var text = _line.ToString();
            var head = text.TrimStart().TrimStart('`').TrimStart();
            if (endOfLine)
            {
                var bare = text.Trim();
                var isFence = bare.Length > 0 && bare.All(c => c == '`');
                if (!head.StartsWith("ACTION", StringComparison.Ordinal) && !isFence) sink!(text);
                _line.Clear();
                return;
            }
            var couldBeAction = head.Length < "ACTION".Length
                ? "ACTION".StartsWith(head, StringComparison.Ordinal)
                : head.StartsWith("ACTION", StringComparison.Ordinal);
            if (couldBeAction) return;   // keep holding until the line decides itself
            sink!(text);
            _line.Clear();
            _passing = true;
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

    // HUD-F04 / UI-F08: honour the configured model (ai_auth.json "model" or
    // PHOENIX_AI_MODEL; "llama3" when neither is set) the way the dashboard's
    // _resolveOllamaModel does: if it isn't pulled, use the closest pulled name
    // (exact, then prefix, then whatever is there) instead of failing, and say
    // so once in the pane. On this box today ai_auth.json says llama3.2 and
    // only llama3:latest is pulled, so that fallback is what keeps Ollama
    // answering until Jerry pulls llama3.2 or changes the config.
    private string? _resolvedOllamaModel;

    private async Task<string> ResolveOllamaModelAsync(string baseUrl)
    {
        if (_resolvedOllamaModel is not null) return _resolvedOllamaModel;
        var preferred = string.IsNullOrWhiteSpace(Config.Model) ? "llama3" : Config.Model.Trim();
        List<string> pulled;
        try
        {
            var json = await _http.GetStringAsync(baseUrl + "/api/tags");
            pulled = JsonSerializer.Deserialize<JsonElement>(json).GetProperty("models").EnumerateArray()
                .Select(m => m.TryGetProperty("name", out var n) ? n.GetString() : null)
                .OfType<string>().ToList();
        }
        catch
        {
            return preferred;   // Ollama itself is down: let /api/chat fail with the real error
        }
        var pick = pulled.FirstOrDefault(n => n == preferred || n == preferred + ":latest")
                   ?? pulled.FirstOrDefault(n => n.StartsWith(preferred, StringComparison.OrdinalIgnoreCase))
                   ?? pulled.FirstOrDefault()
                   ?? preferred;
        if (pick != preferred && pick != preferred + ":latest")
            _note?.Invoke($"[SYS] ollama: model \"{preferred}\" isn't pulled — using \"{pick}\" (ollama pull {preferred} to change that).");
        return _resolvedOllamaModel = pick;
    }

    private async Task<string> ChatOllamaAsync(string systemPrompt)
    {
        var baseUrl = (Config.OllamaUrl ?? "http://localhost:11434").TrimEnd('/');
        var url = baseUrl + "/api/chat";
        var model = await ResolveOllamaModelAsync(baseUrl);
        var tools = systemPrompt.Contains("ACTION {", StringComparison.Ordinal);
        var messages = new List<object> { new { role = "system", content = tools ? systemPrompt + OllamaShapeRules : systemPrompt } };
        messages.AddRange(_history.Select(t => (object)new { role = t.role, content = t.content }));
        var body = tools
            ? JsonSerializer.Serialize(new { model, messages, stream = false, format = OllamaReplyShape, options = new { temperature = 0 } })
            : JsonSerializer.Serialize(new { model, messages, stream = false });
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
        var payload = JsonSerializer.Serialize(new { model, max_tokens = ClaudeMaxTokens, system = systemPrompt, messages, stream = true });

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
        string? stopReason = null;
        string? line;
        while ((line = await reader.ReadLineAsync()) != null)
        {
            if (!line.StartsWith("data:")) continue;
            var jsonStr = line[5..].Trim();
            if (jsonStr.Length == 0) continue;
            JsonElement evt;
            try { evt = JsonSerializer.Deserialize<JsonElement>(jsonStr); }
            catch (JsonException) { continue; }   // not an event we can read; the next line may be
            var type = evt.TryGetProperty("type", out var t) ? t.GetString() : null;
            if (type == "content_block_delta"
                && evt.TryGetProperty("delta", out var d) && d.TryGetProperty("text", out var txt))
            {
                var chunk = txt.GetString() ?? "";
                full.Append(chunk);
                onChunk?.Invoke(chunk);
            }
            else if (type == "error")
            {
                // HUD-F15: a mid-stream error (overloaded_error, rate_limit_error…)
                // arrives as an event on a 200 stream, not as a status code. It
                // used to be swallowed and show up as a truncated or "empty" reply.
                var err = evt.TryGetProperty("error", out var e) && e.ValueKind == JsonValueKind.Object ? e : evt;
                var kind = err.TryGetProperty("type", out var k) ? k.GetString() : "error";
                var msg = err.TryGetProperty("message", out var m) ? m.GetString() : jsonStr;
                throw new Exception($"Claude API stream error ({kind}): {msg}");
            }
            else if (type == "message_delta"
                     && evt.TryGetProperty("delta", out var md) && md.TryGetProperty("stop_reason", out var sr))
            {
                stopReason = sr.GetString();
            }
        }
        // HUD-F15: the reply's own stop reason. A refusal is not an answer, and
        // a reply cut off at the token cap must not be passed off as complete
        // (ParseAction on a truncated ACTION line silently becomes prose).
        if (stopReason == "refusal") throw new Exception("Claude declined to answer this (stop_reason: refusal).");
        if (stopReason == "max_tokens")
            throw new Exception($"reply cut off at max_tokens={ClaudeMaxTokens}. What came through: {full}");
        if (full.Length == 0) throw new Exception("Claude API returned empty response");
        return full.ToString();
    }

    private const int ClaudeMaxTokens = 1024;

    // This machine's real install is a native binary at ~/.local/bin/claude.exe,
    // not the npm-global claude.cmd this used to assume — a mismatch that
    // silently broke the "helpdesk" provider's Ollama-down fallback (confirmed
    // live 2026-09-22: Ollama not running -> falls through to this CLI path ->
    // cmd.exe can't find claude.cmd -> voice/chat gets no reply at all). The
    // lookup is ClaudeCodeSession.InstalledPath, shared with the CLAUDE CODE
    // pane and the startup [SYS] line, so all three agree on what's installed.
    //
    // HUD-F06: the .exe is run directly as FileName. `cmd.exe /c "<path>" …`
    // strips the quotes when the profile path has a space (C:\Users\Laurie
    // Leftwich\) and runs C:\Users\Laurie instead. Only the npm .cmd shim still
    // needs cmd.exe; it is wrapped in a second pair of quotes, cmd's own rule
    // for keeping the inner ones.
    private static ProcessStartInfo ClaudeCliStartInfo(string args)
    {
        var cli = ClaudeCodeSession.InstalledPath() ?? "claude";
        return cli.EndsWith(".cmd", StringComparison.OrdinalIgnoreCase) || cli.EndsWith(".bat", StringComparison.OrdinalIgnoreCase)
            ? new ProcessStartInfo { FileName = "cmd.exe", Arguments = $"/c \"\"{cli}\" {args}\"" }
            : new ProcessStartInfo { FileName = cli, Arguments = args };
    }

    private static Task<string> RunClaudeCliAsync(string prompt, bool fullTools, Action<string>? onChunk)
    {
        var tcs = new TaskCompletionSource<string>();
        var args = fullTools
            ? "--print --dangerously-skip-permissions"
            : "--print --disallowedTools Bash,Write,Edit,WebFetch,WebSearch";

        var psi = ClaudeCliStartInfo(args);
        psi.RedirectStandardInput = true;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        // Claude Code writes UTF-8. Without these, .NET read it as the
        // console code page and every em dash came out as "â€”".
        psi.StandardInputEncoding = new UTF8Encoding(false);
        psi.StandardOutputEncoding = Encoding.UTF8;
        psi.StandardErrorEncoding = Encoding.UTF8;
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
            // HUD-F05: Exited can fire before the last OutputDataReceived
            // callbacks; WaitForExit() with no timeout drains them first, the
            // same way ClaudeCodeSession does. Otherwise a long reply's tail
            // (or the ACTION line at its end) could be lost.
            try { proc.WaitForExit(); } catch { }
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

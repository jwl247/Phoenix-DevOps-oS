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

    public async Task<AiChatResult> SendAsync(string message, Action<string>? onChunk = null)
    {
        _history.Add(("user", message));
        var provider = (Config.Provider ?? "helpdesk").ToLowerInvariant();
        var systemPrompt = "You are H.L.K-10, the onboard AI running inside Phoenix's own HUD — Jerry's platform, " +
                            "not a demo. Be direct, useful, and concise.";

        if (provider is "helpdesk" or "ollama")
        {
            try
            {
                var reply = await ChatOllamaAsync(systemPrompt);
                _history.Add(("assistant", reply));
                return new AiChatResult { Success = true, Provider = "ollama", Reply = reply };
            }
            catch (Exception e)
            {
                if (provider == "ollama")
                    return new AiChatResult { Success = false, Provider = "ollama", Error = e.Message };
                // helpdesk: fall through to restricted Claude CLI safety net, same as main.js
            }
        }

        if (provider == "claude")
        {
            try
            {
                var reply = await ChatClaudeApiStreamAsync(systemPrompt, onChunk);
                _history.Add(("assistant", reply));
                return new AiChatResult { Success = true, Provider = $"claude/{Config.Model ?? "claude-sonnet-5"}", Reply = reply };
            }
            catch (Exception e)
            {
                return new AiChatResult { Success = false, Provider = "claude", Error = e.Message };
            }
        }

        if (provider == "subscription")
        {
            try
            {
                var reply = await RunClaudeCliAsync(BuildFullPrompt(systemPrompt), fullTools: true, onChunk);
                _history.Add(("assistant", reply));
                return new AiChatResult { Success = true, Provider = "claude/subscription", Reply = reply };
            }
            catch (Exception e)
            {
                return new AiChatResult { Success = false, Provider = "claude/subscription", Error = e.Message };
            }
        }

        // Ollama-failure fallback — restricted-tool Claude CLI, same safety net as main.js
        try
        {
            var reply = await RunClaudeCliAsync(BuildFullPrompt(systemPrompt), fullTools: false, onChunk: null);
            _history.Add(("assistant", reply));
            return new AiChatResult { Success = true, Provider = "claude/subscription", Reply = reply };
        }
        catch (Exception e)
        {
            return new AiChatResult
            {
                Success = false,
                Provider = "helpdesk",
                Error = $"All Help Desk providers unavailable. {e.Message}\nStart Ollama (ollama serve) or set ANTHROPIC_API_KEY for Claude."
            };
        }
    }

    private string BuildFullPrompt(string systemPrompt)
    {
        var historyText = string.Join("\n", _history.SkipLast(1).Select(t => $"{(t.role == "user" ? "User" : "Assistant")}: {t.content}"));
        var last = _history.Last().content;
        return $"{systemPrompt}\n\n{(historyText.Length > 0 ? historyText + "\n\n" : "")}User: {last}";
    }

    private async Task<string> ChatOllamaAsync(string systemPrompt)
    {
        var url = (Config.OllamaUrl ?? "http://localhost:11434").TrimEnd('/') + "/api/chat";
        var messages = new List<object> { new { role = "system", content = systemPrompt } };
        messages.AddRange(_history.Select(t => (object)new { role = t.role, content = t.content }));
        var body = JsonSerializer.Serialize(new { model = "llama3", messages, stream = false });
        var res = await _http.PostAsync(url, new StringContent(body, Encoding.UTF8, "application/json"));
        if (!res.IsSuccessStatusCode) throw new Exception($"Ollama {(int)res.StatusCode}");
        var json = await res.Content.ReadAsStringAsync();
        var doc = JsonSerializer.Deserialize<JsonElement>(json);
        var reply = doc.GetProperty("message").GetProperty("content").GetString() ?? "";
        if (reply.Length == 0) throw new Exception("Ollama returned empty response");
        return reply;
    }

    private async Task<string> ChatClaudeApiStreamAsync(string systemPrompt, Action<string>? onChunk)
    {
        var apiKey = Config.Key ?? Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY");
        if (string.IsNullOrEmpty(apiKey)) throw new Exception("No Anthropic API key");
        var model = Config.Model ?? "claude-sonnet-5";

        var messages = _history.Select(t => (object)new { role = t.role, content = t.content }).ToList();
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

    private static string FindClaudeCli()
    {
        var npmGlobal = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "npm", "claude.cmd");
        return File.Exists(npmGlobal) ? $"\"{npmGlobal}\"" : "claude.cmd";
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

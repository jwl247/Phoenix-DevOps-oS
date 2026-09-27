using System.Net.Http;
using System.Text;
using System.Text.Json;

namespace Hud;

/// <summary>
/// H.L.K-10's way to the hands: the same Phoenix Console API the Console's
/// buttons use (portal/server.py -> hands/hands.py on each machine), so voice,
/// typing and clicking all end at one fixed tool list with one set of tiers
/// and one audit log. H.L.K never talks to a machine's hands directly and
/// never holds a hands token; the Console does.
/// </summary>
public sealed class HandsClient
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(60) };
    private readonly string _base =
        (Environment.GetEnvironmentVariable("PHOENIX_CONSOLE_URL") ?? "http://127.0.0.1:8470").TrimEnd('/');

    private JsonElement? _machines;
    private DateTime _machinesAt = DateTime.MinValue;

    /// <summary>machine name -> { ok, version, tools[] }, cached a minute. Null when the Console is down.</summary>
    public async Task<JsonElement?> GetMachinesAsync()
    {
        if (_machines is not null && DateTime.UtcNow - _machinesAt < TimeSpan.FromMinutes(1)) return _machines;
        try
        {
            var json = await Http.GetStringAsync(_base + "/api/hands");
            _machines = JsonSerializer.Deserialize<JsonElement>(json).GetProperty("machines");
            _machinesAt = DateTime.UtcNow;
        }
        catch
        {
            _machines = null;
        }
        return _machines;
    }

    /// <summary>The live tool list, written for the model. Empty when nothing is reachable.</summary>
    public async Task<string> DescribeAsync()
    {
        var machines = await GetMachinesAsync();
        if (machines is null) return "";
        var sb = new StringBuilder();
        foreach (var m in machines.Value.EnumerateObject())
        {
            if (!m.Value.TryGetProperty("ok", out var ok) || !ok.GetBoolean()) continue;
            sb.AppendLine($"- {m.Name}.phx:");
            foreach (var t in m.Value.GetProperty("tools").EnumerateArray())
            {
                var name = t.GetProperty("name").GetString();
                var tier = t.GetProperty("tier").GetString();
                var says = t.GetProperty("says").GetString();
                var args = "";
                if (t.TryGetProperty("params", out var p) && p.ValueKind == JsonValueKind.Object)
                {
                    var parts = new List<string>();
                    foreach (var a in p.EnumerateObject())
                        parts.Add(a.Value.ValueKind == JsonValueKind.Array
                            ? $"{a.Name}: one of {string.Join(", ", a.Value.EnumerateArray().Select(x => x.GetString()))}"
                            : $"{a.Name}: {a.Value.GetString()}");
                    if (parts.Count > 0) args = $" (args: {string.Join("; ", parts)})";
                }
                sb.AppendLine($"    {name}{args}: {says}{(tier == "ask" ? " [asks the user first]" : "")}");
            }
        }
        return sb.ToString();
    }

    /// <summary>
    /// Runs one tool. confirm is set ONLY by the HUD after the user's own yes;
    /// the model's ACTION line can never carry it (AiChatService strips it).
    /// Returns (HTTP status, response body).
    /// </summary>
    public async Task<(int status, JsonElement body)> RunAsync(string machine, string tool, JsonElement args, bool confirm)
    {
        var payload = JsonSerializer.Serialize(new { tool, args, confirm });
        using var req = new HttpRequestMessage(HttpMethod.Post, $"{_base}/api/hands/{Uri.EscapeDataString(machine)}/run")
        {
            Content = new StringContent(payload, Encoding.UTF8, "application/json"),
        };
        req.Headers.Add("X-Phoenix-Console", "1");
        req.Headers.Add("X-Phoenix-Via", "hlk");
        try
        {
            using var res = await Http.SendAsync(req);
            var text = await res.Content.ReadAsStringAsync();
            JsonElement body;
            try { body = JsonSerializer.Deserialize<JsonElement>(text); }
            catch { body = JsonSerializer.Deserialize<JsonElement>(JsonSerializer.Serialize(new { ok = false, error = text })); }
            return ((int)res.StatusCode, body);
        }
        catch (Exception e)
        {
            return (503, JsonSerializer.Deserialize<JsonElement>(
                JsonSerializer.Serialize(new { ok = false, error = $"the Console isn't answering ({e.GetType().Name})" })));
        }
    }
}

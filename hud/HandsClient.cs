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

    // HUD-F03 (2026-09-28 audit): the Console answers /api/hands by asking
    // every machine in turn, 22 s measured with pbm3 down. That used to sit
    // on the message path, so the first H.L.K turn each minute stalled with
    // nothing on screen. Now the catalog is fetched in the background on a
    // timer and a message uses the last one that landed. One snapshot object
    // is swapped whole, so the timer thread and the message path never see
    // half an update.
    private sealed record Snapshot(JsonElement Machines, DateTime At);
    private volatile Snapshot? _snap;
    private readonly object _gate = new();
    private Task? _inflight;
    private int _started;

    private static readonly TimeSpan MaxAge = TimeSpan.FromMinutes(1);
    // Before the very first catalog lands, a message waits this long for it
    // and then goes on without tools rather than stalling the whole turn.
    private static readonly TimeSpan FirstWait = TimeSpan.FromSeconds(3);

    /// <summary>"catalog: compaq, precision (pbm3 unreachable)", or null before the first fetch.</summary>
    public string? CatalogLine { get; private set; }

    /// <summary>Fires with the new CatalogLine whenever it changes. Raised on a background thread.</summary>
    public event Action<string>? CatalogChanged;

    /// <summary>Starts the timer once; later calls do nothing.</summary>
    public void StartBackgroundRefresh(TimeSpan every)
    {
        if (Interlocked.Exchange(ref _started, 1) == 1) return;
        _ = Task.Run(async () =>
        {
            while (true)
            {
                await RefreshAsync();
                await Task.Delay(every);
            }
        });
    }

    private Task RefreshAsync()
    {
        lock (_gate) return _inflight ??= FetchAsync();
    }

    private async Task FetchAsync()
    {
        await Task.Yield();   // never finish inside RefreshAsync's lock, or _inflight would never clear
        try
        {
            var json = await Http.GetStringAsync(_base + "/api/hands");
            var machines = JsonSerializer.Deserialize<JsonElement>(json).GetProperty("machines");
            _snap = new Snapshot(machines, DateTime.UtcNow);
            var up = new List<string>();
            var down = new List<string>();
            foreach (var m in machines.EnumerateObject())
                (m.Value.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.True ? up : down).Add(m.Name);
            SetLine("catalog: " + (up.Count > 0 ? string.Join(", ", up) : "no machine reachable")
                    + (down.Count > 0 ? $" ({string.Join(", ", down)} unreachable)" : ""));
        }
        catch (Exception e)
        {
            // The Console itself isn't answering: no hands, and say so.
            _snap = null;
            SetLine($"the Console isn't answering ({e.GetType().Name}) — no hands until it does");
        }
        finally
        {
            lock (_gate) _inflight = null;
        }
    }

    private void SetLine(string line)
    {
        if (line == CatalogLine) return;
        CatalogLine = line;
        CatalogChanged?.Invoke(line);
    }

    /// <summary>
    /// machine name -> { ok, version, tools[] } from the last background fetch.
    /// Null when the Console is down. Never waits on the Console once a first
    /// catalog exists; a stale one just starts a refresh.
    /// </summary>
    public async Task<JsonElement?> GetMachinesAsync()
    {
        var snap = _snap;
        if (snap is not null && DateTime.UtcNow - snap.At < MaxAge) return snap.Machines;
        var refresh = RefreshAsync();
        if (snap is null) await Task.WhenAny(refresh, Task.Delay(FirstWait));
        return _snap?.Machines ?? snap?.Machines;
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

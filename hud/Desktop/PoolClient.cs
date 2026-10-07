using System.IO;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Hud.Desktop;

/// <summary>
/// Suits in the clone pool (Console list item 1, Jerry 2026-10-07: "clone pool look-up becomes Suit look-up").
/// Search goes two ways at once: the pool by NAME (packages-worker /search) and Atlas by WHAT IT DOES
/// (/connections, the CONNECTIONS.md descriptions). A file Atlas describes is matched back to its pool row,
/// so a word like "checkin" finds lifefirst_checkin.py even though the name alone would not.
/// Code is fetched read-only and checked against its D1 SHA3-512 custody before it is shown.
/// </summary>
public static class PoolClient
{
    public record Suit(string Name, string Hex, string Version, int Tier, string State, string What, string RepoPath)
    {
        /// <summary>genie_control's in-RAM import is Python-only; other code can be read, not imported.</summary>
        public bool Importable => InPool && Name.EndsWith(".py", StringComparison.OrdinalIgnoreCase);
        /// <summary>False = Atlas describes it but it was never intaked (no pool row, no custody).</summary>
        public bool InPool => Hex.Length > 0;
        public string Line => InPool ? $"{Name}  {Version}  T{Tier}  {(Hex.Length > 12 ? Hex[..12] + "…" : Hex)}"
                                     : $"{Name}  - not in the pool";
    }

    /// <summary>Code a suit can be made of (genie_control's suffix map).</summary>
    private static readonly string[] SuitExt = { ".py", ".sh", ".ps1", ".js", ".mjs" };
    private static readonly Regex HexRe = new("^[0-9a-f]{2,128}$", RegexOptions.Compiled);
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(20) };
    private static readonly string[] Boilerplate = { "Auto-generated from TAV intake", "Intaked via " };   // intake placeholders, not descriptions
    private const int MaxViewBytes = 512 * 1024;

    public static bool IsSuitName(string n) => SuitExt.Any(e => n.EndsWith(e, StringComparison.OrdinalIgnoreCase));
    public static bool IsHex(string h) => HexRe.IsMatch(h);

    private static async Task<HttpResponseMessage> Get(string pathAndQuery)
    {
        var url = AtlasClient.WorkerUrl ?? throw new InvalidOperationException("PHOENIX_WORKER_URL isn't set");
        var req = new HttpRequestMessage(HttpMethod.Get, url + pathAndQuery);
        AtlasClient.Sign(req);
        var resp = await Http.SendAsync(req);
        var ctype = resp.Content.Headers.ContentType?.MediaType ?? "";
        if ((int)resp.StatusCode is >= 300 and < 400 || ctype == "text/html")
            throw new InvalidOperationException($"Cloudflare Access refused the request (HTTP {(int)resp.StatusCode}) - check CF_ACCESS_CLIENT_ID/SECRET");
        if ((int)resp.StatusCode == 401) throw new InvalidOperationException("packages-worker said 401 - PHOENIX_AUTH is wrong or stale");
        return resp;
    }

    private static async Task<JsonElement> GetJson(string pathAndQuery)
    {
        using var resp = await Get(pathAndQuery);
        if (!resp.IsSuccessStatusCode) throw new InvalidOperationException($"packages-worker answered {(int)resp.StatusCode}");
        using var doc = JsonDocument.Parse(await resp.Content.ReadAsStringAsync());
        return doc.RootElement.Clone();
    }

    private static string Str(JsonElement e, string p) =>
        e.TryGetProperty(p, out var v) ? v.ValueKind switch { JsonValueKind.String => v.GetString() ?? "", JsonValueKind.Number => v.ToString(), _ => "" } : "";

    private static Suit Row(JsonElement r, string what, string repoPath)
    {
        var ver = Str(r, "version").TrimStart('v');
        return new Suit(Str(r, "name"), Str(r, "hex_id"), ver.Length > 0 ? "v" + ver : "", int.TryParse(Str(r, "tier"), out var t) ? t : 0,
                        Str(r, "state"), what, repoPath);
    }

    /// <summary>Pool by name + Atlas by description, merged. Never throws: the error comes back as text.</summary>
    public static async Task<(IReadOnlyList<Suit> suits, string? error)> SearchAsync(string word)
    {
        try
        {
            var poolTask = GetJson($"/search?q={Uri.EscapeDataString(word)}");
            var atlasTask = GetJson($"/connections?q={Uri.EscapeDataString(word)}");
            var pool = await poolTask;
            JsonElement atlas = default;
            string? atlasErr = null;
            try { atlas = await atlasTask; } catch (Exception e) { atlasErr = e.Message; }

            // What each file does, from Atlas, by its repo path. A pool name is the file name, or
            // folder/name when another file holds the bare name, so it matches the END of a path.
            var what = new Dictionary<string, (string desc, string path)>(StringComparer.OrdinalIgnoreCase);
            static bool Covers(string poolName, string repoPath) =>
                ("/" + repoPath).EndsWith("/" + poolName, StringComparison.OrdinalIgnoreCase);
            if (atlas.ValueKind == JsonValueKind.Object && atlas.TryGetProperty("connections", out var conns))
                foreach (var c in conns.EnumerateArray())
                {
                    var path = Str(c, "path");
                    var file = Path.GetFileName(path);
                    if (IsSuitName(file)) what.TryAdd(path, (Str(c, "description"), path));
                }
            // The glossary's own description, unless it is the intake placeholder.
            var gloss = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (pool.TryGetProperty("glossary", out var gl))
                foreach (var g in gl.EnumerateArray())
                {
                    var d = Str(g, "description");
                    if (d.Length > 0 && !Boilerplate.Any(b => d.StartsWith(b))) gloss.TryAdd(Str(g, "name"), d);
                }

            var found = new List<Suit>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            void Add(JsonElement r)
            {
                var name = Str(r, "name");
                if (!IsSuitName(name) || !seen.Add(Str(r, "hex_id"))) return;
                var hit = what.Values.FirstOrDefault(w => Covers(name, w.path));
                var (desc, path) = hit.path is not null ? hit : (gloss.GetValueOrDefault(name, ""), "");
                found.Add(Row(r, desc, path));
            }
            if (pool.TryGetProperty("clonepool", out var cp)) foreach (var r in cp.EnumerateArray()) Add(r);

            // Files Atlas matched by what they do but the pool didn't match by name: look each up by name.
            var missing = what.Keys.Where(p => !found.Any(s => Covers(s.Name, p))).Take(8).ToList();
            var extra = await Task.WhenAll(missing.Select(async p =>
            {
                try { return (p, await GetJson($"/search?q={Uri.EscapeDataString(Path.GetFileName(p))}")); }
                catch { return (p, default(JsonElement)); }
            }));
            foreach (var (p, j) in extra)
                if (j.ValueKind == JsonValueKind.Object && j.TryGetProperty("clonepool", out var rows))
                    foreach (var r in rows.EnumerateArray())
                        if (Covers(Str(r, "name"), p)) Add(r);

            // Described in Atlas but never intaked: still listed, so the look-up says so instead of "no suits".
            foreach (var (p, (desc, path)) in what)
                if (!found.Any(s => Covers(s.Name, p)))
                    found.Add(new Suit(Path.GetFileName(p), "", "", 0, "", desc, path));

            // In the pool first, then described, then by name.
            var ordered = found.OrderBy(s => !s.InPool).ThenBy(s => s.What.Length == 0).ThenBy(s => s.Name, StringComparer.OrdinalIgnoreCase).ToList();
            return (ordered, atlasErr is null ? null : $"Atlas didn't answer ({atlasErr}); names only");
        }
        catch (Exception e) { return (Array.Empty<Suit>(), e.Message); }
    }

    /// <summary>
    /// The suit's code, read-only. Bytes come from R2 and must match D1's SHA3-512 custody; with no custody
    /// baseline the code is still shown but labelled UNVERIFIED (reading is not running).
    /// </summary>
    public static async Task<(string? code, string note)> FetchCodeAsync(Suit s)
    {
        if (!s.InPool) return LocalCode(s);
        if (!IsHex(s.Hex)) return (null, "bad hex id");
        try
        {
            var meta = await GetJson($"/clonepool/{s.Hex}?meta=true");
            var want = Str(meta, "hash_sha3").ToLowerInvariant();
            using var resp = await Get($"/clonepool/{s.Hex}");
            var ctype = resp.Content.Headers.ContentType?.MediaType ?? "";
            if (!resp.IsSuccessStatusCode || !ctype.Contains("octet-stream"))
                return (null, $"{s.Name}: no bytes in R2 (catalog row only). Re-intake it from the machine that has it.");
            var bytes = await resp.Content.ReadAsByteArrayAsync();
            string note;
            if (want.Length == 0) note = "UNVERIFIED - no SHA3 custody baseline in D1 (genie import will refuse it)";
            else if (!SHA3_512.IsSupported) note = "custody not checked - this Windows has no SHA3 (genie import still checks it)";
            else
            {
                var got = Convert.ToHexString(SHA3_512.HashData(bytes)).ToLowerInvariant();
                if (got != want) return (null, $"{s.Name}: SHA3-512 MISMATCH - R2 bytes don't match custody. Not shown.");
                note = $"verified: SHA3-512 matches custody ({want[..12]}…)";
            }
            if (bytes.Length > MaxViewBytes) note += $" - showing the first {MaxViewBytes / 1024} KB of {bytes.Length / 1024} KB";
            return (Encoding.UTF8.GetString(bytes, 0, Math.Min(bytes.Length, MaxViewBytes)), note);
        }
        catch (Exception e) { return (null, e.Message); }
    }

    /// <summary>A file Atlas knows but the pool doesn't: the repo copy, read-only, labelled as such.</summary>
    private static (string? code, string note) LocalCode(Suit s)
    {
        if (s.RepoPath.Length == 0) return (null, "not in the pool and no repo path");
        var full = Path.GetFullPath(Path.Combine(FileActions.RepoRoot, s.RepoPath.Replace('/', '\\')));
        if (!full.StartsWith(FileActions.RepoRoot, StringComparison.OrdinalIgnoreCase) || !File.Exists(full))
            return (null, $"not in the pool, and {s.RepoPath} isn't on this PC");
        var text = File.ReadAllText(full);
        return (text.Length > MaxViewBytes ? text[..MaxViewBytes] : text,
                $"NOT IN THE POOL - repo copy ({s.RepoPath}), no custody. Intake it to import it.");
    }
}

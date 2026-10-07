using System.IO;
using System.Net.Http;
using System.Text.Json;

namespace Hud.Desktop;

/// <summary>
/// Paths to everything, from Atlas (the CONNECTIONS.md graph the packages-worker serves at
/// /connections). Jerry, 2026-10-06: "i need pathes to everything atlas con provide that".
/// The place picker asks Atlas by word and gets real Phoenix locations back, so "copy to…"
/// lands in the right sector instead of wherever a folder dialog happened to open.
/// Credentials come from the same Windows user env vars usys.ps1 and intake use.
/// </summary>
public static class AtlasClient
{
    public record Place(string Name, string FullPath, string Area, string Note);

    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(10) };

    internal static string? Env(string n) =>
        Environment.GetEnvironmentVariable(n, EnvironmentVariableTarget.User) ?? Environment.GetEnvironmentVariable(n);

    internal static string? WorkerUrl => Env("PHOENIX_WORKER_URL")?.TrimEnd('/');

    /// <summary>The worker's three credentials (bearer + Cloudflare Access), the same ones usys and intake send.</summary>
    internal static void Sign(HttpRequestMessage req)
    {
        if (Env("PHOENIX_AUTH") is { Length: > 0 } a) req.Headers.TryAddWithoutValidation("Authorization", $"Bearer {a}");
        if (Env("CF_ACCESS_CLIENT_ID") is { Length: > 0 } id) req.Headers.TryAddWithoutValidation("CF-Access-Client-Id", id);
        if (Env("CF_ACCESS_CLIENT_SECRET") is { Length: > 0 } s) req.Headers.TryAddWithoutValidation("CF-Access-Client-Secret", s);
    }

    /// <summary>Places that are not repo directories, always offered first.</summary>
    public static IReadOnlyList<Place> FixedPlaces()
    {
        var list = new List<Place>
        {
            new("pbmIII share", FileActions.ThirdBoxShare, "mesh", "pbmIII's read-write disk on the mesh"),
            new("Phoenix repo", FileActions.RepoRoot, "repo", "the one repo, everything in sectors"),
            new("Desktop", Environment.GetFolderPath(Environment.SpecialFolder.Desktop), "this PC", ""),
            new("Downloads", Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads"), "this PC", ""),
        };
        if (Env("CLONEPOOL_DIR") is { Length: > 0 } pool) list.Add(new("Clone pool", pool, "pool", "local trimmed cache (R2 is home)"));
        return list.Where(p => Directory.Exists(p.FullPath)).ToList();
    }

    /// <summary>Atlas lookup by word. Empty list (not an exception) when Atlas can't be reached.</summary>
    public static async Task<(IReadOnlyList<Place> places, string? error)> SearchAsync(string word)
    {
        var url = Env("PHOENIX_WORKER_URL");
        if (string.IsNullOrEmpty(url)) return (Array.Empty<Place>(), "PHOENIX_WORKER_URL isn't set");
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, $"{url.TrimEnd('/')}/connections?q={Uri.EscapeDataString(word)}");
            Sign(req);
            using var resp = await Http.SendAsync(req);
            if (!resp.IsSuccessStatusCode) return (Array.Empty<Place>(), $"Atlas answered {(int)resp.StatusCode}");
            using var doc = JsonDocument.Parse(await resp.Content.ReadAsStringAsync());
            var places = new List<Place>();
            if (doc.RootElement.TryGetProperty("connections", out var arr))
            {
                foreach (var c in arr.EnumerateArray())
                {
                    var rel = c.TryGetProperty("path", out var p) ? p.GetString() ?? "" : "";
                    if (rel.Length == 0) continue;
                    var full = Path.Combine(FileActions.RepoRoot, rel.Replace('/', '\\'));
                    // nodes are dirs or files; a file's place is its folder
                    var dir = Directory.Exists(full) ? full : Path.GetDirectoryName(full);
                    if (dir is null || !Directory.Exists(dir)) continue;
                    var note = c.TryGetProperty("description", out var d) ? d.GetString() ?? "" : "";
                    places.Add(new(c.GetProperty("name").GetString() ?? rel, dir,
                                   c.TryGetProperty("area", out var ar) ? ar.GetString() ?? "" : "",
                                   note.Length > 90 ? note[..90] + "…" : note));
                }
            }
            return (places.GroupBy(x => x.FullPath, StringComparer.OrdinalIgnoreCase).Select(g => g.First()).ToList(), null);
        }
        catch (Exception e) { return (Array.Empty<Place>(), $"Atlas unreachable: {e.Message}"); }
    }
}

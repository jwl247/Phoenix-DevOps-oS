using System.IO;
using System.Text.Json;

namespace Hud;

/// <summary>
/// Which edition of the HUD this is (Jerry, 2026-10-07: "its game implementation won't have all the
/// tools I am privileged enough to use"). The core (eye, voice, drop-down chat, docks) is in every
/// edition; each module below is only reachable when its switch is on, and every entry point checks
/// it. Read once at start from ~/.phoenix/hud-profile.json: {"edition": "full"} or {"edition": "game"}.
/// No file = "full" (Jerry's PC); a game build ships its own file with "game".
/// </summary>
public sealed class HudProfile
{
    public string Edition { get; private init; } = "full";
    public bool Intake { get; private init; }          // intake / clone pool from a dock
    public bool Console { get; private init; }         // the button panel + hands on other machines
    public bool ClaudeCodeTools { get; private init; } // the subscription CLI with Bash/Write
    public bool Jarvis { get; private init; }          // Jerry's Jarvis (pbmIII)
    public IReadOnlyList<(string Name, string Path)> Places { get; private init; } = [];

    public static HudProfile Current { get; } = Load();

    private static HudProfile Load()
    {
        var edition = "full";
        try
        {
            var f = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".phoenix", "hud-profile.json");
            if (File.Exists(f))
                edition = JsonDocument.Parse(File.ReadAllText(f)).RootElement.GetProperty("edition").GetString() ?? "full";
        }
        catch { edition = "game"; }                    // an unreadable profile gets the LEAST tools, never the most
        return edition == "full" ? Full() : Game();
    }

    private static HudProfile Full()
    {
        string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        string repo = Environment.GetEnvironmentVariable("PHOENIX_ROOT") ?? @"F:\Phoenix\Phoenix-DevOps-oS";
        string pool = (Environment.GetEnvironmentVariable("CLONEPOOL_DIR") ?? @"E:\Phoenix\clonepool").Replace('/', '\\');
        if (pool.Length > 2 && pool[0] == '\\' && pool[2] == '\\') pool = $"{char.ToUpper(pool[1])}:{pool[2..]}";   // /e/x -> E:\x
        return new HudProfile
        {
            Edition = "full", Intake = true, Console = true, ClaudeCodeTools = true, Jarvis = true,
            Places = new List<(string, string)>
            {
                ("Desktop", Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory)),
                ("Downloads", Path.Combine(home, "Downloads")),
                ("Documents", Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments)),
                ("Phoenix repo", repo),
                ("Clone pool", pool),
                ("Imports", @"E:\Phoenix\imports"),
                ("Screenshots", Path.Combine(home, ".phoenix", "screenshots")),
            }.Where(p => Directory.Exists(p.Item2)).ToList(),
        };
    }

    private static HudProfile Game()
    {
        string game = Environment.GetEnvironmentVariable("PHOENIX_GAME_DIR") ?? "";
        return new HudProfile
        {
            Edition = "game",
            Places = Directory.Exists(game) ? new List<(string, string)> { ("Game", game) } : [],
        };
    }
}

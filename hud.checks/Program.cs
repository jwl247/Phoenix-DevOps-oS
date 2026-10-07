using Hud;

// H.L.K-10's hands, checked for real. Part 1 needs nothing running. Part 2
// talks to the live Phoenix Console, the machines' hands and the AI, and only
// runs with --live. The one real action it confirms is restarting Ollama on
// pbm3 (a few seconds' blip on a test box).
int pass = 0, fail = 0;
void Check(string name, bool ok, string detail = "")
{
    if (ok) { pass++; Console.WriteLine($"  ok  {name}"); }
    else { fail++; Console.WriteLine($"FAIL  {name} {detail}"); }
}

var a = AiChatService.ParseAction("ACTION {\"machine\": \"compaq.phx\", \"tool\": \"status\", \"args\": {}}");
Check("ACTION line is read, .phx dropped", a is { machine: "compaq", tool: "status" });
a = AiChatService.ParseAction("Sure.\n```\nACTION {\"machine\":\"pbm3\",\"tool\":\"restart_pc\",\"confirm\":true}\n```");
Check("ACTION inside a code fence is read", a is { machine: "pbm3", tool: "restart_pc" });
Check("a plain answer is not an action", AiChatService.ParseAction("The Compaq is fine, 40% memory used.") is null);
Check("broken JSON is not an action", AiChatService.ParseAction("ACTION {machine: compaq") is null);
foreach (var y in new[] { "yes", "Yeah, do it.", "go ahead", "ok", "Yes please", "OK!", "Confirmed.", "yes, please" })
    Check($"yes: \"{y}\"", AiChatService.IsYes(y));
foreach (var n in new[] { "no", "yes wait", "not yet", "what?", "", "yes but first tell me what that restarts on the box please" })
    Check($"not a yes: \"{n}\"", !AiChatService.IsYes(n));
// HUD-F01 (2026-09-28 audit): a clarifying question that merely STARTS with a
// yes-word is not consent. Each of these ran a pending restart before the fix.
foreach (var n in new[] { "ok what does that do", "okay, what will that restart?", "sure but which one", "go ahead and tell me first", "ok?", "yes if it's safe" })
    Check($"a question is not a yes: \"{n}\"", !AiChatService.IsYes(n));

// The eye + docks HUD (Jerry 2026-10-07, docs/plans/hud-eye-and-docks.md): the docks come out only when asked.
foreach (var (t, open, which) in new[] { ("open the dock", true, "both"), ("Expose the right dock.", true, "right"),
             ("show me the left dock", true, "left"), ("close the dock", false, "both"), ("put the docks away", false, "both"),
             ("turn on the dock", true, "both"), ("David, expose the dock", true, "both"), ("open the door", true, "both") })   // STT hears dock as door (10/7)
    Check($"dock command: \"{t}\"", HudOverlay.DockCommand(t) is { } c && c.Open == open && c.Which == which);
foreach (var t in new[] { "what is a dock in Docker and why does it open ports on my machine", "the dock", "dock", "open and close the dock" })
    Check($"not a dock command: \"{t}\"", HudOverlay.DockCommand(t) is null);
Check("Jarvis, ... goes to Jarvis", HudOverlay.IsForJarvis("Jarvis, what's on Laurie's list?", out var jr) && jr == "what's on Laurie's list?");
Check("jarvis: ... goes to Jarvis", HudOverlay.IsForJarvis("jarvis: hi", out var jr2) && jr2 == "hi");
Check("Jarvisville is not Jarvis", !HudOverlay.IsForJarvis("Jarvisville weather", out _));
Check("bare 'Jarvis' asks nothing", !HudOverlay.IsForJarvis("Jarvis", out _));
Check("this PC is the full edition", HudProfile.Current.Edition == "full" && HudProfile.Current.Intake && HudProfile.Current.Console);
Check("left dock = home", HudProfile.Current.LeftPlaces.Count == 1 && HudProfile.Current.LeftPlaces[0].Path == Environment.GetFolderPath(Environment.SpecialFolder.UserProfile));
Check("right dock = Phoenix root + the drives", HudProfile.Current.RightPlaces.Any(p => p.Name == "Phoenix root") && HudProfile.Current.RightPlaces.Any(p => p.Path == @"C:\"));
Check("the full edition's dock places exist", HudProfile.Current.Places.Count > 0 && HudProfile.Current.Places.All(p => System.IO.Directory.Exists(p.Path)));

Check("run box: a folder path opens", RunBox.Launch(System.IO.Path.GetTempPath()).Ok);
Check("run box: nonsense is refused, not crashed", !RunBox.Launch("zzz-no-such-program-xyz").Ok);
Check("the bird ships with the HUD", System.IO.File.Exists(System.IO.Path.Combine(AppContext.BaseDirectory, "phoenix.ico")) || System.IO.File.Exists(@"F:\Phoenix\Phoenix-DevOps-oS\hud\phoenix.ico"));

if (args.Contains("--jarvis"))
{
    var (jok, jtext) = await HudOverlay.AskJarvisAsync("Reply with one word: ok");
    Check($"Jarvis answers through the HUD's own path ({jtext})", jok && jtext.Length > 0);
}

if (args.Contains("--live"))
{
    foreach (var provider in new[] { args.FirstOrDefault(x => x.StartsWith("--provider="))?[11..] ?? "subscription", "ollama" })
    {
        Console.WriteLine($"\n-- live, provider {provider}");
        var ai = new AiChatService();
        ai.Config.Provider = provider;
        var r = await ai.SendAsync("How is the compaq doing? Check its status.");
        Console.WriteLine($"     steps: {string.Join(" | ", r.Steps)}\n     reply: {Short(r.Reply ?? r.Error)}");
        Check($"[{provider}] status of compaq ran through the hands", r.Success && r.Steps.Any(s => s.StartsWith("compaq · status · done")));

        r = await ai.SendAsync("Restart Ollama on pbm3.");
        Console.WriteLine($"     steps: {string.Join(" | ", r.Steps)}\n     reply: {Short(r.Reply ?? r.Error)}");
        Check($"[{provider}] ask-first tool waits for the user", r.Steps.Any(s => s.Contains("waiting for your yes")));
        r = await ai.SendAsync(provider == "ollama" ? "no" : "yes");
        Console.WriteLine($"     steps: {string.Join(" | ", r.Steps)}\n     reply: {Short(r.Reply ?? r.Error)}");
        Check(provider == "ollama" ? $"[{provider}] 'no' does nothing" : $"[{provider}] 'yes' runs it",
              provider == "ollama" ? r.Steps.Any(s => s.Contains("you said no")) : r.Steps.Any(s => s.Contains("done, you said yes")));
    }
}
Console.WriteLine($"\n{pass} passing, {fail} failing");
return fail == 0 ? 0 : 1;

static string Short(string? s) => s is null ? "" : (s.Length > 160 ? s[..160].Replace('\n', ' ') + "…" : s.Replace('\n', ' '));

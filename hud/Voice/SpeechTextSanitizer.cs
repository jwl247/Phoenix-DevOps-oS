using System.Text.RegularExpressions;

namespace Hud.Voice;

/// <summary>
/// Strips Markdown/code/links out of a chat reply before it goes to TTS —
/// without this, a code block gets read aloud symbol by symbol instead of
/// summarized, and "see the [docs](https://...)" gets read as a raw URL.
/// </summary>
public static partial class SpeechTextSanitizer
{
    public static string ForSpeech(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return string.Empty;

        var sanitized = CodeFenceRegex().Replace(text, " I've written the code — check the panel. ");
        sanitized = InlineCodeRegex().Replace(sanitized, "$1");
        sanitized = MarkdownLinkRegex().Replace(sanitized, "$1");
        sanitized = BareUrlRegex().Replace(sanitized, "a link");
        sanitized = MarkdownEmphasisRegex().Replace(sanitized, "$1");
        sanitized = HeadingMarkerRegex().Replace(sanitized, "");
        sanitized = WhitespaceRegex().Replace(sanitized, " ").Trim();
        return sanitized;
    }

    [GeneratedRegex(@"```[\s\S]*?```", RegexOptions.Compiled)]
    private static partial Regex CodeFenceRegex();

    [GeneratedRegex(@"`([^`]+)`", RegexOptions.Compiled)]
    private static partial Regex InlineCodeRegex();

    [GeneratedRegex(@"\[([^\]]+)\]\([^)]+\)", RegexOptions.Compiled)]
    private static partial Regex MarkdownLinkRegex();

    [GeneratedRegex(@"https?://\S+", RegexOptions.Compiled)]
    private static partial Regex BareUrlRegex();

    [GeneratedRegex(@"[*_]{1,3}([^*_]+)[*_]{1,3}", RegexOptions.Compiled)]
    private static partial Regex MarkdownEmphasisRegex();

    [GeneratedRegex(@"^#{1,6}\s*", RegexOptions.Multiline | RegexOptions.Compiled)]
    private static partial Regex HeadingMarkerRegex();

    [GeneratedRegex(@"\s+", RegexOptions.Compiled)]
    private static partial Regex WhitespaceRegex();
}

using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Input;

namespace Hud;

public partial class MainWindow : Window
{
    private readonly AiChatService _ai = new();
    private readonly ScreenCaptureService _capture = new(TimeSpan.FromMilliseconds(1000));
    private readonly ObservableCollection<string> _lines = new();

    public MainWindow()
    {
        InitializeComponent();

        ChatLog.ItemsSource = _lines;
        ProviderLabel.Text = $"provider: {_ai.Config.Provider}";
        _lines.Add($"[SYS] H.L.K-10 online. provider={_ai.Config.Provider}. Config read from ~/.phoenix/ai_auth.json.");

        _capture.FrameCaptured += frame => Dispatcher.Invoke(() => LiveMonitorImage.Source = frame);
        _capture.Start();

        Closed += (_, _) => _capture.Dispose();
    }

    private void TitleBar_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ButtonState == MouseButtonState.Pressed) DragMove();
    }

    private void Close_Click(object sender, RoutedEventArgs e) => Close();

    private void ChatInput_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) _ = SendAsync();
    }

    private void Send_Click(object sender, RoutedEventArgs e) => _ = SendAsync();

    private async Task SendAsync()
    {
        var message = ChatInput.Text.Trim();
        if (message.Length == 0) return;
        ChatInput.Text = "";
        _lines.Add($"[YOU] {message}");
        ScrollToEnd();

        var placeholderIndex = _lines.Count;
        _lines.Add("[H.L.K-10] …");
        ScrollToEnd();

        var result = await _ai.SendAsync(message, chunk =>
        {
            Dispatcher.Invoke(() =>
            {
                if (_lines[placeholderIndex] == "[H.L.K-10] …") _lines[placeholderIndex] = "[H.L.K-10] " + chunk;
                else _lines[placeholderIndex] += chunk;
                ScrollToEnd();
            });
        });

        if (result.Success)
        {
            if (_lines[placeholderIndex] == "[H.L.K-10] …")
                _lines[placeholderIndex] = $"[H.L.K-10 · {result.Provider}] {result.Reply}";
        }
        else
        {
            _lines[placeholderIndex] = $"[ERROR · {result.Provider}] {result.Error}";
        }
        ScrollToEnd();
    }

    private void ScrollToEnd() => ChatScroll.ScrollToEnd();
}

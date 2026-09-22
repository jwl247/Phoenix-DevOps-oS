using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using Hud.Voice;

namespace Hud.Controls;

public partial class KnightRiderBar : UserControl
{
    private Storyboard? _current;
    private VoiceState _lastState = VoiceState.Idle;

    public KnightRiderBar()
    {
        InitializeComponent();
        SizeChanged += (_, _) => Apply(_lastState);
    }

    public void SetState(VoiceState state)
    {
        _lastState = state;
        Apply(state);
    }

    private void Apply(VoiceState state)
    {
        _current?.Stop(Eye);
        _current = null;

        var travel = Math.Max(0, ActualWidth - Eye.Width);

        switch (state)
        {
            case VoiceState.Idle:
                Eye.Opacity = 0;
                return;

            case VoiceState.Listening:
                Eye.Opacity = 1;
                EyeCoreStop.Color = Colors.Red;
                _current = BuildSweep(travel, TimeSpan.FromMilliseconds(650));
                break;

            case VoiceState.Thinking:
                Eye.Opacity = 1;
                EyeCoreStop.Color = (Color)ColorConverter.ConvertFromString("#FFCC33")!;
                _current = BuildPulse();
                break;

            case VoiceState.Speaking:
                Eye.Opacity = 1;
                EyeCoreStop.Color = (Color)ColorConverter.ConvertFromString("#3DE8FF")!;
                _current = BuildSweep(travel, TimeSpan.FromMilliseconds(380));
                break;
        }

        _current?.Begin(Eye, true);
    }

    private static Storyboard BuildSweep(double travel, TimeSpan half)
    {
        var anim = new DoubleAnimation
        {
            From = 0,
            To = travel,
            Duration = half,
            AutoReverse = true,
            RepeatBehavior = RepeatBehavior.Forever,
            EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut }
        };
        Storyboard.SetTargetProperty(anim, new PropertyPath("(Canvas.Left)"));

        var sb = new Storyboard();
        sb.Children.Add(anim);
        return sb;
    }

    private static Storyboard BuildPulse()
    {
        var anim = new DoubleAnimation
        {
            From = 0.25,
            To = 1.0,
            Duration = TimeSpan.FromMilliseconds(500),
            AutoReverse = true,
            RepeatBehavior = RepeatBehavior.Forever
        };
        Storyboard.SetTargetProperty(anim, new PropertyPath(OpacityProperty));

        var sb = new Storyboard();
        sb.Children.Add(anim);
        return sb;
    }
}

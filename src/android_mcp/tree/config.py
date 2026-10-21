"""What counts as interactive."""

# Widgets that are worth listing even when uiautomator does not flag them clickable or focusable.
INTERACTIVE_CLASSES = frozenset(
    {
        "android.widget.Button",
        "android.widget.ImageButton",
        "android.widget.EditText",
        "android.widget.CheckBox",
        "android.widget.Switch",
        "android.widget.RadioButton",
        "android.widget.Spinner",
        "android.widget.SeekBar",
    }
)

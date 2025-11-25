using Avalonia;
using Avalonia.VisualTree;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using System;
using System.Reflection;
using System.Linq;
using System.Collections.Generic;
using System.Data;
using System.IO;
using Microsoft.Data.Sqlite;


namespace VB;

public class PropertiesPanel
{
    private StackPanel panel;
    private Control? selectedControl;

    public event EventHandler? PanelCloseRequested; 
    
    public PropertiesPanel(StackPanel targetPanel)
    {
        panel = targetPanel;
    }
   
    public void ShowPropertiesFor(Control control)
	{
	    selectedControl = control;

	    // Update FormBuilder title if it exists
	    if (panel.Parent?.Parent is StackPanel headerStack)
	    {
		var titleBlock = headerStack.Children
		    .OfType<Border>()
		    .FirstOrDefault()?.Child as Grid;

		var titleText = titleBlock?.Children.OfType<TextBlock>().FirstOrDefault();
		if (titleText != null)
		    titleText.Text = $"FormBuilder: {control.GetType().Name}";
	    }

	    panel.Children.Clear();

	    var controlType = control.GetType().Name;

	    // Get property display order from database
	    //var dbPath = Path.Combine(Environment.CurrentDirectory, "vml.db");
        var dbPath = PropertyStore.GetDbPath();
	    using var conn = new SqliteConnection($"Data Source={dbPath}");

	    conn.Open();
	    
	    var displayRules = new Dictionary<string, (int order, bool hidden)>();
	    
	    // First query - property display rules
	    using (var cmd = conn.CreateCommand())
	    {
		cmd.CommandText = @"
		    SELECT property_name, display_order, is_hidden 
		    FROM property_display 
		    WHERE control_type IN ('*', @controlType) 
		    ORDER BY 
			CASE WHEN control_type = @controlType THEN 0 ELSE 1 END,
			display_order";
		cmd.Parameters.AddWithValue("@controlType", controlType);
		
		using var reader = cmd.ExecuteReader();
		while (reader.Read())
		{
		    var propName = reader.GetString(0);
		    var order = reader.GetInt32(1);
		    var hidden = reader.GetInt32(2) == 1;
		    displayRules[propName] = (order, hidden);
		}
	    }
	    
	    // Second query - property groups
	    var groups = new List<(string name, string display, string[] components, string picker)>();
	    using (var cmd = conn.CreateCommand())
	    {
		cmd.CommandText = "SELECT group_name, display_name, component_properties, picker_type FROM property_groups ORDER BY display_order";
		using var groupReader = cmd.ExecuteReader();
		while (groupReader.Read())
		{
		    groups.Add((
			groupReader.GetString(0),
			groupReader.GetString(1),
			groupReader.GetString(2).Split(','),
			groupReader.GetString(3)
		    ));
		}
	    }
	    
	    // Add property groups first
	    foreach (var group in groups.Where(g => displayRules.ContainsKey(g.name) && !displayRules[g.name].hidden))
	    {
		if (group.picker == "TinyFontPicker")
		    AddFontRow(control, group.display);
	    }
	    
	    // Get all properties
	    var props = control.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)
		.Where(p => p.CanWrite && p.CanRead && !ShouldSkip(p))
		.Where(p => !displayRules.ContainsKey(p.Name) || !displayRules[p.Name].hidden)
		.OrderBy(p => displayRules.ContainsKey(p.Name) ? displayRules[p.Name].order : 1000)
		.ThenBy(p => p.Name);
	    
	    foreach (var prop in props)
	    {
		AddPropertyRow(control, prop);
	    }
	}

private void AddFontRow(Control control, string displayName)
{
    var row = new StackPanel 
    { 
        Orientation = Orientation.Horizontal, 
        Spacing = 5,
        Margin = new Thickness(0, 0, 0, 2)
    };
    
    var label = new TextBlock 
    { 
        Text = displayName,
        Width = 80,
        FontSize = 11,
        TextAlignment = TextAlignment.Right,
        VerticalAlignment = VerticalAlignment.Center
    };
    row.Children.Add(label);
    
    var fontPicker = new TinyFontPicker();
    
    // Get current font properties
    var familyProp = control.GetType().GetProperty("FontFamily");
    var sizeProp = control.GetType().GetProperty("FontSize");
    var weightProp = control.GetType().GetProperty("FontWeight");
    var styleProp = control.GetType().GetProperty("FontStyle");
    
    if (familyProp != null && familyProp.GetValue(control) != null)
        fontPicker.Family = (FontFamily)familyProp.GetValue(control)!;
    if (sizeProp != null && sizeProp.GetValue(control) != null)
        fontPicker.Size = (double)sizeProp.GetValue(control)!;
    if (weightProp != null && weightProp.GetValue(control) != null)
        fontPicker.Weight = (FontWeight)weightProp.GetValue(control)!;
    if (styleProp != null && styleProp.GetValue(control) != null)
        fontPicker.Style = (FontStyle)styleProp.GetValue(control)!;
    
    fontPicker.FontChanged += (s, font) =>
    {
        familyProp?.SetValue(control, font.family);
        sizeProp?.SetValue(control, font.size);
        weightProp?.SetValue(control, font.weight);
        styleProp?.SetValue(control, font.style);
    };
    
    row.Children.Add(fontPicker);
    panel.Children.Add(row);
}

    private void AddPropertyRow(Control control, PropertyInfo prop)
    {
        var row = new StackPanel 
        { 
            Orientation = Orientation.Horizontal, 
            Spacing = 5,
            Margin = new Thickness(0, 0, 0, 2)
        };

	// Debug - check what we're getting for color properties
	if (prop.Name == "Background" || prop.Name == "Foreground" || prop.Name == "BorderBrush")
	{
	}
        
        // Left label - 11px normal
        var label = new TextBlock 
        { 
            Text = prop.Name + ":",
            Width = 80,
            FontSize = 11,
            TextAlignment = TextAlignment.Right,
            VerticalAlignment = VerticalAlignment.Center
        };

        row.Children.Add(label);
	
	// Create appropriate editor based on type

	// Handle Items property
	if (prop.Name == "Items")
	{
	    var btn = new TinyButton { Text = "Edit Items..." };
	    btn.SetButtonColor("#757575");
	    btn.Clicked += (s, e) => ShowItemsEditor(control, prop);
	    row.Children.Add(btn);
	    panel.Children.Add(row);
	    return;
	}

	// Handle Content/Text with multiline editor
	if (prop.Name == "Content" || prop.Name == "Text")
	{
	    var value = prop.GetValue(control);
	    var displayText = value?.ToString() ?? "(empty)";

	    // Truncate for display
	    if (displayText.Contains('\n'))
	    {
		displayText = displayText.Split('\n')[0] + "...";
	    }
	    else if (displayText.Length > 20)
	    {
		displayText = displayText.Substring(0, 20) + "...";
	    }

	    var btn = new TinyButton { Text = displayText };
	    btn.SetButtonColor("#757575");
	    btn.Clicked += (s, e) => ShowComplexContentEditor(control, prop, value);
	    row.Children.Add(btn);
	    panel.Children.Add(row);
	    return;  // Important - exit early!
	}

	// Regular string properties use TinyTextBox
	else if (prop.PropertyType == typeof(string))
	{
	    row.Children.Add(CreateTinyTextBox(control, prop));
	}

		// Create appropriate editor based on type
		if (prop.Name == "Content" || prop.Name == "Text")
	{
	    var value = prop.GetValue(control);
	    var btn = new TinyButton { Text = value?.ToString() ?? "(empty)" };
	    btn.SetButtonColor("#757575");
	    btn.Clicked += (s, e) => ShowComplexContentEditor(control, prop, value);
	    row.Children.Add(btn);
	}
	else if (prop.PropertyType == typeof(string))
    row.Children.Add(CreateTinyTextBox(control, prop));
        else if (prop.PropertyType == typeof(double) || prop.PropertyType == typeof(int))
            row.Children.Add(CreateTinyTextBox(control, prop));
        else if (prop.PropertyType == typeof(bool))
            row.Children.Add(new TinyCheckBox { IsChecked = (bool?)prop.GetValue(control) });
	else if (prop.PropertyType.Name.Contains("Brush") || prop.PropertyType.Name == "IBrush")
            row.Children.Add(CreateTinyColorPicker(control, prop));
        else if (prop.PropertyType.IsEnum)
            row.Children.Add(CreateTinyCombo(control, prop));
	else if (prop.PropertyType == typeof(Thickness) ||
            prop.PropertyType == typeof(CornerRadius) ||
            prop.PropertyType == typeof(Point))
            row.Children.Add(CreateTinyComplexBox(control, prop));
	else if (prop.PropertyType == typeof(Thickness) ||
            prop.PropertyType == typeof(CornerRadius) ||
            prop.PropertyType == typeof(Point) ||
            prop.PropertyType == typeof(Size) ||
            prop.PropertyType == typeof(Rect) ||
            prop.PropertyType == typeof(PixelPoint) ||
            prop.PropertyType == typeof(RelativePoint))
            row.Children.Add(CreateTinyComplexBox(control, prop));
	else if (prop.PropertyType.Name.Contains("Menu") || prop.PropertyType.Name.Contains("Flyout"))
            row.Children.Add(CreateTinyButton(control, prop));
else if (prop.PropertyType == typeof(Effect) || prop.PropertyType.Name == "IEffect")
            row.Children.Add(CreateTinyEffectCombo(control, prop));
        else
            row.Children.Add(new TextBlock { Text = "(complex)", FontSize = 11 });
        

	panel.Children.Add(row);

    }
    
private Control CreateTinyTextBox(Control control, PropertyInfo prop)
{
    var tiny = new TinyTextBox();
    var value = prop.GetValue(control);


    // Round doubles to int for display
    if (value is double d)
        tiny.Text = Math.Round(d).ToString();
    else if (value is int i)
        tiny.Text = i.ToString();
    else
        tiny.Text = value?.ToString() ?? "";

    tiny.TextChanged += (s, newText) =>
    {
        if (prop.PropertyType == typeof(double))
        {
            if (double.TryParse(newText, out var dval))
                prop.SetValue(control, dval);
        }
        else if (prop.PropertyType == typeof(int))
        {
            if (int.TryParse(newText, out var ival))
                prop.SetValue(control, ival);
        }
        else
        {
            prop.SetValue(control, newText);
        }
    };

    return tiny;
}

    private Control CreateTinyCombo(Control control, PropertyInfo prop)
    {
        var tiny = new TinyCombo();
        
        // Add enum values
        foreach (var val in Enum.GetValues(prop.PropertyType))
            tiny.Items.Add(val);
        
        // Set current value
        var currentVal = prop.GetValue(control);
        tiny.Text = currentVal?.ToString() ?? "";
        
        tiny.SelectionChanged += (s, selectedItem) =>
        {
            prop.SetValue(control, selectedItem);
        };
        
        return tiny;
    }

    private Control CreateTinyColorPicker(Control control, PropertyInfo prop)
    {
	    var picker = new TinyColorPicker();
	    var brush = prop.GetValue(control) as ISolidColorBrush;
	    if (brush != null) picker.Color = brush.Color;
	    
	    picker.ColorChanged += (s, color) => prop.SetValue(control, new SolidColorBrush(color));
	    return picker;
    }

	private Control CreateTinyComplexBox(Control control, PropertyInfo prop)
	{
	    var box = new TinyComplexBox
	    {
		PropertyType = prop.PropertyType,
		Value = prop.GetValue(control)
	    };

	    box.ValueChanged += (s, value) =>
	    {
		prop.SetValue(control, value);
	    };

	    return box;
	}

private Control CreateTinyEffectCombo(Control control, PropertyInfo prop)
{
    var combo = new TinyCombo();

    // Populate with presets
    combo.Items.Add("None");
    combo.Items.Add("Subtle Shadow");
    combo.Items.Add("Strong Shadow");
    combo.Items.Add("Long Shadow");
    combo.Items.Add("Light Blur");
    combo.Items.Add("Medium Blur");
    combo.Items.Add("Heavy Blur");
    combo.Items.Add("Soft Glow");
    combo.Items.Add("Hard Edge");
    combo.Items.Add("Frosted Glass");

    // Set current value
    var effect = prop.GetValue(control) as Effect;
    combo.Text = EffectToString(effect);

    // Handle changes
    combo.SelectionChanged += (s, selected) =>
    {
        prop.SetValue(control, StringToEffect(selected.ToString()));
    };

    return combo;
}

private Control CreateTinyButton(Control control, PropertyInfo prop)
{
    var btn = new TinyButton();
    var menu = prop.GetValue(control);
    btn.Text = menu != null ? "Custom Menu" : "(none)";

    btn.Clicked += (s, e) =>
    {
        // TODO: Open MenuEditorWindow and pass control/prop
        // var editor = new MenuEditorWindow();
        // editor.ShowDialog(...);
    };

    return btn;
}

private string EffectToString(Effect? effect)
{
    if (effect == null) return "None";

    if (effect is DropShadowEffect shadow)
    {
        if (shadow.OffsetX == 0 && shadow.OffsetY == 0 && shadow.BlurRadius > 15)
            return "Soft Glow";
        if (shadow.BlurRadius == 0)
            return "Hard Edge";
        if (shadow.OffsetX >= 8 || shadow.OffsetY >= 8)
            return "Long Shadow";
        if (shadow.BlurRadius > 12)
            return "Strong Shadow";
        return "Subtle Shadow";
    }

    if (effect is BlurEffect blur)
    {
        if (blur.Radius >= 15) return "Frosted Glass";
        if (blur.Radius >= 7) return "Medium Blur";
        return "Light Blur";
    }

    return "None";
}

private Effect? StringToEffect(string? name)
{
    return name switch
    {
        "Subtle Shadow" => new DropShadowEffect { BlurRadius = 8, Color = Colors.Black, OffsetX = 2, OffsetY = 2, Opacity = 0.3 },
        "Strong Shadow" => new DropShadowEffect { BlurRadius = 15, Color = Colors.Black, OffsetX = 4, OffsetY = 4, Opacity = 0.6 },
        "Long Shadow" => new DropShadowEffect { BlurRadius = 5, Color = Colors.Black, OffsetX = 10, OffsetY = 10, Opacity = 0.4 },
        "Light Blur" => new BlurEffect { Radius = 3 },
        "Medium Blur" => new BlurEffect { Radius = 8 },
        "Heavy Blur" => new BlurEffect { Radius = 20 },
        "Soft Glow" => new DropShadowEffect { BlurRadius = 20, Color = Color.Parse("#4CAF50"), OffsetX = 0, OffsetY = 0, Opacity = 0.8 },
        "Hard Edge" => new DropShadowEffect { BlurRadius = 0, Color = Colors.Black, OffsetX = 3, OffsetY = 3, Opacity = 0.9 },
        "Frosted Glass" => new BlurEffect { Radius = 15 },
        _ => null
    };
}

    private bool ShouldSkip(PropertyInfo prop)
    {
        // Skip Name - it's immutable after styling
        if (prop.Name == "Name") return true;

        // Only skip truly dangerous/system properties
        var skip = new[] { "Parent", "DataContext" };

        return skip.Contains(prop.Name);
    }

    private async void ShowComplexContentEditor(Control control, PropertyInfo prop, object? currentValue)
    {
        var editor = new TextBox
        {
            Text = currentValue?.ToString() ?? "",
            Width = 400,
            Height = 200,
            AcceptsReturn = true,
            TextWrapping = TextWrapping.Wrap
        };

        var okBtn = new Button
        {
            Content = "OK",
            Width = 80,
            FontWeight = FontWeight.Bold,
            Background = Brushes.White,
            Foreground = new SolidColorBrush(Color.Parse("#2e7d32")),
            BorderBrush = new SolidColorBrush(Color.Parse("#2e7d32")),
            BorderThickness = new Thickness(2)
        };

        var cancelBtn = new Button
        {
            Content = "Cancel",
            Width = 80,
            FontWeight = FontWeight.Bold,
            Background = Brushes.White,
            Foreground = new SolidColorBrush(Color.Parse("#2e7d32")),
            BorderBrush = new SolidColorBrush(Color.Parse("#2e7d32")),
            BorderThickness = new Thickness(2)
        };

        var buttonPanel = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            Spacing = 10,
            Margin = new Thickness(0, 10, 0, 0)
        };
        buttonPanel.Children.Add(okBtn);
        buttonPanel.Children.Add(cancelBtn);

        var stack = new StackPanel();
        stack.Children.Add(editor);
        stack.Children.Add(buttonPanel);

        var container = new Border
        {
            Padding = new Thickness(20),
            Background = new SolidColorBrush(Color.Parse("#F7F7F7")),
            Child = stack
        };

        var window = new Window
        {
            Title = $"Edit {prop.Name}",
            Content = container,
            Width = 440,
            Height = 280,
            CanResize = false,
            WindowStartupLocation = WindowStartupLocation.CenterOwner
        };

        okBtn.Click += (s, e) =>
        {
            prop.SetValue(control, editor.Text);  // Update dummy display
            SyncToRealControl(control, prop.Name, editor.Text);  // Copy to real

            var real = control.Tag as Control;
            if (real != null)
                PropertyStore.SyncControl(real);  // Save REAL control!

            window.Close();
            // Refresh properties panel
            ShowPropertiesFor(control);
        };

        cancelBtn.Click += (s, e) => window.Close();

        await window.ShowDialog(GetParentWindow());
    }

    private async void ShowItemsEditor(Control control, PropertyInfo prop)
	{
	    var items = prop.GetValue(control) as System.Collections.IList;
	    var currentText = items != null ? string.Join("\n", items.Cast<object>()) : "";
	    
	    var hint = new TextBlock
	    {
		Text = "One item per line. For complex items, use code in FormLoad event.",
		FontSize = 10,
		Foreground = new SolidColorBrush(Color.Parse("#999999")),
		FontStyle = FontStyle.Italic,
		Margin = new Thickness(0, 0, 0, 5)
	    };
	    
	    var editor = new TextBox
	    {
		Text = currentText,
		Width = 400,
		Height = 200,
		AcceptsReturn = true,
		TextWrapping = TextWrapping.Wrap
	    };
	    
	    var okBtn = new Button 
	    { 
		Content = "OK", 
		Width = 80,
		FontWeight = FontWeight.Bold,
		Background = Brushes.White,
		Foreground = new SolidColorBrush(Color.Parse("#2e7d32")),
		BorderBrush = new SolidColorBrush(Color.Parse("#2e7d32")),
		BorderThickness = new Thickness(2)
	    };
	    
	    var cancelBtn = new Button 
	    { 
		Content = "Cancel", 
		Width = 80,
		FontWeight = FontWeight.Bold,
		Background = Brushes.White,
		Foreground = new SolidColorBrush(Color.Parse("#2e7d32")),
		BorderBrush = new SolidColorBrush(Color.Parse("#2e7d32")),
		BorderThickness = new Thickness(2)
	    };
	    
	    var buttonPanel = new StackPanel
	    {
		Orientation = Orientation.Horizontal,
		HorizontalAlignment = HorizontalAlignment.Right,
		Spacing = 10,
		Margin = new Thickness(0, 10, 0, 0)
	    };
	    buttonPanel.Children.Add(okBtn);
	    buttonPanel.Children.Add(cancelBtn);
	    
	    var stack = new StackPanel();
	    stack.Children.Add(hint);
	    stack.Children.Add(editor);
	    stack.Children.Add(buttonPanel);
	    
	    var container = new Border
	    {
		Padding = new Thickness(20),
		Background = new SolidColorBrush(Color.Parse("#F7F7F7")),
		Child = stack
	    };
	    
	    var window = new Window
	    {
		Title = "Edit Items",
		Content = container,
		Width = 440,
		Height = 300,
		CanResize = false,
		WindowStartupLocation = WindowStartupLocation.CenterOwner
	    };
	    
	    okBtn.Click += (s, e) =>
	    {
            if (items != null)
            {
                items.Clear();
                var lines = editor.Text.Split('\n', StringSplitOptions.RemoveEmptyEntries);
                foreach (var line in lines)
                items.Add(line.Trim());

                SyncToRealControl(control, "Items", items);

                var real = control.Tag as Control;
                if (real != null)
                    PropertyStore.SyncControl(real);  // Save REAL control!
            }
		    window.Close();
            ShowPropertiesFor(control);
	    };
	    
	    cancelBtn.Click += (s, e) => window.Close();
	    
	    await window.ShowDialog(GetParentWindow());
	}


        private void SyncToRealControl(Control dummy, string propertyName, object? value)
{
    if (dummy.Tag is Control real)
    {
        try 
        { 
            var realProp = real.GetType().GetProperty(propertyName);
            if (realProp != null && realProp.CanWrite)
            {
                realProp.SetValue(real, value);
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[SYNC] Failed to sync {propertyName}: {ex.Message}");
        }
    }
}

	    private Window? GetParentWindow()
	    {
		var current = panel as Visual;
        while (current != null)
        {
            if (current is Window window)
                return window;
            current = current.GetVisualParent();
        }
        return null;
    }
}

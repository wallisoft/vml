using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Layout;
using System.Linq; 

namespace VB;

public class DesignButton : Border
{
    private TextBlock textBlock;
    
    public object? Content
    {
        get => textBlock.Text;
        set => textBlock.Text = value?.ToString() ?? "";
    }
    
    public DesignButton()
    {
        Width = 100;
        Height = 30;
        Background = new SolidColorBrush(Color.Parse("#E0E0E0"));
        BorderBrush = new SolidColorBrush(Color.Parse("#999"));
        BorderThickness = new Avalonia.Thickness(1);
        CornerRadius = new Avalonia.CornerRadius(3);
        
        textBlock = new TextBlock 
        { 
            Text = "Button",
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center
        };
        
        Child = textBlock;
    }
}

public class DesignTextBox : Border
{
    private TextBlock textBlock;
    
    public string Text
    {
        get => textBlock.Text ?? "";
        set => textBlock.Text = value;
    }
    
    public DesignTextBox()
    {
        Width = 150;
        Height = 25;
        Background = Brushes.White;
        BorderBrush = new SolidColorBrush(Color.Parse("#999"));
        BorderThickness = new Avalonia.Thickness(1);
        
        textBlock = new TextBlock 
        { 
            Text = "TextBox",
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Avalonia.Thickness(3, 0)
        };
        
        Child = textBlock;
    }
}

public class DesignTextBlock : TextBlock
{
    public DesignTextBlock()
    {
        Text = "Label";
        FontSize = 14;
        VerticalAlignment = VerticalAlignment.Center;
    }
}

public class DesignCheckBox : StackPanel
{
    public DesignCheckBox()
    {
        Orientation = Orientation.Horizontal;
        Spacing = 5;
        
        var checkBox = new Border
        {
            Width = 16,
            Height = 16,
            Background = Brushes.White,
            BorderBrush = new SolidColorBrush(Color.Parse("#999")),
            BorderThickness = new Avalonia.Thickness(1),
            VerticalAlignment = VerticalAlignment.Center
        };
        
        var label = new TextBlock 
        { 
            Text = "CheckBox",
            VerticalAlignment = VerticalAlignment.Center
        };
        
        Children.Add(checkBox);
        Children.Add(label);
    }
}

public class DesignComboBox : Border
{
    private TextBlock textBlock;
    public System.Collections.ObjectModel.ObservableCollection<object> Items { get; } = new();
    
    public string Text
    {
        get => textBlock.Text ?? "";
        set => textBlock.Text = value;
    }
    
    public DesignComboBox()
    {
        Items.CollectionChanged += (s, e) => 
        {
            // Update display when items change
            if (Items.Count > 0)
                Text = Items[0].ToString() ?? "ComboBox";
        };
        
        Width = 120;
        Height = 25;
        Background = Brushes.White;
        BorderBrush = new SolidColorBrush(Color.Parse("#999"));
        BorderThickness = new Avalonia.Thickness(1);
        
        var grid = new Grid();
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Star });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(20) });
        
        textBlock = new TextBlock 
        { 
            Text = "ComboBox",
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Avalonia.Thickness(3, 0)
        };
        Grid.SetColumn(textBlock, 0);
        
        var arrow = new TextBlock 
        { 
            Text = "▼",
            FontSize = 10,
            VerticalAlignment = VerticalAlignment.Center,
            HorizontalAlignment = HorizontalAlignment.Center
        };
        Grid.SetColumn(arrow, 1);
        
        grid.Children.Add(textBlock);
        grid.Children.Add(arrow);
        
        Child = grid;
    }
}

public class DesignListBox : Border
{
    private TextBlock textBlock;
    public System.Collections.ObjectModel.ObservableCollection<object> Items { get; } = new();
    
    public string Text
    {
        get => textBlock.Text ?? "";
        set => textBlock.Text = value;
    }
    
    public DesignListBox()
    {
        Items.CollectionChanged += (s, e) => 
        {
            if (Items.Count > 0)
                Text = string.Join(", ", Items.Take(3)) + (Items.Count > 3 ? "..." : "");
        };
        
        Width = 150;
        Height = 100;
        Background = Brushes.White;
        BorderBrush = new SolidColorBrush(Color.Parse("#999"));
        BorderThickness = new Avalonia.Thickness(1);
        
        textBlock = new TextBlock 
        { 
            Text = "ListBox",
            Margin = new Avalonia.Thickness(5)
        };
        
        Child = textBlock;
    }
}

public class DesignRadioButton : StackPanel
{
    public DesignRadioButton()
    {
        Orientation = Orientation.Horizontal;
        Spacing = 5;
        
        var radio = new Border
        {
            Width = 16,
            Height = 16,
            Background = Brushes.White,
            BorderBrush = new SolidColorBrush(Color.Parse("#999")),
            BorderThickness = new Avalonia.Thickness(1),
            CornerRadius = new Avalonia.CornerRadius(8),
            VerticalAlignment = VerticalAlignment.Center
        };
        
        var label = new TextBlock 
        { 
            Text = "RadioButton",
            VerticalAlignment = VerticalAlignment.Center
        };
        
        Children.Add(radio);
        Children.Add(label);
    }
}

public class DesignPanel : Border
{
    public DesignPanel(string panelType)
    {
        Width = 200;
        Height = 150;
        Background = new SolidColorBrush(Color.Parse("#E8E8E8"));
        BorderBrush = new SolidColorBrush(Color.Parse("#999"));
        BorderThickness = new Avalonia.Thickness(1);
        
        Child = new TextBlock 
        { 
            Text = panelType,
            Margin = new Avalonia.Thickness(5),
            Foreground = new SolidColorBrush(Color.Parse("#666"))
        };
    }
}

public class DesignBorder : Border
{
    public DesignBorder()
    {
        Width = 150;
        Height = 100;
        Background = new SolidColorBrush(Color.Parse("#FAFAFA"));
        BorderBrush = new SolidColorBrush(Color.Parse("#999"));
        BorderThickness = new Avalonia.Thickness(1);
        
        Child = new TextBlock 
        { 
            Text = "Border",
            Margin = new Avalonia.Thickness(5),
            Foreground = new SolidColorBrush(Color.Parse("#999")),
            FontStyle = FontStyle.Italic
        };
    }
}

public static class DesignProperties
{
    public static readonly AttachedProperty<bool> IsResizableProperty =
        AvaloniaProperty.RegisterAttached<Control, bool>("IsResizable", typeof(DesignProperties), defaultValue: true);
    
    public static bool GetIsResizable(Control control) => 
        control.GetValue(IsResizableProperty);
    
    public static void SetIsResizable(Control control, bool value) => 
        control.SetValue(IsResizableProperty, value);
    
    public static readonly AttachedProperty<bool> IsDraggableProperty =
        AvaloniaProperty.RegisterAttached<Control, bool>("IsDraggable", typeof(DesignProperties), defaultValue: true);
    
    public static bool GetIsDraggable(Control control) => 
        control.GetValue(IsDraggableProperty);
    
    public static void SetIsDraggable(Control control, bool value) => 
        control.SetValue(IsDraggableProperty, value);
    
    public static readonly AttachedProperty<string> ScriptProperty =
        AvaloniaProperty.RegisterAttached<Control, string>("Script", typeof(DesignProperties), defaultValue: "");
    
    public static string GetScript(Control control) => 
        control.GetValue(ScriptProperty) ?? "";
    
    public static void SetScript(Control control, string value) => 
        control.SetValue(ScriptProperty, value ?? "");
}

using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using System;

namespace VB;

public class TinyButton : StackPanel
{
    private Label textLabel;
    private Button actionBtn;
    
    public string Text
    {
        get => textLabel.Content?.ToString() ?? "";
        set => textLabel.Content = value;
    }
    
    public string ButtonColor { get; set; } = "#66bb6a";  // Default green
    
    public event EventHandler? Clicked;
    
    public TinyButton()
    {
        Orientation = Orientation.Horizontal;
        Spacing = 0;
        
        textLabel = new Label
        {
            Width = 70,
            MinHeight = 15,
            FontSize = 11,
            FontWeight = FontWeight.Bold,
            Padding = new Thickness(4, 2, 4, 2),
            Background = Brushes.White,
            BorderBrush = new SolidColorBrush(Color.Parse("#66bb6a")),
            BorderThickness = new Thickness(1, 1, 0, 1),
            CornerRadius = new CornerRadius(2, 0, 0, 2),
            HorizontalContentAlignment = HorizontalAlignment.Left,
            VerticalContentAlignment = VerticalAlignment.Center,
            Cursor = new Cursor(StandardCursorType.Hand)
        };
        
        actionBtn = new Button
        {
            Content = "♻",
            Width = 18,
            Height = 20,
            FontSize = 14,
            FontWeight = FontWeight.Bold,
            Padding = new Thickness(0, -2, 0, 0),
            Background = Brushes.White,
            BorderBrush = new SolidColorBrush(Color.Parse("#66bb6a")),
            BorderThickness = new Thickness(0, 1, 1, 1),
            CornerRadius = new CornerRadius(0, 2, 2, 0),
            HorizontalContentAlignment = HorizontalAlignment.Center,
            VerticalContentAlignment = VerticalAlignment.Center,
            Cursor = new Cursor(StandardCursorType.Hand)
        };
        
        actionBtn.Click += (s, e) => Clicked?.Invoke(this, EventArgs.Empty);
        textLabel.PointerPressed += (s, e) =>
        {
            Clicked?.Invoke(this, EventArgs.Empty);
            e.Handled = true;
        };
        
        Children.Add(textLabel);
        Children.Add(actionBtn);
        
        // Apply color after construction if set
        this.PropertyChanged += (s, e) =>
        {
            if (e.Property.Name == nameof(ButtonColor))
                UpdateColor();
        };
    }
    
    private void UpdateColor()
    {
        actionBtn.Foreground = new SolidColorBrush(Color.Parse(ButtonColor));
    }
    
    public void SetButtonColor(string color)
    {
        ButtonColor = color;
        actionBtn.Foreground = new SolidColorBrush(Color.Parse(color));
    }
}

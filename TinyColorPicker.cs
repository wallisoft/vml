using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using System;

namespace VB;

public class TinyColorPicker : StackPanel
{
    private Label hexLabel;
    private Button pickBtn;
    private Color currentColor = Colors.White;
    
    public Color Color
    {
        get => currentColor;
        set
        {
            currentColor = value;
            hexLabel.Content = currentColor.ToString();
        }
    }
    
    public event EventHandler<Color>? ColorChanged;
    
    public TinyColorPicker()
    {
        Orientation = Orientation.Horizontal;
        Spacing = 0;
        
       hexLabel = new Label
	{
	    Width = 70,  // Was 100
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
        pickBtn = new Button
        {
            Content = "♻",
            Width = 18,
            Height = 20,
            FontSize = 14,
            FontWeight = FontWeight.Bold,
            Padding = new Thickness(0, -1, 0, 0),
            Background = Brushes.White,
            Foreground = new SolidColorBrush(Color.Parse("#ff6600")),
            BorderBrush = new SolidColorBrush(Color.Parse("#66bb6a")),
            BorderThickness = new Thickness(0, 1, 1, 1),
            CornerRadius = new CornerRadius(0, 2, 2, 0),
            HorizontalContentAlignment = HorizontalAlignment.Center,
            VerticalContentAlignment = VerticalAlignment.Center,
            Cursor = new Cursor(StandardCursorType.Hand)
        };
        
        pickBtn.Click += (s, e) => ShowColorPicker();
        hexLabel.PointerPressed += (s, e) =>
        {
            ShowColorPicker();
            e.Handled = true;
        };
        
        Children.Add(hexLabel);
        Children.Add(pickBtn);
    }
    
private async void ShowColorPicker()
{
    var colorView = new ColorView
    {
        Color = currentColor
    };
    
    var okBtn = new Button 
	{ 
		Content = "OK", 
			Width = 80,
			FontWeight = FontWeight.Bold,
			Background = Brushes.White,
			Foreground = new SolidColorBrush(Color.Parse("#2e7d32")),
			BorderBrush = new SolidColorBrush(Color.Parse("#2e7d32")),
			BorderThickness = new Thickness(2),
			HorizontalContentAlignment = HorizontalAlignment.Center,
			VerticalContentAlignment = VerticalAlignment.Center
		};

		var cancelBtn = new Button 
		{ 
			Content = "Cancel", 
			Width = 80,
			FontWeight = FontWeight.Bold,
			Background = Brushes.White,
			Foreground = new SolidColorBrush(Color.Parse("#2e7d32")),
			BorderBrush = new SolidColorBrush(Color.Parse("#2e7d32")),
			BorderThickness = new Thickness(2),
			HorizontalContentAlignment = HorizontalAlignment.Center,
			VerticalContentAlignment = VerticalAlignment.Center
		};
			var buttonPanel = new StackPanel
    {
        Orientation = Orientation.Horizontal,
        HorizontalAlignment = HorizontalAlignment.Right,
        Spacing = 10,
        Margin = new Thickness(0, 10, 0, 0),
        Children = { okBtn, cancelBtn }
    };
    
    var container = new Border
    {
        Padding = new Thickness(20),
        Child = new StackPanel
        {
            Children = { colorView, buttonPanel }
        }
    };
    
    var window = new Window
    {
        Title = "Pick Color",
        Content = container,
        SizeToContent = SizeToContent.WidthAndHeight,
        CanResize = false,
        WindowStartupLocation = WindowStartupLocation.CenterOwner
    };
    
    okBtn.Click += (s, e) =>
    {
        currentColor = colorView.Color;
        hexLabel.Content = currentColor.ToString();
        ColorChanged?.Invoke(this, currentColor);
        window.Close();
    };
    
    cancelBtn.Click += (s, e) => window.Close();
    
    await window.ShowDialog((Window)this.VisualRoot!);
}
}

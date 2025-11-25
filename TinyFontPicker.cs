using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using System;
using System.Collections.Generic;
using System.Linq;

namespace VB;

public class TinyFontPicker : StackPanel
{
    private Label fontLabel;
    private Button pickBtn;
    private FontFamily currentFamily = FontFamily.Default;
    private double currentSize = 12;
    private FontWeight currentWeight = FontWeight.Normal;
    private FontStyle currentStyle = FontStyle.Normal;
    
    public FontFamily Family
    {
        get => currentFamily;
        set { currentFamily = value; UpdateLabel(); }
    }
    
    public double Size
    {
        get => currentSize;
        set { currentSize = value; UpdateLabel(); }
    }
    
    public FontWeight Weight
    {
        get => currentWeight;
        set { currentWeight = value; UpdateLabel(); }
    }
    
    public FontStyle Style
    {
        get => currentStyle;
        set { currentStyle = value; UpdateLabel(); }
    }
    
    public event EventHandler<(FontFamily family, double size, FontWeight weight, FontStyle style)>? FontChanged;
    
    public TinyFontPicker()
    {
        Orientation = Orientation.Horizontal;
        Spacing = 0;
        
        fontLabel = new Label
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
        
        pickBtn = new Button
        {
            Content = "♻",
            Width = 18,
            Height = 20,
            FontSize = 14,
            FontWeight = FontWeight.Bold,
            Padding = new Thickness(0, -2, 0, 0),
            Background = Brushes.White,
            Foreground = new SolidColorBrush(Color.Parse("#2196F3")),
            BorderBrush = new SolidColorBrush(Color.Parse("#66bb6a")),
            BorderThickness = new Thickness(0, 1, 1, 1),
            CornerRadius = new CornerRadius(0, 2, 2, 0),
            HorizontalContentAlignment = HorizontalAlignment.Center,
            VerticalContentAlignment = VerticalAlignment.Center,
            Cursor = new Cursor(StandardCursorType.Hand)
        };
        
        UpdateLabel();
        
        pickBtn.Click += (s, e) => ShowFontPicker();
        fontLabel.PointerPressed += (s, e) =>
        {
            ShowFontPicker();
            e.Handled = true;
        };
        
        Children.Add(fontLabel);
        Children.Add(pickBtn);
    }
    
    private void UpdateLabel()
    {
        var weightStr = currentWeight != FontWeight.Normal ? $" {currentWeight}" : "";
        var styleStr = currentStyle != FontStyle.Normal ? $" {currentStyle}" : "";
        fontLabel.Content = $"{currentFamily.Name} {currentSize}{weightStr}{styleStr}";
    }
    
private async void ShowFontPicker()
{
    var greenBorder = new SolidColorBrush(Color.Parse("#66bb6a"));
    
    // Common fonts
    var fonts = new[] 
    { 
        "Arial", "Calibri", "Cambria", "Comic Sans MS", "Consolas", "Courier New", 
        "Georgia", "Helvetica", "Lucida Console", "Segoe UI", "Times New Roman", 
        "Trebuchet MS", "Verdana", "Inter"
    };
    
    var familyCombo = new ComboBox 
    { 
        Width = 200,
        Background = Brushes.White,
        BorderBrush = greenBorder,
        BorderThickness = new Thickness(1)
    };
    foreach (var font in fonts)
        familyCombo.Items.Add(font);
    familyCombo.SelectedItem = currentFamily.Name;
    
    var sizeBox = new TextBox
    { 
        Width = 40,
        Text = currentSize.ToString(),
        Background = Brushes.White,
        BorderBrush = greenBorder,
        BorderThickness = new Thickness(1),
        HorizontalContentAlignment = HorizontalAlignment.Center,
        HorizontalAlignment = HorizontalAlignment.Left
    };
    
    var weightCombo = new ComboBox 
    { 
        Width = 120,
        Background = Brushes.White,
        BorderBrush = greenBorder,
        BorderThickness = new Thickness(1)
    };
    var weights = new[] { "Thin", "ExtraLight", "Light", "Normal", "Medium", "SemiBold", "Bold", "ExtraBold", "Black", "ExtraBlack" };
    foreach (var w in weights)
        weightCombo.Items.Add(w);
    weightCombo.SelectedItem = currentWeight.ToString();
    
    var styleCombo = new ComboBox 
    { 
        Width = 120,
        Background = Brushes.White,
        BorderBrush = greenBorder,
        BorderThickness = new Thickness(1)
    };
    var styles = new[] { "Normal", "Italic", "Oblique" };
    foreach (var s in styles)
        styleCombo.Items.Add(s);
    styleCombo.SelectedItem = currentStyle.ToString();
    
    var previewText = new TextBlock 
    { 
        Text = "The quick brown fox jumps over the lazy dog\nABCDEFGHIJKLMNOPQRSTUVWXYZ\n0123456789",
        FontFamily = currentFamily,
        FontSize = currentSize,
        FontWeight = currentWeight,
        FontStyle = currentStyle,
        TextWrapping = TextWrapping.Wrap,
        Padding = new Thickness(10)
    };
    
    var preview = new Border
    {
        Child = previewText,
        Margin = new Thickness(0, 10, 0, 0),
        Background = Brushes.White,
        BorderBrush = Brushes.LightGray,
        BorderThickness = new Thickness(1),
        Height = 150
    };
    
    // Update preview on changes
    familyCombo.SelectionChanged += (s, e) =>
    {
        if (familyCombo.SelectedItem != null)
            previewText.FontFamily = new FontFamily(familyCombo.SelectedItem.ToString()!);
    };
    
    sizeBox.TextChanged += (s, e) =>
    {
	if (double.TryParse(sizeBox.Text, out var size) && size > 0 && size <= 500)
        previewText.FontSize = size;
    };
    
    weightCombo.SelectionChanged += (s, e) =>
    {
        if (weightCombo.SelectedItem != null)
        {
            previewText.FontWeight = weightCombo.SelectedItem.ToString() switch
            {
                "Thin" => FontWeight.Thin,
                "ExtraLight" => FontWeight.ExtraLight,
                "Light" => FontWeight.Light,
                "Normal" => FontWeight.Normal,
                "Medium" => FontWeight.Medium,
                "SemiBold" => FontWeight.SemiBold,
                "Bold" => FontWeight.Bold,
                "ExtraBold" => FontWeight.ExtraBold,
                "Black" => FontWeight.Black,
                "ExtraBlack" => FontWeight.ExtraBlack,
                _ => FontWeight.Normal
            };
        }
    };
    
    styleCombo.SelectionChanged += (s, e) =>
    {
        if (styleCombo.SelectedItem != null)
        {
            previewText.FontStyle = styleCombo.SelectedItem.ToString() switch
            {
                "Italic" => FontStyle.Italic,
                "Oblique" => FontStyle.Oblique,
                _ => FontStyle.Normal
            };
        }
    };
    
    var grid = new Grid
    {
        RowDefinitions = new RowDefinitions("Auto,Auto,Auto,Auto,*"),
        ColumnDefinitions = new ColumnDefinitions("Auto,*"),
        Margin = new Thickness(10),
        RowSpacing = 8
    };
    
    grid.Children.Add(new TextBlock 
    { 
        Text = "Font Family:", 
        VerticalAlignment = VerticalAlignment.Center,
        TextAlignment = TextAlignment.Right,
        Margin = new Thickness(0, 0, 10, 0)
    });
    Grid.SetRow(grid.Children[^1], 0);
    Grid.SetColumn(grid.Children[^1], 0);
    
    grid.Children.Add(familyCombo);
    Grid.SetRow(grid.Children[^1], 0);
    Grid.SetColumn(grid.Children[^1], 1);
    
    grid.Children.Add(new TextBlock 
    { 
        Text = "Size:", 
        VerticalAlignment = VerticalAlignment.Center,
        TextAlignment = TextAlignment.Right,
        Margin = new Thickness(0, 0, 10, 0)
    });
    Grid.SetRow(grid.Children[^1], 1);
    Grid.SetColumn(grid.Children[^1], 0);
    
    grid.Children.Add(sizeBox);
    Grid.SetRow(grid.Children[^1], 1);
    Grid.SetColumn(grid.Children[^1], 1);
    
    grid.Children.Add(new TextBlock 
    { 
        Text = "Weight:", 
        VerticalAlignment = VerticalAlignment.Center,
        TextAlignment = TextAlignment.Right,
        Margin = new Thickness(0, 0, 10, 0)
    });
    Grid.SetRow(grid.Children[^1], 2);
    Grid.SetColumn(grid.Children[^1], 0);
    
    grid.Children.Add(weightCombo);
    Grid.SetRow(grid.Children[^1], 2);
    Grid.SetColumn(grid.Children[^1], 1);
    
    grid.Children.Add(new TextBlock 
    { 
        Text = "Style:", 
        VerticalAlignment = VerticalAlignment.Center,
        TextAlignment = TextAlignment.Right,
        Margin = new Thickness(0, 0, 10, 0)
    });
    Grid.SetRow(grid.Children[^1], 3);
    Grid.SetColumn(grid.Children[^1], 0);
    
    grid.Children.Add(styleCombo);
    Grid.SetRow(grid.Children[^1], 3);
    Grid.SetColumn(grid.Children[^1], 1);
    
    grid.Children.Add(preview);
    Grid.SetRow(grid.Children[^1], 4);
    Grid.SetColumn(grid.Children[^1], 1);
    
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
    
    var mainStack = new StackPanel { Children = { grid, buttonPanel } };
    
    var container = new Border
    {
        Padding = new Thickness(20),
        Background = new SolidColorBrush(Color.Parse("#F7F7F7")),
        Child = mainStack
    };
    
    var window = new Window
    {
        Title = "Pick Font",
        Content = container,
        Width = 400,
        Height = 420,
        CanResize = false,
        WindowStartupLocation = WindowStartupLocation.CenterOwner
    };
    
    okBtn.Click += (s, e) =>
    {
        currentFamily = new FontFamily(familyCombo.SelectedItem?.ToString() ?? "Arial");
        
        if (double.TryParse(sizeBox.Text, out var size))
            currentSize = size;
        
        currentWeight = weightCombo.SelectedItem?.ToString() switch
        {
            "Thin" => FontWeight.Thin,
            "ExtraLight" => FontWeight.ExtraLight,
            "Light" => FontWeight.Light,
            "Medium" => FontWeight.Medium,
            "SemiBold" => FontWeight.SemiBold,
            "Bold" => FontWeight.Bold,
            "ExtraBold" => FontWeight.ExtraBold,
            "Black" => FontWeight.Black,
            "ExtraBlack" => FontWeight.ExtraBlack,
            _ => FontWeight.Normal
        };
        
        currentStyle = styleCombo.SelectedItem?.ToString() switch
        {
            "Italic" => FontStyle.Italic,
            "Oblique" => FontStyle.Oblique,
            _ => FontStyle.Normal
        };
        
        UpdateLabel();
        FontChanged?.Invoke(this, (currentFamily, currentSize, currentWeight, currentStyle));
        window.Close();
    };
    
    cancelBtn.Click += (s, e) => window.Close();
    
    await window.ShowDialog((Window)this.VisualRoot!);
}
}

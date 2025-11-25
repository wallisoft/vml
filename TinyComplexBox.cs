using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using System;
using System.Linq;

namespace VB;

public class TinyComplexBox : StackPanel
{
    private Label valueLabel;
    private TextBox? editBox;
    private Panel? parentPanel;
    private Type propertyType;
    private object? currentValue;
    
    public object? Value
    {
        get => currentValue;
        set
        {
            currentValue = value;
            if (valueLabel != null)  // Only update if label exists
                UpdateLabel();
        }
    }
    
    public Type PropertyType
    {
        get => propertyType;
        set => propertyType = value;
    }
    
    public event EventHandler<object>? ValueChanged;
    
   public TinyComplexBox()
{
    Orientation = Orientation.Horizontal;
    Spacing = 0;
    
    valueLabel = new Label
    {
        Width = 70,
        MinHeight = 15,
        FontSize = 11,
        FontWeight = FontWeight.Bold,
        Padding = new Thickness(4, 2, 4, 2),
        Background = Brushes.White,
        BorderBrush = new SolidColorBrush(Color.Parse("#66bb6a")),
        BorderThickness = new Thickness(1),
        CornerRadius = new CornerRadius(2),
        HorizontalContentAlignment = HorizontalAlignment.Left,
        VerticalContentAlignment = VerticalAlignment.Center,
        Cursor = new Cursor(StandardCursorType.Ibeam)
    };
    
    valueLabel.PointerPressed += (s, e) =>
    {
        ShowEditBox();
        e.Handled = true;
    };
    
    Children.Add(valueLabel);
    
    UpdateLabel();  // Now it's safe to call
}
    
   private void UpdateLabel()
{
    if (valueLabel == null) return;  // Add this line
    
    if (currentValue == null)
    {
        valueLabel.Content = "(not set)";
        return;
    }
    
    string display = currentValue switch
    {
        Thickness t => $"{Math.Round(t.Left)},{Math.Round(t.Top)},{Math.Round(t.Right)},{Math.Round(t.Bottom)}",
        CornerRadius cr => $"{Math.Round(cr.TopLeft)},{Math.Round(cr.TopRight)},{Math.Round(cr.BottomRight)},{Math.Round(cr.BottomLeft)}",
        Point p => $"{Math.Round(p.X)},{Math.Round(p.Y)}",
        Size s => $"{Math.Round(s.Width)},{Math.Round(s.Height)}",
        Rect r => $"{Math.Round(r.X)},{Math.Round(r.Y)},{Math.Round(r.Width)},{Math.Round(r.Height)}",
        PixelPoint pp => $"{pp.X},{pp.Y}",
        RelativePoint rp => $"{Math.Round(rp.Point.X)},{Math.Round(rp.Point.Y)}",
        _ => currentValue.ToString() ?? "(unknown)"
    };
    
    valueLabel.Content = display;
}

    
    private void ShowEditBox()
    {
        parentPanel = this.Parent as Panel;
        if (parentPanel == null) return;
        
        editBox = new TextBox
        {
            Text = valueLabel.Content?.ToString() ?? "",
            Width = 120,
            MinHeight = 15,
            FontSize = 11,
            Padding = new Thickness(4, 2, 4, 2)
        };
        
        editBox.KeyDown += (s, e) =>
        {
            if (e.Key == Key.Enter)
            {
                TryApplyValue();
                SwapBack();
                e.Handled = true;
            }
        };
        
        editBox.LostFocus += (s, e) =>
        {
            TryApplyValue();
            SwapBack();
        };
        
        var index = parentPanel.Children.IndexOf(this);
        parentPanel.Children.RemoveAt(index);
        parentPanel.Children.Insert(index, editBox);
        editBox.Focus();
    }
    
    private void TryApplyValue()
    {
        if (editBox == null) return;
        
        var parsed = ParseValue(editBox.Text);
        if (parsed != null)
        {
            currentValue = parsed;
            UpdateLabel();
            ValueChanged?.Invoke(this, parsed);
        }
    }
    
    private object? ParseValue(string text)
    {
        var parts = text.Split(',').Select(s => s.Trim()).ToArray();
        
        if (propertyType == typeof(Thickness))
        {
            // Single value = all sides
            if (parts.Length == 1 && double.TryParse(parts[0], out var all))
                return new Thickness(all);
            
            // Four values = left,top,right,bottom
            if (parts.Length == 4 && 
                double.TryParse(parts[0], out var left) &&
                double.TryParse(parts[1], out var top) &&
                double.TryParse(parts[2], out var right) &&
                double.TryParse(parts[3], out var bottom))
                return new Thickness(left, top, right, bottom);
        }
        else if (propertyType == typeof(CornerRadius))
        {
            // Single value = all corners
            if (parts.Length == 1 && double.TryParse(parts[0], out var all))
                return new CornerRadius(all);
            
            // Four values = topLeft,topRight,bottomRight,bottomLeft
            if (parts.Length == 4 && 
                double.TryParse(parts[0], out var tl) &&
                double.TryParse(parts[1], out var tr) &&
                double.TryParse(parts[2], out var br) &&
                double.TryParse(parts[3], out var bl))
                return new CornerRadius(tl, tr, br, bl);
        }
        else if (propertyType == typeof(Point))
        {
            if (parts.Length == 2 && 
                double.TryParse(parts[0], out var x) &&
                double.TryParse(parts[1], out var y))
                return new Point(x, y);
        }
		else if (propertyType == typeof(Size))
{
    if (parts.Length == 2 &&
        double.TryParse(parts[0], out var w) &&
        double.TryParse(parts[1], out var h))
        return new Size(w, h);
}
else if (propertyType == typeof(Rect))
{
    if (parts.Length == 4 &&
        double.TryParse(parts[0], out var x) &&
        double.TryParse(parts[1], out var y) &&
        double.TryParse(parts[2], out var w) &&
        double.TryParse(parts[3], out var h))
        return new Rect(x, y, w, h);
}
else if (propertyType == typeof(PixelPoint))
{
    if (parts.Length == 2 &&
        int.TryParse(parts[0], out var x) &&
        int.TryParse(parts[1], out var y))
        return new PixelPoint(x, y);
}
else if (propertyType == typeof(RelativePoint))
{
    if (parts.Length == 2 &&
        double.TryParse(parts[0], out var x) &&
        double.TryParse(parts[1], out var y))
        return new RelativePoint(x, y, RelativeUnit.Relative);
}
        
        return null;  // Invalid format
    }
    
    private void SwapBack()
    {
        if (editBox == null || parentPanel == null) return;
        
        var idx = parentPanel.Children.IndexOf(editBox);
        if (idx >= 0)
        {
            parentPanel.Children.RemoveAt(idx);
            parentPanel.Children.Insert(idx, this);
        }
    }
}

using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using System;

namespace VB;

public class TinyCheckBox : Border
{
    private bool isChecked;
    
    public bool? IsChecked
    {
        get => isChecked;
        set
        {
            isChecked = value ?? false;
            Background = isChecked 
                ? new SolidColorBrush(Color.Parse("#ff6600"))  // Orange
                : Brushes.White;
        }
    }
    
    public event EventHandler? IsCheckedChanged;
    
    public TinyCheckBox()
    {
        Width = 15;
        Height = 15;
        Background = Brushes.White;
        BorderBrush = new SolidColorBrush(Color.Parse("#66bb6a"));
        BorderThickness = new Thickness(1);
        CornerRadius = new CornerRadius(2);
        HorizontalAlignment = HorizontalAlignment.Left;
        Cursor = new Cursor(StandardCursorType.Hand);
        
        PointerPressed += (s, e) =>
        {
            IsChecked = !isChecked;
            IsCheckedChanged?.Invoke(this, EventArgs.Empty);
            e.Handled = true;
        };
    }
}

using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using System;
using System.Collections.Generic;

namespace VB;

public class TinyCombo : StackPanel
{
    private Label valueBox;
    private Button dropBtn;
    private Panel? parentPanel;
    private List<object> items = new();
    
    public string Text
    {
        get => valueBox.Content?.ToString() ?? "";
        set => valueBox.Content = value;
    }
    
    public List<object> Items => items;
    public event EventHandler<object>? SelectionChanged;
    
    public TinyCombo()
    {
        Orientation = Orientation.Horizontal;
        Spacing = 0;
        
	valueBox = new Label
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

	// And in ShowComboBox:
	var combo = new ComboBox 
	{ 
		Width = 88,  // Was 118 (70 + 18)
		Height = 18,
		// ... rest
	};	

        dropBtn = new Button
        {
	    Content = "♻",
	    Width = 20,
	    Height = 20,
	    FontSize = 14,
	    FontWeight = FontWeight.Bold,
	    Padding = new Thickness(0, -1, 0, 0),
	    Background = Brushes.White,
	    Foreground = new SolidColorBrush(Color.Parse("#66bb6a")),  // GREEN
	    BorderBrush = new SolidColorBrush(Color.Parse("#66bb6a")),
	    BorderThickness = new Thickness(0, 1, 1, 1),
	    CornerRadius = new CornerRadius(0, 2, 2, 0),
	    HorizontalContentAlignment = HorizontalAlignment.Center,
	    VerticalContentAlignment = VerticalAlignment.Center,
	    Cursor = new Cursor(StandardCursorType.Hand)
        };
        
        dropBtn.Click += (s, e) => ShowComboBox();
        valueBox.PointerPressed += (s, e) =>
        {
            ShowComboBox();
            e.Handled = true;
        };
        
        Children.Add(valueBox);
        Children.Add(dropBtn);
    }
    
    private void ShowComboBox()
{
    parentPanel = this.Parent as Panel;
    if (parentPanel == null || items.Count == 0) return;

    var combo = new ComboBox
    {
        Width = 118,
        Height = 18,
        MinHeight = 18,
        MaxHeight = 18,
        FontSize = 11,
        Padding = new Thickness(4, 0, 4, 0),
        BorderBrush = new SolidColorBrush(Color.Parse("#2196F3")),
        BorderThickness = new Thickness(1)
    };
    foreach (var item in items)
        combo.Items.Add(item);
    combo.SelectedItem = valueBox.Content?.ToString();

    combo.SelectionChanged += (s, e) =>
    {
        if (combo.SelectedItem != null)
        {
            valueBox.Content = combo.SelectedItem.ToString();
            SelectionChanged?.Invoke(this, combo.SelectedItem);
        }
    };

    combo.DropDownClosed += (s, e) =>
    {
        var idx = parentPanel.Children.IndexOf(combo);
        if (idx >= 0)
        {
            parentPanel.Children.RemoveAt(idx);
            parentPanel.Children.Insert(idx, this);
        }
    };

    var index = parentPanel.Children.IndexOf(this);
    parentPanel.Children.RemoveAt(index);
    parentPanel.Children.Insert(index, combo);
    combo.Focus();
    combo.IsDropDownOpen = true;
    }

}

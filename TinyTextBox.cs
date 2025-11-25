using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using System;

namespace VB;

public class TinyTextBox : StackPanel
{
    private Label fakeBox;
    private TextBox? realTextBox;
    private Panel? parentPanel;
    
    public string Text
    {
        get => fakeBox.Content?.ToString() ?? "";
        set => fakeBox.Content = value;
    }
    
    public event EventHandler<string>? TextChanged;
    
    public TinyTextBox()
    {
        Orientation = Orientation.Horizontal;
        Spacing = 0;
        
	fakeBox = new Label
	{
	    Width = 70,  // Was 100
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

	// And update realTextBox width:
	realTextBox = new TextBox
	{
	    Text = fakeBox.Content?.ToString() ?? "",
	    Width = 70,  // Was 100
	    MinHeight = 15,
	    FontSize = 11,
	    Padding = new Thickness(4, 2, 4, 2)
};
        
        fakeBox.PointerPressed += (s, e) =>
        {
            ShowRealTextBox();
            e.Handled = true;
        };
        
        Children.Add(fakeBox);
    }
    
    private void ShowRealTextBox()
    {
        Console.WriteLine("[TINYTEXTBOX] ShowRealTextBox called");
        parentPanel = this.Parent as Panel;
        if (parentPanel == null) 
        {
            Console.WriteLine("[TINYTEXTBOX] No parent panel!");
            return;
        }
        
        realTextBox = new TextBox
        {
            Text = fakeBox.Content?.ToString() ?? "",
            Width = 120,
            MinHeight = 15,
            FontSize = 11,
            Padding = new Thickness(4, 2, 4, 2)
        };
        
        realTextBox.KeyDown += (s, e) =>
        {
            if (e.Key == Key.Enter)
            {
                SwapBack();
                e.Handled = true;
            }
        };
        
        realTextBox.LostFocus += (s, e) => SwapBack();
        
        var index = parentPanel.Children.IndexOf(this);
        parentPanel.Children.RemoveAt(index);
        parentPanel.Children.Insert(index, realTextBox);
        realTextBox.Focus();
        realTextBox.CaretIndex = realTextBox.Text?.Length ?? 0;
    }
    
    private void SwapBack()
    {
        Console.WriteLine("[TINYTEXTBOX] SwapBack called");
        if (realTextBox == null || parentPanel == null) return;
        
        fakeBox.Content = realTextBox.Text;
        TextChanged?.Invoke(this, realTextBox.Text);
        
        var idx = parentPanel.Children.IndexOf(realTextBox);
        if (idx >= 0)
        {
            parentPanel.Children.RemoveAt(idx);
            parentPanel.Children.Insert(idx, this);
        }
    }
}

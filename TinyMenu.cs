using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks; 
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Input;
using Avalonia.VisualTree; 
using Microsoft.Data.Sqlite;

namespace VB;

/// <summary>
/// TinyMenu - Completely VML-driven menu system
/// Reads menu structure, theme, and handlers from database
/// </summary>
public class TinyMenu : Border
{
    private readonly string _dbPath;
    private Grid _menuBar;
    private List<MenuItemData> _menuItems = new();
    private Border? _activePopup;
    private MenuTheme _theme;
    private Canvas? _overlayCanvas; 
    private System.Timers.Timer? _closeTimer;  
    private List<Border> _activePopups = new(); 
    
    public TinyMenu(string dbPath)
    {
        _dbPath = dbPath;
        LoadTheme();
        LoadMenuStructure();
        BuildUI();
        
        // Setup overlay canvas when attached to visual tree
        this.AttachedToVisualTree += (s, e) =>
        {
            var rootGrid = FindRootGrid();
            
            if (rootGrid != null && _overlayCanvas == null)
            {
                _overlayCanvas = new Canvas 
                { 
                    Background = Brushes.Transparent,
                    IsHitTestVisible = false, 
                    ZIndex = 999
                };
                
                Grid.SetRow(_overlayCanvas, 1);
                Grid.SetRowSpan(_overlayCanvas, 2);
                
                rootGrid.Children.Add(_overlayCanvas);
                
                // Add PointerExited to overlay
                _overlayCanvas.PointerExited += (s, e) =>
                {
                    Task.Delay(150).ContinueWith(_ =>
                    {
                        Avalonia.Threading.Dispatcher.UIThread.Post(() =>
                        {
                            if (_activePopup != null && !_overlayCanvas.IsPointerOver)
                            {
                                ClosePopup();
                            }
                        });
                    });
                };

                _overlayCanvas.PointerPressed += (s2, e2) =>
                {
                    ClosePopup();
                };
            }
        };

    }
        
    private void LoadTheme()
    {
        _theme = new MenuTheme
        {
            Background = GetProperty("MenuTheme", "Background") ?? "#107C10",
            Foreground = GetProperty("MenuTheme", "Foreground") ?? "White",
            HoverBackground = GetProperty("MenuTheme", "HoverBackground") ?? "White",
            HoverForeground = GetProperty("MenuTheme", "HoverForeground") ?? "#107C10",
            PopupBackground = GetProperty("MenuTheme", "PopupBackground") ?? "White",
            PopupBorder = GetProperty("MenuTheme", "PopupBorder") ?? "#107C10",
            Height = double.Parse(GetProperty("MenuTheme", "Height") ?? "30")
        };
    }
    
    private void LoadMenuStructure()
    {
        using var conn = new SqliteConnection($"Data Source={_dbPath}");
        conn.Open();
        
        // Get all MenuItem objects
        var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            SELECT ut.id, ut.name, ut.parent_id
            FROM ui_tree ut
            WHERE ut.control_type = 'MenuItem'
            ORDER BY ut.display_order";
        
        using var reader = cmd.ExecuteReader();
        var items = new List<(int id, string name, int? parentId)>();
        
        while (reader.Read())
        {
            items.Add((
                reader.GetInt32(0),
                reader.GetString(1),
                reader.IsDBNull(2) ? null : reader.GetInt32(2)
            ));
        }
        reader.Close();
        
        // Load properties for each menu item
        foreach (var (id, name, parentId) in items)
        {
            var menuItem = new MenuItemData
            {
                Id = id,
                Name = name,
                ParentId = parentId,
                Text = GetPropertyById(id, "Text") ?? name,
                Shortcut = GetPropertyById(id, "Shortcut"),
                Align = GetPropertyById(id, "Align"),
                OnClick = GetPropertyById(id, "OnClick")
            };
            
            _menuItems.Add(menuItem);
        }
    }
    
    private void BuildUI()
    {
        _menuBar = new Grid
        {
            Background = Brush.Parse(_theme.Background),
            Height = _theme.Height
        };
        
        // Build top-level menu buttons (items with no parent or parent = MenuBar)
        var topLevel = _menuItems.Where(m => 
            m.ParentId == null || 
            GetParentName(m.ParentId.Value) == "MenuBar").ToList();
        
        // Separate left and right aligned items
        var leftItems = topLevel.Where(m => m.Align != "Right").ToList();
        var rightItems = topLevel.Where(m => m.Align == "Right").ToList();
        
        _menuBar.ColumnDefinitions = new ColumnDefinitions(
            string.Join(",", leftItems.Select(_ => "Auto")) + ",*"
        );
        
        // Add left-aligned items
        for (int i = 0; i < leftItems.Count; i++)
        {
            var menuItem = leftItems[i];
            var button = CreateTopLevelButton(menuItem);
            Grid.SetColumn(button, i);
            _menuBar.Children.Add(button);
        }
        
        // Add right-aligned items in the star column
        if (rightItems.Any())
        {
            var rightPanel = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
            foreach (var menuItem in rightItems)
            {
                var button = CreateTopLevelButton(menuItem);
                rightPanel.Children.Add(button);
            }
            Grid.SetColumn(rightPanel, leftItems.Count);
            _menuBar.Children.Add(rightPanel);
        }
        
        Child = _menuBar;
    }
    
    private Button CreateTopLevelButton(MenuItemData menuItem)
    {
        var button = new Button
        {
            Content = menuItem.Text,
            Background = Brushes.Transparent,
            Foreground = Brush.Parse(_theme.Foreground),
            BorderThickness = new Thickness(0),
            Padding = new Thickness(15, 0),
            VerticalAlignment = VerticalAlignment.Center,
            Cursor = new Cursor(StandardCursorType.Hand)
        };

        
        button.Click += (s, e) =>
        {
            ShowPopup(menuItem, button);
        };


        // Hover - show popup
        button.PointerEntered += (s, e) =>
        {
            button.Background = Brush.Parse(_theme.HoverBackground);
            button.Foreground = Brush.Parse(_theme.HoverForeground);
            ShowPopup(menuItem, button);
        };
        
        button.PointerExited += (s, e) =>
        {
            // Delay closing to allow moving to popup
            Task.Delay(100).ContinueWith(_ =>
            {
                Avalonia.Threading.Dispatcher.UIThread.Post(() =>
                {
                    if (_activePopup?.Tag != menuItem || !IsPointerOverPopup())
                    {
                        button.Background = Brushes.Transparent;
                        button.Foreground = Brush.Parse(_theme.Foreground);
                    }
                });
            });
        };
        
        return button;
    }

    private void ShowPopup(MenuItemData menuItem, Control parentControl, bool isNested = false, Point? nestPosition = null)
    {
        // Close all popups if this is a top-level menu item
        if (!isNested)
        {
            CloseAllPopups();
        }

        // Get child items
        var children = _menuItems.Where(m => m.ParentId == menuItem.Id).ToList();
        if (children.Count == 0) return;

        var stack = new StackPanel { Spacing = 0 };

        foreach (var child in children)
        {
            // Check if this item has children (for nested menus)
            var hasChildren = _menuItems.Any(m => m.ParentId == child.Id);
            var contentPanel = new Grid();
            contentPanel.ColumnDefinitions = new ColumnDefinitions("*,Auto,Auto");
            
            var textBlock = new TextBlock
            {
                Text = child.Text,
                VerticalAlignment = VerticalAlignment.Center
            };
            Grid.SetColumn(textBlock, 0);
            contentPanel.Children.Add(textBlock);
            
            if (child.Shortcut != null)
            {
                var shortcutBlock = new TextBlock
                {
                    Text = child.Shortcut,
                    Foreground = Brushes.Gray,
                    Margin = new Thickness(20, 0, 0, 0),
                    VerticalAlignment = VerticalAlignment.Center
                };
                Grid.SetColumn(shortcutBlock, 1);
                contentPanel.Children.Add(shortcutBlock);
            }
            
            if (hasChildren)
            {
                var arrowBlock = new TextBlock
                {
                    Text = ">",
                    Foreground = Brushes.Gray,
                    Margin = new Thickness(10, 0, 0, 0),
                    VerticalAlignment = VerticalAlignment.Center
                };
                Grid.SetColumn(arrowBlock, 2);
                contentPanel.Children.Add(arrowBlock);
            }
            
            var itemButton = new Button
            {
                Content = contentPanel,
                Background = Brush.Parse(_theme.PopupBackground),
                Foreground = Brushes.Black,
                BorderThickness = new Thickness(0),
                HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                Padding = new Thickness(15, 8),
                Cursor = new Cursor(StandardCursorType.Hand),
                Tag = child  // Store menu item for nested lookup
            };

            // Hover
            itemButton.PointerEntered += (s, e) =>
            {
                itemButton.Background = Brush.Parse(_theme.HoverBackground);
                itemButton.Foreground = Brush.Parse(_theme.HoverForeground);

                // Show nested popup if has children
                if (hasChildren)
                {
                    // Close any previously open nested popups at this level or deeper
                    CloseNestedPopups(itemButton);

                    // Get button position for nested popup
                    var rootGrid = FindRootGrid();
                    if (rootGrid != null && _overlayCanvas != null)
                    {
                        var buttonPos = itemButton.TranslatePoint(new Point(itemButton.Bounds.Width, 0), rootGrid);
                        ShowPopup(child, itemButton, true, buttonPos);
                    }
                }
            };

            itemButton.PointerExited += (s, e) =>
            {
                if (!hasChildren)
                {
                    itemButton.Background = Brushes.Transparent;
                    itemButton.Foreground = Brushes.Black;
                }
            };

            // Click - execute action (only if no children)
            if (!hasChildren)
            {
                itemButton.Click += (s, e) =>
                {
                    CloseAllPopups();
                    if (!string.IsNullOrEmpty(child.OnClick))
                    {
                        ExecuteMenuAction(child.OnClick);
                    }
                };
            }

            stack.Children.Add(itemButton);
            }

            // Create popup border
            var popup = new Border
            {
                Background = Brush.Parse(_theme.PopupBackground),
                BorderBrush = Brush.Parse(_theme.PopupBorder),
                BorderThickness = new Thickness(2),
                CornerRadius = new CornerRadius(3),
                BoxShadow = new BoxShadows(new BoxShadow { Blur = 3, Color = Color.Parse("#107C10"), OffsetY = 0 }),
                Child = stack,
                Tag = menuItem
            };

            // Start close timer when mouse leaves popup
            popup.PointerExited += (s, e) =>
            {
                _closeTimer?.Stop();
                _closeTimer = new System.Timers.Timer(500);
                _closeTimer.Elapsed += (s2, e2) =>
                {
                    Avalonia.Threading.Dispatcher.UIThread.Post(() =>
                    {
                        // Check if mouse is over any popup
                        if (!_activePopups.Any(p => p.IsPointerOver))
                        {
                            CloseAllPopups();
                        }
                    });
                };
                _closeTimer.Start();
            };

            // Cancel timer when mouse returns
            popup.PointerEntered += (s, e) =>
            {
                _closeTimer?.Stop();
            };

            // Position popup
            if (_overlayCanvas != null)
            {
                _overlayCanvas.IsHitTestVisible = true;

                var rootGrid = FindRootGrid();
                if (rootGrid != null)
                {
                    if (isNested && nestPosition.HasValue)
                    {
                        // Nested popup - position to right of parent item
                        Canvas.SetLeft(popup, nestPosition.Value.X);
                        Canvas.SetTop(popup, nestPosition.Value.Y - 30);
                    }
                    else
                    {
                        // Top-level popup - position below menu button
                    var buttonPos = parentControl.TranslatePoint(new Point(0, 0), rootGrid);
                    if (buttonPos.HasValue)
                    {
                        Canvas.SetLeft(popup, buttonPos.Value.X);
                        Canvas.SetTop(popup, 0);
                    }
                }
            }
            _overlayCanvas.Children.Add(popup);
            _activePopups.Add(popup);
        }
    }
        
    private void CloseNestedPopups(Control fromItem)
    {
        // Close all popups that are children of this item's popup
        // (simplified - just close all except first one for now)
        while (_activePopups.Count > 1)
        {
            var popup = _activePopups[_activePopups.Count - 1];
            _overlayCanvas?.Children.Remove(popup);
            _activePopups.RemoveAt(_activePopups.Count - 1);
        }
    }

    public void CloseAllPopups()
    {
        _closeTimer?.Stop();
        
        foreach (var popup in _activePopups)
        {
            if (_overlayCanvas != null && _overlayCanvas.Children.Contains(popup))
            {
                _overlayCanvas.Children.Remove(popup);
            }
            popup.Child = null;
        }
        
        _activePopups.Clear();
        
        if (_overlayCanvas != null)
        {
            _overlayCanvas.IsHitTestVisible = false;
        }
    }

    // Keep old ClosePopup for compatibility
    private void ClosePopup() => CloseAllPopups();

    private void ExecuteMenuAction(string onClick)
    {
        Console.WriteLine($"[TINYMENU] Executing: {onClick}");

        // Check for direct commands
        if (onClick.StartsWith("FormOpen ") || onClick.StartsWith("FormOpenModal "))
        {
            var modal = onClick.StartsWith("FormOpenModal");
            var vmlPath = onClick.Substring(modal ? 14 : 9).Trim();

            Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
            {
                FormLoader.Open(vmlPath, modal);
            });
            return;
        }

        // Otherwise look for script in registry
        var script = ScriptRegistry.Get(onClick);
        if (script != null)
        {
            ScriptHandler.Execute(script.Content, script.Interpreter);
        }
        else
        {
            Console.WriteLine($"[TINYMENU] No handler or script found for: {onClick}");
        }
    }
    
    private string? GetProperty(string objectName, string propertyName)
    {
        using var conn = new SqliteConnection($"Data Source={_dbPath}");
        conn.Open();
        
        var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            SELECT up.property_value
            FROM ui_tree ut
            JOIN ui_properties up ON ut.id = up.ui_tree_id
            WHERE ut.name = @name AND up.property_name = @prop";
        cmd.Parameters.AddWithValue("@name", objectName);
        cmd.Parameters.AddWithValue("@prop", propertyName);
        
        return cmd.ExecuteScalar()?.ToString();
    }
    
    private string? GetPropertyById(int id, string propertyName)
    {
        using var conn = new SqliteConnection($"Data Source={_dbPath}");
        conn.Open();
        
        var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT property_value FROM ui_properties WHERE ui_tree_id = @id AND property_name = @prop";
        cmd.Parameters.AddWithValue("@id", id);
        cmd.Parameters.AddWithValue("@prop", propertyName);
        
        return cmd.ExecuteScalar()?.ToString();
    }
    
    private string GetParentName(int parentId)
    {
        using var conn = new SqliteConnection($"Data Source={_dbPath}");
        conn.Open();
        
        var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT name FROM ui_tree WHERE id = @id";
        cmd.Parameters.AddWithValue("@id", parentId);
        
        return cmd.ExecuteScalar()?.ToString() ?? "";
    }

    private Grid? FindRootGrid()
    {
        // Walk up the visual tree to find MainGrid
        var current = this.Parent;
        while (current != null)
        {
            if (current is Grid grid && grid.Name == "MainGrid")
                return grid;

            if (current is Visual visual)
                current = visual.GetVisualParent();
            else
                break;
        }
        return null;
    }

    private bool IsPointerOverPopup()
    {
        if (_activePopup == null) return false;

        // Check if popup is being hovered
        return _activePopup.IsPointerOver;
    }

}

public class MenuItemData
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public int? ParentId { get; set; }
    public string Text { get; set; } = "";
    public string? Shortcut { get; set; }
    public string? OnClick { get; set; }
    public string? Align { get; set; }
}

public class MenuTheme
{
    public string Background { get; set; } = "#107C10";
    public string Foreground { get; set; } = "White";
    public string HoverBackground { get; set; } = "White";
    public string HoverForeground { get; set; } = "#107C10";
    public string PopupBackground { get; set; } = "White";
    public string PopupBorder { get; set; } = "#107C10";
    public double Height { get; set; } = 30;
}

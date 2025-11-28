using System;
using System.Collections.Generic;
using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Input;
using Microsoft.Data.Sqlite;

namespace VB;

/// <summary>
/// VML ContextMenu control - provides right-click context menu functionality
/// Can be used both in the designer and in VML applications
/// </summary>
public static class VmlContextMenu
{
    private static Dictionary<string, ContextMenu> _contextMenus = new();
    private static Dictionary<string, VmlMenuItem> _menuStructure = new();
    
    public class VmlMenuItem
    {
        public string Header { get; set; } = "";
        public string? Name { get; set; }
        public string? OnClick { get; set; }
        public bool IsSeparator { get; set; }
        public string? Shortcut { get; set; }
        public List<VmlMenuItem> SubItems { get; set; } = new();
    }
    
    /// <summary>
    /// Load all context menus from database and attach to controls
    /// </summary>
    public static void LoadFromDatabase(string dbPath, Canvas? designCanvas)
    {
        using var conn = new SqliteConnection($"Data Source={dbPath}");
        conn.Open();
        
        // Find all ContextMenu controls
        var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            SELECT ut.id, ut.name,
                   MAX(CASE WHEN up.property_name = 'AttachTo' THEN up.property_value END) as attachTo
            FROM ui_tree ut
            LEFT JOIN ui_properties up ON ut.id = up.ui_tree_id
            WHERE ut.control_type = 'ContextMenu'
            GROUP BY ut.id";
        
        using var reader = cmd.ExecuteReader();
        var contextMenus = new List<(int id, string name, string attachTo)>();
        
        while (reader.Read())
        {
            var id = reader.GetInt32(0);
            var name = reader.GetString(1);
            var attachTo = reader.IsDBNull(2) ? "" : reader.GetString(2);
            contextMenus.Add((id, name, attachTo));
        }
        reader.Close();
        
        // Load each context menu
        foreach (var (menuId, menuName, attachTo) in contextMenus)
        {
            var menu = LoadContextMenuById(conn, menuId, menuName);

            // Store for later use
            _contextMenus[menuName] = menu;

            // We don't auto-attach anymore - menus are opened manually in DesignerMouseHandler
            Console.WriteLine($"[CONTEXT] Loaded: {menuName}");
        }
    }
    
    /// <summary>
    /// Load a specific context menu by ID
    /// </summary>
    private static ContextMenu LoadContextMenuById(SqliteConnection conn, int menuId, string menuName)
    {
        var contextMenu = new ContextMenu();
        var items = new List<MenuItem>();
        
        // Load menu items for this context menu  
        var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            SELECT ut.id, ut.name, ut.parent_id,
                   MAX(CASE WHEN up.property_name = 'Text' THEN up.property_value END) as text,
                   MAX(CASE WHEN up.property_name = 'OnClick' THEN up.property_value END) as onclick,
                   MAX(CASE WHEN up.property_name = 'IsSeparator' THEN up.property_value END) as separator,
                   MAX(CASE WHEN up.property_name = 'Shortcut' THEN up.property_value END) as shortcut
            FROM ui_tree ut
            LEFT JOIN ui_properties up ON ut.id = up.ui_tree_id
            WHERE ut.control_type = 'MenuItem'
            GROUP BY ut.id
            ORDER BY ut.display_order";
        
        using var reader = cmd.ExecuteReader();
        var menuItems = new Dictionary<int, (VmlMenuItem item, int? parentId)>();
        
        while (reader.Read())
        {
            var id = reader.GetInt32(0);
            var name = reader.IsDBNull(1) ? "" : reader.GetString(1);
            var parentId = reader.IsDBNull(2) ? (int?)null : reader.GetInt32(2);
            var text = reader.IsDBNull(3) ? "" : reader.GetString(3);
            var onClick = reader.IsDBNull(4) ? null : reader.GetString(4);
            var isSeparator = reader.IsDBNull(5) ? false : reader.GetString(5) == "true";
            var shortcut = reader.IsDBNull(6) ? null : reader.GetString(6);
            
            var item = new VmlMenuItem
            {
                Name = name,
                Header = text,
                OnClick = onClick,
                IsSeparator = isSeparator,
                Shortcut = shortcut
            };
            
            menuItems[id] = (item, parentId);
        }
        reader.Close();
        
        // Build hierarchy and create MenuItems
        var rootItems = new List<VmlMenuItem>();
        
        foreach (var kvp in menuItems)
        {
            var (item, parentId) = kvp.Value;
            
            // Check if parent is the context menu
            if (parentId == menuId)
            {
                rootItems.Add(item);
            }
            else if (parentId.HasValue && menuItems.ContainsKey(parentId.Value))
            {
                // Add to parent's subitems
                menuItems[parentId.Value].item.SubItems.Add(item);
            }
        }
        
        // Convert VmlMenuItems to Avalonia MenuItems
        foreach (var vmlItem in rootItems)
        {
            contextMenu.Items.Add(CreateMenuItem(vmlItem));
        }
        return contextMenu;
    }
    
    /// <summary>
    /// Create an Avalonia MenuItem from VmlMenuItem
    /// </summary>
    private static MenuItem CreateMenuItem(VmlMenuItem vmlItem)
    {
        if (vmlItem.IsSeparator)
        {
            return new MenuItem { Header = "-" };
        }
        
        var menuItem = new MenuItem { Header = vmlItem.Header };
        
        // Add click handler
        if (!string.IsNullOrEmpty(vmlItem.OnClick))
        {
            menuItem.Click += (s, e) =>
            {
                var target = GetContextMenuTarget();
                var onClickHandler = vmlItem.OnClick;
                string handlerName = onClickHandler;
                string[]? handlerArgs = null;
                
                // Parse args: ScriptName(arg1,arg2)
                if (onClickHandler.Contains("(") && onClickHandler.EndsWith(")"))
                {
                    var parenStart = onClickHandler.IndexOf("(");
                    handlerName = onClickHandler.Substring(0, parenStart);
                    var argsStr = onClickHandler.Substring(parenStart + 1, onClickHandler.Length - parenStart - 2);
                    if (!string.IsNullOrEmpty(argsStr))
                        handlerArgs = argsStr.Split(",").Select(a => a.Trim()).ToArray();
                }
                
                Console.WriteLine($"[CONTEXTMENU] Executing: {handlerName} with args: {string.Join(", ", handlerArgs ?? Array.Empty<string>())} for {target?.Name ?? "none"}");
                var script = ScriptRegistry.Get(handlerName);
                if (script != null)
                {
                    ScriptHandler.Execute(script.Content, script.Interpreter, null, handlerArgs);
                }
                else
                {
                    Console.WriteLine($"[CONTEXTMENU] Script not found: {handlerName}");
                }
            };
        }
        
        // Add sub-items
        foreach (var subItem in vmlItem.SubItems)
        {
            menuItem.Items.Add(CreateMenuItem(subItem));
        }
        
        return menuItem;
    }
    
    /// <summary>
    /// Attach context menu to canvas with custom handler
    /// </summary>
    private static void AttachToCanvas(Canvas canvas, ContextMenu menu)
    {
            Console.WriteLine($"[CONTEXT] AttachToCanvas called");
        // Replace default right-click handler
        canvas.PointerPressed += (s, e) =>
        {
            var point = e.GetCurrentPoint(canvas);
            if (point.Properties.IsRightButtonPressed)
            {
                            Console.WriteLine($"[CONTEXT] Right button detected, opening menu");
                // Find what was clicked
                var clickedControl = FindControlAt(canvas, point.Position);
                SetContextMenuTarget(clickedControl);
                
                // Show menu
                menu.Open(canvas);
                e.Handled = true;
            }
        };
    }
    
    /// <summary>
    /// Find control at position
    /// </summary>
    private static Control? FindControlAt(Canvas canvas, Point position)
    {
        foreach (var child in canvas.Children.OfType<Control>().Reverse())
        {
            if (child.Name == "selectionBorder" || child.Name == "designOverlay")
                continue;
                
            var bounds = new Rect(
                Canvas.GetLeft(child), 
                Canvas.GetTop(child),
                child.Bounds.Width, 
                child.Bounds.Height
            );
            
            if (bounds.Contains(position))
            {
                return child;
            }
        }
        return null;
    }
    
    // Track the current target for context menu
    private static Control? _currentTarget;
    
    public static void SetContextMenuTarget(Control? target)
    {
        _currentTarget = target;
        if (target != null)
        {
            VmlBootstrap.SelectControl(target);
        }
    }
    
    private static Control? GetContextMenuTarget()
    {
        return _currentTarget;
    }
    
    /// <summary>
    /// Get a loaded context menu by name
    /// </summary>
    public static ContextMenu? GetContextMenu(string name)
    {
        return _contextMenus.ContainsKey(name) ? _contextMenus[name] : null;
    }
}

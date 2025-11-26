using System;
using System.Collections.Generic;
using Avalonia.Controls;
using Avalonia.Controls.Shapes;
using Microsoft.Data.Sqlite;

namespace VB;

public static class ControlRegistry
{
    private static Dictionary<string, Func<Control>> _factories = new();
    private static Dictionary<string, ControlTypeInfo> _typeInfo = new();
    private static bool _initialized = false;

    public static void Initialize()
    {
        if (_initialized) return;
        
        // Register built-in factories
        RegisterFactory("Button", () => new Button { Content = "Button" });
        RegisterFactory("TextBox", () => new TextBox());
        RegisterFactory("TextBlock", () => new TextBlock { Text = "TextBlock" });
        RegisterFactory("CheckBox", () => new CheckBox { Content = "CheckBox" });
        RegisterFactory("ComboBox", () => new ComboBox());
        RegisterFactory("ListBox", () => new ListBox());
        RegisterFactory("StackPanel", () => new StackPanel());
        RegisterFactory("Grid", () => new Grid());
        RegisterFactory("Border", () => new Border());
        RegisterFactory("Canvas", () => new Canvas());
        RegisterFactory("ScrollViewer", () => new ScrollViewer());
        RegisterFactory("DockPanel", () => new DockPanel());
        RegisterFactory("Slider", () => new Slider());
        RegisterFactory("ProgressBar", () => new ProgressBar());
        RegisterFactory("Image", () => new Image());
        RegisterFactory("RadioButton", () => new RadioButton { Content = "Option" });
        RegisterFactory("ToggleSwitch", () => new ToggleSwitch());
        RegisterFactory("Rectangle", () => new Rectangle());
        RegisterFactory("Window", () => new Window());
        RegisterFactory("TinyMenu", () => new TinyMenu(PropertyStore.GetDbPath()));
        
        // Load metadata from database
        LoadTypeInfo();
        
        _initialized = true;
        Console.WriteLine($"[CONTROL REGISTRY] Initialized with {_factories.Count} control types");
    }

    public static void RegisterFactory(string name, Func<Control> factory)
    {
        _factories[name] = factory;
    }

    public static Control Create(string typeName, string? name = null)
    {
        if (!_initialized) Initialize();
        
        if (!_factories.TryGetValue(typeName, out var factory))
        {
            Console.WriteLine($"[CONTROL REGISTRY] Unknown type: {typeName}, using Border");
            return new Border { Name = name };
        }
        
        var control = factory();
        if (name != null) control.Name = name;
        
        // Apply default size from type info
        if (_typeInfo.TryGetValue(typeName, out var info))
        {
            if (info.DefaultWidth > 0) control.Width = info.DefaultWidth;
            if (info.DefaultHeight > 0) control.Height = info.DefaultHeight;
        }
        
        Console.WriteLine($"[CONTROL REGISTRY] Created {typeName} '{name ?? "unnamed"}'");
        return control;
    }

    public static ControlTypeInfo? GetTypeInfo(string typeName)
    {
        if (!_initialized) Initialize();
        return _typeInfo.TryGetValue(typeName, out var info) ? info : null;
    }

    public static IEnumerable<ControlTypeInfo> GetAllTypes()
    {
        if (!_initialized) Initialize();
        return _typeInfo.Values;
    }

    public static IEnumerable<ControlTypeInfo> GetTypesByCategory(string category)
    {
        if (!_initialized) Initialize();
        foreach (var info in _typeInfo.Values)
            if (info.Category == category)
                yield return info;
    }

    private static void LoadTypeInfo()
    {
        try
        {
            using var conn = new SqliteConnection($"Data Source={PropertyStore.GetDbPath()}");
            conn.Open();
            var cmd = conn.CreateCommand();
            cmd.CommandText = "SELECT name, dotnet_type, category, icon, default_width, default_height, default_props, is_container, is_user_defined FROM control_types";
            
            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                var info = new ControlTypeInfo
                {
                    Name = reader.GetString(0),
                    DotNetType = reader.GetString(1),
                    Category = reader.IsDBNull(2) ? "Common" : reader.GetString(2),
                    Icon = reader.IsDBNull(3) ? "📦" : reader.GetString(3),
                    DefaultWidth = reader.IsDBNull(4) ? 100 : reader.GetDouble(4),
                    DefaultHeight = reader.IsDBNull(5) ? 30 : reader.GetDouble(5),
                    DefaultProps = reader.IsDBNull(6) ? null : reader.GetString(6),
                    IsContainer = !reader.IsDBNull(7) && reader.GetInt32(7) == 1,
                    IsUserDefined = !reader.IsDBNull(8) && reader.GetInt32(8) == 1
                };
                _typeInfo[info.Name] = info;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[CONTROL REGISTRY] Error loading types: {ex.Message}");
        }
    }
}

public class ControlTypeInfo
{
    public string Name { get; set; } = "";
    public string DotNetType { get; set; } = "";
    public string Category { get; set; } = "Common";
    public string Icon { get; set; } = "📦";
    public double DefaultWidth { get; set; } = 100;
    public double DefaultHeight { get; set; } = 30;
    public string? DefaultProps { get; set; }
    public bool IsContainer { get; set; }
    public bool IsUserDefined { get; set; }
}

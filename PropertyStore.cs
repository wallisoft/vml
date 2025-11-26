using System;
using System.Collections.Generic;
using System.Data;
using Microsoft.Data.Sqlite;
using System.IO;

namespace VB;

public static class PropertyStore
{
    private static bool _initialized = false;
    private static SqliteConnection? connection;
    
    public static string GetDbPath()
    {
        // 1. Environment variable (highest priority - for testing/override)
        var envPath = Environment.GetEnvironmentVariable("VML_DB_PATH");
        if (!string.IsNullOrEmpty(envPath))
        {
            if (envPath.StartsWith("~/"))
                envPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), envPath.Substring(2));
            return envPath;
        }
        
        // 2. Config file ~/.vml/config
        var configDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".vml");
        var configFile = Path.Combine(configDir, "config");
        
        if (File.Exists(configFile))
        {
            var configPath = File.ReadAllText(configFile).Trim();
            if (configPath.StartsWith("~/"))
                configPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), configPath.Substring(2));
            if (!string.IsNullOrEmpty(configPath))
                return configPath;
        }

        // 3. Auto-detect: Debug build vs installed
        var exeDir = AppContext.BaseDirectory;
        
        // Check if running from bin/Debug or bin/Release (dev build)
        if (exeDir.Contains("/bin/Debug/") || exeDir.Contains("\\bin\\Debug\\") ||
            exeDir.Contains("/bin/Release/") || exeDir.Contains("\\bin\\Release\\"))
        {
            // Dev: use vml/vml.db relative to project root
            var devDb = Path.Combine(exeDir, "..", "..", "..", "vml", "vml.db");
            return Path.GetFullPath(devDb);
        }
        
        // 4. Default: installed location ~/.vml/vml.db
        return Path.Combine(configDir, "vml.db");
    }
        
        public static void Initialize()
    {
        if (_initialized) return;
        _initialized = true;
        
        try
        {
            var dbPath = GetDbPath();
            
            // Create directory if needed
            var dbDir = Path.GetDirectoryName(dbPath);
            if (!Directory.Exists(dbDir))
                Directory.CreateDirectory(dbDir!);
                
            connection = new SqliteConnection($"Data Source={dbPath}");
            connection.Open();
            
            var cmd = connection.CreateCommand();
            
            // Create ui_tree table (VML structure)
            cmd.CommandText = @"
                CREATE TABLE IF NOT EXISTS ui_tree (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER,
                    control_type TEXT NOT NULL,
                    name TEXT,
                    source_file TEXT,
                    is_root INTEGER DEFAULT 0,
                    display_order INTEGER DEFAULT 0,
                    imported_at INTEGER,
                    FOREIGN KEY (parent_id) REFERENCES ui_tree(id) ON DELETE CASCADE
                )";
            cmd.ExecuteNonQuery();
            
            // Create ui_properties table
            cmd.CommandText = @"
                CREATE TABLE IF NOT EXISTS ui_properties (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ui_tree_id INTEGER NOT NULL,
                    property_name TEXT NOT NULL,
                    property_value TEXT,
                    FOREIGN KEY (ui_tree_id) REFERENCES ui_tree(id) ON DELETE CASCADE
                )";
            cmd.ExecuteNonQuery();
            
            // Create settings table
            cmd.CommandText = @"
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    description TEXT
                )";
            cmd.ExecuteNonQuery();

            // Add default settings
            cmd.CommandText = @"
                INSERT OR IGNORE INTO settings (key, value, description) VALUES
                ('vml_parser', 'vml-parse', 'VML Parser'),
                ('vml_dir', '/home/steve/Downloads/vml/vml', 'VML files directory'),
                ('theme', 'light', 'UI theme (light/dark)'),
                ('grid_snap', 'true', 'Snap to grid when dragging'),
                ('grid_size', '10', 'Grid size in pixels'),
                ('api_server_enabled', 'false', 'Enable HTTP API server'),
                ('api_server_port', '8889', 'API server port'),
                ('default_editor_linux', 'code --wait {file}', 'Linux external editor'),
                ('default_editor_windows', 'notepad {file}', 'Windows external editor'),
                ('selected_control', '', 'Currently selected control name')";
            cmd.ExecuteNonQuery();
            
            // Create properties table (control runtime properties)
            cmd.CommandText = @"
                CREATE TABLE IF NOT EXISTS properties (
                    control_name TEXT NOT NULL,
                    property_name TEXT NOT NULL,
                    property_value TEXT,
                    PRIMARY KEY (control_name, property_name)
                )";
            cmd.ExecuteNonQuery();
            
            // Create dialog results table for script access
            cmd.CommandText = @"
                CREATE TABLE IF NOT EXISTS dialog_results (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    timestamp INTEGER
                )";
            cmd.ExecuteNonQuery();

            // Create property_display table (controls individual property display)
            cmd.CommandText = @"
                CREATE TABLE IF NOT EXISTS property_display (
                    control_type TEXT NOT NULL,
                    property_name TEXT NOT NULL,
                    display_name TEXT,
                    display_order INTEGER DEFAULT 0,
                    is_hidden INTEGER DEFAULT 0,
                    category TEXT,
                    editor_type TEXT,
                    PRIMARY KEY (control_type, property_name)
                )";
            cmd.ExecuteNonQuery();

            // Create property_groups table (for composite controls like Font picker)
            cmd.CommandText = @"
                CREATE TABLE IF NOT EXISTS property_groups (
                    control_type TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    display_name TEXT,
                    component_properties TEXT,
                    picker_type TEXT,
                    display_order INTEGER DEFAULT 0,
                    is_expanded INTEGER DEFAULT 1,
                    PRIMARY KEY (control_type, group_name)
                )";
            cmd.ExecuteNonQuery();

            // Add property display ordering - common properties first
            cmd.CommandText = @"
                INSERT OR IGNORE INTO property_display (control_type, property_name, display_order, is_hidden) VALUES
                -- Font group properties (hidden individually, shown in Font picker)
                ('*', 'FontFamily', 0, 1),
                ('*', 'FontSize', 0, 1),
                ('*', 'FontWeight', 0, 1),
                ('*', 'FontStyle', 0, 1),
                -- Common properties
                ('*', 'Name', 10, 0),
                ('*', 'Width', 20, 0),
                ('*', 'Height', 30, 0),
                ('*', 'X', 40, 0),
                ('*', 'Y', 50, 0),
                -- Content properties
                ('Button', 'Content', 60, 0),
                ('TextBox', 'Text', 60, 0),
                ('TextBlock', 'Text', 60, 0),
                ('Label', 'Content', 60, 0),
                -- Appearance
                ('*', 'Background', 70, 0),
                ('*', 'Foreground', 80, 0),
                ('*', 'BorderBrush', 90, 0),
                ('*', 'BorderThickness', 100, 0),
                ('*', 'Padding', 110, 0),
                ('*', 'Margin', 120, 0),
                -- Behavior
                ('*', 'IsVisible', 200, 0),
                ('*', 'IsEnabled', 210, 0),
                ('*', 'Opacity', 220, 0)";
            cmd.ExecuteNonQuery();

            // Add Font group (composite picker)
            cmd.CommandText = @"
                INSERT OR IGNORE INTO property_groups (control_type, group_name, display_name, component_properties, picker_type, display_order) VALUES
                ('*', 'Font', 'Font', 'FontFamily,FontSize,FontWeight,FontStyle', 'TinyFontPicker', 5)";
            cmd.ExecuteNonQuery();

            // Create scripts table
            cmd.CommandText = @"
                CREATE TABLE IF NOT EXISTS scripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    interpreter TEXT NOT NULL,
                    instance TEXT,
                    content TEXT NOT NULL,
                    source_file TEXT,
                    created_at INTEGER
                )";
            cmd.ExecuteNonQuery();

            // Create control_events table
            cmd.CommandText = @"
                CREATE TABLE IF NOT EXISTS control_events (
                    control_type TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    dotnet_event TEXT NOT NULL,
                    display_order INTEGER DEFAULT 0,
                    PRIMARY KEY (control_type, event_name)
                )";
            cmd.ExecuteNonQuery();

            // Populate default control events
            cmd.CommandText = @"
                INSERT OR IGNORE INTO control_events VALUES
                    ('Button','OnClick','Click',1),
                    ('Button','OnPointerPressed','PointerPressed',2),
                    ('Button','OnPointerReleased','PointerReleased',3),
                    ('TextBox','OnTextChanged','TextChanged',1),
                    ('TextBox','OnGotFocus','GotFocus',2),
                    ('TextBox','OnLostFocus','LostFocus',3),
                    ('TextBox','OnKeyDown','KeyDown',4),
                    ('CheckBox','OnChecked','IsCheckedChanged',1),
                    ('CheckBox','OnUnchecked','IsCheckedChanged',2),
                    ('ComboBox','OnSelectionChanged','SelectionChanged',1),
                    ('ListBox','OnSelectionChanged','SelectionChanged',1),
                    ('ListBox','OnDoubleTapped','DoubleTapped',2),
                    ('Slider','OnValueChanged','ValueChanged',1),
                    ('Window','OnOpened','Opened',1),
                    ('Window','OnClosing','Closing',2),
                    ('Window','OnClosed','Closed',3),
                    ('MenuItem','OnClick','Click',1),
                    ('TabControl','OnSelectionChanged','SelectionChanged',1),
                    ('TreeView','OnSelectionChanged','SelectionChanged',1),
                    ('Expander','OnExpanded','IsExpandedChanged',1),
                    ('Expander','OnCollapsed','IsExpandedChanged',2),
                    ('ToggleSwitch','OnChecked','IsCheckedChanged',1),
                    ('ToggleSwitch','OnUnchecked','IsCheckedChanged',2),
                    ('RadioButton','OnChecked','IsCheckedChanged',1)";
            cmd.ExecuteNonQuery();
            // Create control_types table
            cmd.CommandText = @"
                CREATE TABLE IF NOT EXISTS control_types (
                    name TEXT PRIMARY KEY,
                    dotnet_type TEXT NOT NULL,
                    category TEXT DEFAULT 'Common',
                    icon TEXT,
                    default_width REAL DEFAULT 100,
                    default_height REAL DEFAULT 30,
                    default_props TEXT,
                    is_container INTEGER DEFAULT 0,
                    is_user_defined INTEGER DEFAULT 0
                )";
            cmd.ExecuteNonQuery();
            // Populate default control types
            cmd.CommandText = @"
                INSERT OR IGNORE INTO control_types VALUES
                    ('Button','Avalonia.Controls.Button','Common','🔘',100,30,'Content=Button',0,0),
                    ('TextBox','Avalonia.Controls.TextBox','Input','📝',150,30,null,0,0),
                    ('TextBlock','Avalonia.Controls.TextBlock','Common','📄',100,20,'Text=TextBlock',0,0),
                    ('CheckBox','Avalonia.Controls.CheckBox','Input','☑️',100,20,'Content=CheckBox',0,0),
                    ('ComboBox','Avalonia.Controls.ComboBox','Input','📋',120,30,null,0,0),
                    ('ListBox','Avalonia.Controls.ListBox','Input','📃',150,100,null,0,0),
                    ('StackPanel','Avalonia.Controls.StackPanel','Layout','📦',200,200,null,1,0),
                    ('Grid','Avalonia.Controls.Grid','Layout','🔲',200,200,null,1,0),
                    ('Border','Avalonia.Controls.Border','Layout','🖼️',150,100,null,1,0),
                    ('Canvas','Avalonia.Controls.Canvas','Layout','🎨',300,200,null,1,0),
                    ('ScrollViewer','Avalonia.Controls.ScrollViewer','Layout','📜',200,150,null,1,0),
                    ('DockPanel','Avalonia.Controls.DockPanel','Layout','🔳',200,200,null,1,0),
                    ('Slider','Avalonia.Controls.Slider','Input','🎚️',150,20,null,0,0),
                    ('ProgressBar','Avalonia.Controls.ProgressBar','Display','📊',150,20,null,0,0),
                    ('Image','Avalonia.Controls.Image','Display','🖼️',100,100,null,0,0),
                    ('RadioButton','Avalonia.Controls.RadioButton','Input','🔘',100,20,'Content=Option',0,0),
                    ('ToggleSwitch','Avalonia.Controls.ToggleSwitch','Input','🔀',60,30,null,0,0)";
            cmd.ExecuteNonQuery();

            Console.WriteLine($"[PROPERTY STORE] Initialized at {dbPath}");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[PROPERTY STORE] Error: {ex.Message}");
        }
    }
        
    public static void Set(string controlName, string propertyName, string? value)
    {
        if (connection == null) Initialize();
        
        try
        {
            var cmd = connection!.CreateCommand();
            cmd.CommandText = @"
                INSERT OR REPLACE INTO properties (control_name, property_name, property_value)
                VALUES (@name, @prop, @value)";
            cmd.Parameters.AddWithValue("@name", controlName);
            cmd.Parameters.AddWithValue("@prop", propertyName);
            cmd.Parameters.AddWithValue("@value", value ?? string.Empty);
            cmd.ExecuteNonQuery();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[PROPERTY STORE] Set error: {ex.Message}");
        }
    }
        
    public static string? Get(string controlName, string propertyName)
    {
        if (connection == null) Initialize();
        
        try
        {
            var cmd = connection!.CreateCommand();
            cmd.CommandText = @"
                SELECT property_value FROM properties 
                WHERE control_name = @name AND property_name = @prop";
            cmd.Parameters.AddWithValue("@name", controlName);
            cmd.Parameters.AddWithValue("@prop", propertyName);
            
            var result = cmd.ExecuteScalar();
            return result?.ToString();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[PROPERTY STORE] Get error: {ex.Message}");
            return null;
        }
    }
    
    public static void SyncControl(Avalonia.Controls.Control control)
    {
        if (control.Name == null) return;
        
        var props = control.GetType().GetProperties();
        foreach (var prop in props)
        {
            try
            {
                var value = prop.GetValue(control);
                if (value != null)
                {
                    Set(control.Name, prop.Name, value.ToString());
                    UpdateVML(control.Name, prop.Name, value.ToString());
                }
            }
            catch
            {
                // Skip properties that can't be read
            }
        }
    }
    
    public static void UpdateVML(string controlName, string propertyName, string value)
    {
        var dbPath = GetDbPath();
        using var conn = new SqliteConnection($"Data Source={dbPath}");
        conn.Open();
        
        using var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            UPDATE source_files 
            SET content = REPLACE(
                content,
                'Name=""' || @controlName || '""',
                'Name=""' || @controlName || '"" ' || @propertyName || '=""' || @value || '""'
            )
            WHERE path = 'designer.vml'";
        cmd.Parameters.AddWithValue("@controlName", controlName);
        cmd.Parameters.AddWithValue("@propertyName", propertyName);
        cmd.Parameters.AddWithValue("@value", value);
        cmd.ExecuteNonQuery();
    }

    public static Dictionary<string, object?> GetControlProperties(string controlName)
    {
        var props = new Dictionary<string, object?>();
        
        if (connection == null) Initialize();
        
        try
        {
            var cmd = connection!.CreateCommand();
            cmd.CommandText = "SELECT property_name, property_value FROM properties WHERE control_name = @name";
            cmd.Parameters.AddWithValue("@name", controlName);
            
            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                props[reader.GetString(0)] = reader.GetString(1);
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[PROPERTY STORE] Query error: {ex.Message}");
        }
        
        return props;
    }
    
    public static void Close()
    {
        connection?.Close();
    }
}

using System;
using System.IO;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Layout;
using Microsoft.Data.Sqlite;

namespace VB;

public static class FormLoader
{
    public static void Open(string vmlPath, bool modal = false)
    {
        Console.WriteLine($"[FORMLOADER] Opening {vmlPath} (modal={modal})");
        
        // Resolve path
        if (!vmlPath.Contains("/") && !vmlPath.Contains("\\"))
        {
            var vmlDir = Settings.Get("vml_dir");
            if (string.IsNullOrEmpty(vmlDir))
            {
                Console.WriteLine($"[FORMLOADER] Error: vml_dir not set in database");
                return;
            }
            vmlPath = Path.Combine(vmlDir, vmlPath);
        }
        
        if (!File.Exists(vmlPath))
        {
            Console.WriteLine($"[FORMLOADER] Error: File not found: {vmlPath}");
            return;
        }
        
        // Import using parser (handles timestamp checking internally now)
        VmlDatabaseParser.LoadVml(vmlPath); 

        // Load scripts from database into registry
        LoadScriptsIntoRegistry(PropertyStore.GetDbPath());

        // Load and display form
        ShowFormFromDatabase(vmlPath, modal);
    }

    private static void ShowFormFromDatabase(string vmlPath, bool modal)
    {

    Console.WriteLine($"[FORMLOADER] ShowFormFromDatabase: {vmlPath}, modal={modal}");

        var dbPath = PropertyStore.GetDbPath();
        
        using var conn = new SqliteConnection($"Data Source={dbPath}");
        conn.Open();
        
        // Find root control from this VML file
        var cmd = conn.CreateCommand();
        cmd.CommandText = @"
            SELECT id, control_type, name 
            FROM ui_tree 
            WHERE source_file = @file AND (is_root = 1 OR parent_id IS NULL)
            ORDER BY display_order 
            LIMIT 1";
        cmd.Parameters.AddWithValue("@file", vmlPath);

            Console.WriteLine($"[FORMLOADER] Looking for controls with source_file = {vmlPath}");
        
        using var reader = cmd.ExecuteReader();
        if (!reader.Read())
        {
            Console.WriteLine($"[FORMLOADER] Error: No root control found in {vmlPath}");


        // DEBUG: Show what's actually in the database
        reader.Close();
        cmd.CommandText = "SELECT DISTINCT source_file FROM ui_tree LIMIT 10";
        using var debugReader = cmd.ExecuteReader();
        Console.WriteLine("[FORMLOADER] Available source_files:");
        while (debugReader.Read())

            Console.WriteLine($"  - {debugReader.GetString(0)}");

            return;
        }
        
        var id = reader.GetInt32(0);
        var controlType = reader.GetString(1);
        var name = reader.IsDBNull(2) ? null : reader.GetString(2);
        reader.Close();
        
        // Build control tree
        var root = DesignerWindow.CreateControlByType(conn, id, controlType, name);
        
        if (root == null)
        {
            Console.WriteLine($"[FORMLOADER] Error: Failed to build control tree");
            return;
        }
        
        // Create window
        var window = new Window
        {
            Title = Path.GetFileNameWithoutExtension(vmlPath),
            Width = 600,
            Height = 400
        };
        
        // If root is a Window, copy its properties
        if (root is Window vmlWindow)
        {
            window.Width = vmlWindow.Width;
            window.Height = vmlWindow.Height;
            window.Title = vmlWindow.Title ?? window.Title;
            window.Content = vmlWindow.Content;
        }
        else
        {
            window.Content = root;
        }
        
        // Wire control events
        WireEvents(window, window);

        // Show window
        if (modal && DesignerWindow.mainWindow != null)
        {
            window.ShowDialog(DesignerWindow.mainWindow);
        }
        else
        {
            window.Show();
        }
        
        Console.WriteLine($"[FORMLOADER] ✓ Displayed {Path.GetFileName(vmlPath)}");
    }

    private static void WireEvents(Control control, Window window)
    {
        var dbPath = PropertyStore.GetDbPath();
        using var conn = new SqliteConnection($"Data Source={dbPath}");
        conn.Open();
        WireControlEvents(conn, control, window);
    }

    private static void WireControlEvents(SqliteConnection conn, Control control, Window window)
    {
        if (control.Name != null)
        {
            // Query On* properties for this control
            var cmd = conn.CreateCommand();
            cmd.CommandText = @"
                SELECT up.property_name, up.property_value 
                FROM ui_properties up 
                JOIN ui_tree ut ON up.ui_tree_id = ut.id 
                WHERE ut.name = @name AND up.property_name LIKE 'On%'";
            cmd.Parameters.AddWithValue("@name", control.Name);
            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                var eventName = reader.GetString(0);
                var handler = reader.GetString(1);
                WireEvent(control, eventName, handler, window);
            }
        }

        // Recurse children
        if (control is Panel panel)
            foreach (var child in panel.Children) WireControlEvents(conn, child, window);
        else if (control is ContentControl cc && cc.Content is Control content)
            WireControlEvents(conn, content, window);
        else if (control is Decorator dec && dec.Child is Control child)
            WireControlEvents(conn, child, window);
    }

    private static void WireEvent(Control control, string eventName, string handler, Window window)
    {
        Console.WriteLine($"[FORMLOADER] Wiring {control.Name}.{eventName} -> {handler}");
        
        // Lookup .NET event name from control_events table
        var dbPath = PropertyStore.GetDbPath();
        using var conn = new SqliteConnection($"Data Source={dbPath}");
        conn.Open();
        var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT dotnet_event FROM control_events WHERE control_type = @type AND event_name = @event";
        cmd.Parameters.AddWithValue("@type", control.GetType().Name);
        cmd.Parameters.AddWithValue("@event", eventName);
        var dotnetEvent = cmd.ExecuteScalar()?.ToString();
        
        if (string.IsNullOrEmpty(dotnetEvent))
        {
            Console.WriteLine($"[FORMLOADER] Unknown event mapping: {eventName}");
            return;
        }
        
        Action action = () => ExecuteHandler(handler, window);
        
        // Wire based on .NET event name
        switch (dotnetEvent)
        {
            case "Click": ((Button)control).Click += (s, e) => action(); break;
            case "TextChanged": ((TextBox)control).TextChanged += (s, e) => action(); break;
            case "SelectionChanged" when control is ComboBox cb: cb.SelectionChanged += (s, e) => action(); break;
            case "SelectionChanged" when control is ListBox lb: lb.SelectionChanged += (s, e) => action(); break;
            case "IsCheckedChanged": ((CheckBox)control).IsCheckedChanged += (s, e) => action(); break;
            case "GotFocus": control.GotFocus += (s, e) => action(); break;
            case "LostFocus": control.LostFocus += (s, e) => action(); break;
            case "PointerEntered": control.PointerEntered += (s, e) => action(); break;
            case "PointerExited": control.PointerExited += (s, e) => action(); break;
            case "PointerPressed": control.PointerPressed += (s, e) => action(); break;
            case "PointerReleased": control.PointerReleased += (s, e) => action(); break;
            case "Opened" when control is Window w: w.Opened += (s, e) => action(); break;
            case "Closing" when control is Window w2: w2.Closing += (s, e) => action(); break;
            case "DoubleTapped": control.DoubleTapped += (s, e) => action(); break;
            case "KeyDown": control.KeyDown += (s, e) => action(); break;
            case "KeyUp": control.KeyUp += (s, e) => action(); break;
            default:
               Console.WriteLine($"[FORMLOADER] Unhandled .NET event: {dotnetEvent}");
            break;
        }
    }

    private static void ExecuteHandler(string handler, Window window)
    {
        Console.WriteLine($"[FORMLOADER] Executing: {handler}");
        
        // Parse args from handler: ScriptName(arg1,arg2) -> name + args[]
        string handlerName = handler;
        string[]? handlerArgs = null;
        
        if (handler.Contains("(") && handler.EndsWith(")"))
        {
            var parenStart = handler.IndexOf("(");
            handlerName = handler.Substring(0, parenStart);
            var argsStr = handler.Substring(parenStart + 1, handler.Length - parenStart - 2);
            if (!string.IsNullOrEmpty(argsStr))
                handlerArgs = argsStr.Split(",").Select(a => a.Trim()).ToArray();
            Console.WriteLine($"[FORMLOADER] Parsed: {handlerName} with args: {string.Join(", ", handlerArgs ?? Array.Empty<string>())}");
        }
        
        // Direct commands
        if (handlerName == "FormClose" || handlerName == "Close" || handler == "FormClose()" || handler == "Close()")
        {
            window.Close();
            return;
        }
        if (handlerName.StartsWith("FormOpen") || handlerName.StartsWith("FormOpenModal"))
        {
            var modal = handlerName.StartsWith("FormOpenModal");
            var vmlPath = handlerArgs?[0] ?? handlerName.Substring(modal ? 13 : 8).Trim();
            Open(vmlPath, modal);
            return;
        }
        
        // Script lookup
        var script = ScriptRegistry.Get(handlerName);
        Console.WriteLine($"[FORMLOADER] Script: {script?.Name ?? "null"}, Interp: {script?.Interpreter ?? "null"}, Instance: {script?.Instance ?? "null"}");
        if (script != null)
        {
            var interpreter = script.Instance != "" ? $"{script.Interpreter} {script.Instance}" : script.Interpreter;
            ScriptHandler.Execute(script.Content, interpreter, null, handlerArgs);
        }
        else
        {
            Console.WriteLine($"[FORMLOADER] No handler found: {handlerName}");
        }
    }

    private static void LoadScriptsIntoRegistry(string dbPath)
    {
        using var conn = new SqliteConnection($"Data Source={dbPath}");
        conn.Open();
        var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT name, content, interpreter, instance FROM scripts";
        
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            var name = reader.GetString(0);
            var content = reader.GetString(1);
            var interpreter = reader.GetString(2);
            var instance = reader.IsDBNull(3) ? "" : reader.GetString(3);
            ScriptRegistry.Register(name, content, interpreter, instance);
        }
    }
}

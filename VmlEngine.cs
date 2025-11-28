using System;
using System.Collections.Generic;
using System.Linq;
using NLua;
using Microsoft.Data.Sqlite;
using Avalonia.Controls;

namespace VB;

public class VmlEngine
{
    private Lua _lua;
    
    public VmlEngine()
    {
        _lua = new Lua();
        _lua.State.Encoding = System.Text.Encoding.UTF8;

        // Load standard libraries
        _lua.DoString("io = require('io')");
        _lua.DoString("os = require('os')");
        _lua.DoString("utf8 = require('utf8')");
        _lua.DoString("debug = require('debug')");
        _lua.DoString("coroutine = require('coroutine')");
        _lua.DoString("package = require('package')");  // Includes loadlib 

        // Register VML functions
        _lua.RegisterFunction("Vml", this, GetType().GetMethod(nameof(Vml)));
        Console.WriteLine("[LUA] Engine initialized with universal dispatcher");
    }
        
    public void Execute(string script)
    {
        try
        {
            _lua.DoString(script);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[LUA] Error: {ex.Message}");
            throw;
        }
    }
    
    // ===== DIALOG FUNCTIONS =====

    public string FileOpenDialog(string title, string filter)
    {
        var tcs = new System.Threading.Tasks.TaskCompletionSource<string>();
        
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
        {
            var dialog = new Avalonia.Controls.OpenFileDialog
            {
                Title = title,
                AllowMultiple = false
            };
            
            if (filter != "*")
            {
                dialog.Filters = new()
                {
                    new Avalonia.Controls.FileDialogFilter 
                    { 
                        Name = filter, 
                        Extensions = { filter.TrimStart('*', '.') } 
                    }
                };
            }
            
            var files = await dialog.ShowAsync(DesignerWindow.mainWindow);
            tcs.SetResult(files?.Length > 0 ? files[0] : "");
        });
        
        return tcs.Task.Result;
    }

    public string FileSaveDialog(string title, string defaultName, string filter)
    {
        var tcs = new System.Threading.Tasks.TaskCompletionSource<string>();
        
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
        {
            var dialog = new Avalonia.Controls.SaveFileDialog
            {
                Title = title,
                InitialFileName = defaultName
            };
            
            if (filter != "*")
            {
                dialog.DefaultExtension = filter.TrimStart('*', '.');
                dialog.Filters = new()
                {
                    new Avalonia.Controls.FileDialogFilter 
                    { 
                        Name = filter, 
                        Extensions = { filter.TrimStart('*', '.') } 
                    }
                };
            }
            
            var result = await dialog.ShowAsync(DesignerWindow.mainWindow);
            tcs.SetResult(result ?? "");
        });
        
        return tcs.Task.Result;
    }

    public string FolderSelectDialog(string title)
    {
        var tcs = new System.Threading.Tasks.TaskCompletionSource<string>();
        
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
        {
            var dialog = new Avalonia.Controls.OpenFolderDialog
            {
                Title = title
            };
            
            var result = await dialog.ShowAsync(DesignerWindow.mainWindow);
            tcs.SetResult(result ?? "");
        });
        
        return tcs.Task.Result;
    }

    public void InfoDialog(string message)
    {
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
        {
            var msgBox = new Avalonia.Controls.Window
            {
                Title = "Information",
                Width = 400,
                Height = 200,
                WindowStartupLocation = Avalonia.Controls.WindowStartupLocation.CenterOwner,
                Content = new Avalonia.Controls.StackPanel
                {
                    Margin = new Avalonia.Thickness(20),
                    Spacing = 15,
                    Children =
                    {
                        new Avalonia.Controls.TextBlock 
                        { 
                            Text = message, 
                            TextWrapping = Avalonia.Media.TextWrapping.Wrap,
                            FontSize = 14
                        },
                        new Avalonia.Controls.Button 
                        { 
                            Content = "OK",
                            HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Center,
                            Width = 100,
                            Height = 35
                        }
                    }
                }
            };
            
            var button = (Avalonia.Controls.Button)((Avalonia.Controls.StackPanel)msgBox.Content).Children[1];
            button.Click += (s, e) => msgBox.Close();
            
            await msgBox.ShowDialog(DesignerWindow.mainWindow);
        }).Wait();
    }

    public void ErrorDialog(string message)
    {
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
        {
            var msgBox = new Avalonia.Controls.Window
            {
                Title = "Error",
                Width = 400,
                Height = 200,
                WindowStartupLocation = Avalonia.Controls.WindowStartupLocation.CenterOwner,
                Content = new Avalonia.Controls.StackPanel
                {
                    Margin = new Avalonia.Thickness(20),
                    Spacing = 15,
                    Children =
                    {
                        new Avalonia.Controls.TextBlock 
                        { 
                            Text = message, 
                            TextWrapping = Avalonia.Media.TextWrapping.Wrap,
                            FontSize = 14
                        },
                        new Avalonia.Controls.Button 
                        { 
                            Content = "OK",
                            HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Center,
                            Width = 100,
                            Height = 35
                        }
                    }
                }
            };
            
            var button = (Avalonia.Controls.Button)((Avalonia.Controls.StackPanel)msgBox.Content).Children[1];
            button.Click += (s, e) => msgBox.Close();
            
            await msgBox.ShowDialog(DesignerWindow.mainWindow);
        }).Wait();
    }

    public bool ConfirmDialog(string message)
    {
        var tcs = new System.Threading.Tasks.TaskCompletionSource<bool>();
        
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
        {
            var result = false;
            var msgBox = new Avalonia.Controls.Window
            {
                Title = "Confirm",
                Width = 400,
                Height = 200,
                WindowStartupLocation = Avalonia.Controls.WindowStartupLocation.CenterOwner,
                Content = new Avalonia.Controls.StackPanel
                {
                    Margin = new Avalonia.Thickness(20),
                    Spacing = 15,
                    Children =
                    {
                        new Avalonia.Controls.TextBlock 
                        { 
                            Text = message, 
                            TextWrapping = Avalonia.Media.TextWrapping.Wrap,
                            FontSize = 14
                        },
                        new Avalonia.Controls.StackPanel
                        {
                            Orientation = Avalonia.Layout.Orientation.Horizontal,
                            HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Center,
                            Spacing = 15,
                            Children =
                            {
                                new Avalonia.Controls.Button { Content = "Yes", Width = 100, Height = 35 },
                                new Avalonia.Controls.Button { Content = "No", Width = 100, Height = 35 }
                            }
                        }
                    }
                }
            };
            
            var buttons = (Avalonia.Controls.StackPanel)((Avalonia.Controls.StackPanel)msgBox.Content).Children[1];
            ((Avalonia.Controls.Button)buttons.Children[0]).Click += (s, e) => { result = true; msgBox.Close(); };
            ((Avalonia.Controls.Button)buttons.Children[1]).Click += (s, e) => { msgBox.Close(); };
            
            await msgBox.ShowDialog(DesignerWindow.mainWindow);
            tcs.SetResult(result);
        });
        
        return tcs.Task.Result;
    }

    public string InputDialog(string prompt, string defaultValue)
    {
        var tcs = new System.Threading.Tasks.TaskCompletionSource<string>();
        
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
        {
            var textBox = new Avalonia.Controls.TextBox 
            { 
                Text = defaultValue,
                Width = 350,
                Margin = new Avalonia.Thickness(0, 10, 0, 10)
            };
            
            var inputValue = "";
            var msgBox = new Avalonia.Controls.Window
            {
                Title = "Input",
                Width = 450,
                Height = 200,
                WindowStartupLocation = Avalonia.Controls.WindowStartupLocation.CenterOwner,
                Content = new Avalonia.Controls.StackPanel
                {
                    Margin = new Avalonia.Thickness(20),
                    Spacing = 15,
                    Children =
                    {
                        new Avalonia.Controls.TextBlock 
                        { 
                            Text = prompt,
                            FontSize = 14
                        },
                        textBox,
                        new Avalonia.Controls.StackPanel
                        {
                            Orientation = Avalonia.Layout.Orientation.Horizontal,
                            HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Center,
                            Spacing = 15,
                            Children =
                            {
                                new Avalonia.Controls.Button { Content = "OK", Width = 100, Height = 35 },
                                new Avalonia.Controls.Button { Content = "Cancel", Width = 100, Height = 35 }
                            }
                        }
                    }
                }
            };
            
            var buttons = (Avalonia.Controls.StackPanel)((Avalonia.Controls.StackPanel)msgBox.Content).Children[2];
            ((Avalonia.Controls.Button)buttons.Children[0]).Click += (s, e) => { inputValue = textBox.Text ?? ""; msgBox.Close(); };
            ((Avalonia.Controls.Button)buttons.Children[1]).Click += (s, e) => { msgBox.Close(); };
            
            await msgBox.ShowDialog(DesignerWindow.mainWindow);
            tcs.SetResult(inputValue);
        });
        
        return tcs.Task.Result;
    }

    public LuaTable SqlQuery(string sql)
    {
        try
        {
            // Create table using Lua code
            _lua.DoString("_sqlResults = {}");
            var results = _lua["_sqlResults"] as LuaTable;
            
            using var conn = new SqliteConnection($"Data Source={PropertyStore.GetDbPath()}");
            conn.Open();
            var cmd = conn.CreateCommand();
            cmd.CommandText = sql;
            
            using var reader = cmd.ExecuteReader();
            int rowIndex = 1;
            
            while (reader.Read())
            {
                _lua.DoString($"_sqlResults[{rowIndex}] = {{}}");
                var row = _lua[$"_sqlResults[{rowIndex}]"] as LuaTable;
                
                for (int i = 0; i < reader.FieldCount; i++)
                {
                    var colName = reader.GetName(i);
                    var value = reader.GetValue(i);
                    if (row != null)
                        row[colName] = value == DBNull.Value ? null : value;
                }
                
                rowIndex++;
            }
            
            return results;
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[LUA] SQL Query Error: {ex.Message}");
            _lua.DoString("return {}");
            return _lua["_sqlResults"] as LuaTable;
        }
    }

    public int SqlExecute(string sql)
    {
        try
        {
            using var conn = new SqliteConnection($"Data Source={PropertyStore.GetDbPath()}");
            conn.Open();
            var cmd = conn.CreateCommand();
            cmd.CommandText = sql;
            return cmd.ExecuteNonQuery();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[LUA] SQL Execute Error: {ex.Message}");
            return -1;
        }
    }
    
    // ===== PROPERTY FUNCTIONS =====

    public string GetProperty(string controlName, string propertyName)
    {
        return Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            // Try to get runtime value from actual control first
            var control = FindControlInWindow(controlName);
            if (control != null)
            {
                try
                {
                    if (propertyName == "Text" && control is TextBox tb)
                        return tb.Text ?? "";
                    if (propertyName == "SelectedItem" && control is ComboBox cb)
                        return cb.SelectedItem?.ToString() ?? "";
                    if (propertyName == "SelectedIndex" && control is ComboBox cb2)
                        return cb2.SelectedIndex.ToString();
                    if (propertyName == "IsChecked" && control is CheckBox chk)
                        return chk.IsChecked?.ToString() ?? "false";
                }
                catch { }
            }
            
            // Fall back to PropertyStore for design-time properties
            return PropertyStore.Get(controlName, propertyName) ?? "";
        }).Result;
    }
    
    private Control? FindControlInWindow(string name)
    {
        var lifetime = Avalonia.Application.Current?.ApplicationLifetime as Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime;
        if (lifetime != null)
            foreach (var window in lifetime.Windows)
            {
                var found = FindControlRecursive(window, name);
                if (found != null) return found;
            }
        return null;
    }
    
    private Control? FindControlRecursive(Control parent, string name)
    {
        Console.WriteLine($"[FIND] Checking {parent.GetType().Name} '{parent.Name}'");
        if (parent.Name == name) return parent;
        
        if (parent is Window w)
        {
            if (w.Content is Control wContent)
                if (FindControlRecursive(wContent, name) is Control found)
                    return found;
        }
        
        if (parent is Panel panel)
            foreach (var child in panel.Children)
                if (FindControlRecursive(child, name) is Control found2)
                    return found2;
        
        if (parent is ContentControl cc && cc.Content is Control content)
            return FindControlRecursive(content, name);
            
        if (parent is Decorator dec && dec.Child is Control decChild)
            return FindControlRecursive(decChild, name);
            
        return null;
    }
    
    public void SetProperty(string controlName, string propertyName, string value)
    {
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(controlName);
            Console.WriteLine($"[SETPROP] Setting {controlName}.{propertyName} = {value}, found: {control?.GetType().Name ?? "null"}");
            
            if (control != null)
            {
                try
                {
                    if (propertyName == "Text" && control is TextBox tb)
                        tb.Text = value;
                    else if (propertyName == "Text" && control is TextBlock tbl)
                        tbl.Text = value;
                    else if (propertyName == "Content" && control is Button btn)
                        btn.Content = value;
                    else if (propertyName == "IsChecked" && control is CheckBox chk)
                        chk.IsChecked = bool.Parse(value);
                    else if (propertyName == "SelectedIndex" && control is ComboBox cb)
                        cb.SelectedIndex = int.Parse(value);
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[SETPROP] Error: {ex.Message}");
                }
            }
        }).Wait();
    }

    // ===== CANVAS/FORM FUNCTIONS =====
    
    public void ReloadCanvas()
    {
        DesignerWindow.RefreshCanvas();
    }
    
    public void FormOpen(string vmlPath)
    {
        FormLoader.Open(vmlPath, false);
    }
    
    public void FormOpenModal(string vmlPath)
    {
        Console.WriteLine($"[VML] FormOpenModal: {vmlPath}");

        // Marshal to UI thread
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            FormLoader.Open(vmlPath, modal: true);
        });
    }
    
    public void AppExit()
    {
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            if (Avalonia.Application.Current?.ApplicationLifetime 
                is Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime desktop)
            {
                desktop.Shutdown();
            }
        });
    }
    
    // ===== SHELL FUNCTION =====
    
    public string Shell(string command)
    {
        try
        {
            var process = new System.Diagnostics.Process
            {
                StartInfo = new System.Diagnostics.ProcessStartInfo
                {
                    FileName = "/bin/bash",
                    Arguments = $"-c \"{command}\"",
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false
                }
            };
            
            process.Start();
            var output = process.StandardOutput.ReadToEnd();
            process.WaitForExit();
            
            return output;
        }
        catch (Exception ex)
        {
            return $"Error: {ex.Message}";
        }
    }

    public object? Vml(string command, params object[] args)
    {
        try
        {
            switch (command)
            {
                // Dialogs
                case "FileOpenDialog":
                    return FileOpenDialog(args[0].ToString()!, args.Length > 1 ? args[1].ToString()! : "");
                case "FileSaveDialog":
                    return FileSaveDialog(args[0].ToString()!, args[1].ToString()!, args.Length > 2 ? args[2].ToString()! : "");
                case "FolderSelectDialog":
                    return FolderSelectDialog(args[0].ToString()!);
                case "InfoDialog":
                    InfoDialog(args[0].ToString()!);
                    return null;
                case "ErrorDialog":
                    ErrorDialog(args[0].ToString()!);
                    return null;
                case "ConfirmDialog":
                    return ConfirmDialog(args[0].ToString()!);
                case "InputDialog":
                    return InputDialog(args[0].ToString()!, args.Length > 1 ? args[1].ToString()! : "");

                // Database
                case "SqlQuery":
                    return SqlQuery(args[0].ToString()!);
                case "SqlExecute":
                    return SqlExecute(args[0].ToString()!);

                // Properties
                case "GetProperty":
                    return GetProperty(args[0].ToString()!, args[1].ToString()!);
                case "GetSelectedControlName":
                    return DesignerWindow.GetSelectedControl()?.Name ?? "";
                case "SetMenuItemText":
                    TinyMenu.SetMenuItemText(args[0].ToString()!, args[1].ToString()!);
                    return null;
                case "SetMenuItemEnabled":
                    TinyMenu.SetMenuItemEnabled(args[0].ToString()!, bool.Parse(args[1].ToString()!));
                    return null;
                // Dynamic Control Commands
                case "CreateControl":
                    return CreateDynamicControl(args[0].ToString()!, args[1].ToString()!, args.Length > 2 ? args[2].ToString()! : null);
                case "DeleteControl":
                    DeleteDynamicControl(args[0].ToString()!);
                    return null;
                case "SetControlPosition":
                    SetControlPosition(args[0].ToString()!, Convert.ToDouble(args[1]), Convert.ToDouble(args[2]));
                    return null;
                case "SetControlSize":
                    SetControlSize(args[0].ToString()!, Convert.ToDouble(args[1]), Convert.ToDouble(args[2]));
                    return null;
                case "GetControlChildren":
                    return GetControlChildren(args[0].ToString()!);
                case "GetControlParent":
                    return GetControlParent(args[0].ToString()!);
                case "SetProperty":
                    SetProperty(args[0].ToString()!, args[1].ToString()!, args[2].ToString()!);
                    return null;
                // Settings
                case "SelectControl":
                    SelectControlByName(args[0].ToString()!);
                    return null;
                case "GetControlX":
                    return GetControlX(args[0].ToString()!);
                case "GetResizeZone":
                    return GetResizeZone(args[0].ToString()!, Convert.ToDouble(args[1]), Convert.ToDouble(args[2]));
                case "GetControlWidth":
                    return GetControlWidth(args[0].ToString()!);
                case "GetControlHeight":
                case "ClearChildren":
                    ClearChildren(args[0].ToString()!);
                    return null;
                case "GetControlType":
                    return GetControlType(args[0].ToString()!);
                case "SetControlVisible":
                case "RunScript":
                    RunScript(args[0].ToString()!);
                    return null;
                case "GetPropertyGroups":
                    return GetPropertyGroups();
                case "GetGroupProperties":
                    return GetGroupProperties(Convert.ToInt32(args[0]), args.Length > 1 ? args[1].ToString()! : "*");
                    SetControlVisible(args[0].ToString()!, bool.Parse(args[1].ToString()!));
                    return null;
                    return GetControlHeight(args[0].ToString()!);
                case "GetControlY":
                    return GetControlY(args[0].ToString()!);
                case "UpdateSelectionBorder":
                    UpdateSelectionBorder();
                    return null;
                case "GetControlAt":
                    return GetControlAt(Convert.ToDouble(args[0]), Convert.ToDouble(args[1]));
                case "GetSetting":
                    return Settings.Get(args[0].ToString()!);
                case "SetSetting":
                    Settings.Set(args[0].ToString()!, args[1].ToString()!);
                    return null;

                // Forms
                case "FormOpen":
                    FormOpen(args[0].ToString()!);
                    return null;
                case "FormOpenModal":
                    FormOpenModal(args[0].ToString()!);
                    return null;
                case "ReloadCanvas":
                    ReloadCanvas();
                    return null;

                // System
                case "AppExit":
                    AppExit();
                    return null;
                case "Shell":
                    return Shell(args[0].ToString()!);
                case "ExecuteScript":
                    ScriptHandler.Execute(args[0].ToString()!, args[1].ToString()!);
                    return null;

                default:
                    Console.WriteLine($"[VML] Unknown command: {command}");
                    return null;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[VML] Error executing {command}: {ex.Message}");
            return null;
        }
    }

    // ========================================
    // DYNAMIC CONTROL METHODS
    // ========================================
    
    
    private void SelectControlByName(string name)
    {
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            if (control != null)
            {
                DesignerWindow.SelectControl(control);
                Vml("RunScript", "RefreshProperties");
                Console.WriteLine($"[VMLENGINE] Selected: {name}");
            }
        }).Wait();
    }


    private string? GetResizeZone(string name, double localX, double localY)
    {
        return Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            if (control == null) return null;
            const double edgeSize = 8;
            var w = control.Bounds.Width;
            var h = control.Bounds.Height;
            bool onLeft = localX <= edgeSize;
            bool onRight = localX >= w - edgeSize;
            bool onTop = localY <= edgeSize;
            bool onBottom = localY >= h - edgeSize;
            if (onTop && onLeft) return "NW";
            if (onTop && onRight) return "NE";
            if (onBottom && onLeft) return "SW";
            if (onBottom && onRight) return "SE";
            if (onTop) return "N";
            if (onBottom) return "S";
            if (onLeft) return "W";
            if (onRight) return "E";
            return null;
        }).Result;
    }

    private double GetControlWidth(string name)
    {
        return Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            return control?.Bounds.Width ?? 0;
        }).Result;
    }

    private double GetControlHeight(string name)
    {
        return Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            return control?.Bounds.Height ?? 0;
        }).Result;
    }

    private void ClearChildren(string name)
    {
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            if (control is Panel panel)
                panel.Children.Clear();
        }).Wait();
    }

    private string GetControlType(string name)
    {
        return Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            if (control == null) return "";
            var typeName = control.GetType().Name;
            if (typeName.StartsWith("Design"))
                return typeName.Substring(6);
            return typeName;
        }).Result;
    }

    private void SetControlVisible(string name, bool visible)
    {
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            if (control != null)
                control.IsVisible = visible;
        }).Wait();
    }

    private void RunScript(string scriptName)
    {
        var script = ScriptRegistry.Get(scriptName);
        if (script != null)
            ScriptHandler.Execute(script.Content, script.Interpreter);
    }

    private string GetPropertyGroups()
    {
        var dbPath = PropertyStore.GetDbPath();
        using var conn = new Microsoft.Data.Sqlite.SqliteConnection($"Data Source={dbPath}");
        conn.Open();
        var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT id, name, display_name, icon, is_expanded FROM property_groups ORDER BY display_order";
        var results = new System.Collections.Generic.List<string>();
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
            results.Add($"{reader.GetInt32(0)}|{reader.GetString(1)}|{reader.GetString(2)}|{reader.GetString(3)}|{reader.GetInt32(4)}");
        return string.Join("\n", results);
    }

    private string GetGroupProperties(int groupId, string controlType)
    {
        var dbPath = PropertyStore.GetDbPath();
        using var conn = new Microsoft.Data.Sqlite.SqliteConnection($"Data Source={dbPath}");
        conn.Open();
        var cmd = conn.CreateCommand();
        cmd.CommandText = @"SELECT property_name, display_name, editor_type, options 
            FROM control_properties 
            WHERE group_id = @gid AND (applies_to = * OR applies_to LIKE % || @ctype || %) 
            ORDER BY display_order";
        cmd.Parameters.AddWithValue("@gid", groupId);
        cmd.Parameters.AddWithValue("@ctype", controlType);
        var results = new System.Collections.Generic.List<string>();
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            var opts = reader.IsDBNull(3) ? "" : reader.GetString(3);
            results.Add($"{reader.GetString(0)}|{reader.GetString(1)}|{reader.GetString(2)}|{opts}");
        }
        return string.Join("\n", results);
    }

    private double GetControlX(string name)
    {
        return Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            return control != null ? Canvas.GetLeft(control) : 0;
        }).Result;
    }

    private double GetControlY(string name)
    {
        return Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            return control != null ? Canvas.GetTop(control) : 0;
        }).Result;
    }

    private void UpdateSelectionBorder()
    {
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            DesignerWindow.UpdateSelectionBorder();
        }).Wait();
    }


    private string? GetControlAt(double x, double y)
    {
        return Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var canvas = FindControlInWindow("DesignCanvas") as Canvas;
            if (canvas == null) return null;
            
            foreach (var child in canvas.Children.OfType<Control>().Reverse())
            {
                if (child.Name == "SelectionBorder" || child.Name == "DesignOverlay") continue;
                var left = Canvas.GetLeft(child);
                var top = Canvas.GetTop(child);
                var bounds = new Avalonia.Rect(left, top, child.Bounds.Width, child.Bounds.Height);
                if (bounds.Contains(new Avalonia.Point(x, y)))
                    return child.Name;
            }
            return null;
        }).Result;
    }


    private string CreateDynamicControl(string controlType, string name, string? parentName)
    {
        return Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            // Auto-generate name if not provided
            if (string.IsNullOrEmpty(name))
            {
                if (!DesignerWindow.controlCounters.ContainsKey(controlType))
                    DesignerWindow.controlCounters[controlType] = 0;
                DesignerWindow.controlCounters[controlType]++;
                name = $"{controlType}_{DesignerWindow.controlCounters[controlType]}";
            }
            var (dummy, real) = DesignerWindow.CreateControlPair(controlType, name);
            if (dummy == null || real == null)
            {
                Console.WriteLine($"[VMLENGINE] Failed to create {controlType}");
                return "";
            }
            
            if (parentName != null)
            {
                var parent = FindControlInWindow(parentName);
                if (parent is Canvas canvas)
                {
                    Canvas.SetLeft(dummy, 10);
                    Canvas.SetTop(dummy, 10);
                    Canvas.SetLeft(real, 10);
                    Canvas.SetTop(real, 10);
                    canvas.Children.Add(dummy);
                    canvas.Children.Add(real);
                }
                else if (parent is Panel panel)
                {
                    panel.Children.Add(dummy);
                    panel.Children.Add(real);
                }
            }
            Console.WriteLine($"[VMLENGINE] Created {controlType} '{name}' in {parentName ?? "orphan"}");
            return name;
        }).Result;
    }
    
    private void DeleteDynamicControl(string name)
    {
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            if (control?.Parent is Panel panel)
            {
                panel.Children.Remove(control);
                Console.WriteLine($"[VMLENGINE] Deleted '{name}'");
            }
        }).Wait();
    }
    
    private void SetControlPosition(string name, double x, double y)
    {
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            if (control != null)
            {
                Canvas.SetLeft(control, x);
                Canvas.SetTop(control, y);
            }
        }).Wait();
    }
    
    private void SetControlSize(string name, double width, double height)
    {
        Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            if (control != null)
            {
                control.Width = width;
                control.Height = height;
            }
        }).Wait();
    }
    
    private string[] GetControlChildren(string name)
    {
        return Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            if (control is Panel panel)
                return panel.Children.Select(c => c.Name ?? "unnamed").ToArray();
            return Array.Empty<string>();
        }).Result;
    }
    
    private string? GetControlParent(string name)
    {
        return Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
        {
            var control = FindControlInWindow(name);
            return (control?.Parent as Control)?.Name;
        }).Result;
    }
//
}

/// <summary>
/// Globals available to C# scripts - provides VML API
/// </summary>
public class VmlScriptGlobals
{
    private readonly VmlEngine _engine;
    public string[] Args { get; set; } = Array.Empty<string>();
    
    public VmlScriptGlobals()
    {
        _engine = new VmlEngine();
    }
    
    /// <summary>
    /// VML universal dispatcher - same API as Lua
    /// Usage: Vml("InfoDialog", "Hello from C#!")
    /// </summary>
    public object? Vml(string command, params object[] args)
    {
        return _engine.Vml(command, args);
    }
}

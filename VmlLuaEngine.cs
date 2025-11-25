using System;
using System.Collections.Generic;
using System.Linq;
using NLua;
using Microsoft.Data.Sqlite;
using Avalonia.Controls;

namespace VB;

public class VmlLuaEngine
{
    private Lua _lua;
    
    public VmlLuaEngine()
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
        // Try to get runtime value from actual control first
        var control = FindControlInWindow(controlName);
        Console.WriteLine($"[GETPROP] Looking for {controlName}.{propertyName}, found: {control?.GetType().Name ?? "null"}");
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
    }
    
    private Control? FindControlInWindow(string name)
    {
        var lifetime = Avalonia.Application.Current?.ApplicationLifetime as Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime;
        Console.WriteLine($"[FINDCTRL] Searching for {name}, windows: {lifetime?.Windows.Count ?? 0}");
        if (Avalonia.Application.Current.ApplicationLifetime is Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime desktop)
        foreach (var window in desktop.Windows)
        {
            var found = FindControlRecursive(window, name);
            if (found != null) return found;
        }
        return null;
    }
    
    private Control? FindControlRecursive(Control parent, string name)
    {
        Console.WriteLine($"[FINDCTRL] Checking {parent.GetType().Name} {parent.Name ?? "unnamed"}");
        if (parent.Name == name) return parent;
        
        if (parent is Panel panel)
            foreach (var child in panel.Children)
                if (FindControlRecursive(child, name) is Control found)
                    return found;
        if (parent is Window w)
            Console.WriteLine($"[FINDCTRL] Window content: {w.Content?.GetType().Name ?? "null"}");
        else if (parent is ContentControl cc && cc.Content is Control content)
            return FindControlRecursive(content, name);
        else if (parent is Decorator dec && dec.Child is Control decChild)
            return FindControlRecursive(decChild, name);
            
        return null;
    }
    
    public void SetProperty(string controlName, string propertyName, string value)
    {
        PropertyStore.Set(controlName, propertyName, value);
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
        Console.WriteLine($"[VML] {command}({string.Join(", ", args.Select(a => a?.ToString() ?? "null"))})");

            Console.WriteLine($"[VML] *** CALLED *** command={command}, args={args?.Length ?? 0}");

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
                case "SetProperty":
                    SetProperty(args[0].ToString()!, args[1].ToString()!, args[2].ToString()!);
                    return null;
                // Settings
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
}

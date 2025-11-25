using Avalonia.Media;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using Wasmtime;
using Microsoft.CodeAnalysis.CSharp.Scripting;
using Microsoft.CodeAnalysis.Scripting;
using Microsoft.Data.Sqlite;

namespace VB;

public static class ScriptHandler
{
    private static readonly Dictionary<string, string> InterpreterCommands = new()
    {
        { "bash", "/bin/bash" },
        { "python", "/usr/bin/python3" },
        { "node", "/usr/bin/node" },
        { "ruby", "/usr/bin/ruby" },
        { "perl", "/usr/bin/perl" },
        { "powershell", "pwsh" }
    };

    // Named interpreter instances for state persistence
    private static readonly Dictionary<string, VmlLuaEngine> LuaInstances = new();
    private static readonly Dictionary<string, Microsoft.CodeAnalysis.Scripting.ScriptState<object>> CSharpInstances = new();
    private static readonly Dictionary<string, Wasmtime.Engine> WasmEngines = new();
    
    private static string? _tempDbPath;
    
    /// <summary>
    /// Initialize temporary session database for scripts
    /// </summary>
    public static void InitializeTempDatabase()
    {
        _tempDbPath = ":memory:";  // 100x faster!
        
        // Create empty database
        using var conn = new SqliteConnection($"Data Source={_tempDbPath}");
        conn.Open();
        
        Console.WriteLine($"[SCRIPT] Temp database: {_tempDbPath}");
    }
    
    /// <summary>
    /// Clean up temporary database on exit
    /// </summary>
    public static void CleanupTempDatabase()
    {
        if (_tempDbPath != null && File.Exists(_tempDbPath))
        {
            try
            {
                File.Delete(_tempDbPath);
                Console.WriteLine($"[SCRIPT] Cleaned up temp database");
            }
            catch { }
        }
    }
    
    public static void Execute(string scriptCode, string interpreter, Dictionary<string, string>? args = null)
    {
        var cleanInterp = interpreter.Split(' ')[0].ToLower();

        // Lua interpreter - run on background thread to avoid UI deadlock
        if (cleanInterp == "lua")
        {
            System.Threading.Tasks.Task.Run(() =>
            {
                try
                {
                    var instanceName = interpreter.Contains(" ") ? interpreter.Split(" ")[1] : "";
                    Console.WriteLine($"[LUA] Instance check: interpreter='{interpreter}', instanceName='{instanceName}', exists={LuaInstances.ContainsKey(instanceName)}");
                    VmlLuaEngine engine;
                    if (string.IsNullOrEmpty(instanceName))
                        engine = new VmlLuaEngine();
                    else if (!LuaInstances.TryGetValue(instanceName, out engine!))
                        LuaInstances[instanceName] = engine = new VmlLuaEngine();
                    engine.Execute(scriptCode);
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[LUA] Script error: {ex.Message}");
                }
            });
            return;
        }
        // C# interpreter - Roslyn scripting
        if (cleanInterp == "csharp" || cleanInterp == "cs")
        {
            System.Threading.Tasks.Task.Run(async () =>
            {
                try
                {
                    var instanceName = interpreter.Contains(" ") ? interpreter.Split(" ")[1] : "";
                    Console.WriteLine($"[CSHARP] Instance check: interpreter='{interpreter}', instanceName='{instanceName}', exists={CSharpInstances.ContainsKey(instanceName)}");
                    
                    var globals = new VmlScriptGlobals();
                    var options = ScriptOptions.Default
                        .WithReferences(typeof(VmlLuaEngine).Assembly)
                        .WithImports("System", "VB");
                    
                    if (string.IsNullOrEmpty(instanceName))
                    {
                        await CSharpScript.RunAsync(scriptCode, options, globals);
                    }
                    else if (CSharpInstances.TryGetValue(instanceName, out var state))
                    {
                        CSharpInstances[instanceName] = await state.ContinueWithAsync(scriptCode, options);
                    }
                    else
                    {
                        CSharpInstances[instanceName] = await CSharpScript.RunAsync(scriptCode, options, globals);
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[CSHARP] Script error: {ex.Message}");
                }
            });
            return;
        }

        // WebAssembly interpreter
        if (cleanInterp == "wasm" || cleanInterp == "wat")
        {
            System.Threading.Tasks.Task.Run(() =>
            {
                try
                {
                    var instanceName = interpreter.Contains(" ") ? interpreter.Split(" ")[1] : "";
                    Console.WriteLine($"[WASM] Instance check: interpreter='{interpreter}', instanceName='{instanceName}', exists={WasmEngines.ContainsKey(instanceName)}");

                    // Get or create engine
                    Wasmtime.Engine engine;
                    if (string.IsNullOrEmpty(instanceName))
                        engine = new Wasmtime.Engine();
                    else if (!WasmEngines.TryGetValue(instanceName, out engine!))
                        WasmEngines[instanceName] = engine = new Wasmtime.Engine();

                    // Compile module
                    var module = Wasmtime.Module.FromText(engine, "temp", scriptCode);

                    // Create linker and store
                    var linker = new Wasmtime.Linker(engine);
                    var store = new Wasmtime.Store(engine);

                    // Instantiate and invoke
                    var instance = linker.Instantiate(store, module);
                    var mainFunc = instance.GetFunction("_start") ?? instance.GetFunction("main");
                    
                    if (mainFunc != null)
                    {
                        mainFunc.Invoke();
                        Console.WriteLine("[WASM] Execution complete");
                    }
                    else
                    {
                        Console.WriteLine("[WASM] No _start or main function found");
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[WASM] Error: {ex.Message}");
                }
            });
            return;
        }

        if (cleanInterp == "vml")
        {
            ExecuteVmlCommands(scriptCode);
            return;
        }
        
        if (!InterpreterCommands.TryGetValue(cleanInterp, out var interpreterPath))
        {
            Console.WriteLine($"[SCRIPT] Unknown interpreter: {interpreter}");
            return;
        }
        
        // Create temp script file
        var tempScript = Path.GetTempFileName();
        File.WriteAllText(tempScript, scriptCode);
        
        try
        {
            var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = interpreterPath,
                    Arguments = $"\"{tempScript}\"",
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false
                }
            };
            
            // Set environment variables for ALL scripts
            var env = process.StartInfo.Environment;
            
            // Core system paths - available to all scripts
            env["VML_DB_PATH"] = PropertyStore.GetDbPath();
            env["VML_DIR"] = Settings.Get("vml_dir", "./vml");
            env["VML_APP_DIR"] = AppDomain.CurrentDomain.BaseDirectory;
            env["VML_PARSER"] = Settings.Get("vml_parser", "vml-parse");
            env["VML_TEMP_DB"] = _tempDbPath ?? "";
            
            // Add custom args if provided
            if (args != null)
            {
                foreach (var kvp in args)
                    env[$"VML_{kvp.Key.ToUpper()}"] = kvp.Value;
            }
            
            Console.WriteLine($"[SCRIPT] Executing with {cleanInterp}...");
            
            process.Start();
            var output = process.StandardOutput.ReadToEnd();
            var error = process.StandardError.ReadToEnd();
            process.WaitForExit();
            
            if (!string.IsNullOrEmpty(output))
            {
                Console.WriteLine($"[SCRIPT OUTPUT]");
                Console.WriteLine(output.TrimEnd());
            }
            
            if (!string.IsNullOrEmpty(error))
            {
                Console.WriteLine($"[SCRIPT ERROR]");
                Console.WriteLine(error.TrimEnd());
            }
            
            Console.WriteLine($"[SCRIPT] Exit code: {process.ExitCode}");
        }
        finally
        {
            File.Delete(tempScript);
        }
    }
    
    public static void ExecuteVmlCommands(string commands)
    {
        var lines = commands.Split('\n', StringSplitOptions.RemoveEmptyEntries);
        
        foreach (var line in lines)
        {
            var trimmed = line.Trim();
            if (trimmed.StartsWith("#") || string.IsNullOrEmpty(trimmed)) continue;
            
            var parts = trimmed.Split(' ', 2);
            var command = parts[0];
            var args = parts.Length > 1 ? parts[1] : "";
            
            switch (command)
            {
                // ===== FORM COMMANDS =====
                case "FormOpen":
                case "FormOpenModal":
                    var modal = command == "FormOpenModal";
                    Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
                    {
                        FormLoader.Open(args.Trim(), modal);
                    });
                    break;
                
                // ===== DIALOG COMMANDS (BLOCKING - Results in VML_TEMP_DB) =====
                case "FileOpenDialog":
                    // FileOpenDialog title|filter
                    {
                        var dialogArgs = args.Split('|');
                        var title = dialogArgs.Length > 0 ? dialogArgs[0] : "Open File";
                        var filter = dialogArgs.Length > 1 ? dialogArgs[1] : "*";
                        
                        var dialogTask = Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
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
                            
                            var result = await dialog.ShowAsync(DesignerWindow.mainWindow);
                            return result?.Length > 0 ? result[0] : "";
                        });
                        
                        var selectedFile = dialogTask.Result;
                        StoreDialogResult("last_result", selectedFile);
                        Console.WriteLine($"VML_DIALOG_RESULT={selectedFile}");
                    }
                    break;
                
                case "FileSaveDialog":
                    // FileSaveDialog title|defaultname|filter
                    {
                        var dialogArgs = args.Split('|');
                        var title = dialogArgs.Length > 0 ? dialogArgs[0] : "Save File";
                        var defaultName = dialogArgs.Length > 1 ? dialogArgs[1] : "untitled";
                        var filter = dialogArgs.Length > 2 ? dialogArgs[2] : "*";
                        
                        var dialogTask = Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
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
                            return result ?? "";
                        });
                        
                        var selectedFile = dialogTask.Result;
                        StoreDialogResult("last_result", selectedFile);
                        Console.WriteLine($"VML_DIALOG_RESULT={selectedFile}");
                    }
                    break;
                
                case "FolderSelectDialog":
                    // FolderSelectDialog title
                    {
                        var title = string.IsNullOrEmpty(args) ? "Select Folder" : args;
                        
                        var dialogTask = Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
                        {
                            var dialog = new Avalonia.Controls.OpenFolderDialog
                            {
                                Title = title
                            };
                            
                            var result = await dialog.ShowAsync(DesignerWindow.mainWindow);
                            return result ?? "";
                        });
                        
                        var selectedFolder = dialogTask.Result;
                        StoreDialogResult("last_result", selectedFolder);
                        Console.WriteLine($"VML_DIALOG_RESULT={selectedFolder}");
                    }
                    break;
                
                case "InfoDialog":
                    // InfoDialog message - fire and forget, don't block
                    Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
                    {
                        var msgBox = new Avalonia.Controls.Window
                        {
                            Title = "Information",
                            Width = 400,
                            Height = 200,
                            CanResize = false,
                            WindowStartupLocation = Avalonia.Controls.WindowStartupLocation.CenterOwner,
                            Background = Brushes.White,
                            Content = new Avalonia.Controls.StackPanel
                            {
                                Margin = new Avalonia.Thickness(20),
                                Spacing = 15,
                                Children =
                                {
                                    new Avalonia.Controls.TextBlock
                                    {
                                        Text = args,
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

                        if (DesignerWindow.mainWindow != null)
                            await msgBox.ShowDialog(DesignerWindow.mainWindow);
                        else
                            msgBox.Show();
                    });
                    break;

                case "ErrorDialog":
                    // ErrorDialog message - fire and forget, don't block
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
                                        Text = args, 
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
                    });
                    // NO .Wait() - just continue
                    break; 

                case "ConfirmDialog":
                    // ConfirmDialog message - returns true/false
                    {
                        var dialogTask = Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
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
                                            Text = args, 
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
                            return result;
                        });
                        
                        var confirmed = dialogTask.Result;
                        StoreDialogResult("last_result", confirmed.ToString().ToLower());
                        Console.WriteLine($"VML_DIALOG_RESULT={confirmed.ToString().ToLower()}");
                    }
                    break;
                
                case "InputDialog":
                    // InputDialog prompt|defaultvalue
                    {
                        var dialogArgs = args.Split('|');
                        var prompt = dialogArgs.Length > 0 ? dialogArgs[0] : "Enter value:";
                        var defaultValue = dialogArgs.Length > 1 ? dialogArgs[1] : "";
                        
                        var dialogTask = Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
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
                            return inputValue;
                        });
                        
                        var userInput = dialogTask.Result;
                        StoreDialogResult("last_result", userInput);
                        Console.WriteLine($"VML_DIALOG_RESULT={userInput}");
                    }
                    break;
                
                // ===== DATABASE COMMANDS =====
                case "SqlExecute":
                    // SqlExecute SQL statement
                    try
                    {
                        using var conn = new SqliteConnection($"Data Source={PropertyStore.GetDbPath()}");
                        conn.Open();
                        var cmd = conn.CreateCommand();
                        cmd.CommandText = args;
                        int affected = cmd.ExecuteNonQuery();
                        Console.WriteLine($"[VML] SQL affected {affected} rows");
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"[VML] SQL Error: {ex.Message}");
                    }
                    break;
                
                case "SqlQuery":
                    // SqlQuery SQL query
                    try
                    {
                        using var conn = new SqliteConnection($"Data Source={PropertyStore.GetDbPath()}");
                        conn.Open();
                        var cmd = conn.CreateCommand();
                        cmd.CommandText = args;
                        using var reader = cmd.ExecuteReader();
                        while (reader.Read())
                        {
                            var values = new List<string>();
                            for (int i = 0; i < reader.FieldCount; i++)
                                values.Add(reader.GetValue(i)?.ToString() ?? "");
                            Console.WriteLine(string.Join("|", values));
                        }
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"[VML] SQL Error: {ex.Message}");
                    }
                    break;
                
                // ===== CANVAS/CONTROL COMMANDS =====
                case "ReloadCanvas":
                    Console.WriteLine("[VML] Reloading canvas...");
                    DesignerWindow.RefreshCanvas();
                    break;
                
                case "GetProperty":
                    // GetProperty controlname propertyname
                    var getParts = args.Split(' ', 2);
                    if (getParts.Length == 2)
                    {
                        var value = PropertyStore.Get(getParts[0], getParts[1]);
                        Console.WriteLine(value);
                    }
                    break;
                
                case "SetProperty":
                    // SetProperty controlname propertyname value
                    var setParts = args.Split(' ', 3);
                    if (setParts.Length == 3)
                    {
                        PropertyStore.Set(setParts[0], setParts[1], setParts[2]);
                        Console.WriteLine($"[VML] Set {setParts[0]}.{setParts[1]} = {setParts[2]}");
                    }
                    break;
                
                // ===== APP COMMANDS =====
                case "AppExit":
                    Console.WriteLine("[VML] Exit command received");
                    Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(() =>
                    {
                        if (Avalonia.Application.Current?.ApplicationLifetime 
                            is Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime desktop)
                        {
                            desktop.Shutdown();
                        }
                    });
                    break;
                
                default:
                    Console.WriteLine($"[VML] Unknown command: {command}");
                    break;
            }
        }
    }

    /// <summary>
    /// Helper to store dialog results in temp database
    /// </summary>
    private static void StoreDialogResult(string key, string value)
    {
        if (string.IsNullOrEmpty(_tempDbPath)) return;
        
        try
        {
            using var conn = new SqliteConnection($"Data Source={_tempDbPath}");
            conn.Open();
            var cmd = conn.CreateCommand();
            cmd.CommandText = @"
                INSERT OR REPLACE INTO dialog_results (key, value, timestamp) 
                VALUES (@key, @value, @timestamp)";
            cmd.Parameters.AddWithValue("@key", key);
            cmd.Parameters.AddWithValue("@value", value);
            cmd.Parameters.AddWithValue("@timestamp", DateTimeOffset.UtcNow.ToUnixTimeSeconds());
            cmd.ExecuteNonQuery();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[VML] Error storing dialog result: {ex.Message}");
        }
    }

    public static void LoadScriptsFromDatabase(string sourceFile)
    {
        try 
        {
            var dbPath = PropertyStore.GetDbPath();
            using var conn = new SqliteConnection($"Data Source={dbPath}");
            conn.Open();
            
            var cmd = conn.CreateCommand();
            cmd.CommandText = @"
                SELECT ut.name, up.property_value
                FROM ui_tree ut
                JOIN ui_properties up ON ut.id = up.ui_tree_id
                WHERE ut.name LIKE '%Script%' 
                AND up.property_name = 'Content'
                AND ut.source_file LIKE @file";
            cmd.Parameters.AddWithValue("@file", $"%{sourceFile}%");
            
            using var reader = cmd.ExecuteReader();
            int count = 0;
            while (reader.Read())
            {
                var name = reader.GetString(0);
                var content = reader.GetString(1)
                    .Replace("<<EOF", "").Replace("EOF", "")
                    .Replace("<<LUA", "").Replace("LUA", "")
                    .Trim();
                
                Console.WriteLine($"[SCRIPT] Registering {name}");
                ScriptRegistry.Register(name, content, "lua");
                count++;
            }
            
            Console.WriteLine($"[SCRIPT] Loaded {count} scripts");
        }
        catch (Exception ex) 
        {
            Console.WriteLine($"[SCRIPT] Error: {ex.Message}");
        }
    }
}

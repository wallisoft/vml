using Avalonia;
using static VB.Settings;
using Avalonia.Controls;
using System;
using System.IO;
using System.Linq;


namespace VB;

class Program
{
    public static string[]? CommandLineArgs { get; private set; }
    
    [STAThread]
    public static void Main(string[] args)
    {
        CommandLineArgs = args;
        
        Console.WriteLine("🚀 Visualised v1.0");
        Console.WriteLine("═══════════════════════════════════");
        
        // Parse --db argument first
        string dbPath = null;
        var argsList = args.ToList();
        for (int i = 0; i < argsList.Count; i++) {
            if (argsList[i] == "--db" && i + 1 < argsList.Count) {
                dbPath = argsList[i + 1];
                Console.WriteLine($"Database: {dbPath}");
                Environment.SetEnvironmentVariable("VML_DB_PATH", dbPath);
                // Remove --db and path from args
                argsList.RemoveAt(i);
                argsList.RemoveAt(i);
                args = argsList.ToArray();
                break;
            }
        }
        
        // No args or --designer: Designer mode
        if (args.Length == 0 || args[0] == "--designer")
        {
            Console.WriteLine("Mode: Designer");
            Console.WriteLine("═══════════════════════════════════\n");
            BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
            return;
        }

        // --dialog-open: Show file open dialog
        if (args[0] == "--dialog-open")
        {
            var title = args.Length > 1 ? args[1] : "Open File";
            var filter = args.Length > 2 ? args[2] : "*";

            PropertyStore.Initialize();

            BuildAvaloniaApp().Start((Application app, string[] startArgs) =>
            {
                if (app.ApplicationLifetime is Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime desktop)
                {
                    // Create hidden window for dialog parent
                    var hiddenWindow = new Window
                    {
                        Width = 1,
                        Height = 1,
                        IsVisible = false,
                        ShowInTaskbar = false
                    };
                    desktop.MainWindow = hiddenWindow;
                    DesignerWindow.mainWindow = hiddenWindow;

                    // Show dialog and wait for result
                    var result = DialogHelper.ShowOpenDialog(title, filter).Result;
                    if (!string.IsNullOrEmpty(result))
                        Console.WriteLine(result);

                    System.Threading.Thread.Sleep(100);
                    desktop.Shutdown();
                }
            }, args);
            return;
        }

        // --dialog-save: Show file save dialog
        if (args[0] == "--dialog-save")
        {
            var title = args.Length > 1 ? args[1] : "Save File";
            var defaultName = args.Length > 2 ? args[2] : "untitled";
            var filter = args.Length > 3 ? args[3] : "*";

            PropertyStore.Initialize();

            BuildAvaloniaApp().Start((Application app, string[] startArgs) =>
            {
                if (app.ApplicationLifetime is Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime desktop)
                {
                    // Create hidden window for dialog parent
                    var hiddenWindow = new Window
                    {
                        Width = 1,
                        Height = 1,
                        IsVisible = false,
                        ShowInTaskbar = false
                    };
                    desktop.MainWindow = hiddenWindow;
                    DesignerWindow.mainWindow = hiddenWindow;

                    // Show dialog and wait for result
                    var result = DialogHelper.ShowSaveDialog(title, defaultName, filter).Result;
                    if (!string.IsNullOrEmpty(result))
                        Console.WriteLine(result);

                    System.Threading.Thread.Sleep(100);
                    desktop.Shutdown();
                }
            }, args);
            return;
        }
        
        // --vml-exec: Execute VML commands (for scripts)
        if (args[0] == "--vml-exec")
        {
            if (args.Length < 2)
            {
                Console.WriteLine("Usage: vml --vml-exec \"VML commands\"");
                return;
            }
            
            // Initialize main database (where dialog_results are stored)
            PropertyStore.Initialize();
            
            BuildAvaloniaApp().Start((Application app, string[] startArgs) =>
            {
                if (app.ApplicationLifetime is Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime desktop)
                {
                    // Create minimal hidden window for dialog parent
                    var hiddenWindow = new Window 
                    { 
                        Width = 1,
                        Height = 1,
                        IsVisible = false,
                        ShowInTaskbar = false
                    };
                    desktop.MainWindow = hiddenWindow;
                    DesignerWindow.mainWindow = hiddenWindow;
                    
                    // Execute VML command (will block for dialogs)
                    ScriptHandler.ExecuteVmlCommands(args[1]);
                    
                    // Wait a moment for async operations
                    System.Threading.Thread.Sleep(500);
                    desktop.Shutdown();
                }
            }, args);
            return;
        }

        // Direct .vml file: Run as form
        if (args[0].EndsWith(".vml"))
        {
            var vmlPath = args[0];
            Console.WriteLine($"Mode: Running {vmlPath}");
            Console.WriteLine("═══════════════════════════════════\n");
            PropertyStore.Initialize();
            BuildAvaloniaApp().Start((Application app, string[] startArgs) =>
            {
                if (app.ApplicationLifetime is Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime desktop)
                {
                    // Create hidden window for dialog parent
                    var hiddenWindow = new Window
                    {
                        Width = 1,
                        Height = 1,
                        IsVisible = false,
                        ShowInTaskbar = false
                    };
                    desktop.MainWindow = hiddenWindow;
                    DesignerWindow.mainWindow = hiddenWindow;
                    
                    // Set vml_dir based on file location
                    var vmlDir = Path.GetDirectoryName(Path.GetFullPath(vmlPath));
                    Settings.Set("vml_dir", vmlDir);
                    Console.WriteLine($"[PROGRAM] vml_dir set to: {vmlDir}");
                    
                    FormLoader.Open(vmlPath, false);
                }
            }, args);
            return;
        }


        // --help: Show usage
        if (args[0] == "--help" || args[0] == "-h")
        {
            Console.WriteLine("Usage:");
            Console.WriteLine("═══════════════════════════════════\n");
            Console.WriteLine("  vml                    # Open designer");
            Console.WriteLine("  vml --designer         # Open designer");
            Console.WriteLine("  vml <app-name>         # Run installed app");
            Console.WriteLine("  vml --vml-exec \"commands\"");
            Console.WriteLine("  vml --dialog-open <title> <filter>");
            Console.WriteLine("  vml --dialog-save <title> <default> <filter>");
            Console.WriteLine("  vml --help");
            Console.WriteLine();
            return;
        }
    }

    public static AppBuilder BuildAvaloniaApp()
        => AppBuilder.Configure<App>()
            .UsePlatformDetect()
            .WithInterFont()
            .LogToTrace();
}

using System;
using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
namespace VB;
public partial class App : Application
{
    public override void Initialize()
    {
        AvaloniaXamlLoader.Load(this);
    }
    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            // Initialize PropertyStore and temp database FIRST
            PropertyStore.Initialize();
            
            // Cleanup temp database on exit
            desktop.Exit += (s, e) =>
            {
                ScriptHandler.CleanupTempDatabase();
            };
            
            // Check for direct .vml file argument
            var args = Program.CommandLineArgs;
            if (args != null && args.Length > 0 && args[0].EndsWith(".vml"))
            {
                Console.WriteLine($"[APP] Direct form mode: {args[0]}");
                
                // Set vml_dir based on file location
                var vmlPath = args[0];
                var vmlDir = System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(vmlPath));
                Settings.Set("vml_dir", vmlDir);
                
                // Create hidden main window
                var hiddenWindow = new MainWindow { IsVisible = false, ShowInTaskbar = false };
                desktop.MainWindow = hiddenWindow;
                DesignerWindow.mainWindow = hiddenWindow;
                
                // Open the form
                FormLoader.Open(vmlPath, false);
            }
            else
            {
                // Designer mode
                var mainWindow = new MainWindow();
                
                var designerVml = Settings.Get("designer_vml", "/home/steve/Downloads/vml/vml/designer.vml");
                Console.WriteLine($"[APP] Loading designer from: {designerVml}");
                
                if (!System.IO.File.Exists(designerVml))
                {
                    Console.WriteLine($"[APP] Warning: {designerVml} not found");
                    using var conn = new Microsoft.Data.Sqlite.SqliteConnection($"Data Source={PropertyStore.GetDbPath()}");
                    conn.Open();
                    var cmd = conn.CreateCommand();
                    cmd.CommandText = "SELECT COUNT(*) FROM ui_tree WHERE source_file LIKE '%designer%'";
                    var count = (long)cmd.ExecuteScalar()!;
                    
                    if (count > 0)
                    {
                        Console.WriteLine($"[APP] ✓ Using cached designer ({count} controls)");
                        DesignerWindow.BuildUI(mainWindow, designerVml);
                    }
                    else
                    {
                        throw new System.Exception($"Designer VML not found: {designerVml}");
                    }
                }
                else
                {
                    DesignerWindow.LoadAndApply(mainWindow, designerVml);
                }
                
                desktop.MainWindow = mainWindow;
            }
        }
        base.OnFrameworkInitializationCompleted();
    }
}

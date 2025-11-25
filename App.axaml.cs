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
            
            var mainWindow = new MainWindow();
            
            // Get designer VML path from settings
            var designerVml = Settings.Get("designer_vml", "/home/steve/Downloads/vml/vml/designer.vml");
            
            Console.WriteLine($"[APP] Loading designer from: {designerVml}");
            
            // Check if file exists
            if (!System.IO.File.Exists(designerVml))
            {
                Console.WriteLine($"[APP] Warning: {designerVml} not found");
                Console.WriteLine($"[APP] Checking for cached version in database...");
                
                // Check if we have cached designer data
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
                    Console.WriteLine($"[APP] ✗ No cached designer found");
                    throw new System.Exception($"Designer VML not found and no cache available: {designerVml}");
                }
            }
            else
            {
                // Normal flow - load from VML
                DesignerWindow.LoadAndApply(mainWindow, designerVml);
            }
            
            desktop.MainWindow = mainWindow;
        }

        base.OnFrameworkInitializationCompleted();
    }
}

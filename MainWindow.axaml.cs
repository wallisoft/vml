using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using System;
using System.IO;
using System.Threading.Tasks;

namespace VB;

public partial class MainWindow : Window
{
    public string CurrentProjectPath { get; set; } = "";
    private VbApiServer? apiServer;
    
    public MainWindow()
    {
        InitializeComponent();
        
        // Initialize core systems
        PropertyStore.Initialize();
        ProjectManager.Initialize();
        
        // Start API server based on settings
        StartApiServerIfEnabled();
    }
    
    private void StartApiServerIfEnabled()
    {
        try
        {
            var apiEnabled = Settings.Get("api_server_enabled", "true");
            if (apiEnabled == "true")
            {
                var port = Settings.Get("api_server_port", "8889");
                Console.WriteLine($"[API] Starting server on port {port}");
                
                apiServer = new VbApiServer(this);
                apiServer.Start();
                Console.WriteLine($"[API] Server started successfully on http://localhost:{port}");
            }
            else
            {
                Console.WriteLine("[API] Server disabled in settings");
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[API] Failed to start: {ex.Message}");
        }
    }
    
    public async void HandleOpen(object? s, RoutedEventArgs e)
    {
        var storage = StorageProvider;
        var files = await storage.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Open VML Project",
            AllowMultiple = false,
            FileTypeFilter = new[]
            {
                new FilePickerFileType("VML Files") { Patterns = new[] { "*.vml" } },
                new FilePickerFileType("All Files") { Patterns = new[] { "*" } }
            }
        });
        
        if (files.Count > 0)
        {
            var path = files[0].Path.LocalPath;
            OpenProject(path);
        }
    }
    
    public void OpenProject(string path)
    {
        try
        {
            Console.WriteLine($"[PROJECT] Opening: {path}");
            CurrentProjectPath = path;
            
            var name = Path.GetFileNameWithoutExtension(path);
            ProjectManager.AddProject(name, path);
            
            // Load the VML into the designer
            VmlBootstrap.LoadAndApply(this, path);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[PROJECT] Failed to open: {ex.Message}");
        }
    }
    
    public void HandleExit(object? s, RoutedEventArgs e)
    {
        apiServer?.Stop();
        Close();
    }
    
    protected override void OnClosed(EventArgs e)
    {
        apiServer?.Stop();
        base.OnClosed(e);
    }
}

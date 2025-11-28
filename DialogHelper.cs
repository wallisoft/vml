using System;
using System.Threading.Tasks;
using Avalonia.Controls;
using Avalonia.Threading;

namespace VB;

public static class DialogHelper
{
    /// <summary>
    /// Show open dialog and return selected path to stdout (for scripts)
    /// </summary>
    public static async Task<string?> ShowOpenDialog(string title = "Open File", string filter = "*")
    {
        var tcs = new TaskCompletionSource<string?>();
        
        await Dispatcher.UIThread.InvokeAsync(async () =>
        {
            var dialog = new OpenFileDialog
            {
                Title = title,
                AllowMultiple = false
            };
            
            if (filter != "*")
            {
                dialog.Filters = new()
                {
                    new FileDialogFilter { Name = filter, Extensions = { filter.TrimStart('*', '.') } }
                };
            }
            
            var result = await dialog.ShowAsync(VmlBootstrap.mainWindow);
            tcs.SetResult(result?.Length > 0 ? result[0] : null);
        });
        
        return await tcs.Task;
    }
    
    /// <summary>
    /// Show save dialog and return selected path to stdout (for scripts)
    /// </summary>
    public static async Task<string?> ShowSaveDialog(string title = "Save File", string defaultName = "untitled", string filter = "*")
    {
        var tcs = new TaskCompletionSource<string?>();
        
        await Dispatcher.UIThread.InvokeAsync(async () =>
        {
            var dialog = new SaveFileDialog
            {
                Title = title,
                InitialFileName = defaultName
            };
            
            if (filter != "*")
            {
                dialog.DefaultExtension = filter.TrimStart('*', '.');
                dialog.Filters = new()
                {
                    new FileDialogFilter { Name = filter, Extensions = { filter.TrimStart('*', '.') } }
                };
            }
            
            var result = await dialog.ShowAsync(VmlBootstrap.mainWindow);
            tcs.SetResult(result);
        });
        
        return await tcs.Task;
    }
}

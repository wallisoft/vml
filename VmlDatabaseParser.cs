using System;
using System.Diagnostics;
using Microsoft.Data.Sqlite;
using System.IO;

namespace VB;

public static class VmlDatabaseParser
{
    public static void LoadVml(string vmlPath)
    {
        var dbPath = PropertyStore.GetDbPath();
        using var conn = new SqliteConnection($"Data Source={dbPath}");
        conn.Open();
        
        // Check if file changed since last import
        var fileTime = new DateTimeOffset(File.GetLastWriteTimeUtc(vmlPath)).ToUnixTimeSeconds();
        
        using (var checkCmd = conn.CreateCommand())
        {
            checkCmd.CommandText = "SELECT MAX(imported_at) FROM ui_tree WHERE source_file = @src";
            checkCmd.Parameters.AddWithValue("@src", vmlPath);
            var lastImport = checkCmd.ExecuteScalar();
            
            if (lastImport != DBNull.Value && Convert.ToInt64(lastImport) >= fileTime)
            {
                Console.WriteLine($"[PARSER] ✓ Up-to-date (cached: {vmlPath})");
                return;
            }
        }
        
        // Delete old + re-import
        using (var delCmd = conn.CreateCommand())
        {
            delCmd.CommandText = "DELETE FROM ui_tree WHERE source_file = @src; DELETE FROM scripts WHERE source_file = @src;";
            delCmd.Parameters.AddWithValue("@src", vmlPath);
            delCmd.ExecuteNonQuery();
        }
        conn.Close();
        
        var parser = Settings.Get("vml_parser");
        if (string.IsNullOrEmpty(parser)) parser = "vml-parse";
        
        // Use bash like old version - pipe SQL directly to sqlite3
        var bashCmd = $"{parser} '{vmlPath}' | sqlite3 '{dbPath}'";
        var psi = new ProcessStartInfo("/bin/bash", $"-c \"{bashCmd}\"") 
        { 
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false 
        };
        
        var proc = Process.Start(psi)!;
        var stdout = proc.StandardOutput.ReadToEnd();
        var stderr = proc.StandardError.ReadToEnd();
        proc.WaitForExit();
        
        if (!string.IsNullOrEmpty(stdout)) Console.WriteLine(stdout);
        if (!string.IsNullOrEmpty(stderr)) Console.WriteLine(stderr);
        
        Console.WriteLine($"[PARSER] Loaded {vmlPath}");
    }
}

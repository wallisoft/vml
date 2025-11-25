using System;
using Microsoft.Data.Sqlite;

namespace VB;

/// <summary>
/// Simple settings manager - key/value storage in database
/// </summary>
public static class Settings
{
    private static string DbPath => PropertyStore.GetDbPath();
    
    public static string Get(string key, string defaultValue = "")
    {
        try
        {
            using var conn = new SqliteConnection($"Data Source={DbPath}");
            conn.Open();
            
            using var cmd = conn.CreateCommand();
            cmd.CommandText = "SELECT value FROM settings WHERE key = @key";
            cmd.Parameters.AddWithValue("@key", key);
            
            var result = cmd.ExecuteScalar();
            return result?.ToString() ?? defaultValue;
        }
        catch
        {
            return defaultValue;
        }
    }
    
    public static int GetInt(string key, int defaultValue = 0)
    {
        var value = Get(key);
        return int.TryParse(value, out var result) ? result : defaultValue;
    }
    
    public static double GetDouble(string key, double defaultValue = 0.0)
    {
        var value = Get(key);
        return double.TryParse(value, out var result) ? result : defaultValue;
    }
    
    public static bool GetBool(string key, bool defaultValue = false)
    {
        var value = Get(key).ToLower();
        return value == "true" || value == "1";
    }
    
    public static void Set(string key, string value, string? description = null)
    {
        try
        {
            using var conn = new SqliteConnection($"Data Source={DbPath}");
            conn.Open();
            
            using var cmd = conn.CreateCommand();
            cmd.CommandText = @"
                INSERT INTO settings (key, value, description) 
                VALUES (@key, @value, @desc)
                ON CONFLICT(key) DO UPDATE SET value = @value";
            
            cmd.Parameters.AddWithValue("@key", key);
            cmd.Parameters.AddWithValue("@value", value);
            cmd.Parameters.AddWithValue("@desc", description ?? "");
            cmd.ExecuteNonQuery();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[SETTINGS] Error setting {key}: {ex.Message}");
        }
    }
    
    public static void SetInt(string key, int value) => Set(key, value.ToString());
    public static void SetDouble(string key, double value) => Set(key, value.ToString());
    public static void SetBool(string key, bool value) => Set(key, value ? "true" : "false");
}

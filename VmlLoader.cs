using Microsoft.Data.Sqlite;
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace VB;

public class VmlLoader
{
    public static List<VmlControl> Load(string filePath)
    {
        var controls = new List<VmlControl>();
        VmlControl? current = null;
        string? heredocMarker = null;
        var heredocContent = new StringBuilder();
        string? heredocProperty = null;
        
        foreach (var line in File.ReadAllLines(filePath))
        {
            var trimmed = line.Trim();
            
            // Handle heredoc content
            if (heredocMarker != null)
            {
                if (trimmed == heredocMarker)
                {
                    // End of heredoc
                    if (current != null && heredocProperty != null)
                    {
                        current.Properties[heredocProperty] = heredocContent.ToString();
                    }
                    heredocMarker = null;
                    heredocContent.Clear();
                    heredocProperty = null;
                }
                else
                {
                    heredocContent.AppendLine(line);
                }
                continue;
            }
            
            // Skip blank lines and comments
            if (string.IsNullOrWhiteSpace(trimmed) || trimmed.StartsWith("#"))
                continue;
                
            if (trimmed.StartsWith("@"))
            {
                if (current != null)
                    controls.Add(current);
                    
                var parts = trimmed.Substring(1).Split(' ', 2);
                current = new VmlControl
                {
                    Type = parts[0],
                    Name = parts.Length > 1 ? parts[1] : null,
                    Properties = new Dictionary<string, string>()
                };
            }
            else if (current != null && line.Length > 0 && char.IsWhiteSpace(line[0]))
            {
                // This is a property line (starts with any whitespace)
                var parts = trimmed.Split('=', 2);
                if (parts.Length == 2)
                {
                    var propName = parts[0].Trim();
                    var propValue = parts[1].Trim();
                    
                    // Check for heredoc syntax (<<EOF)
                    if (propValue.StartsWith("<<"))
                    {
                        heredocMarker = propValue.Substring(2).Trim();
                        heredocProperty = propName;
                        heredocContent.Clear();
                    }
                    else
                    {
                        current.Properties[propName] = propValue;
                    }
                }
            }
        }
        
        if (current != null)
            controls.Add(current);
            
        return controls;
    }
    
    public static List<VmlControl> LoadFromDatabase(string controlName, string dbPath = "vml.db")
    {
        var controls = new List<VmlControl>();
        
        using var conn = new SqliteConnection($"Data Source={dbPath}");
        conn.Open();
        
        // Find root control by name
        using var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT id, control_type FROM ui_tree WHERE name = @name";
        cmd.Parameters.AddWithValue("@name", controlName);
        
        using var reader = cmd.ExecuteReader();
        if (reader.Read())
        {
            var id = reader.GetInt32(0);
            var type = reader.GetString(1);
            reader.Close();
            
            var control = LoadControlRecursive(conn, id, type, controlName);
            if (control != null)
                controls.Add(control);
        }
        
        return controls;
    }
    
    private static VmlControl? LoadControlRecursive(SqliteConnection conn, int id, string type, string name)
    {
        var control = new VmlControl
        {
            Type = type,
            Name = name,
            Properties = new Dictionary<string, string>()
        };
        
        // Load properties
        using var propCmd = conn.CreateCommand();
        propCmd.CommandText = "SELECT property_name, property_value FROM ui_properties WHERE ui_tree_id = @id";
        propCmd.Parameters.AddWithValue("@id", id);
        
        using var propReader = propCmd.ExecuteReader();
        while (propReader.Read())
        {
            control.Properties[propReader.GetString(0)] = propReader.GetString(1);
        }
        propReader.Close();
        
        // Load children
        using var childCmd = conn.CreateCommand();
        childCmd.CommandText = "SELECT id, control_type, name FROM ui_tree WHERE parent_id = @id ORDER BY display_order";
        childCmd.Parameters.AddWithValue("@id", id);
        
        using var childReader = childCmd.ExecuteReader();
        var childData = new List<(int id, string type, string name)>();
        while (childReader.Read())
        {
            childData.Add((childReader.GetInt32(0), childReader.GetString(1), childReader.GetString(2)));
        }
        childReader.Close();
        
        foreach (var (childId, childType, childName) in childData)
        {
            var child = LoadControlRecursive(conn, childId, childType, childName);
            if (child != null)
            {
                child.Properties["Parent"] = name;
                control.Children.Add(child);
            }
        }
        
        return control;
    }

    public static List<VmlControl> FlattenControls(List<VmlControl> controls)
    {
        var result = new List<VmlControl>();
        foreach (var control in controls)
        {
            result.Add(control);
            if (control.Children.Count > 0)
            {
                result.AddRange(FlattenControls(control.Children));
            }
        }
        return result;
    }
}
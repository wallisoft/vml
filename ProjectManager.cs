using System;
using System.Collections.Generic;
using System.Data.SQLite;
using System.IO;
using System.Linq;

namespace VB;

public class ProjectManager
{
    private const string DB_NAME = "vml.db";
    private static string DbPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".vml", DB_NAME);
    
    public static void Initialize()
    {
        var dir = Path.GetDirectoryName(DbPath);
        if (!Directory.Exists(dir)) Directory.CreateDirectory(dir!);
        
        if (!File.Exists(DbPath))
        {
            SQLiteConnection.CreateFile(DbPath);
            using var conn = new SQLiteConnection($"Data Source={DbPath};Version=3;");
            conn.Open();
            
            var cmd = conn.CreateCommand();
            cmd.CommandText = @"
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_opened DATETIME
                );
                
                CREATE TABLE forms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    vml_content TEXT NOT NULL,
                    is_startup BOOLEAN DEFAULT 0,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                );
                
                CREATE TABLE resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    data BLOB,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                );
            ";
            cmd.ExecuteNonQuery();
            
            Console.WriteLine($"[DB] Created database at {DbPath}");
        }
    }
    
    public static List<string> GetRecentProjects()
    {
        Initialize();
        var projects = new List<string>();
        
        using var conn = new SQLiteConnection($"Data Source={DbPath};Version=3;");
        conn.Open();
        var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT path FROM projects ORDER BY last_opened DESC LIMIT 10";
        
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            projects.Add(reader.GetString(0));
        }
        
        return projects;
    }
    
    public static void AddProject(string name, string path)
    {
        Initialize();
        using var conn = new SQLiteConnection($"Data Source={DbPath};Version=3;");
        conn.Open();
        var cmd = conn.CreateCommand();
        cmd.CommandText = "INSERT INTO projects (name, path, last_opened) VALUES (@name, @path, datetime('now'))";
        cmd.Parameters.AddWithValue("@name", name);
        cmd.Parameters.AddWithValue("@path", path);
        cmd.ExecuteNonQuery();
        
        Console.WriteLine($"[DB] Added project: {name}");
    }
}


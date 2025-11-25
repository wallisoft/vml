using System;
using System.Collections.Generic;

namespace VB;

/// <summary>
/// Central registry for @Script objects defined in VML
/// Scripts are loaded once and can be executed by event handlers
/// </summary>
public static class ScriptRegistry
{
    private static readonly Dictionary<string, VmlScript> Scripts = new();
    
    public static void Register(string name, string content, string interpreter = "bash", string instance = "")
    {
        Scripts[name] = new VmlScript
        {
            Name = name,
            Content = content,
            Interpreter = interpreter,
            Instance = instance
        };
        Console.WriteLine($"[SCRIPT REGISTRY] Registered: {name} ({interpreter}{(instance != "" ? " " + instance : "")})");
    }
    
    public static VmlScript? Get(string name)
    {
        return Scripts.TryGetValue(name, out var script) ? script : null;
    }
    
    public static void Clear()
    {
        Scripts.Clear();
    }
    
    public static int Count => Scripts.Count;
}

public class VmlScript
{
    public string Name { get; set; } = "";
    public string Content { get; set; } = "";
    public string Interpreter { get; set; } = "bash";
    public string Instance { get; set; } = "";
}


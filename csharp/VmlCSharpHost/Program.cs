// VML's C# script host.
//
// The engine starts this once and talks to it over stdin/stdout, one JSON message per line:
//   engine -> host   {"type":"run", "id":1, "code":"...", "args":[...], "key":"<form or instance>"}
//   host -> engine   {"type":"call", "cmd":"SetProperty", "args":[...]}   (a Vml() call from the script)
//   engine -> host   {"type":"result", "value":"..."}                     (its answer)
//   host -> engine   {"type":"done", "id":1, "value":"...", "error":null}
// A Vml() call can run another script (Lua or C#), so while waiting for a result the host also
// accepts nested "run" messages. Scripts are compiled once with Roslyn and cached by their text.

using System.Collections.Concurrent;
using System.Text.Json;
using Microsoft.CodeAnalysis.CSharp.Scripting;
using Microsoft.CodeAnalysis.Scripting;

/// <summary>What every C# script can see: Vml(...), args, and State (shared by the scripts of one form).</summary>
public class Globals
{
    public string[] args = Array.Empty<string>();
    public Dictionary<string, object> State = new();
    public string Vml(string command, params object[] a) => Host.Call(command, a);
}

public static class Host
{
    static TextReader input;
    static TextWriter proto;
    static readonly ConcurrentDictionary<string, ScriptRunner<object>> cache = new();
    static readonly Dictionary<string, Dictionary<string, object>> states = new();

    static readonly ScriptOptions options = ScriptOptions.Default
        .WithImports("System", "System.IO", "System.Linq", "System.Text", "System.Collections.Generic",
                     "System.Text.RegularExpressions", "System.Net.Http", "System.Threading.Tasks")
        .WithReferences(typeof(object).Assembly, typeof(Console).Assembly, typeof(Enumerable).Assembly,
                        typeof(List<>).Assembly, typeof(System.Text.RegularExpressions.Regex).Assembly,
                        typeof(System.Net.Http.HttpClient).Assembly, typeof(File).Assembly,
                        typeof(System.Text.Json.JsonSerializer).Assembly,
                        System.Reflection.Assembly.Load("System.Runtime"), System.Reflection.Assembly.Load("System.Collections"));

    public static void Main()
    {
        input = new StreamReader(Console.OpenStandardInput());
        proto = new StreamWriter(Console.OpenStandardOutput()) { AutoFlush = true };
        Console.SetOut(new LogWriter());                     // a script's Console.WriteLine goes to VML's log
        Send(new() { ["type"] = "ready" });
        string line;
        while ((line = input.ReadLine()) != null)
        {
            var msg = JsonDocument.Parse(line).RootElement;
            if (msg.GetProperty("type").GetString() == "run") Run(msg);
        }
    }

    static void Run(JsonElement msg)
    {
        var id = msg.GetProperty("id").GetInt32();
        var code = msg.GetProperty("code").GetString() ?? "";
        var key = msg.TryGetProperty("key", out var k) ? k.GetString() ?? "" : "";
        try
        {
            var runner = cache.GetOrAdd(code, c => CSharpScript.Create<object>(c, options, typeof(Globals)).CreateDelegate());
            if (!states.TryGetValue(key, out var state)) states[key] = state = new Dictionary<string, object>();
            var g = new Globals
            {
                args = msg.GetProperty("args").EnumerateArray().Select(a => a.ToString()).ToArray(),
                State = state,
            };
            var result = runner(g).GetAwaiter().GetResult();
            Send(new() { ["type"] = "done", ["id"] = id, ["value"] = result?.ToString() ?? "" });
        }
        catch (CompilationErrorException e)
        {
            cache.TryRemove(code, out _);
            Send(new() { ["type"] = "done", ["id"] = id, ["error"] = string.Join("\n", e.Diagnostics) });
        }
        catch (Exception e)
        {
            Send(new() { ["type"] = "done", ["id"] = id, ["error"] = e.GetBaseException().Message });
        }
    }

    public static string Call(string command, object[] args)
    {
        Send(new() { ["type"] = "call", ["cmd"] = command, ["args"] = args.Select(a => a?.ToString() ?? "").ToArray() });
        string line;
        while ((line = input.ReadLine()) != null)
        {
            var msg = JsonDocument.Parse(line).RootElement;
            var type = msg.GetProperty("type").GetString();
            if (type == "result") return msg.GetProperty("value").ToString();
            if (type == "run") Run(msg);                         // the call ran another C# script first
        }
        Environment.Exit(0);
        return "";
    }

    static void Send(Dictionary<string, object> msg) => proto.WriteLine(JsonSerializer.Serialize(msg));

    class LogWriter : TextWriter
    {
        readonly System.Text.StringBuilder buf = new();
        public override System.Text.Encoding Encoding => System.Text.Encoding.UTF8;
        public override void Write(char c)
        {
            if (c == '\n') { Send(new() { ["type"] = "log", ["text"] = buf.ToString() }); buf.Clear(); }
            else if (c != '\r') buf.Append(c);
        }
    }
}

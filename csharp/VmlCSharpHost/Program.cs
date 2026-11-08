// VML's C# script host.
//
// The engine starts this once and talks to it over stdin/stdout, one JSON message per line:
//   engine -> host   {"type":"run", "id":1, "code":"...", "args":[...], "key":"<form or instance>"}
//   host -> engine   {"type":"call", "cmd":"SetProperty", "args":[...]}   (a Vml() call from the script)
//   engine -> host   {"type":"result", "value":"..."}                     (its answer)
//   host -> engine   {"type":"done", "id":1, "value":"...", "error":null}
// A Vml() call can run another script (Lua or C#), so while waiting for a result the host also
// accepts nested "run" messages. Scripts are compiled once with Roslyn and cached by their text.
//
// Break mode (the debugger's breakpoints and stepping): a "run" with "debug": {name, breaks, step} is compiled
// with a call before each statement, __Dbg.Line(line, locals), which stops where it should:
//   host -> engine   {"type":"pause", "name":"btnGo_OnClick", "line":3, "depth":12, "locals":[[name, type, value]...]}
//   engine -> host   {"type":"resume", "mode":"" | "into" | "over" | "out", "breaks":[3, 7]}
// Without breakpoints or a step going, scripts are compiled as written and run at full speed.

using System.Collections.Concurrent;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
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
        var debugging = msg.TryGetProperty("debug", out var dbg);
        if (debugging) __Dbg.Enter(dbg);
        try
        {
            ScriptRunner<object> runner = null;
            if (debugging)                                   // with a line hook before each statement, if it compiles so
                foreach (var withLocals in new[] { true, false })
                {
                    var marked = Instrument.Mark(code, withLocals);
                    try { runner = cache.GetOrAdd("dbg" + (withLocals ? "L" : "") + ":" + code, _ => Compile(marked)); break; }
                    catch (CompilationErrorException e)
                    {
                        Send(new() { ["type"] = "log", ["text"] = "break mode: couldn't mark this script" + (withLocals ? " with its locals" : "") + ": " + string.Join("; ", e.Diagnostics.Take(3)) });
                    }
                }
            runner ??= cache.GetOrAdd(code, c => CSharpScript.Create<object>(c, options, typeof(Globals)).CreateDelegate());
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
        finally
        {
            if (debugging) __Dbg.Leave();
        }
    }

    static ScriptRunner<object> Compile(string code)
    {
        var s = CSharpScript.Create<object>(code, options.AddReferences(typeof(__Dbg).Assembly), typeof(Globals));
        var errors = s.Compile().Where(d => d.Severity == DiagnosticSeverity.Error).ToArray();
        if (errors.Length > 0) throw new CompilationErrorException("", System.Collections.Immutable.ImmutableArray.Create(errors));
        return s.CreateDelegate();
    }

    // (for __Dbg: a pause waits here for the engine's answer, answering any script it runs meanwhile)
    public static JsonElement WaitFor(string wanted)
    {
        string line;
        while ((line = input.ReadLine()) != null)
        {
            var msg = JsonDocument.Parse(line).RootElement;
            var type = msg.GetProperty("type").GetString();
            if (type == wanted) return msg;
            if (type == "run") Run(msg);
        }
        Environment.Exit(0);
        return default;
    }

    public static void Tell(Dictionary<string, object> msg) => Send(msg);

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


/// <summary>Break mode inside a C# script: where to stop, and the stop itself (the engine shows it).</summary>
public static class __Dbg
{
    class Frame { public string Name = ""; public HashSet<int> Breaks = new(); public string Mode; public int Depth; }
    static readonly Stack<Frame> frames = new();

    public static void Enter(JsonElement d)
    {
        var f = new Frame { Name = d.TryGetProperty("name", out var n) ? n.GetString() ?? "" : "" };
        if (d.TryGetProperty("breaks", out var b) && b.ValueKind == JsonValueKind.Array)
            foreach (var x in b.EnumerateArray()) f.Breaks.Add(x.GetInt32());
        if (d.TryGetProperty("step", out var s) && s.ValueKind == JsonValueKind.String) { f.Mode = s.GetString(); f.Depth = int.MaxValue; }
        frames.Push(f);
    }

    public static void Leave() { if (frames.Count > 0) frames.Pop(); }

    public static void Line(int line, Func<object[]> locals)
    {
        if (frames.Count == 0) return;
        var f = frames.Peek();
        if (f.Mode == null && f.Breaks.Count == 0) return;
        var depth = new System.Diagnostics.StackTrace().FrameCount;
        var stop = f.Mode switch { "into" => true, "over" => depth <= f.Depth, "out" => depth < f.Depth, _ => false };
        if (!stop && !f.Breaks.Contains(line)) return;
        var shown = new List<object[]>();
        try
        {
            var pairs = locals?.Invoke() ?? Array.Empty<object>();
            for (var i = 0; i + 1 < pairs.Length; i += 2)
            {
                var v = pairs[i + 1];
                var text = v is string str ? "\"" + str + "\"" : v is System.Collections.IEnumerable e && v is not string
                    ? "{" + string.Join(", ", e.Cast<object>().Take(8)) + "}" : v?.ToString() ?? "null";
                shown.Add(new object[] { pairs[i]?.ToString() ?? "", v?.GetType().Name ?? "null", text.Length > 400 ? text[..400] + "…" : text });
            }
        }
        catch { }
        Host.Tell(new() { ["type"] = "pause", ["name"] = f.Name, ["line"] = line, ["depth"] = depth, ["locals"] = shown });
        var answer = Host.WaitFor("resume");
        var mode = answer.TryGetProperty("mode", out var m) ? m.GetString() ?? "" : "";
        f.Mode = mode == "" ? null : mode;
        f.Depth = depth;
        if (answer.TryGetProperty("breaks", out var b) && b.ValueKind == JsonValueKind.Array)
        {
            f.Breaks.Clear();
            foreach (var x in b.EnumerateArray()) f.Breaks.Add(x.GetInt32());
        }
    }
}

/// <summary>A script with __Dbg.Line(n, locals) before each statement in a block (or at the top level), the
/// locals being those declared (with a value) before it in the blocks around it, and the parameters it's in.</summary>
public static class Instrument
{
    public static string Mark(string code, bool withLocals)
    {
        var tree = CSharpSyntaxTree.ParseText(code, new CSharpParseOptions(kind: SourceCodeKind.Script));
        var root = (CompilationUnitSyntax)tree.GetRoot();
        var marks = new List<(int pos, string text)>();
        foreach (var st in root.DescendantNodes().OfType<StatementSyntax>())
        {
            var holder = st.Parent;
            if (holder is GlobalStatementSyntax g) holder = g.Parent;
            if (holder is not BlockSyntax && holder is not CompilationUnitSyntax) continue;
            if (st is LocalFunctionStatementSyntax || st is BlockSyntax) continue;
            var line = st.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
            var names = withLocals ? InScope(st).Distinct().ToList() : new List<string>();
            var arr = string.Join(", ", names.Select(n => $"\"{n}\", (object){n}"));
            var at = st.Parent is GlobalStatementSyntax gs ? gs.SpanStart : st.SpanStart;
            marks.Add((at, $"__Dbg.Line({line}, () => new object[] {{ {arr} }}); "));
        }
        var text = code;
        foreach (var (pos, ins) in marks.OrderByDescending(m => m.pos)) text = text.Insert(pos, ins);
        return text;
    }

    static IEnumerable<string> Declared(StatementSyntax s)
    {
        if (s is LocalDeclarationStatementSyntax d && !d.Declaration.Type.ToString().StartsWith("ref") && d.UsingKeyword == default)
            foreach (var v in d.Declaration.Variables)
                if (v.Initializer != null) yield return v.Identifier.Text;
    }

    static IEnumerable<string> InScope(SyntaxNode node)
    {
        var child = node;
        for (var a = node.Parent; a != null; child = a, a = a.Parent)
        {
            switch (a)
            {
                case BlockSyntax b:
                    foreach (var s in b.Statements.TakeWhile(s => s != child)) foreach (var n in Declared(s)) yield return n;
                    break;
                case CompilationUnitSyntax cu:                   // (a script's top-level variables are fields to Roslyn)
                    foreach (var m in cu.Members.TakeWhile(m => m != child))
                    {
                        if (m is GlobalStatementSyntax gs) foreach (var n in Declared(gs.Statement)) yield return n;
                        if (m is FieldDeclarationSyntax fd)
                            foreach (var v in fd.Declaration.Variables) if (v.Initializer != null) yield return v.Identifier.Text;
                    }
                    break;
                case MethodDeclarationSyntax md:
                    foreach (var p in md.ParameterList.Parameters) if (p.Modifiers.Count == 0) yield return p.Identifier.Text;
                    break;
                case ForEachStatementSyntax fe when child == fe.Statement:
                    yield return fe.Identifier.Text;
                    break;
                case ForStatementSyntax fs when child == fs.Statement && fs.Declaration != null:
                    foreach (var v in fs.Declaration.Variables) yield return v.Identifier.Text;
                    break;
                case CatchClauseSyntax cc when cc.Declaration != null && cc.Declaration.Identifier.Text != "":
                    yield return cc.Declaration.Identifier.Text;
                    break;
                case LocalFunctionStatementSyntax lf:
                    foreach (var p in lf.ParameterList.Parameters) if (p.Modifiers.Count == 0) yield return p.Identifier.Text;
                    break;
                case ParenthesizedLambdaExpressionSyntax pl:
                    foreach (var p in pl.ParameterList.Parameters) if (p.Modifiers.Count == 0) yield return p.Identifier.Text;
                    break;
                case SimpleLambdaExpressionSyntax sl:
                    yield return sl.Parameter.Identifier.Text;
                    break;
            }
        }
    }
}

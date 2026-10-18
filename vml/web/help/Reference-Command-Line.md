# Command line reference

The `vml` command, Visualised 1.6.1.

```
vml [form.vml | app.vmlproj] [--db path/to/vml.db] [--shot out.png]   (no form: open the VML designer)
   vml setup-csharp                                         (optional: build the C# script host)
   vml apk form.vml [out.apk] [--new-app]                   (an Android app of its own: Pro)
   vml apk-key [save FILE | restore FILE [--replace]]       (the key your Android apps are signed with: keep a copy)
   vml html form.vml [out.html] [--open] [--cdn] [--no-pass]  (a web page, Lua engine inside it; --cdn: load it online instead;
                                                            --no-pass: leave out this licence's pass for the Link relay)
vml onl-key KEY                                         (the TinyWeb key vml.onl publishing uses)
vml mcp                                                 (an MCP server, so an AI assistant can make and publish apps)
```

On Windows the same commands are run with `vml.exe` from Visualised's folder; double-clicking a `.vml` or `.vmlproj` file opens it.

# How To Script in Python and C#

## Introduction

Lua is Visualised's own language, and the one that runs everywhere: desktop, web and phone. On a computer, a script can also be Python, C#, Bash or PowerShell. Python and C# are built in the way Lua is: each form keeps its variables between scripts, `Vml()` calls answer at once, and the debugger stops in them and steps through them.

## Step 1: A Python script

Give the script `Interpreter=python`:

~~~
@Script AddUp
Interpreter=python
<<PY
runs = globals().get("runs", 0) + 1
total = sum(n * n for n in range(1, 5))
Vml("SetProperty", "lblTotal", "Text", f"Total {total} (run {runs})")
print(total)
PY
~~~

- `Vml("Command", ...)` works as it does in Lua; `args` holds what the script was given.
- What it **prints** is its answer (what `Vml("RunScript", "AddUp")` returns).
- Its variables stay with the form: `runs` counts up, run after run.

It runs in your own Python (`python3`, or `python` on Windows), so anything you've installed with `pip` can be imported. Visualised starts one Python for the app the first time a Python script runs, and keeps it: after that a script starts in a few milliseconds.

That Python is a program of its own, kept apart from Visualised's: what your scripts import, install or change can't upset Visualised, and Visualised can't upset them.

## Step 2: A C# script

`Interpreter=csharp`, once the free .NET SDK is installed and C# is switched on (**Settings > C# Scripting**):

~~~
@Script AddUp
Interpreter=csharp
<<CS
var total = 0;
for (var i = 1; i <= 4; i++) total += i * i;
Vml("SetProperty", "lblTotal", "Text", "Total " + total);
return total;
CS
~~~

`State` is a dictionary the form's C# scripts share; `return` gives the script's answer.

## Step 3: Debug them

Breakpoints and stepping work in Python and C# as in Lua ([How To Debug Your Scripts](How-To-Debug-Your-Scripts)): click the Script Editor's margin, run the form, and it stops there with its locals. Step into goes into your functions; Step over runs them.

## Conclusion

Lua for apps that go everywhere; Python for its packages; C# for .NET. All three share the form, the `Vml()` commands and the debugger.

Next: [How To Style Controls with CSS](How-To-Style-Controls-with-CSS).

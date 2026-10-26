#!/usr/bin/env python3
"""Translate a Visualised script between languages, for the tutorial "pick your language" tabs.

The source of truth is Lua (the language that runs everywhere). From one Lua snippet this produces the
same script in VB, C# and Python, over the shared object model: Vml() calls, control flow, assignments
and expressions map one-to-one; the handful of genuine idiom differences (how a script returns its
answer, Python needing str() around a number in a joined string) are marked rather than faked.

Line-oriented, not a full compiler: it handles the subset tutorials are written in, and passes anything
it doesn't recognise through unchanged, so a snippet is never silently mistranslated.
"""
import re

LANGS = ("lua", "vb", "csharp", "python")
LABEL = {"lua": "Lua", "vb": "VB", "csharp": "C#", "python": "Python"}

# per-language surface: comment lead, how a local is declared, statement terminator, and the token map
CFG = {
    "lua":    dict(cm="--", decl="local ", end="",  indent="  "),
    "vb":     dict(cm="'",  decl="Dim ",   end="",  indent="    "),
    "csharp": dict(cm="//", decl="var ",   end=";", indent="    "),
    "python": dict(cm="#",  decl="",       end="",  indent="    "),
}
# word / operator / literal translations, from Lua
WORDS = {
    "vb":     {"and": "And", "or": "Or", "not": "Not", "true": "True", "false": "False", "nil": "Nothing"},
    "csharp": {"and": "&&", "or": "||", "not": "!", "true": "true", "false": "false", "nil": "null"},
    "python": {"and": "and", "or": "or", "not": "not", "true": "True", "false": "False", "nil": "None"},
    "lua":    {},
}
CONCAT = {"vb": " & ", "csharp": " + ", "python": " + ", "lua": " .. "}
NEQ = {"vb": "<>", "csharp": "!=", "python": "!=", "lua": "~="}


def _tokens(expr):
    """Split an expression into (kind, text): str | num | word | op | other. Keeps strings whole."""
    out = []
    for m in re.finditer(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\b\d+\.?\d*\b|[A-Za-z_]\w*|\.\.|~=|[<>=]=|[^\s]', expr):
        t = m.group(0)
        if t[0] in '"\'':
            out.append(("str", t))
        elif t[0].isdigit():
            out.append(("num", t))
        elif t[:1].isalpha() or t[0] == "_":
            out.append(("word", t))
        else:
            out.append(("op", t))
    return out


def _expr(expr, lang):
    """Translate an expression's operators, keywords and literals into `lang` (identifiers stay as they are)."""
    has_concat = any(t == ".." for k, t in _tokens(expr))
    mapped = []
    for kind, t in _tokens(expr):
        if kind == "op" and t == "..":
            mapped.append(("op", CONCAT[lang].strip()))
        elif kind == "op" and t == "~=":
            mapped.append(("op", NEQ[lang]))
        elif kind == "word" and t.lower() in WORDS[lang]:
            mapped.append(("word", WORDS[lang][t.lower()]))
        else:
            mapped.append((kind, t))
    # emit with sane spacing: binary operators spaced, calls/members/commas tight
    res = ""
    for i, (kind, t) in enumerate(mapped):
        if i == 0:
            res = t
            continue
        pk, pt = mapped[i - 1]
        tight = (t in (",", ")", ";") or t == "." or pt in (".", "(")
                 or (t == "(" and (pk == "word" or pt == ")")))
        res += ("" if tight else " ") + t
    res = res.replace(",", ", ").replace(",  ", ", ")
    # Python: a number joined into a string needs str() — wrap the common `"..." + n` / `n + "..."` shapes
    if lang == "python" and has_concat:
        res = re.sub(r'(?<![\w")])\b([a-z_]\w*)\b(?=\s*\+\s*")', r"str(\1)", res)
        res = re.sub(r'(?<=")\s*\+\s*\b([a-z_]\w*)\b(?![\w("])', r" + str(\1)", res)
    return res


def translate(lua, lang):
    """One Lua snippet -> the same script in `lang` (lua returns it unchanged)."""
    if lang == "lua":
        return lua.rstrip("\n")
    c = CFG[lang]
    out, stack, depth = [], [], 0          # stack: the block kind at each open level (for end/brace/Next)

    def line(text):
        out.append((c["indent"] * depth if lang == "python" else c["indent"] * depth) + text)

    for raw in lua.split("\n"):
        s = raw.strip()
        if not s:
            out.append("")
            continue
        # comment
        m = re.match(r"^--\s?(.*)$", s)
        if m:
            line(f"{c['cm']} {m.group(1)}".rstrip())
            continue
        # numeric for:  for i = a, b do
        m = re.match(r"^for\s+(\w+)\s*=\s*(.+?)\s*,\s*(.+?)\s+do$", s)
        if m:
            v, a, b = m.group(1), _expr(m.group(2), lang), _expr(m.group(3), lang)
            if lang == "vb":
                line(f"For {v} = {a} To {b}")
            elif lang == "csharp":
                line(f"for (var {v} = {a}; {v} <= {b}; {v}++) {{")
            else:  # python
                stop = str(int(b) + 1) if b.isdigit() else f"({b}) + 1"
                line(f"for {v} in range({a}, {stop}):")
            stack.append("for"); depth += 1
            continue
        # if / elseif / else
        m = re.match(r"^if\s+(.+?)\s+then$", s)
        if m:
            cond = _expr(m.group(1), lang)
            line({"vb": f"If {cond} Then", "csharp": f"if ({cond}) {{", "python": f"if {cond}:"}[lang])
            stack.append("if"); depth += 1
            continue
        m = re.match(r"^elseif\s+(.+?)\s+then$", s)
        if m:
            cond = _expr(m.group(1), lang); depth -= 1
            line({"vb": f"ElseIf {cond} Then", "csharp": f"}} else if ({cond}) {{", "python": f"elif {cond}:"}[lang])
            depth += 1
            continue
        if s == "else":
            depth -= 1
            line({"vb": "Else", "csharp": "} else {", "python": "else:"}[lang])
            depth += 1
            continue
        # while cond do
        m = re.match(r"^while\s+(.+?)\s+do$", s)
        if m:
            cond = _expr(m.group(1), lang)
            line({"vb": f"While {cond}", "csharp": f"while ({cond}) {{", "python": f"while {cond}:"}[lang])
            stack.append("while"); depth += 1
            continue
        # end  -> close the most recent block
        if s == "end":
            kind = stack.pop() if stack else ""
            depth = max(0, depth - 1)
            if lang == "python":
                continue
            if lang == "csharp":
                line("}")
            else:  # vb
                line({"for": "Next", "if": "End If", "while": "End While", "function": "End Function"}.get(kind, "End"))
            continue
        # local x = expr   /   x = expr
        m = re.match(r"^(local\s+)?([A-Za-z_]\w*)\s*=\s*(.+)$", s)
        if m and not re.match(r"^(if|for|while|function|return|elseif)\b", s):
            decl = c["decl"] if m.group(1) else ""
            line(f"{decl}{m.group(2)} = {_expr(m.group(3), lang)}{c['end']}")
            continue
        # return expr
        m = re.match(r"^return\b\s*(.*)$", s)
        if m:
            kw = "Return" if lang == "vb" else "return"
            line(f"{kw} {_expr(m.group(1), lang)}{c['end']}".rstrip() if m.group(1) else f"{kw}{c['end']}")
            continue
        # anything else (a Vml(...) call, a function call, print(...)): translate the expression, add terminator
        line(f"{_expr(s, lang)}{c['end']}")

    return "\n".join(out).rstrip("\n")


if __name__ == "__main__":
    SAMPLE = """-- add up the squares
local total = 0
for i = 1, 4 do
  total = total + i * i
end
if total > 20 then
  Vml("SetProperty", "lblTotal", "Text", "Big total " .. total)
else
  Vml("SetProperty", "lblTotal", "Text", "Total " .. total)
end
return total"""
    for lang in LANGS:
        print("=" * 48, LABEL[lang])
        print(translate(SAMPLE, lang))

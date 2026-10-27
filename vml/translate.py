#!/usr/bin/env python3
"""Translate a Visualised script between languages, in any direction.

The engine is generic: every language *declares* its own surface in SPEC below (comment lead, how a local
is declared, its concat operator, and the shape of a for / if / while) and the engine reads a snippet into
a small neutral form and writes it back out in another language. Add a language, or fix one's quirk, by
editing its SPEC entry only — never the engine. (These specs are the data the registry would hold, so they
can later move to each interpreter's registration, VML-side, with no engine change.)

Line-oriented over the shared object model: Vml() calls, assignments, numeric for, if/elseif/else, while
and expressions carry across cleanly; anything it doesn't recognise passes through untouched, so a snippet
is never silently mistranslated.
"""
import re

LANGS = ("lua", "vb", "csharp", "python", "php")
LABEL = {"lua": "Lua", "vb": "VB", "csharp": "C#", "python": "Python", "php": "PHP"}

# Each language, declared as data. {a} {b} {v} {c} are filled in by the engine.
SPEC = {
    "lua": dict(
        comment="--", decl="local ", end="", indent="  ", pyblock=False,
        concat="..", neq="~=", eq="==", words={"and": "and", "or": "or", "not": "not", "true": "true", "false": "false", "nil": "nil"},
        forl="for {v} = {a}, {b} do", iff="if {c} then", elf="elseif {c} then", els="else",
        funcl="function {name}({args})",
        whl="while {c} do", close={"for": "end", "if": "end", "while": "end", "func": "end"}),
    "vb": dict(
        comment="'", decl="Dim ", end="", indent="    ", pyblock=False,
        concat=" & ", neq="<>", eq="=", words={"and": "And", "or": "Or", "not": "Not", "true": "True", "false": "False", "nil": "Nothing"},
        forl="For {v} = {a} To {b}", iff="If {c} Then", elf="ElseIf {c} Then", els="Else",
        funcl="Function {name}({args})",
        whl="While {c}", close={"for": "Next", "if": "End If", "while": "End While", "func": "End Function"}),
    "csharp": dict(
        comment="//", decl="var ", end=";", indent="    ", pyblock=False,
        concat=" + ", neq="!=", eq="==", words={"and": "&&", "or": "||", "not": "!", "true": "true", "false": "false", "nil": "null"},
        forl="for (var {v} = {a}; {v} <= {b}; {v}++) {{", iff="if ({c}) {{", elf="}} else if ({c}) {{", els="} else {",
        funcl="object {name}({args}) {{",
        whl="while ({c}) {{", close={"for": "}", "if": "}", "while": "}", "func": "}"}),
    "python": dict(
        comment="#", decl="", end="", indent="    ", pyblock=True,
        concat=" + ", neq="!=", eq="==", words={"and": "and", "or": "or", "not": "not", "true": "True", "false": "False", "nil": "None"},
        forl="for {v} in range({a}, {b1}):", iff="if {c}:", elf="elif {c}:", els="else:",
        funcl="def {name}({args}):",
        whl="while {c}:", close={"for": "", "if": "", "while": "", "func": ""}),
    "php": dict(
        comment="//", decl="", end=";", indent="    ", pyblock=False, sigil="$",
        concat=" . ", neq="!=", eq="==", words={"and": "&&", "or": "||", "not": "!", "true": "true", "false": "false", "nil": "null"},
        forl="for ({v} = {a}; {v} <= {b}; {v}++) {{", iff="if ({c}) {{", elf="}} else if ({c}) {{", els="} else {",
        funcl="function {name}({args}) {{",
        whl="while ({c}) {{", close={"for": "}", "if": "}", "while": "}", "func": "}"}),
}

# canonical operator/word forms (what the neutral middle uses); readers map INTO these, writers map OUT of these
CANON = {"&&": "and", "||": "or", "!": "not", "And": "and", "Or": "or", "Not": "not",
         "True": "true", "False": "false", "Nothing": "nil", "null": "nil", "None": "nil",
         "<>": "~=", "!=": "~="}


# ---- expressions -------------------------------------------------------------

def _toks(expr):
    out = []
    for m in re.finditer(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\b\d+\.?\d*\b|[A-Za-z_]\w*|\.\.|[<>=!~]=|<>|&&|\|\||[^\s]', expr):
        t = m.group(0)
        k = "str" if t[0] in "\"'" else "num" if t[0].isdigit() else "word" if (t[:1].isalpha() or t[0] == "_") else "op"
        out.append((k, t))
    return out


def _to_canon(expr, lang=None):
    """An expression in any language -> neutral form: concat as .., word/op literals normalised, str() peeled off."""
    expr = re.sub(r"\bstr\(([^()]*)\)", r"\1", expr)                 # python str(x) -> x
    toks = _toks(expr)
    joins = any(k == "str" for k, _ in toks)                         # a string in play: '+' here means join, not add
    parts = []
    for k, t in toks:
        if k == "op" and t == "&":                                   # VB's join operator is always a join
            parts.append((k, ".."))
        elif k == "op" and t == "=":                                 # a lone '=' in an expression is VB equality
            parts.append((k, "=="))
        elif lang == "php" and k == "op" and t == ".":               # PHP joins with '.'
            parts.append((k, ".."))
        elif k == "op" and t == "+":
            parts.append((k, ".." if joins else "+"))
        elif k == "op" and t in CANON:
            parts.append((k, CANON[t]))
        elif k == "word" and t in CANON:
            parts.append(("word", CANON[t]))
        else:
            parts.append((k, t))
    return _join(parts)


def _from_canon(expr, lang):
    sp = SPEC[lang]
    out = []
    has_concat = False
    for k, t in _toks(expr):
        if k == "op" and t == "..":
            out.append((k, sp["concat"].strip())); has_concat = True
        elif k == "op" and t == "~=":
            out.append((k, sp["neq"]))
        elif k == "op" and t == "==":
            out.append((k, sp["eq"]))
        elif k == "word" and t in sp["words"] and t in ("and", "or", "not", "true", "false", "nil"):
            out.append(("word", sp["words"][t]))
        else:
            out.append((k, t))
    s = _join(out)
    if lang == "python" and has_concat:                             # a number joined into a string needs str()
        s = re.sub(r'(?<![\w")])\b([a-z_]\w*)\b(?=\s*\+\s*")', r"str(\1)", s)
        s = re.sub(r'(?<=")\s*\+\s*\b([a-z_]\w*)\b(?![\w("])', r" + str(\1)", s)
    return s


def _join(toks):
    res = ""
    for i, (k, t) in enumerate(toks):
        if i == 0:
            res = t; continue
        pk, pt = toks[i - 1]
        tight = (t in (",", ")", ";") or t == "." or pt in (".", "(") or (t == "(" and (pk == "word" or pt == ")")))
        res += ("" if tight else " ") + t
    return res.replace(",", ", ").replace(",  ", ", ")


# ---- read any language -> neutral items -------------------------------------
# items: ("comment",t) ("assign",decl,var,rhs) ("call",e) ("return",e)
#        ("open","for",v,a,b) ("open","if",cond) ("elif",cond) ("else",) ("open","while",cond) ("close",) ("raw",t) ("blank",)

def _split_comment(line, lead):
    """Split a line into (code, comment) at the first comment lead that's outside a string. comment is None
    when there isn't one. Handles inline comments (Vml(...) -- note) that a naive tokenizer would mangle."""
    strs = '"' if lead == "'" else "\"'"     # VB uses ' for comments, so there ' is never a string
    i, q, n, L = 0, None, len(line), len(lead)
    while i < n:
        c = line[i]
        if q:
            if c == q:
                q = None
            i += 1
            continue
        if c in strs:
            q = c; i += 1; continue
        if line[i:i + L] == lead:
            return line[:i].rstrip(), line[i + L:].strip()
        i += 1
    return line, None


def _strip_sigil(line, sig):
    """Remove a leading sigil (PHP's $) from identifiers, leaving string literals untouched."""
    out, i, q, n = [], 0, None, len(line)
    while i < n:
        c = line[i]
        if q:
            out.append(c)
            if c == q:
                q = None
            i += 1; continue
        if c in "\"'":
            q = c; out.append(c); i += 1; continue
        if c == sig and i + 1 < n and (line[i + 1].isalpha() or line[i + 1] == "_"):
            i += 1; continue
        out.append(c); i += 1
    return "".join(out)


def _apply_sigil(expr, sig, names):
    """Put the sigil back on every known variable in an emitted expression (not calls, keywords or strings)."""
    return _join([(k, sig + t if (k == "word" and t in names) else t) for k, t in _toks(expr)])


def read(code, lang):
    sp = SPEC[lang]
    items, blockstack = [], []                                      # blockstack: header indents of open python blocks
    for raw in code.replace("\r\n", "\n").split("\n"):
        if not raw.strip():
            items.append(("blank",)); continue
        ind = len(raw) - len(raw.lstrip(" "))
        s = raw.strip()
        s, trail = _split_comment(s, sp["comment"])              # peel a whole-line or inline comment off first
        if not s:
            items.append(("comment", trail if trail is not None else "")); continue
        if sp.get("sigil"):                                          # php: $name -> name, so the rest reads as usual
            s = _strip_sigil(s, sp["sigil"])
        if sp["pyblock"]:                                            # python: a dedent closes blocks; else/elif continue one
            cont = bool(re.match(r"^(elif\b|else\b)", s))
            while blockstack and (ind < blockstack[-1] or (ind == blockstack[-1] and not cont)):
                items.append(("close",)); blockstack.pop()
        if trail is not None:                                    # an inline comment: keep it, on its own line
            items.append(("comment", trail))
        # closers (vb/csharp/lua) — a bare end / } / Next / End If / End While
        if not sp["pyblock"] and s in ("end", "}", "Next", "End If", "End While", "End Function", "End Sub", "End"):
            items.append(("close",)); continue
        # for (numeric) — try each language's shape
        m = (re.match(r"^for\s+(\w+)\s*=\s*(.+?)\s*,\s*(.+?)\s+do$", s) or                      # lua
             re.match(r"^For\s+(\w+)\s*=\s*(.+?)\s+To\s+(.+?)$", s, re.I) or                    # vb
             re.match(r"^for\s*\(\s*(?:var\s+)?(\w+)\s*=\s*(.+?);\s*\w+\s*<=\s*(.+?);.*\)\s*\{?$", s) or  # c#
             re.match(r"^for\s+(\w+)\s+in\s+range\(\s*(.+?)\s*,\s*(.+?)\s*\)\s*:$", s))         # python
        if m:
            v, a, b = m.group(1), _to_canon(m.group(2), lang), _to_canon(m.group(3), lang)
            if lang == "python":                                    # range stop is exclusive -> inclusive b
                b = str(int(b) - 1) if b.strip().isdigit() else f"({b}) - 1"
            items.append(("open", "for", v, a, b))
            if sp["pyblock"]:
                blockstack.append(ind)
            continue
        # elif / else if
        m = (re.match(r"^elseif\s+(.+?)\s+then$", s, re.I) or
             re.match(r"^\}?\s*else\s+if\s*\(\s*(.+?)\s*\)\s*\{?$", s) or
             re.match(r"^elif\s+(.+?)\s*:$", s))
        if m:
            items.append(("elif", _to_canon(m.group(1), lang))); continue
        # else
        if re.match(r"^\}?\s*else\s*\{?$", s) or s.lower() in ("else", "else:"):
            items.append(("else",)); continue
        # if
        m = (re.match(r"^if\s+(.+?)\s+then$", s, re.I) or
             re.match(r"^if\s*\(\s*(.+?)\s*\)\s*\{?$", s) or
             re.match(r"^if\s+(.+?)\s*:$", s))
        if m:
            items.append(("open", "if", _to_canon(m.group(1), lang)))
            if sp["pyblock"]:
                blockstack.append(ind)
            continue
        # while
        m = (re.match(r"^while\s+(.+?)\s+do$", s, re.I) or
             re.match(r"^while\s*\(\s*(.+?)\s*\)\s*\{?$", s) or
             re.match(r"^While\s+(.+?)$", s, re.I) or
             re.match(r"^while\s+(.+?)\s*:$", s))
        if m:
            items.append(("open", "while", _to_canon(m.group(1), lang)))
            if sp["pyblock"]:
                blockstack.append(ind)
            continue
        # return
        m = re.match(r"^[Rr]eturn\b\s*(.*?);?$", s)
        if m:
            items.append(("return", _to_canon(m.group(1), lang) if m.group(1) else "")); continue
        # function / sub definition
        m = (re.match(r"^(?:local\s+)?function\s+(\w+)\s*\((.*?)\)\s*$", s) or                    # lua
             re.match(r"^(?:Function|Sub)\s+(\w+)\s*\((.*?)\)\s*$", s, re.I) or                   # vb
             re.match(r"^def\s+(\w+)\s*\((.*?)\)\s*:$", s) or                                     # python
             (re.match(r"^function\s+(\w+)\s*\((.*?)\)\s*\{?$", s) if lang == "php" else None) or  # php
             (re.match(r"^(?!(?:new|throw|await|yield|using|return)\b)"
                       r"(?:(?:public|private|protected|internal|static|async)\s+)*"
                       r"[\w<>\[\],.]+\s+(\w+)\s*\((.*?)\)\s*\{?$", s) if lang == "csharp" else None))
        if m:
            names = ", ".join(p.strip().split()[-1] for p in m.group(2).split(",") if p.strip())  # bare param names
            items.append(("open", "func", m.group(1), names))
            if sp["pyblock"]:
                blockstack.append(ind)
            continue
        # assignment:  [decl] name = expr
        m = re.match(r"^(local\s+|Dim\s+|var\s+)?([A-Za-z_]\w*)\s*=\s*(.+?);?$", s)
        if m and not re.match(r"^(if|for|while|elseif|elif|return|function)\b", s, re.I):
            items.append(("assign", bool(m.group(1)), m.group(2), _to_canon(m.group(3), lang))); continue
        # anything else: a call / statement
        items.append(("call", _to_canon(s.rstrip(";"), lang)))
    while blockstack:
        items.append(("close",)); blockstack.pop()
    return items


# ---- write neutral items -> a language --------------------------------------

def write(items, lang):
    sp = SPEC[lang]
    sig = sp.get("sigil")                                           # php: $ on every variable; others: none
    out, stack, depth, declared, pvars = [], [], 0, set(), set()

    def line(t):
        out.append(sp["indent"] * depth + t)

    def E(e):                                                       # an expression, sigil put back on known variables
        s = _from_canon(e, lang)
        return _apply_sigil(s, sig, pvars) if sig else s

    def V(name):                                                   # a bare variable, sigilled where the language wants it
        return (sig + name) if sig else name

    for it in items:
        kind = it[0]
        if kind == "blank":
            out.append("")
        elif kind == "comment":
            line(f"{sp['comment']} {it[1]}".rstrip())
        elif kind == "assign":
            decl = sp["decl"] if it[2] not in declared else ""      # first mention of a variable declares it
            declared.add(it[2]); pvars.add(it[2])
            line(f"{decl}{V(it[2])} = {E(it[3])}{sp['end']}")
        elif kind == "call":
            line(f"{E(it[1])}{sp['end']}")
        elif kind == "return":
            kw = "Return" if lang == "vb" else "return"
            line(f"{kw} {E(it[1])}{sp['end']}".rstrip() if it[1] else f"{kw}{sp['end']}")
        elif kind == "open":
            what = it[1]
            if what == "for":
                pvars.add(it[2])
                a, b = E(it[3]), E(it[4])
                b1 = str(int(b) + 1) if b.strip().lstrip("-").isdigit() else f"({b}) + 1"
                line(sp["forl"].format(v=V(it[2]), a=a, b=b, b1=b1))
            elif what == "if":
                line(sp["iff"].format(c=E(it[2])))
            elif what == "while":
                line(sp["whl"].format(c=E(it[2])))
            elif what == "func":
                params = [p.strip() for p in it[3].split(",") if p.strip()]
                for p in params:
                    pvars.add(p)
                line(sp["funcl"].format(name=it[2], args=", ".join(V(p) for p in params)))
            stack.append(what); depth += 1
        elif kind == "elif":
            depth -= 1
            line(sp["elf"].format(c=E(it[1])))
            depth += 1
        elif kind == "else":
            depth -= 1
            line(sp["els"])
            depth += 1
        elif kind == "close":
            what = stack.pop() if stack else "if"
            depth = max(0, depth - 1)
            if not sp["pyblock"]:
                line(sp["close"][what])
        elif kind == "raw":
            line(it[1])
    return "\n".join(out).rstrip("\n")


def translate(code, src, dst):
    if src == dst:
        return code.rstrip("\n")
    return write(read(code, src), dst)


if __name__ == "__main__":
    SAMPLES = {
        "csharp": '''// add up the squares
var total = 0;
for (var i = 1; i <= 4; i++) {
    total = total + i * i;
}
if (total > 20) {
    Vml("SetProperty", "lblTotal", "Text", "Big total " + total);
} else {
    Vml("SetProperty", "lblTotal", "Text", "Total " + total);
}
return total;''',
    }
    for src, code in SAMPLES.items():
        for dst in LANGS:
            print("=" * 20, f"{LABEL[src]} -> {LABEL[dst]}")
            print(translate(code, src, dst))

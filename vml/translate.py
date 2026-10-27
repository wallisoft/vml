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

LANGS = ("lua", "vb", "csharp", "python")
LABEL = {"lua": "Lua", "vb": "VB", "csharp": "C#", "python": "Python"}

# Each language, declared as data. {a} {b} {v} {c} are filled in by the engine.
SPEC = {
    "lua": dict(
        comment="--", decl="local ", end="", indent="  ", pyblock=False,
        concat="..", neq="~=", words={"and": "and", "or": "or", "not": "not", "true": "true", "false": "false", "nil": "nil"},
        forl="for {v} = {a}, {b} do", iff="if {c} then", elf="elseif {c} then", els="else",
        whl="while {c} do", close={"for": "end", "if": "end", "while": "end"}),
    "vb": dict(
        comment="'", decl="Dim ", end="", indent="    ", pyblock=False,
        concat=" & ", neq="<>", words={"and": "And", "or": "Or", "not": "Not", "true": "True", "false": "False", "nil": "Nothing"},
        forl="For {v} = {a} To {b}", iff="If {c} Then", elf="ElseIf {c} Then", els="Else",
        whl="While {c}", close={"for": "Next", "if": "End If", "while": "End While"}),
    "csharp": dict(
        comment="//", decl="var ", end=";", indent="    ", pyblock=False,
        concat=" + ", neq="!=", words={"and": "&&", "or": "||", "not": "!", "true": "true", "false": "false", "nil": "null"},
        forl="for (var {v} = {a}; {v} <= {b}; {v}++) {{", iff="if ({c}) {{", elf="}} else if ({c}) {{", els="} else {",
        whl="while ({c}) {{", close={"for": "}", "if": "}", "while": "}"}),
    "python": dict(
        comment="#", decl="", end="", indent="    ", pyblock=True,
        concat=" + ", neq="!=", words={"and": "and", "or": "or", "not": "not", "true": "True", "false": "False", "nil": "None"},
        forl="for {v} in range({a}, {b1}):", iff="if {c}:", elf="elif {c}:", els="else:",
        whl="while {c}:", close={"for": "", "if": "", "while": ""}),
}

# canonical operator/word forms (what the neutral middle uses); readers map INTO these, writers map OUT of these
CANON = {"&&": "and", "||": "or", "!": "not", "And": "and", "Or": "or", "Not": "not",
         "True": "true", "False": "false", "Nothing": "nil", "null": "nil", "None": "nil",
         "<>": "~=", "!=": "~="}


# ---- expressions -------------------------------------------------------------

def _toks(expr):
    out = []
    for m in re.finditer(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\b\d+\.?\d*\b|[A-Za-z_]\w*|\.\.|[<>=!~]=|&&|\|\||[^\s]', expr):
        t = m.group(0)
        k = "str" if t[0] in "\"'" else "num" if t[0].isdigit() else "word" if (t[:1].isalpha() or t[0] == "_") else "op"
        out.append((k, t))
    return out


def _to_canon(expr):
    """An expression in any language -> neutral form: concat as .., word/op literals normalised, str() peeled off."""
    expr = re.sub(r"\bstr\(([^()]*)\)", r"\1", expr)                 # python str(x) -> x
    toks = _toks(expr)
    joins = any(k == "str" for k, _ in toks)                         # a string in play: '+' here means join, not add
    parts = []
    for k, t in toks:
        if k == "op" and t == "&":                                   # VB's join operator is always a join
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
        if sp["pyblock"]:                                            # python: a dedent closes blocks; else/elif continue one
            cont = bool(re.match(r"^(elif\b|else\b)", s))
            while blockstack and (ind < blockstack[-1] or (ind == blockstack[-1] and not cont)):
                items.append(("close",)); blockstack.pop()
        if trail is not None:                                    # an inline comment: keep it, on its own line
            items.append(("comment", trail))
        # closers (vb/csharp/lua) — a bare end / } / Next / End If / End While
        if not sp["pyblock"] and s in ("end", "}", "Next", "End If", "End While", "End"):
            items.append(("close",)); continue
        # for (numeric) — try each language's shape
        m = (re.match(r"^for\s+(\w+)\s*=\s*(.+?)\s*,\s*(.+?)\s+do$", s) or                      # lua
             re.match(r"^For\s+(\w+)\s*=\s*(.+?)\s+To\s+(.+?)$", s, re.I) or                    # vb
             re.match(r"^for\s*\(\s*(?:var\s+)?(\w+)\s*=\s*(.+?);\s*\w+\s*<=\s*(.+?);.*\)\s*\{?$", s) or  # c#
             re.match(r"^for\s+(\w+)\s+in\s+range\(\s*(.+?)\s*,\s*(.+?)\s*\)\s*:$", s))         # python
        if m:
            v, a, b = m.group(1), _to_canon(m.group(2)), _to_canon(m.group(3))
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
            items.append(("elif", _to_canon(m.group(1)))); continue
        # else
        if re.match(r"^\}?\s*else\s*\{?$", s) or s.lower() in ("else", "else:"):
            items.append(("else",)); continue
        # if
        m = (re.match(r"^if\s+(.+?)\s+then$", s, re.I) or
             re.match(r"^if\s*\(\s*(.+?)\s*\)\s*\{?$", s) or
             re.match(r"^if\s+(.+?)\s*:$", s))
        if m:
            items.append(("open", "if", _to_canon(m.group(1))))
            if sp["pyblock"]:
                blockstack.append(ind)
            continue
        # while
        m = (re.match(r"^while\s+(.+?)\s+do$", s, re.I) or
             re.match(r"^while\s*\(\s*(.+?)\s*\)\s*\{?$", s) or
             re.match(r"^While\s+(.+?)$", s, re.I) or
             re.match(r"^while\s+(.+?)\s*:$", s))
        if m:
            items.append(("open", "while", _to_canon(m.group(1))))
            if sp["pyblock"]:
                blockstack.append(ind)
            continue
        # return
        m = re.match(r"^[Rr]eturn\b\s*(.*?);?$", s)
        if m:
            items.append(("return", _to_canon(m.group(1)) if m.group(1) else "")); continue
        # assignment:  [decl] name = expr
        m = re.match(r"^(local\s+|Dim\s+|var\s+)?([A-Za-z_]\w*)\s*=\s*(.+?);?$", s)
        if m and not re.match(r"^(if|for|while|elseif|elif|return|function)\b", s, re.I):
            items.append(("assign", bool(m.group(1)), m.group(2), _to_canon(m.group(3)))); continue
        # anything else: a call / statement
        items.append(("call", _to_canon(s.rstrip(";"))))
    while blockstack:
        items.append(("close",)); blockstack.pop()
    return items


# ---- write neutral items -> a language --------------------------------------

def write(items, lang):
    if lang == "lua" and False:
        pass
    sp = SPEC[lang]
    out, stack, depth, declared = [], [], 0, set()

    def line(t):
        out.append(sp["indent"] * depth + t)

    for it in items:
        kind = it[0]
        if kind == "blank":
            out.append("")
        elif kind == "comment":
            line(f"{sp['comment']} {it[1]}".rstrip())
        elif kind == "assign":
            decl = sp["decl"] if it[2] not in declared else ""      # first mention of a variable declares it
            declared.add(it[2])
            line(f"{decl}{it[2]} = {_from_canon(it[3], lang)}{sp['end']}")
        elif kind == "call":
            line(f"{_from_canon(it[1], lang)}{sp['end']}")
        elif kind == "return":
            kw = "Return" if lang == "vb" else "return"
            line(f"{kw} {_from_canon(it[1], lang)}{sp['end']}".rstrip() if it[1] else f"{kw}{sp['end']}")
        elif kind == "open":
            what = it[1]
            if what == "for":
                v, a, b = it[2], _from_canon(it[3], lang), _from_canon(it[4], lang)
                b1 = str(int(b) + 1) if b.strip().lstrip("-").isdigit() else f"({b}) + 1"
                line(sp["forl"].format(v=v, a=a, b=b, b1=b1))
            elif what == "if":
                line(sp["iff"].format(c=_from_canon(it[2], lang)))
            elif what == "while":
                line(sp["whl"].format(c=_from_canon(it[2], lang)))
            stack.append(what); depth += 1
        elif kind == "elif":
            depth -= 1
            line(sp["elf"].format(c=_from_canon(it[1], lang)))
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

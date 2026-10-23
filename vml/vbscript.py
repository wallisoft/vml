r"""
A small, classic-VB-flavoured interpreter for Visualised scripts (Interpreter=vb).

Pure Python, in-process, no .NET — the lightweight option beside Lua, for people who think
in VB. Case-insensitive, loose typing. A script talks to the app through Vml(command, ...),
the very same bridge Lua uses, and an event handler is just a Sub named for it:

    @Script OnClick
    Interpreter=vb
    <<VB
    Sub OnClick()
        Dim name
        name = Trim(Vml("GetProperty", "txtName", "Text"))
        If name = "" Then
            Vml("SetProperty", "lblHi", "Text", "Who are you?")
        Else
            Vml("SetProperty", "lblHi", "Text", "Hello, " & name & "!")
        End If
    End Sub
    VB

Supported: Dim, assignment, If/ElseIf/Else (single- and multi-line), For/Next (+Step),
For Each/In, Do/Loop (While/Until, either end), While/Wend, Select Case, Sub/Function
(params, Exit, `name = value` or Return for the result, Call), the operators
^ * / \ Mod + - & = <> < > <= >= And Or Xor Not, ( ), comments (' and Rem), _ line
continuation, and the usual built-ins (Len, Left, Right, Mid, Trim, UCase, InStr, Replace,
CStr, CInt, CDbl, Chr, Asc, MsgBox, ...). Everything is case-insensitive.

This is a useful subset, not the whole language — the full VB.NET lives on the .NET path.
"""
import re


class VbError(Exception):
    pass


# control-flow signals (not errors)
class _Exit(Exception):
    def __init__(self, what):
        self.what = what   # "sub" | "function" | "for" | "do"


class _Return(Exception):
    def __init__(self, value):
        self.value = value


EMPTY = ""   # VB Empty: reads as "" / 0 depending on context

# ---------------------------------------------------------------- lexer

_TOKEN = re.compile(r"""
    (?P<ws>[ \t]+)
  | (?P<num>\d+\.\d+|\.\d+|\d+)
  | (?P<str>"(?:[^"]|"")*")
  | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op><=|>=|<>|[-+*/\\^&=<>().,])
""", re.VERBOSE)

WORD_OPS = {"and", "or", "xor", "mod", "not"}


def _tokenize(s):
    toks, i = [], 0
    while i < len(s):
        m = _TOKEN.match(s, i)
        if not m:
            raise VbError(f"can't read {s[i]!r}")
        i = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        val = m.group()
        if kind == "str":
            val = val[1:-1].replace('""', '"')
        toks.append((kind, val))
    return toks


def _strip_comment(line):
    out, q, i = [], False, 0
    while i < len(line):
        c = line[i]
        if c == '"':
            q = not q
        elif c == "'" and not q:
            break
        out.append(c)
        i += 1
    return "".join(out)


def _logical_lines(code):
    """Physical lines -> logical ones: join `_` continuations, drop comments and blanks.
    Each item is (tokens, source_text) for error messages."""
    phys = code.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    joined, buf = [], ""
    for ln in phys:
        cur = buf + ln
        stripped = _strip_comment(cur)
        if stripped.rstrip().endswith("_") and not stripped.rstrip().endswith("__"):
            buf = stripped.rstrip()[:-1] + " "
            continue
        buf = ""
        joined.append(stripped)
    if buf:
        joined.append(buf)
    out = []
    for ln in joined:
        t = ln.strip()
        if not t:
            continue
        low = t.lower()
        if low == "rem" or low.startswith("rem "):
            continue
        out.append((_tokenize(t), t))
    return out


# ---------------------------------------------------------------- parser (line/block structured)

def kw(tok):
    return tok[0] == "id" and tok[1].lower()


class Parser:
    def __init__(self, lines):
        self.lines = lines
        self.i = 0

    def peek_kw(self):
        if self.i >= len(self.lines):
            return None
        toks = self.lines[self.i][0]
        return toks[0][1].lower() if toks and toks[0][0] == "id" else None

    def block(self, enders):
        """Parse statements until (not consuming) a line starting with one of `enders`."""
        stmts = []
        while self.i < len(self.lines):
            if self.peek_kw() in enders:
                return stmts
            stmts.append(self.statement())
        if enders:
            raise VbError(f"missing {' / '.join(sorted(enders))}")
        return stmts

    def statement(self):
        toks, src = self.lines[self.i]
        head = toks[0][1].lower() if toks[0][0] == "id" else None
        if head == "dim":
            self.i += 1
            names = [t[1] for t in toks[1:] if t[0] == "id" and t[1].lower() != "as"]
            # stop names at "As" (ignore the type)
            out = []
            for t in toks[1:]:
                if t[0] == "id" and t[1].lower() == "as":
                    break
                if t[0] == "id":
                    out.append(t[1])
            return ("dim", out or names)
        if head == "if":
            return self.if_stmt(toks)
        if head == "for":
            if len(toks) > 1 and toks[1][0] == "id" and toks[1][1].lower() == "each":
                return self.for_each(toks)
            return self.for_stmt(toks)
        if head == "do":
            return self.do_stmt(toks)
        if head == "while":
            return self.while_stmt(toks)
        if head == "select":
            return self.select_stmt(toks)
        if head in ("sub", "function"):
            return self.proc_stmt(toks, head)
        if head == "exit":
            self.i += 1
            what = toks[1][1].lower() if len(toks) > 1 and toks[1][0] == "id" else ""
            return ("exit", what)
        if head == "return":
            self.i += 1
            expr = parse_expr(toks[1:]) if len(toks) > 1 else ("lit", EMPTY)
            return ("return", expr)
        if head == "call":
            self.i += 1
            return ("callstmt", parse_call(toks[1:]))
        if head == "set":
            self.i += 1
            return self.assign_or_call(toks[1:], src)
        self.i += 1
        return self.assign_or_call(toks, src)

    def assign_or_call(self, toks, src):
        # assignment if there's a top-level '=' ; else a call statement
        depth = 0
        for j, t in enumerate(toks):
            if t[0] == "op" and t[1] == "(":
                depth += 1
            elif t[0] == "op" and t[1] == ")":
                depth -= 1
            elif depth == 0 and t[0] == "op" and t[1] == "=":
                target = toks[:j]
                if not target or target[0][0] != "id":
                    raise VbError(f"can't assign here: {src}")
                return ("assign", target[0][1], parse_expr(toks[j + 1:]))
        # a bare call: Name arg1, arg2   or   Name(arg1, arg2)
        if toks and toks[0][0] == "id":
            if len(toks) > 1 and toks[1] == ("op", "(") and toks[-1] == ("op", ")"):
                return ("callstmt", parse_call(toks))
            name = toks[0][1]
            args = split_args(toks[1:])
            return ("callstmt", ("call", name, args))
        raise VbError(f"don't understand: {src}")

    def if_stmt(self, toks):
        # find top-level Then
        ti = find_kw(toks, "then")
        if ti is None:
            raise VbError("If without Then")
        cond = parse_expr(toks[1:ti])
        after = toks[ti + 1:]
        if after:   # single-line If ... Then <stmt> [Else <stmt>]
            self.i += 1
            ei = find_kw(after, "else")
            then_toks = after[:ei] if ei is not None else after
            else_toks = after[ei + 1:] if ei is not None else []
            then_s = [self._inline(then_toks)] if then_toks else []
            else_s = [self._inline(else_toks)] if else_toks else []
            return ("if", [(cond, then_s)], else_s)
        # multi-line
        self.i += 1
        branches = []
        body = self.block({"elseif", "else", "end"})
        branches.append((cond, body))
        while self.peek_kw() == "elseif":
            et, _ = self.lines[self.i]
            eti = find_kw(et, "then")
            econd = parse_expr(et[1:eti])
            self.i += 1
            branches.append((econd, self.block({"elseif", "else", "end"})))
        else_body = []
        if self.peek_kw() == "else":
            self.i += 1
            else_body = self.block({"end"})
        self._end("if")
        return ("if", branches, else_body)

    def _inline(self, toks):
        # parse a single inline statement (for single-line If)
        head = toks[0][1].lower() if toks[0][0] == "id" else None
        if head == "exit":
            return ("exit", toks[1][1].lower() if len(toks) > 1 else "")
        if head == "call":
            return ("callstmt", parse_call(toks[1:]))
        if head == "return":
            return ("return", parse_expr(toks[1:]) if len(toks) > 1 else ("lit", EMPTY))
        # assign or call, reuse logic without consuming lines
        depth = 0
        for j, t in enumerate(toks):
            if t == ("op", "("):
                depth += 1
            elif t == ("op", ")"):
                depth -= 1
            elif depth == 0 and t == ("op", "="):
                return ("assign", toks[0][1], parse_expr(toks[j + 1:]))
        if len(toks) > 1 and toks[1] == ("op", "(") and toks[-1] == ("op", ")"):
            return ("callstmt", parse_call(toks))
        return ("callstmt", ("call", toks[0][1], split_args(toks[1:])))

    def for_stmt(self, toks):
        # For <var> = <a> To <b> [Step <c>]
        var = toks[1][1]
        eq = find_op(toks, "=")
        toi = find_kw(toks, "to")
        si = find_kw(toks, "step")
        start = parse_expr(toks[eq + 1:toi])
        if si is not None:
            stop = parse_expr(toks[toi + 1:si])
            step = parse_expr(toks[si + 1:])
        else:
            stop = parse_expr(toks[toi + 1:])
            step = ("lit", 1)
        self.i += 1
        body = self.block({"next"})
        self._next()
        return ("for", var, start, stop, step, body)

    def for_each(self, toks):
        var = toks[2][1]
        ini = find_kw(toks, "in")
        seq = parse_expr(toks[ini + 1:])
        self.i += 1
        body = self.block({"next"})
        self._next()
        return ("foreach", var, seq, body)

    def do_stmt(self, toks):
        pre = None  # (kind, expr) with kind in while/until, at the top
        if len(toks) > 1 and kw(toks[1]) in ("while", "until"):
            pre = (kw(toks[1]), parse_expr(toks[2:]))
        self.i += 1
        body = self.block({"loop"})
        lt, _ = self.lines[self.i]
        post = None
        if len(lt) > 1 and kw(lt[1]) in ("while", "until"):
            post = (kw(lt[1]), parse_expr(lt[2:]))
        self.i += 1  # consume Loop
        return ("do", pre, post, body)

    def while_stmt(self, toks):
        cond = parse_expr(toks[1:])
        self.i += 1
        body = self.block({"wend"})
        self.i += 1
        return ("do", ("while", cond), None, body)

    def select_stmt(self, toks):
        # Select Case <expr>
        ci = find_kw(toks, "case")
        subj = parse_expr(toks[ci + 1:])
        self.i += 1
        cases = []   # (list_of_exprs_or_None_for_else, body)
        while self.peek_kw() == "case":
            ct, _ = self.lines[self.i]
            self.i += 1
            if len(ct) > 1 and kw(ct[1]) == "else":
                tests = None
            else:
                tests = [parse_expr(g) for g in split_args(ct[1:])]
            body = self.block({"case", "end"})
            cases.append((tests, body))
        self._end("select")
        return ("select", subj, cases)

    def proc_stmt(self, toks, kind):
        name = toks[1][1]
        params = []
        op = find_op(toks, "(")
        if op is not None:
            cp = find_op(toks, ")")
            inner = toks[op + 1:cp]
            for g in split_args(inner):
                ids = [t[1] for t in g if t[0] == "id" and t[1].lower() not in ("byval", "byref")]
                if ids:
                    params.append(ids[0])
        self.i += 1
        body = self.block({"end"})
        self._end(kind)
        return ("proc", kind, name, params, body)

    def _end(self, what):
        kwd = self.peek_kw()
        if kwd != "end":
            raise VbError(f"expected End {what.capitalize()}")
        self.i += 1

    def _next(self):
        if self.peek_kw() != "next":
            raise VbError("For without Next")
        self.i += 1


# ---- token helpers ----

def find_kw(toks, word):
    depth = 0
    for j, t in enumerate(toks):
        if t == ("op", "("):
            depth += 1
        elif t == ("op", ")"):
            depth -= 1
        elif depth == 0 and t[0] == "id" and t[1].lower() == word:
            return j
    return None


def find_op(toks, op):
    depth = 0
    for j, t in enumerate(toks):
        if t == ("op", "("):
            depth += 1
            if op == "(" and depth == 1:
                return j
        elif t == ("op", ")"):
            if op == ")" and depth == 1:
                return j
            depth -= 1
        elif depth == 0 and t == ("op", op):
            return j
    return None


def split_args(toks):
    """Split a token list on top-level commas into groups (each a token list)."""
    if not toks:
        return []
    groups, cur, depth = [], [], 0
    for t in toks:
        if t == ("op", "("):
            depth += 1
            cur.append(t)
        elif t == ("op", ")"):
            depth -= 1
            cur.append(t)
        elif depth == 0 and t == ("op", ","):
            groups.append(cur)
            cur = []
        else:
            cur.append(t)
    groups.append(cur)
    return [g for g in groups]


def parse_call(toks):
    # Name ( args )
    name = toks[0][1]
    op = find_op(toks, "(")
    if op is None:
        return ("call", name, split_args(toks[1:]))
    cp = find_op(toks, ")")
    inner = toks[op + 1:cp if cp is not None else len(toks)]
    args = split_args(inner) if inner else []
    return ("call", name, args)


# ---------------------------------------------------------------- expressions (precedence climbing)

# low -> high
def parse_expr(toks):
    toks = [t for t in toks if t != ("op", "")]
    if not toks:
        return ("lit", EMPTY)
    p = _Expr(toks)
    node = p.parse(0)
    if p.i != len(p.toks):
        raise VbError("trailing tokens in expression")
    return node


_BINLEVELS = [
    {"or": "or", "xor": "xor"},
    {"and": "and"},
    {"=": "=", "<>": "<>", "<": "<", ">": ">", "<=": "<=", ">=": ">="},
    {"&": "&"},
    {"+": "+", "-": "-"},
    {"*": "*", "/": "/", "\\": "\\", "mod": "mod"},
    {"^": "^"},
]


class _Expr:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def at(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def opval(self):
        t = self.at()
        if t[0] == "op":
            return t[1]
        if t[0] == "id" and t[1].lower() in WORD_OPS:
            return t[1].lower()
        return None

    def parse(self, level):
        if level == 1:  # unary Not sits just above And
            # handle Not as prefix
            if self.opval() == "not":
                self.i += 1
                return ("not", self.parse(level))
        if level >= len(_BINLEVELS):
            return self.unary()
        left = self.parse(level + 1)
        while True:
            op = self.opval()
            if op in _BINLEVELS[level]:
                self.i += 1
                right = self.parse(level + 1)
                left = ("bin", _BINLEVELS[level][op], left, right)
            else:
                return left

    def unary(self):
        if self.at() == ("op", "-"):
            self.i += 1
            return ("neg", self.unary())
        if self.opval() == "not":
            self.i += 1
            return ("not", self.unary())
        return self.atom()

    def atom(self):
        kind, val = self.at()
        if kind == "num":
            self.i += 1
            return ("lit", float(val) if "." in val else int(val))
        if kind == "str":
            self.i += 1
            return ("lit", val)
        if kind == "op" and val == "(":
            self.i += 1
            node = self.parse(0)
            if self.at() != ("op", ")"):
                raise VbError("missing )")
            self.i += 1
            return node
        if kind == "id":
            low = val.lower()
            if low in ("true", "false"):
                self.i += 1
                return ("lit", low == "true")
            if low in ("nothing", "null", "empty"):
                self.i += 1
                return ("lit", EMPTY)
            self.i += 1
            if self.at() == ("op", "("):   # a call
                self.i += 1
                args = []
                if self.at() != ("op", ")"):
                    args.append(self.parse(0))
                    while self.at() == ("op", ","):
                        self.i += 1
                        args.append(self.parse(0))
                if self.at() != ("op", ")"):
                    raise VbError(f"missing ) after {val}(")
                self.i += 1
                return ("callexpr", val, args)
            return ("var", val)
        raise VbError(f"unexpected {val!r} in expression")


# ---------------------------------------------------------------- values / coercion

def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def to_num(v):
    if isinstance(v, bool):
        return -1 if v else 0        # VB True = -1
    if is_num(v):
        return v
    s = str(v).strip()
    if s == "":
        return 0
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            raise VbError(f"'{v}' is not a number")


def to_str(v):
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if v is None:
        return ""
    return str(v)


def truth(v):
    if isinstance(v, bool):
        return v
    if is_num(v):
        return v != 0
    return str(v) not in ("", "0", "False", "false")


# ---------------------------------------------------------------- interpreter

class Frame:
    def __init__(self, module, locals_=None):
        self.module = module
        self.locals = locals_ if locals_ is not None else module

    def get(self, name):
        n = name.lower()
        if n in self.locals:
            return self.locals[n]
        if n in self.module:
            return self.module[n]
        return EMPTY

    def set(self, name, val):
        n = name.lower()
        if n in self.locals or n not in self.module:
            self.locals[n] = val
        else:
            self.module[n] = val

    def dim(self, name):
        self.locals.setdefault(name.lower(), EMPTY)


class VbEnv:
    """One per form (like a Lua state): module-level vars and the Subs/Functions it has defined."""

    def __init__(self, host=None, log=print):
        self.vars = {}
        self.procs = {}       # name.lower() -> ("proc", kind, name, params, body)
        self.host = host      # host(command, *args) -> Vml bridge
        self.log = log

    # -- public entry --
    def run(self, code, args=(), label="vb"):
        parser = Parser(_logical_lines(code))
        stmts = parser.block(set())
        top = Frame(self.vars)
        top.locals["args"] = list(args)
        # run top-level (registers procs, runs any loose statements)
        self.exec_block(stmts, top)
        # if a Sub/Function matches the handler name, call it
        if label and label.lower() in self.procs:
            return self.call_proc(self.procs[label.lower()], list(args))
        return ""

    # -- statements --
    def exec_block(self, stmts, frame):
        for s in stmts:
            self.exec_stmt(s, frame)

    def exec_stmt(self, s, frame):
        op = s[0]
        if op == "dim":
            for n in s[1]:
                frame.dim(n)
        elif op == "assign":
            frame.set(s[1], self.eval(s[2], frame))
        elif op == "callstmt":
            self.eval(s[1], frame)
        elif op == "if":
            for cond, body in s[1]:
                if truth(self.eval(cond, frame)):
                    self.exec_block(body, frame)
                    return
            self.exec_block(s[2], frame)
        elif op == "for":
            _, var, a, b, st, body = s
            i = to_num(self.eval(a, frame))
            end = to_num(self.eval(b, frame))
            step = to_num(self.eval(st, frame))
            frame.set(var, i)
            while (step >= 0 and frame.get(var) <= end) or (step < 0 and frame.get(var) >= end):
                try:
                    self.exec_block(body, frame)
                except _Exit as ex:
                    if ex.what in ("for", ""):
                        break
                    raise
                frame.set(var, to_num(frame.get(var)) + step)
        elif op == "foreach":
            _, var, seqx, body = s
            seq = self.eval(seqx, frame)
            if isinstance(seq, str):
                seq = [seq]
            for item in seq:
                frame.set(var, item)
                try:
                    self.exec_block(body, frame)
                except _Exit as ex:
                    if ex.what in ("for", ""):
                        break
                    raise
        elif op == "do":
            _, pre, post, body = s
            while True:
                if pre:
                    k, e = pre
                    ok = truth(self.eval(e, frame))
                    if (k == "while" and not ok) or (k == "until" and ok):
                        break
                try:
                    self.exec_block(body, frame)
                except _Exit as ex:
                    if ex.what in ("do", ""):
                        break
                    raise
                if post:
                    k, e = post
                    ok = truth(self.eval(e, frame))
                    if (k == "while" and not ok) or (k == "until" and ok):
                        break
                if not pre and not post:
                    break   # a Do/Loop with no condition would spin; stop (be forgiving)
        elif op == "select":
            _, subjx, cases = s
            subj = self.eval(subjx, frame)
            for tests, body in cases:
                if tests is None:
                    self.exec_block(body, frame)
                    return
                for te in tests:
                    if equal(subj, self.eval(te, frame)):
                        self.exec_block(body, frame)
                        return
        elif op == "proc":
            self.procs[s[2].lower()] = s
        elif op == "exit":
            raise _Exit(s[1])
        elif op == "return":
            raise _Return(self.eval(s[1], frame))
        else:
            raise VbError(f"can't run statement {op}")

    # -- calls --
    def call_proc(self, proc, args):
        _, kind, name, params, body = proc
        loc = {}
        for i, p in enumerate(params):
            loc[p.lower()] = args[i] if i < len(args) else EMPTY
        loc[name.lower()] = EMPTY          # VB: a Function returns via its own name
        frame = Frame(self.vars, loc)
        try:
            self.exec_block(body, frame)
        except _Exit as ex:
            if ex.what not in ("sub", "function", ""):
                raise
        except _Return as r:
            return r.value
        return loc.get(name.lower(), EMPTY) if kind == "function" else ""

    # -- expressions --
    def eval(self, node, frame):
        t = node[0]
        if t == "lit":
            return node[1]
        if t == "var":
            return frame.get(node[1])
        if t == "neg":
            return -to_num(self.eval(node[1], frame))
        if t == "not":
            v = self.eval(node[1], frame)
            if isinstance(v, bool):
                return not v
            return ~int(to_num(v))
        if t == "bin":
            return self.binop(node[1], self.eval(node[2], frame), self.eval(node[3], frame))
        if t in ("call", "callexpr"):
            name = node[1]
            rawargs = node[2]
            if t == "call":
                argvals = [self.eval(parse_expr(g), frame) for g in rawargs]
            else:
                argvals = [self.eval(a, frame) for a in rawargs]
            return self.invoke(name, argvals, frame)
        raise VbError(f"can't evaluate {t}")

    def binop(self, op, a, b):
        if op == "&":
            return to_str(a) + to_str(b)
        if op in ("=", "<>", "<", ">", "<=", ">="):
            return compare(op, a, b)
        if op in ("and", "or", "xor"):
            if isinstance(a, bool) and isinstance(b, bool):
                return {"and": a and b, "or": a or b, "xor": a != b}[op]
            ai, bi = int(to_num(a)), int(to_num(b))
            return {"and": ai & bi, "or": ai | bi, "xor": ai ^ bi}[op]
        x, y = to_num(a), to_num(b)
        if op == "+":
            return x + y
        if op == "-":
            return x - y
        if op == "*":
            return x * y
        if op == "/":
            if y == 0:
                raise VbError("division by zero")
            return x / y
        if op == "\\":
            return int(x) // int(y)
        if op == "mod":
            return int(x) % int(y)
        if op == "^":
            return x ** y
        raise VbError(f"bad operator {op}")

    def invoke(self, name, args, frame):
        low = name.lower()
        if low in self.procs:
            return self.call_proc(self.procs[low], args)
        if low == "vml":
            if self.host is None:
                self.log(f"[vb] Vml({args[0] if args else ''}) — no host")
                return ""
            return self.host(*[to_str(a) if not is_num(a) and not isinstance(a, bool) else a for a in args])
        if low in BUILTINS:
            return BUILTINS[low](self, args)
        # unknown name with no args: treat as a variable read (forgiving)
        if not args:
            return frame.get(name)
        raise VbError(f"unknown '{name}'")


# ---------------------------------------------------------------- comparisons

def _both_num(a, b):
    return (is_num(a) or isinstance(a, bool)) and (is_num(b) or isinstance(b, bool))


def equal(a, b):
    if _both_num(a, b):
        return to_num(a) == to_num(b)
    return to_str(a) == to_str(b)


def compare(op, a, b):
    if _both_num(a, b):
        x, y = to_num(a), to_num(b)
    else:
        x, y = to_str(a), to_str(b)
    return {"=": x == y, "<>": x != y, "<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y}[op]


# ---------------------------------------------------------------- built-in functions

def _arg(args, i, default=EMPTY):
    return args[i] if i < len(args) else default


BUILTINS = {
    "len": lambda e, a: len(to_str(_arg(a, 0))),
    "left": lambda e, a: to_str(_arg(a, 0))[:int(to_num(_arg(a, 1, 0)))],
    "right": lambda e, a: to_str(_arg(a, 0))[-int(to_num(_arg(a, 1, 0))):] if int(to_num(_arg(a, 1, 0))) else "",
    "mid": lambda e, a: _mid(a),
    "trim": lambda e, a: to_str(_arg(a, 0)).strip(),
    "ltrim": lambda e, a: to_str(_arg(a, 0)).lstrip(),
    "rtrim": lambda e, a: to_str(_arg(a, 0)).rstrip(),
    "ucase": lambda e, a: to_str(_arg(a, 0)).upper(),
    "lcase": lambda e, a: to_str(_arg(a, 0)).lower(),
    "replace": lambda e, a: to_str(_arg(a, 0)).replace(to_str(_arg(a, 1)), to_str(_arg(a, 2))),
    "instr": lambda e, a: to_str(_arg(a, 0)).find(to_str(_arg(a, 1))) + 1,
    "cstr": lambda e, a: to_str(_arg(a, 0)),
    "cint": lambda e, a: int(round(to_num(_arg(a, 0, 0)))),
    "clng": lambda e, a: int(round(to_num(_arg(a, 0, 0)))),
    "cdbl": lambda e, a: float(to_num(_arg(a, 0, 0))),
    "val": lambda e, a: _val(_arg(a, 0, 0)),
    "str": lambda e, a: (" " if to_num(_arg(a, 0, 0)) >= 0 else "") + to_str(to_num(_arg(a, 0, 0))),
    "chr": lambda e, a: chr(int(to_num(_arg(a, 0, 0)))),
    "asc": lambda e, a: ord(to_str(_arg(a, 0, " "))[:1] or " "),
    "abs": lambda e, a: abs(to_num(_arg(a, 0, 0))),
    "int": lambda e, a: int(to_num(_arg(a, 0, 0)) // 1),
    "ucase$": lambda e, a: to_str(_arg(a, 0)).upper(),
    "msgbox": lambda e, a: (e.host("InfoDialog", to_str(_arg(a, 0))) if e.host else e.log("[vb] MsgBox: " + to_str(_arg(a, 0)))) or "",
}


def _mid(a):
    s = to_str(_arg(a, 0))
    start = int(to_num(_arg(a, 1, 1)))
    start = max(1, start)
    if len(a) >= 3:
        n = int(to_num(a[2]))
        return s[start - 1:start - 1 + n]
    return s[start - 1:]


def _val(v):
    s = to_str(v).strip()
    m = re.match(r"[-+]?(\d+\.\d+|\.\d+|\d+)", s)
    if not m:
        return 0
    t = m.group()
    return float(t) if "." in t else int(t)


# ---------------------------------------------------------------- self-test

if __name__ == "__main__":
    calls = []

    def host(cmd, *a):
        calls.append((cmd, a))
        if cmd == "GetProperty":
            return "  steve  "
        return ""

    env = VbEnv(host=host)
    code = '''
Sub OnClick()
    Dim name, i, total
    name = Trim(Vml("GetProperty", "txtName", "Text"))
    If name = "" Then
        Vml("SetProperty", "lblHi", "Text", "Who are you?")
    Else
        Vml("SetProperty", "lblHi", "Text", "Hello, " & UCase(Left(name, 1)) & Mid(name, 2) & "!")
    End If
    total = 0
    For i = 1 To 5
        total = total + i
    Next
    Vml("SetProperty", "lblSum", "Text", "Sum 1..5 = " & total)
End Sub
'''
    r = env.run(code, [], "OnClick")
    for c in calls:
        print(c)
    print("factorial check:")
    code2 = '''
Function Fact(n)
    If n <= 1 Then
        Fact = 1
    Else
        Fact = n * Fact(n - 1)
    End If
End Function
Sub Go()
    Vml("SetProperty", "x", "Text", "5! = " & Fact(5))
End Sub
'''
    calls.clear()
    env2 = VbEnv(host=host)
    env2.run(code2, [], "Go")
    print(calls)

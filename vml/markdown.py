"""
Markdown to HTML, for the desktop's help and the MarkdownView and MarkdownEditor controls. No dependencies; it covers
what docs use, drawn the way GitHub draws it: headings (each with an anchor, as GitHub makes them, h1 and h2 ruled
under), paragraphs, bullet and numbered lists (nested by indenting, numbering carried on), task lists - [ ] / - [x],
``` code blocks ``` (coloured for the usual languages), `code`, **bold**, *italic*, ~~struck~~, [links](url),
![images](file), tables (striped), > quotes and --- rules. Raw HTML in the text is shown as text, never run.
The HTML is shaped for Qt's rich text, which reads a subset of HTML and CSS (no borders on paragraphs, no rounded
corners, no max-width), so rules and bars are drawn with tables. The web uses marked instead (vml/web/marked.min.js).
"""
import html
import re

# GitHub's own colours (its light theme)
INK, MUTED, LINE, TINT, LINK = "#1F2328", "#59636E", "#D1D9E0", "#F6F8FA", "#0969DA"
CODE_TINT = "#EFF1F3"                                    # inline `code`: a shade darker than a code block
FONT = "'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "'Cascadia Mono', Consolas, 'DejaVu Sans Mono', 'Liberation Mono', monospace"
# code colours, as GitHub's: keywords, strings, comments, numbers, function names
K_KEY, K_STR, K_COM, K_NUM, K_FN = "#CF222E", "#0A3069", "#59636E", "#0550AE", "#8250DF"
KEYWORDS = set("""
and break do else elseif end false for function goto if in local nil not or repeat return then true until while
as assert async await class continue def del except finally from global import is lambda None nonlocal pass raise
True False try with yield case const default delete export extends let new null static super switch this throw
typeof undefined var void bool byte char decimal double float int long namespace object private protected public
readonly short string struct using virtual done esac fi elif echo
""".split())
SIZES = {1: 2.0, 2: 1.5, 3: 1.25, 4: 1.0, 5: 0.875, 6: 0.85}      # headings, as GitHub sizes them
ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


def slug(text):
    """A heading's anchor, as GitHub makes it: lower case, punctuation gone, spaces to hyphens."""
    t = re.sub(r"<[^>]+>", "", text).strip().lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


def _inline(text):
    """**bold**, *italic*, ~~struck~~, `code`, ![images](src), [links](url), <https://autolinks>, in escaped text."""
    codes = []

    def keep(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"
    text = re.sub(r"`([^`]+)`", keep, text)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)",
                  lambda m: f'<img src="{m.group(2)}" alt="{m.group(1)}">', text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)",
                  lambda m: f'<a href="{m.group(2)}" style="color:{LINK}; text-decoration:none">{m.group(1)}</a>', text)
    text = re.sub(r"&lt;(https?://[^\s&]+)&gt;",
                  lambda m: f'<a href="{m.group(1)}" style="color:{LINK}; text-decoration:none">{m.group(1)}</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<i>\1</i>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: f'<code style="background-color:{CODE_TINT}; font-family:{MONO}; font-size:85%">'
                  f'&nbsp;{codes[int(m.group(1))]}&nbsp;</code>', text)


TOKEN = re.compile(r"""(?P<com>--\[\[.*?\]\]|--[^\n]*|//[^\n]*|/\*.*?\*/|(?<![\w$&\#])\#(?![!{])[^\n]*)
                      |(?P<str>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|\[\[.*?\]\])
                      |(?P<num>\b(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b)
                      |(?P<fn>\b[A-Za-z_]\w*(?=\s*\())
                      |(?P<word>\b[A-Za-z_]\w*\b)""", re.S | re.X)


def highlight(code):
    """A code block coloured the way GitHub colours one: comments, strings, numbers, keywords, function calls.
    One pass over the raw text, so a keyword inside a string or a comment keeps the string's or comment's colour."""
    out, last = [], 0
    for m in TOKEN.finditer(code):
        out.append(html.escape(code[last:m.start()]))
        text, kind = m.group(0), m.lastgroup
        colour = {"com": K_COM, "str": K_STR, "num": K_NUM, "fn": K_FN}.get(kind)
        if kind in ("word", "fn") and text in KEYWORDS:
            colour = K_KEY
        elif kind == "word":
            colour = None
        out.append(f'<span style="color:{colour}">{html.escape(text)}</span>' if colour else html.escape(text))
        last = m.end()
    out.append(html.escape(code[last:]))
    return "".join(out)


def rule(colour, height, gap):
    """A line across the page: Qt can't border a paragraph, so a one-cell table draws it."""
    return (f'<table width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 {gap}px 0">'
            f'<tr><td bgcolor="{colour}" height="{height}" style="font-size:1px">&nbsp;</td></tr></table>')


def to_html(md, base_size=16, tab_lang="lua"):                              # GitHub's own: 16px, line height 1.5
    lines = str(md or "").replace("\r\n", "\n").replace("\t", "    ").split("\n")
    out, para, lists = [], [], []                           # lists: the open ones, (kind, indent), innermost last

    def flush_para():
        if para:
            out.append(f'<p style="margin:0 0 16px 0; line-height:125%">{_inline(html.escape(" ".join(para)))}</p>')
            para.clear()

    def close_lists(deeper_than=-1):
        while lists and lists[-1][1] > deeper_than:
            out.append(f"</{lists.pop()[0]}>")
            if not lists:                                   # Qt drops a list's bottom margin: room under it by hand
                out.append('<p style="margin:0; font-size:6px">&nbsp;</p>')

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        fence = re.match(r"^(```|~~~)", s)
        if fence:                                           # a code block
            flush_para(); close_lists()
            info = s[len(fence.group(1)):].strip().lower()   # the word after the fence, e.g. script / lua
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence.group(1)):
                body.append(lines[i])
                i += 1
            i += 1
            src = "\n".join(body)
            as_tabs = info in ("script", "tabs", "lua tabs", "vml")
            if as_tabs:                                      # one Lua snippet, shown in every language (a tab bar)
                from . import translate as _tr
                lang = tab_lang if tab_lang in _tr.LANGS else "lua"
                bits = []
                for lg in _tr.LANGS:
                    if lg == lang:
                        bits.append(f'<b style="color:{INK}">{_tr.LABEL[lg]}</b>')
                    else:
                        bits.append(f'<a href="lang:{lg}" style="color:{LINK}; text-decoration:none">{_tr.LABEL[lg]}</a>')
                bar = ' &nbsp;&middot;&nbsp; '.join(bits)
                shown = _tr.translate(src, "lua", lang)
            else:
                bar, shown = None, src
            code = highlight(shown).replace("\n", "<br>").replace("  ", "&nbsp; ")
            cell = (f'<table width="100%" cellpadding="16" cellspacing="0" style="margin:0 0 {0 if as_tabs else 16}px 0">'
                    f'<tr><td bgcolor="{TINT}" style="font-family:{MONO}; font-size:{round(base_size * 0.85)}px; '
                    f'line-height:130%; color:{INK}">{code}</td></tr></table>')
            if as_tabs:
                out.append(f'<p style="margin:0 0 4px 0; font-size:{round(base_size * 0.82)}px">{bar}</p>')
                out.append(cell)
                out.append('<p style="margin:0 0 16px 0; font-size:2px">&nbsp;</p>')
            else:
                out.append(cell)
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", s)
        if m:                                               # a heading
            flush_para(); close_lists()
            level, text = len(m.group(1)), m.group(2)
            top = 24 if out else 0
            out.append(f'<a name="{slug(text)}"></a><p style="margin:{top}px 0 {8 if level <= 2 else 16}px 0; '
                       f'font-size:{round(base_size * SIZES[level])}px; font-weight:600; line-height:125%; '
                       f'color:{MUTED if level == 6 else INK}">{_inline(html.escape(text))}</p>')
            if level <= 2:
                out.append(rule(LINE, 1, 16))
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):                 # a rule
            flush_para(); close_lists()
            out.append(rule(LINE, 4, 24))
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{3,}", lines[i + 1].strip()):   # a table
            flush_para(); close_lists()
            cells = lambda row: [c.strip() for c in row.strip().strip("|").split("|")]
            aligns = ["center" if c.startswith(":") and c.endswith(":") else "right" if c.endswith(":") else "left"
                      for c in cells(lines[i + 1])]
            al = lambda n: aligns[n] if n < len(aligns) else "left"
            head, rows = cells(s), []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            t = [f'<table cellpadding="7" cellspacing="0" border="1" style="border-color:{LINE}; border-style:solid; '
                 f'border-collapse:collapse; margin:0 0 16px 0">']
            t.append("<tr>" + "".join(f'<th align="{al(n)}" style="font-weight:600">{_inline(html.escape(c))}</th>'
                                      for n, c in enumerate(head)) + "</tr>")
            for k, r in enumerate(rows):
                bg = f' bgcolor="{TINT}"' if k % 2 else ""
                t.append(f"<tr{bg}>" + "".join(f'<td align="{al(n)}">{_inline(html.escape(c))}</td>'
                                               for n, c in enumerate(r)) + "</tr>")
            out.append("".join(t) + "</table>")
            continue
        if s.startswith(">"):                                      # a quote
            flush_para(); close_lists()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f'<table cellpadding="0" cellspacing="0" style="margin:0 0 16px 0"><tr>'
                       f'<td bgcolor="{LINE}" width="4" style="font-size:1px">&nbsp;</td><td width="16"></td>'
                       f'<td style="color:{MUTED}; line-height:125%">{_inline(html.escape(" ".join(quote)))}</td></tr></table>')
            continue
        m = ITEM.match(line)
        if m:                                               # a list item: deeper indents nest, lines under it join it
            flush_para()
            indent = len(m.group(1))
            kind = "ol" if m.group(2)[0].isdigit() else "ul"
            close_lists(indent)
            if lists and lists[-1][1] == indent and lists[-1][0] != kind:
                close_lists(indent - 1)                     # same depth, other kind: a new list
            if not lists or lists[-1][1] < indent:
                start = ""
                if kind == "ol":
                    start = f' start="{int(re.match(r"[0-9]+", m.group(2)).group(0))}"'
                out.append(f'<{kind}{start} style="margin:0 0 {4 if lists else 16}px 0">')
                lists.append((kind, indent))
            item = [m.group(3)]
            i += 1
            while i < len(lines) and lines[i].startswith(" " * (indent + 2)) and lines[i].strip() \
                    and not ITEM.match(lines[i]):
                item.append(lines[i].strip())
                i += 1
            text = _inline(html.escape(" ".join(item)))
            task = re.match(r"^\[([ xX])\]\s+(.*)$", text, re.S)
            if task:
                done = task.group(1).lower() == "x"
                text = f'<span style="color:{INK if done else MUTED}">{"&#9745;" if done else "&#9744;"}</span>&nbsp; {task.group(2)}'
            out.append(f'<li style="margin:0 0 4px 0; line-height:125%">{text}</li>')
            continue
        if not s:
            flush_para()
            if lists and i + 1 < len(lines) and ITEM.match(lines[i + 1]):
                i += 1                                      # a blank line between items: still the same list
                continue
            close_lists()
            i += 1
            continue
        close_lists()
        para.append(s)
        i += 1
    flush_para(); close_lists()
    return f'<div style="font-family:{FONT}; font-size:{base_size}px; color:{INK}">' + "\n".join(out) + "</div>"

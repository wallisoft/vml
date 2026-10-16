"""
Markdown to HTML, for the desktop's help and the MarkdownView and MarkdownEditor controls. No dependencies; it covers
what docs use: headings (each with an anchor, as GitHub makes them), paragraphs, bullet and numbered lists,
``` code blocks ```, `code`, **bold**, *italic*, [links](url), tables, > quotes and --- rules. Raw HTML in the text is
shown as text, never run. The HTML is shaped for Qt's rich text (which reads a subset of HTML and CSS); the web uses
marked instead (vml/web/marked.min.js).
"""
import html
import re

INK, MUTED, LINE, TINT, LINK = "#1F2937", "#6B7280", "#E5E7EB", "#F3F4F6", "#2563EB"


def slug(text):
    """A heading's anchor, as GitHub makes it: lower case, punctuation gone, spaces to hyphens."""
    t = re.sub(r"<[^>]+>", "", text).strip().lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


def _inline(text):
    """**bold**, *italic*, `code`, [links](url), <https://autolinks>, in already-escaped text."""
    codes = []

    def keep(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"
    text = re.sub(r"`([^`]+)`", keep, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)",
                  lambda m: f'<a href="{m.group(2)}" style="color:{LINK}; text-decoration:none">{m.group(1)}</a>', text)
    text = re.sub(r"&lt;(https?://[^\s&]+)&gt;", lambda m: f'<a href="{m.group(1)}" style="color:{LINK}">{m.group(1)}</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<i>\1</i>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: f'<code style="background-color:{TINT}; font-family:monospace; font-size:85%">'
                  f'&nbsp;{codes[int(m.group(1))]}&nbsp;</code>', text)


def to_html(md, base_size=16):                              # GitHub's own: 16px, line height 1.5
    """The HTML body for some Markdown."""
    lines = str(md or "").replace("\r\n", "\n").split("\n")
    out, i, para, lst = [], 0, [], None

    def flush_para():
        if para:
            out.append(f'<p style="margin:0 0 10px 0">{_inline(html.escape(" ".join(para), quote=True))}</p>')
            para.clear()

    def close_list():
        nonlocal lst
        if lst:
            out.append(f"</{lst}>")
            lst = None
    sizes = {1: 2.0, 2: 1.5, 3: 1.25, 4: 1.0, 5: 0.875, 6: 0.85}      # as GitHub sizes its headings
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):                                    # a code block
            flush_para(); close_list()
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            code = html.escape("\n".join(body)).replace("\n", "<br>").replace("  ", "&nbsp; ")
            out.append(f'<table width="100%" cellpadding="10" cellspacing="0" style="margin:4px 0 12px 0">'
                       f'<tr><td bgcolor="{TINT}" style="font-family:monospace; font-size:{round(base_size * 0.85)}px">{code}</td></tr></table>')
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", s)
        if m:                                                      # a heading
            flush_para(); close_list()
            level, text = len(m.group(1)), m.group(2)
            size = round(base_size * sizes[level])
            rule = f' style="border-bottom:1px solid {LINE}"' if level <= 2 else ""
            out.append(f'<a name="{slug(text)}"></a><p style="margin:{14 if level > 1 else 4}px 0 6px 0; font-size:{size}px; '
                       f'font-weight:700; color:{INK}"{rule}>{_inline(html.escape(text))}</p>')
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):                 # a rule
            flush_para(); close_list()
            out.append(f'<hr style="color:{LINE}">')
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{3,}", lines[i + 1].strip()):   # a table
            flush_para(); close_list()
            cells = lambda row: [c.strip() for c in row.strip().strip("|").split("|")]
            head = cells(s)
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            t = [f'<table cellpadding="6" cellspacing="0" border="1" style="border-color:{LINE}; margin:4px 0 12px 0; border-collapse:collapse">']
            t.append("<tr>" + "".join(f'<th bgcolor="{TINT}" align="left">{_inline(html.escape(c))}</th>' for c in head) + "</tr>")
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{_inline(html.escape(c))}</td>" for c in r) + "</tr>")
            out.append("".join(t) + "</table>")
            continue
        if s.startswith(">"):                                      # a quote
            flush_para(); close_list()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f'<table cellpadding="8" cellspacing="0" style="margin:4px 0 12px 0"><tr><td bgcolor="{LINE}" width="3"></td>'
                       f'<td style="color:{MUTED}">{_inline(html.escape(" ".join(quote)))}</td></tr></table>')
            continue
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if m:                                                      # a list item (lines indented under it join it)
            flush_para()
            kind = "ol" if m.group(2)[0].isdigit() else "ul"
            if lst != kind:
                close_list()
                out.append(f'<{kind} style="margin:0 0 10px 0">')
                lst = kind
            item = [m.group(3)]
            i += 1
            while i < len(lines) and lines[i].startswith(("  ", "\t")) and lines[i].strip() \
                    and not re.match(r"^\s*([-*+]|\d+[.)])\s+", lines[i]):
                item.append(lines[i].strip())
                i += 1
            out.append(f'<li style="margin-bottom:3px">{_inline(html.escape(" ".join(item)))}</li>')
            continue
        if not s:
            flush_para(); close_list()
            i += 1
            continue
        close_list()
        para.append(s)
        i += 1
    flush_para(); close_list()
    return (f'<div style="font-size:{base_size}px; color:{INK}; line-height:150%">' + "\n".join(out) + "</div>")

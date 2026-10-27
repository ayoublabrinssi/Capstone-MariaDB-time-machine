"""Turns wikitext into plain blocks of text, good enough to read and to diff.

This is not a MediaWiki parser. It drops templates, references and
categories, keeps links as their label, and splits the rest into headings,
list items, paragraphs, images and simple tables. Old revisions from 2002
are short plain text, so they come through unchanged.

Images and tables are blocks too, so the diff can say when one was added or
removed. Their text is a small encoding, read back by image() and table():
an image is "file name\ncaption"; a table has one line per row, cells split
by tabs, each cell starting with "!" (header) or "|", and an optional first
line "+caption".
"""
import difflib
import html
import re

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_REF = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", re.S | re.I)
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_TABLE = re.compile(r"\{\|(?:(?!\{\|).)*?\|\}", re.S)
_FILE = re.compile(r"\[\[(File|Image|Category):([^\[\]]*(?:\[\[[^\[\]]*\]\][^\[\]]*)*)\]\]", re.I)
_GALLERY = re.compile(r"<gallery[^>]*>(.*?)</gallery>", re.S | re.I)
_INFOBOX = re.compile(r"\{\{\s*Infobox", re.I)
_LEAD = re.compile(r"\|\s*(?:image_skyline|image1|image)\s*=\s*(?:\[\[(?:File|Image):)?([^|{}\[\]\n]+?\.(?:jpe?g|png|gif|svg|tiff?|webp))", re.I)
_LEAD_CAPTION = re.compile(r"\|\s*(?:caption_skyline|caption1|image_caption|caption)\s*=[ \t]*([^\n]*)")
_FILE_OPTION = re.compile(r"^(?:thumb|thumbnail|frame|framed|frameless|border|left|right|center|centre|none|upright"
                          r"|baseline|middle|sub|super|top|text-top|bottom|text-bottom|\d*x?\d+\s*px"
                          r"|(?:upright|alt|link|class|lang|page|thumbtime|start|end)\s*=.*)$", re.I)
_CONVERT = re.compile(r"\{\{\s*(?:convert|cvt)\s*\|([^{}]*)\}\}", re.I)
_RANGE = {"-", "–", "to", "and", "or", "x", "by", "+/-"}
_UNITS = {"C": "°C", "F": "°F", "C-change": "°C", "F-change": "°F"}
_LANG_TEMPLATE = re.compile(r"\{\{\s*([A-Za-z][\w /-]*?)\s*\|([^{}]*)\}\}")
_LANGUAGES = {"ar": "Arabic", "ary": "Moroccan Arabic", "ber": "Berber", "zgh": "Standard Moroccan Tamazight",
              "shi": "Tachelhit", "tzm": "Central Atlas Tamazight", "rif": "Tarifit", "kab": "Kabyle",
              "mey": "Hassaniya Arabic", "fr": "French", "es": "Spanish", "pt": "Portuguese", "la": "Latin",
              "xpu": "Punic", "grc": "Ancient Greek", "grc-gre": "Ancient Greek", "he": "Hebrew"}
_PRONOUNCE = re.compile(r"^(?:ipa.*|ipac-.*|respell|audio|pronunciation)$")
_SLOT = re.compile(r"^\x00(\d+)\x00$")
_INTERWIKI = re.compile(r"\[\[(?:[a-z]{2,3}(?:-[a-z]+)*|simple):[^\[\]]*\]\]")
_RULE = re.compile(r"^-{4,}", re.M)
_LINK_LABEL = re.compile(r"\[\[[^\[\]|]*\|([^\[\]]*)\]\]")
_LINK = re.compile(r"\[\[([^\[\]]*)\]\]")
_EXT_LINK = re.compile(r"\[(?:https?:)?//[^\s\]]+\s*([^\]]*)\]")
_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_HEADING = re.compile(r"^(={2,6})\s*(.*?)\s*\1\s*$")


def _repeat(pattern, text, repl=""):
    """Applies a pattern until nothing changes, to remove nested markup."""
    while True:
        new = pattern.sub(repl, text)
        if new == text:
            return text
        text = new


def _split(text):
    """Splits on | but not inside [[...]] or {{...}}."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth = max(depth - 1, 0)
        elif ch == "|" and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _inline(text):
    """Cleans one line of markup (a caption or a table cell) down to plain text."""
    text = _CONVERT.sub(_convert, text)
    text = _LANG_TEMPLATE.sub(_language, text)
    text = _repeat(_TEMPLATE, text)
    text = _repeat(_FILE, text)
    text = _LINK_LABEL.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _EXT_LINK.sub(r"\1", text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = _TAG.sub("", text)
    text = html.unescape(text).replace("'''", "").replace("''", "")
    return " ".join(text.replace("\x00", "").split())


def _convert(match):
    """{{convert|27|C}} is a number with its unit, so it is kept as "27 °C"."""
    params = [p.strip() for p in match.group(1).split("|") if "=" not in p]
    words = []
    for p in params:
        if re.fullmatch(r"-?[\d.,]+", p) or (words and p in _RANGE):
            words.append(p)
        else:
            if words:
                words.append(_UNITS.get(p, p))
            break
    return " ".join(words).replace(" - ", "-").replace(" – ", "–")


def _language(match):
    """Keeps the names in other languages (Arabic, Berber...) that the lead sentence gives.

    {{lang-ar|الرباط}} becomes "Arabic: الرباط", {{lang|ar|الرباط}} and
    {{transl|ar|ar-Ribāṭ}} keep just the text. Pronunciation guides are dropped.
    Any other template is left for the general rule, which removes it.
    """
    name = match.group(1).strip().lower()
    params = [p.strip() for p in match.group(2).split("|")]
    named = dict(p.split("=", 1) for p in params if "=" in p)
    plain = [p for p in params if "=" not in p and p]
    if _PRONOUNCE.match(name):
        return ""
    if name.startswith("lang-") or name == "langx":
        code = name[5:] if name.startswith("lang-") else (plain.pop(0) if plain else "")
        if code == "latn" and plain:
            code = plain.pop(0)
        if not plain:
            return ""
        text = plain[0] + (f", {plain[1]}" if len(plain) > 1 else "")
        if named.get("translit"):
            text += f", {named['translit'].strip()}"
        label = _LANGUAGES.get(code)
        return f"{label}: {text}" if label else text
    if name in ("lang", "transl", "transliteration", "native name", "nativename", "script", "lang-latn") and len(plain) > 1:
        return plain[1]
    if name in ("script/arabic", "ar", "rtl-lang") and plain:
        return plain[-1]
    if name in ("literally", "lit") and plain:
        return "lit. \"" + plain[0] + "\""
    return match.group(0)


def _tidy(text):
    """Removes the punctuation left behind where a template used to be: "(, ; )"."""
    while True:
        new = re.sub(r"\balso(?=\s*[,;)])", "", text)
        new = re.sub(r"\(\s*[,;:]+\s*", "(", new)
        new = re.sub(r"\s*[,;:]+\s*\)", ")", new)
        new = re.sub(r"\(\s*\)", "", new)
        new = re.sub(r"([,;])(\s*[,;])+", r"\1", new)
        new = re.sub(r"\s+([,;.)])", r"\1", new)
        new = re.sub(r"  +", " ", new)
        if new == text:
            return text.strip()
        text = new


# blocks shown whole, never as a word diff: an image, a gallery image, a table
MEDIA = ("img", "gimg", "table")


def _image(name, caption="", kind="img"):
    # some names carry an invisible direction mark copied from Arabic text
    name = re.sub("[\u200b-\u200f\u202a-\u202e]", "", name)
    name = " ".join(name.replace("_", " ").split())
    return (kind, f"{name}\n{_inline(caption)}") if name else None


def _file(match):
    """An image link: the file name, then options, then the caption last."""
    params = _split(match.group(2))
    caption = [p for p in params[1:] if not _FILE_OPTION.match(p.strip())]
    return _image(params[0], caption[-1] if caption else "")


def _gallery(body):
    out = []
    for line in body.splitlines():
        name, _, caption = line.strip().partition("|")
        name = re.sub(r"^(?:File|Image):", "", name, flags=re.I)
        if name:
            out.append(_image(name, caption, "gimg"))
    return out


def _lead_image(text):
    """The main photo from the infobox, which is a template and would be dropped."""
    start = _INFOBOX.search(text)
    if not start:
        return None
    depth, i = 0, start.start()
    while i < len(text) - 1:
        pair = text[i:i + 2]
        if pair == "{{":
            depth += 1
            i += 2
        elif pair == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                break
        else:
            i += 1
    box = text[start.start():i]
    found = _LEAD.search(box)
    if not found:
        return None
    caption = _LEAD_CAPTION.search(box[found.end():])
    return _image(found.group(1), caption.group(1) if caption else "")


def _table(source):
    """A wikitable as rows of cells. Row and column spans are ignored.

    A table used only to set lists side by side (twin towns, for example) has
    no header and only lists in its cells: it comes back as plain list items.
    """
    caption, rows, row = "", [], []
    for line in source.splitlines()[1:]:
        line = line.strip()
        if line.startswith("|}"):
            break
        if line.startswith("|+"):
            caption = _inline(_split(line[2:])[-1])
        elif line.startswith("|-"):
            if row:
                rows.append(row)
            row = []
        elif line[:1] in ("!", "|"):
            mark = line[0]
            # "||" alone on a line starts an empty cell
            body = line[2:] if line[:2] in ("||", "!!") else line[1:]
            for cell in re.split(r"\|\||!!" if mark == "!" else r"\|\|", body):
                parts = _split(cell)
                if len(parts) > 1 and "=" in parts[0]:
                    cell = "|".join(parts[1:])
                row.append([mark, _inline(cell), []])
        elif line and row:
            if line[0] in "*#":
                row[-1][2].append(_inline(line.lstrip("*#:; ")))
            else:
                row[-1][1] += " " + _inline(line)
    if row:
        rows.append(row)
    cells = [c for r in rows for c in r if c[1].strip() or c[2]]
    if not cells:
        return None
    if not caption and all(c[0] == "|" and c[2] and not c[1].strip() for c in cells):
        return [("li", item) for c in cells for item in c[2] if item]
    lines = (["+" + caption] if caption else []) + [
        "\t".join(mark + " ".join(filter(None, [text.strip(), ", ".join(items)])) for mark, text, items in r)
        for r in rows if any(c[1].strip() or c[2] for c in r)]
    return ("table", "\n".join(lines))


def image(text):
    """Reads an image block back: (file name, caption)."""
    name, _, caption = text.partition("\n")
    return name, caption


def table(text):
    """Reads a table block back: (caption, rows), each row a list of (is_header, text)."""
    lines = text.split("\n")
    caption = lines.pop(0)[1:] if lines and lines[0].startswith("+") else ""
    return caption, [[(c[:1] == "!", c[1:]) for c in line.split("\t")] for line in lines]


def clean(wikitext):
    """Returns a list of (kind, text) with kind 'h', 'li', 'p', 'img', 'gimg' (gallery) or 'table'."""
    text = wikitext or ""
    text = _COMMENT.sub("", text)
    text = _REF.sub("", text)
    slots = []

    def slot(block):
        if not block:
            return "\n"
        if isinstance(block, list):
            return "".join(slot(b) for b in block)
        slots.append(block)
        return f"\n\x00{len(slots) - 1}\x00\n"

    lead = _lead_image(text)
    text = _GALLERY.sub(lambda m: "".join(slot(b) for b in _gallery(m.group(1))), text)
    text = _CONVERT.sub(_convert, text)
    text = _LANG_TEMPLATE.sub(_language, text)
    text = _repeat(_TEMPLATE, text)
    text = _repeat(_TABLE, text, lambda m: slot(_table(m.group(0))))
    text = _FILE.sub(lambda m: "" if m.group(1).lower() == "category" else slot(_file(m)), text)
    text = _INTERWIKI.sub("", text)
    text = _RULE.sub("", text)
    text = _LINK_LABEL.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _EXT_LINK.sub(r"\1", text)
    text = _TAG.sub("", text)
    text = html.unescape(text).replace("'''", "").replace("''", "")

    blocks, para = ([lead] if lead else []), []

    def flush():
        if para:
            blocks.append(("p", _tidy(" ".join(para))))
            para.clear()

    for line in text.splitlines():
        line = line.strip()
        heading = _HEADING.match(line)
        filled = _SLOT.match(line)
        if filled:
            flush()
            blocks.append(slots[int(filled.group(1))])
        elif not line or line.startswith(("{", "}", "|", "!", "__")):
            flush()
        elif heading:
            flush()
            if heading.group(2):
                blocks.append(("h", heading.group(2)))
        elif line[0] == ";" and line[1:].strip():
            # a definition-list term, used as a small heading
            flush()
            blocks.append(("h", line[1:].strip()))
        elif line[0] in "*#":
            flush()
            item = _tidy(line.lstrip("*#:; "))
            if item:
                blocks.append(("li", item))
        else:
            para.append(line)
    flush()
    return blocks


def diff(old_blocks, new_blocks):
    """Compares two lists of blocks.

    Returns a list of (op, kind, parts). op is 'same', 'del', 'add' or 'mod'.
    For 'mod', parts is a list of (word_op, words) with word_op 'same', 'del'
    or 'add'. For the others, parts is the block text. Runs of unchanged
    blocks come back as ('skip', None, count).
    """
    old_text = [t for _, t in old_blocks]
    new_text = [t for _, t in new_blocks]
    out = []
    matcher = difflib.SequenceMatcher(None, old_text, new_text, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            out.append(("skip", None, i2 - i1))
        elif op == "delete":
            out.extend(("del", k, t) for k, t in old_blocks[i1:i2])
        elif op == "insert":
            out.extend(("add", k, t) for k, t in new_blocks[j1:j2])
        else:
            pairs = min(i2 - i1, j2 - j1)
            for n in range(pairs):
                kind, old = old_blocks[i1 + n]
                new_kind, new = new_blocks[j1 + n]
                if kind == new_kind and kind not in MEDIA and _similar(old, new):
                    out.append(("mod", kind, _word_diff(old, new)))
                else:
                    out.append(("del", kind, old))
                    out.append(("add", new_kind, new))
            out.extend(("del", k, t) for k, t in old_blocks[i1 + pairs:i2])
            out.extend(("add", k, t) for k, t in new_blocks[j1 + pairs:j2])
    return out


def _similar(old, new):
    """True when two blocks share at least half their words, so a word diff reads well."""
    return difflib.SequenceMatcher(None, old.split(), new.split(), autojunk=False).ratio() >= 0.5


def _word_diff(old, new):
    a, b = old.split(), new.split()
    parts = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            parts.append(("same", " ".join(a[i1:i2])))
            continue
        if i2 > i1:
            parts.append(("del", " ".join(a[i1:i2])))
        if j2 > j1:
            parts.append(("add", " ".join(b[j1:j2])))
    return parts


def side_by_side(changes):
    """Turns the output of diff() into rows for two columns, old and new.

    Returns a list of ('skip', count) or ('row', left, right). left and right
    are None (nothing on that side) or (kind, parts), parts being a list of
    (word_op, words) as in diff(). Removed blocks followed by added blocks
    are paired up, so a rewritten paragraph sits next to its new version.
    """
    rows, dels, adds = [], [], []

    def flush():
        for n in range(max(len(dels), len(adds))):
            left = (dels[n][0], [("del", dels[n][1])]) if n < len(dels) else None
            right = (adds[n][0], [("add", adds[n][1])]) if n < len(adds) else None
            rows.append(("row", left, right))
        dels.clear()
        adds.clear()

    for op, kind, parts in changes:
        if op == "del":
            if adds:
                flush()
            dels.append((kind, parts))
        elif op == "add":
            adds.append((kind, parts))
        else:
            flush()
            if op == "skip":
                rows.append(("skip", parts))
            else:
                rows.append(("row",
                             (kind, [p for p in parts if p[0] != "add"]),
                             (kind, [p for p in parts if p[0] != "del"])))
    flush()
    return rows

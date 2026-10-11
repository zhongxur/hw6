"""Defense layers that are plain code (no model involved).

CODE layer  - clean_document(): turn a file into the text a PERSON would see. Hidden HTML
              (CSS display/visibility/size/color/off-screen tricks, `hidden`, comments, scripts),
              invisible PDF text (white, microscopic, or off the page), the hidden parts of an
              email, and zero-width characters are removed and reported, not shown to the model.
              Links are replaced with [link removed].
DESIGN layer - cross_check() and scrub_output(): the quoted numbers must come from the document's
              labeled quote fields, and nothing the model writes can carry links or addresses out.
              (handbook.decide() makes the decision and approval-gated trap tools are wired in agent.py.)

Instruction-like phrases are only *flagged* (security_flags) for the audit trail. They never
block or blank a document, so clean quotes that say "please ignore the earlier quote" still work.
"""

from __future__ import annotations

import email
import re
import unicodedata
from dataclasses import dataclass, field
from email import policy
from pathlib import Path

from bs4 import BeautifulSoup, Comment, Tag
from pypdf import PdfReader
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

TAG_CHARS = re.compile("[\U000E0000-\U000E007F]+")  # Unicode "tag" block: invisible, but models can read it
URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.I)
MAX_DOC_CHARS = 20_000


def strip_invisible(text: str) -> tuple[str, list[str]]:
    """Drop zero-width / format characters. Text smuggled in Unicode tag characters is decoded and
    returned so it can be reported (a person sees nothing there, a model can read it)."""
    smuggled = ["".join(chr(ord(c) - 0xE0000) for c in run) for run in TAG_CHARS.findall(text)]
    text = TAG_CHARS.sub("", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    return text, [s for s in smuggled if s.strip()]


@dataclass
class CleanDoc:
    text: str
    removed: list[dict] = field(default_factory=list)  # what was cut, where, and why
    flags: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ HTML

_NAMED = {"white": (255, 255, 255), "black": (0, 0, 0), "transparent": None}


def _rgb(color: str | None):
    if not color:
        return None
    c = color.strip().lower()
    if c in _NAMED:
        return _NAMED[c]
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", c)
    if m:
        h = m.group(1)
        h = "".join(ch * 2 for ch in h) if len(h) == 3 else h
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\((\d+),(\d+),(\d+)(?:,([\d.]+))?\)", c)
    if m:
        if m.group(4) is not None and float(m.group(4)) < 0.1:
            return None  # fully transparent text
        return tuple(int(m.group(i)) for i in (1, 2, 3))
    return None


def _contrast(a, b) -> float:
    """WCAG contrast ratio between two sRGB colors (1 = identical, 21 = black on white)."""
    def lum(rgb):
        ch = [x / 255 for x in rgb]
        ch = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _parse_css(soup: BeautifulSoup) -> list[tuple[str, dict]]:
    rules = []
    for style in soup.find_all("style"):
        css = re.sub(r"/\*.*?\*/", "", style.get_text(), flags=re.S)
        for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
            decl = _parse_decl(body)
            for sel in selectors.split(","):
                rules.append((sel.strip(), decl))
    return rules


def _parse_decl(body: str) -> dict:
    out = {}
    for part in body.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip().lower().replace(" ", "")
    return out


def _selector_matches(sel: str, el: Tag) -> bool:
    """Simple selectors only: tag, .class, #id, tag.class (enough for vendor HTML)."""
    m = re.fullmatch(r"([a-z0-9]*)((?:[.#][\w-]+)*)", sel.strip().lower())
    if not m:
        return False
    tag, rest = m.groups()
    if tag and el.name != tag:
        return False
    for kind, name in re.findall(r"([.#])([\w-]+)", rest):
        if kind == "." and name not in (el.get("class") or []):
            return False
        if kind == "#" and el.get("id") != name:
            return False
    return bool(tag or rest)


def _px(v: str | None) -> float | None:
    m = re.match(r"(-?[\d.]+)(px|pt|em|rem|%)?", v or "")
    if not m:
        return None
    n = float(m.group(1))
    return {"pt": n * 1.33, "em": n * 16, "rem": n * 16, "%": n * 0.16}.get(m.group(2) or "px", n)


def _hidden_reason(style: dict, el: Tag, background: str) -> str | None:
    if el.has_attr("hidden"):
        return "hidden attribute"
    if el.get("aria-hidden") == "true":
        return "aria-hidden"
    if style.get("display") == "none":
        return "display:none"
    if style.get("visibility") in ("hidden", "collapse"):
        return "visibility:hidden"
    if style.get("opacity") in ("0", "0.0", "0%"):
        return "opacity:0"
    size = _px(style.get("font-size"))
    if size is not None and size <= 3:
        return f"font-size {style['font-size']}"
    color = style.get("color")
    if color:
        fg, bg = _rgb(color), _rgb(background) or (255, 255, 255)
        if fg is None and color.startswith(("rgba", "transparent")):
            return f"transparent text color {color}"
        if fg is not None and _contrast(fg, bg) < 1.6:
            return f"text color {color} almost invisible on {background} background"
    if style.get("transform", "").startswith(("scale(0", "scale(0.0")) or style.get("max-height") in ("0", "0px"):
        return "shrunk to nothing"
    for prop in ("left", "top", "right", "text-indent", "margin-left", "margin-top"):
        v = _px(style.get(prop))
        if v is not None and v <= -500:
            return f"off-screen {prop}:{style[prop]}"
    if style.get("clip", "").startswith("rect(0") or style.get("clip-path", "").startswith("inset(50%"):
        return "clipped to nothing"
    if (_px(style.get("height")) == 0 or _px(style.get("width")) == 0) and style.get("overflow") == "hidden":
        return "zero-size box"
    return None


def clean_html(html: str, where: str = "html") -> CleanDoc:
    soup = BeautifulSoup(html, "html.parser")
    removed: list[dict] = []

    def cut(node, why):
        txt = node.get_text(" ", strip=True) if isinstance(node, Tag) else str(node).strip()
        if txt:
            removed.append({"where": where, "why": why, "text": strip_invisible(txt)[0][:400]})
        node.extract()

    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        cut(c, "HTML comment")
    rules = _parse_css(soup)
    for t in soup.find_all(["script", "style", "noscript", "template", "meta", "link", "iframe", "object"]):
        if t.name in ("script", "noscript", "template", "iframe", "object"):
            cut(t, f"<{t.name}> element")
        else:
            t.extract()

    body = soup.body or soup
    bg_style = {}
    for sel, decl in rules:
        if _selector_matches(sel, body) if isinstance(body, Tag) and body.name else False:
            bg_style.update(decl)
    if isinstance(body, Tag):
        bg_style.update(_parse_decl(body.get("style", "")))
    background = (bg_style.get("background-color") or bg_style.get("background") or "#ffffff").split()[0]

    # walk top-down; once a parent is cut, its children go with it
    for el in list(body.find_all(True)):
        if not any(p is body for p in el.parents):  # an ancestor was already cut
            continue
        style = {}
        for sel, decl in rules:
            if _selector_matches(sel, el):
                style.update(decl)
        style.update(_parse_decl(el.get("style", "")))
        why = _hidden_reason(style, el, background)
        if why:
            cut(el, why)

    for tr in body.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        tr.replace_with(soup.new_string(": ".join(cells) + "\n"))
    for br in body.find_all("br"):
        br.replace_with("\n")
    title = soup.title.get_text(strip=True) if soup.title else ""
    if soup.head:
        soup.head.extract()
    text = body.get_text("\n")
    text = (f"Title: {title}\n" if title else "") + text
    return CleanDoc(text=text, removed=removed)


# ------------------------------------------------------------------ PDF

def _mul(a, b):
    """3x3 affine matrix product, matrices as [a, b, c, d, e, f]."""
    return [
        a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5],
    ]


def _str(operand) -> str:
    if isinstance(operand, bytes):
        return operand.decode("latin-1")
    return str(operand)


def clean_pdf(path: Path) -> CleanDoc:
    """Keep only text a person can see: dark enough, big enough, and on the page."""
    reader = PdfReader(str(path))
    lines: list[str] = []
    removed: list[dict] = []
    for page_no, page in enumerate(reader.pages, 1):
        box = page.mediabox
        x0, y0, x1, y1 = float(box.left), float(box.bottom), float(box.right), float(box.top)
        content = ContentStream(page.get_contents(), reader)
        ctm, stack = [1, 0, 0, 1, 0, 0], []
        fill, font_size, tm, tlm, leading = (0.0, 0.0, 0.0), 12.0, [1, 0, 0, 1, 0, 0], [1, 0, 0, 1, 0, 0], 0.0
        render_mode = 0
        for operands, op in content.operations:
            op = op.decode() if isinstance(op, bytes) else op
            if op == "q":  # text state (render mode, font size, leading) is part of the graphics state
                stack.append((ctm[:], fill, render_mode, font_size, leading))
            elif op == "Q" and stack:
                ctm, fill, render_mode, font_size, leading = stack.pop()
            elif op == "cm":
                ctm = _mul([float(x) for x in operands], ctm)
            elif op == "rg":
                fill = tuple(float(x) for x in operands)
            elif op == "g":
                fill = (float(operands[0]),) * 3
            elif op == "k":
                c, m, y, k = (float(x) for x in operands)
                fill = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
            elif op == "Tr":
                render_mode = int(operands[0])
            elif op == "Tf":
                font_size = float(operands[1])
            elif op == "TL":
                leading = float(operands[0])
            elif op == "BT":
                tm, tlm = [1, 0, 0, 1, 0, 0], [1, 0, 0, 1, 0, 0]
            elif op == "Tm":
                tm = tlm = [float(x) for x in operands]
            elif op in ("Td", "TD"):
                tlm = _mul([1, 0, 0, 1, float(operands[0]), float(operands[1])], tlm)
                tm = tlm[:]
            elif op == "T*":
                tlm = _mul([1, 0, 0, 1, 0, -leading], tlm)
                tm = tlm[:]
            elif op in ("Tj", "TJ", "'", '"'):
                if op == "TJ":
                    text = "".join(_str(x) for x in operands[0] if isinstance(x, (TextStringObject, ByteStringObject)))
                else:
                    text = _str(operands[-1])
                if not text.strip():
                    continue
                m = _mul(tm, ctm)
                size = font_size * (m[0] ** 2 + m[1] ** 2) ** 0.5
                x, y = m[4], m[5]
                why = None
                if render_mode in (3, 7):
                    why = f"invisible text render mode {render_mode} Tr"
                elif min(fill) >= 0.9:
                    why = f"white text (fill {fill})"
                elif size < 3:
                    why = f"microscopic text ({size:.1f}pt)"
                elif not (x0 - 5 <= x <= x1 and y0 - 5 <= y <= y1):
                    why = f"off the page at ({x:.0f}, {y:.0f})"
                if why:
                    removed.append({"where": f"pdf page {page_no}", "why": why, "text": text[:400]})
                else:
                    lines.append(text)
    return CleanDoc(text="\n".join(lines), removed=removed)


# ------------------------------------------------------------------ email

def clean_eml(path: Path) -> CleanDoc:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    header = "\n".join(f"{h}: {msg[h]}" for h in ("From", "To", "Subject", "Date") if msg[h])
    plain = [p for p in msg.walk() if p.get_content_type() == "text/plain"]
    html = [p for p in msg.walk() if p.get_content_type() == "text/html"]
    removed: list[dict] = []
    flags: list[str] = []
    if html:
        # an email app shows the HTML part, so that is what a person reads
        doc = clean_html(html[0].get_content(), where="email HTML part")
        body, removed = doc.text, doc.removed
        if plain:
            p_words = set(re.findall(r"[a-z0-9$.]+", strip_invisible(plain[0].get_content())[0].lower()))
            h_words = set(re.findall(r"[a-z0-9$.]+", body.lower()))
            extra = p_words - h_words
            if len(extra) > 3:
                flags.append(f"plain-text part has words the HTML part does not show: {sorted(extra)[:12]}")
    elif plain:
        body = plain[0].get_content()
    else:
        body = ""
    attachments = [p.get_filename() for p in msg.walk() if p.get_filename()]
    if attachments:
        flags.append(f"attachments not read: {attachments}")
    return CleanDoc(text=header + "\n\n" + body, removed=removed, flags=flags)


# ------------------------------------------------------------------ entry point

INSTRUCTION_HINTS = [
    (r"\b(send_email|approve_payment)\b", "names one of the agent's tools"),
    (r"\b(ignore|disregard)\b.{0,40}\b(instruction|rule|handbook|above|previous)", "tells the reader to ignore rules"),
    (r"\b(replaces|supersedes|overrides)\b", "claims to replace a quoted value"),
    (r"\b(pre-?approved|standing instruction|owner (has )?approved)\b", "claims a prior approval"),
    (r"\b(mark|set) (the|this) quote as\b", "tries to set the decision"),
    (r"\b(reviewer|assistant|AI|agent)\b,?\s+(please|must|should)\b", "addresses the reviewer/AI directly"),
]


def clean_document(path: Path) -> CleanDoc:
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        doc = clean_html(path.read_text(encoding="utf-8", errors="replace"))
    elif suffix == ".pdf":
        doc = clean_pdf(path)
    elif suffix == ".eml":
        doc = clean_eml(path)
    else:
        doc = CleanDoc(text=path.read_text(encoding="utf-8", errors="replace"))

    text, smuggled = strip_invisible(doc.text)
    for hidden in smuggled:
        doc.removed.append({"where": "visible text", "why": "invisible Unicode tag characters", "text": hidden[:400]})
    for url in URL_RE.findall(text):
        doc.removed.append({"where": "visible text", "why": "link", "text": url})
    text = URL_RE.sub("[link removed]", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    doc.text = text[:MAX_DOC_CHARS]

    for item in doc.removed:
        doc.flags.append(f"removed {item['why']} ({item['where']}): {item['text'][:120]}")
    for pattern, label in INSTRUCTION_HINTS:
        m = re.search(pattern, doc.text, re.I)
        if m:
            doc.flags.append(f"visible text {label}: '{doc.text[max(0, m.start() - 40): m.end() + 60]}'")
    return doc


# ------------------------------------------------------------------ design-layer checks

_FIELD_PATTERNS = {
    "unit_price": r"unit price\s*:?\s*\$\s*([\d,]+(?:\.\d+)?)",
    "lead_time_days": r"lead time\s*:?\s*([\d,]+)\s*(?:business\s+|calendar\s+)?days?",
    "min_order": r"minimum order\s*:?\s*([\d,]+)\s*units?",
    "sku": r"\b(CC-[A-Z]{2}-\d{3})\b",
}


def labeled_fields(text: str) -> dict[str, list]:
    """Values that sit on the quote's labeled lines ('Unit price: $9.83'), not in prose."""
    found = {}
    for name, pat in _FIELD_PATTERNS.items():
        vals = []
        for v in re.findall(pat, text, re.I):
            v = v.replace(",", "")
            vals.append(v.upper() if name == "sku" else float(v) if name == "unit_price" else int(v))
        found[name] = list(dict.fromkeys(vals))
    return found


def cross_check(extracted: dict, text: str) -> tuple[dict, list[str]]:
    """Keep the model's value only if it matches the labeled quote field; otherwise use the field.

    If a labeled field appears with two different values, the field is set to None (unknown) so the
    handbook check fails safe and a person looks at it.
    """
    fields = labeled_fields(text)
    out, notes = dict(extracted), []

    # letterhead check: the vendor is whoever the document names first (header / signature line);
    # a later "vendor of record" claim cannot swap in a different, approved vendor
    from handbook import tables  # local import: handbook -> models only, no cycle

    names = list(tables()["approved"]) + list(tables()["removed"])
    low = text.lower()
    hits = sorted((low.find(n.lower()), n) for n in names if n.lower() in low)
    if hits:
        letterhead = hits[0][1]
        if re.sub(r"\W", "", (extracted.get("vendor") or "").lower()) != re.sub(r"\W", "", letterhead.lower()):
            notes.append(f"vendor: model said {extracted.get('vendor')!r}, letterhead names {letterhead!r}; using the letterhead")
            out["vendor"] = letterhead

    for name in ("sku", "unit_price", "lead_time_days", "min_order"):
        vals = fields[name]
        if len(vals) == 1 and extracted.get(name) != vals[0]:
            notes.append(f"{name}: model said {extracted.get(name)!r}, labeled field says {vals[0]!r}; using the field")
            out[name] = vals[0]
        elif len(vals) > 1 and name != "sku":
            notes.append(f"{name}: labeled field has conflicting values {vals}; set to unknown for human review")
            out[name] = None
        elif not vals and extracted.get(name) is not None:
            if str(extracted[name]).rstrip("0").rstrip(".") not in text.replace(",", ""):
                notes.append(f"{name}: {extracted[name]!r} does not appear in the visible document; set to unknown")
                out[name] = None
    return out, notes


def scrub_output(s: str) -> str:
    """Nothing the model writes may carry a link or an address out of the desk."""
    s = URL_RE.sub("[link removed]", s)
    return re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "[address removed]", s)

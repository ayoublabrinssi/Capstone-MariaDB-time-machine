"""Draws the three UML diagrams shown in the README.

A class diagram of the data model, an object diagram of one moment, and a
sequence diagram of what the page does when you pick a date. Standard UML:
visibility (+ and -), derived attributes (/), multiplicities, roles,
composition, lifelines, calls and replies, opt fragments.
Run it again after a schema change:  python3 design/draw_uml.py
It writes a light and a dark SVG of each diagram into design/uml/.
"""
import os
from xml.sax.saxutils import escape

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uml')

THEMES = {
    'light': dict(fill='#e6e6e6', stroke='#3c3c3c', text='#111111', line='#222222', note='#ffffff', soft='#444444'),
    'dark':  dict(fill='#2d333b', stroke='#9aa4af', text='#e6edf3', line='#c9d1d9', note='#161b22', soft='#aab4bf'),
}
FONT = "Arial, Helvetica, 'Liberation Sans', sans-serif"
LH = 17      # line height of an attribute
PAD = 6

class Svg:
    def __init__(self, w, h, theme, title):
        self.w, self.h, self.t, self.title = w, h, THEMES[theme], title
        self.out = []
    def add(self, s): self.out.append(s)
    def text(self, x, y, s, size=12, anchor='start', bold=False, italic=False, underline=False, color=None):
        style = ''
        if bold: style += 'font-weight:bold;'
        if italic: style += 'font-style:italic;'
        if underline: style += 'text-decoration:underline;'
        self.add('<text x="%s" y="%s" font-size="%s" text-anchor="%s" fill="%s" style="%s">%s</text>'
                 % (x, y, size, anchor, color or self.t['text'], style, escape(s)))
    def line(self, pts, dashed=False):
        d = ' '.join('%s,%s' % p for p in pts)
        self.add('<polyline points="%s" fill="none" stroke="%s" stroke-width="1.2"%s/>'
                 % (d, self.t['line'], ' stroke-dasharray="5,4"' if dashed else ''))
    def box(self, x, y, w, name, attrs=(), ops=(), stereo=None, obj=False):
        """A class (or object) box. Returns its height. attrs/ops: strings, or (string, 'u') for underlined."""
        head = 46 if stereo else 30
        ha = len(attrs) * LH + 12 if attrs else (12 if ops else 0)
        ho = len(ops) * LH + 12 if ops else 0
        h = head + ha + ho
        t = self.t
        self.add('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" stroke="%s" stroke-width="1.2"/>' % (x, y, w, h, t['fill'], t['stroke']))
        if stereo:
            self.text(x + w / 2, y + 18, '«' + stereo + '»', size=11.5, anchor='middle')
            self.text(x + w / 2, y + 36, name, size=13.5, anchor='middle', bold=True, underline=obj)
        else:
            self.text(x + w / 2, y + 20, name, size=13.5, anchor='middle', bold=True, underline=obj)
        yy = y + head
        if attrs or ops:
            self.add('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="1.2"/>' % (x, yy, x + w, yy, t['stroke']))
        for i, a in enumerate(attrs):
            s, u = (a, False) if isinstance(a, str) else (a[0], True)
            self.text(x + PAD, yy + 18 + i * LH, s, underline=u)
        yy += ha
        if ops:
            self.add('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="1.2"/>' % (x, yy, x + w, yy, t['stroke']))
            for i, a in enumerate(ops):
                s, u = (a, False) if isinstance(a, str) else (a[0], True)
                self.text(x + PAD, yy + 18 + i * LH, s, underline=u)
        return h
    def diamond(self, x, y, direction):
        """Solid composition diamond with one tip at (x, y), pointing away in the given direction."""
        L, Wd = 16, 5
        dx, dy = {'down': (0, 1), 'left': (-1, 0), 'right': (1, 0), 'up': (0, -1)}[direction]
        px, py = -dy, dx
        pts = [(x, y), (x + dx * L / 2 + px * Wd, y + dy * L / 2 + py * Wd), (x + dx * L, y + dy * L), (x + dx * L / 2 - px * Wd, y + dy * L / 2 - py * Wd)]
        self.add('<polygon points="%s" fill="%s" stroke="%s" stroke-width="1"/>' % (' '.join('%s,%s' % p for p in pts), self.t['line'], self.t['line']))
    def arrow(self, x, y, direction):
        """Open arrow head (navigability) with its tip at (x, y)."""
        dx, dy = {'right': (1, 0), 'left': (-1, 0), 'down': (0, 1), 'up': (0, -1)}[direction]
        px, py = -dy, dx
        a = (x - dx * 11 + px * 5, y - dy * 11 + py * 5)
        b = (x - dx * 11 - px * 5, y - dy * 11 - py * 5)
        self.add('<polyline points="%s,%s %s,%s %s,%s" fill="none" stroke="%s" stroke-width="1.2"/>' % (a[0], a[1], x, y, b[0], b[1], self.t['line']))
    def call(self, x1, x2, y, label, reply=False):
        """A message between two lifelines. A call is a solid line with a filled head,
        a reply a dashed line with an open head. The label sits above the line."""
        self.line([(x1, y), (x2, y)], dashed=reply)
        d = 1 if x2 > x1 else -1
        if reply:
            self.arrow(x2, y, 'right' if d > 0 else 'left')
        else:
            self.add('<polygon points="%s,%s %s,%s %s,%s" fill="%s"/>'
                     % (x2, y, x2 - d * 11, y - 5, x2 - d * 11, y + 5, self.t['line']))
        left = min(x1, x2)
        for i, part in enumerate(reversed(label.split('\n'))):
            self.text(left + 10, y - 7 - i * 15, part, size=12)
    def fragment(self, x, y, w, h, kind, guard, gx=None):
        """A combined fragment (opt, alt, loop) with its pentagon tag and guard."""
        t = self.t
        self.add('<rect x="%s" y="%s" width="%s" height="%s" fill="none" stroke="%s" stroke-width="1.2"/>' % (x, y, w, h, t['stroke']))
        tw = 44
        self.add('<polygon points="%s,%s %s,%s %s,%s %s,%s %s,%s" fill="%s" stroke="%s" stroke-width="1.2"/>'
                 % (x, y, x + tw, y, x + tw, y + 12, x + tw - 8, y + 20, x, y + 20, t['fill'], t['stroke']))
        self.text(x + 8, y + 15, kind, size=12, bold=True)
        self.text(gx or x + tw + 10, y + 15, guard, size=12)
    def actor(self, x, y):
        """A stick figure, head top at y."""
        c = self.t['line']
        self.add('<circle cx="%s" cy="%s" r="7" fill="none" stroke="%s" stroke-width="1.4"/>' % (x, y + 7, c))
        self.add('<path d="M%s %s V%s M%s %s H%s M%s %s L%s %s M%s %s L%s %s" fill="none" stroke="%s" stroke-width="1.4"/>'
                 % (x, y + 14, y + 30, x - 11, y + 20, x + 11, x, y + 30, x - 9, y + 42, x, y + 30, x + 9, y + 42, c))
    def reading(self, x, y):
        """Small filled triangle: the reading direction of an association name."""
        self.add('<polygon points="%s,%s %s,%s %s,%s" fill="%s"/>' % (x, y - 8, x + 7, y - 4, x, y, self.t['text']))
    def note(self, x, y, w, lines):
        h = len(lines) * 15 + 12
        c = 10
        t = self.t
        self.add('<polygon points="%s,%s %s,%s %s,%s %s,%s %s,%s" fill="%s" stroke="%s" stroke-width="1"/>'
                 % (x, y, x + w - c, y, x + w, y + c, x + w, y + h, x, y + h, t['note'], t['stroke']))
        self.add('<polyline points="%s,%s %s,%s %s,%s" fill="none" stroke="%s" stroke-width="1"/>' % (x + w - c, y, x + w - c, y + c, x + w, y + c, t['stroke']))
        for i, s in enumerate(lines):
            self.text(x + 7, y + 17 + i * 15, s, size=11)
        return h
    def save(self, path):
        head = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s" width="%s" height="%s" font-family="%s" role="img">'
                '<title>%s</title>' % (self.w, self.h, self.w, self.h, FONT, escape(self.title)))
        open(path, 'w', encoding='utf-8').write(head + '\n' + '\n'.join(self.out) + '\n</svg>\n')

def class_diagram(theme):
    s = Svg(1010, 500, theme, 'UML class diagram of the data model: Page, Article, ArticlePeriod, RevisionText, ExactText')
    # associations first, so the boxes sit on top of the line ends
    s.line([(505, 143), (505, 215)])                       # Page - Article
    s.line([(405, 80), (141, 80), (141, 215)])             # Page - ArticlePeriod
    s.line([(605, 80), (892, 80), (892, 215)])             # Page - RevisionText
    s.line([(630, 262), (790, 262)])                       # Article -> RevisionText
    s.line([(630, 426), (790, 426)])                       # Article -> ExactText
    s.line([(300, 456), (330, 440)], dashed=True)          # note - Article
    # classes
    s.box(405, 16, 200, 'Page', ['+ page_id: INT {unique}', '+ title: VARCHAR {unique}', '+ /revisions: INT', '+ /first_edit: DATETIME', '+ /last_edit: DATETIME'])
    s.box(330, 215, 300, 'Article', ['+ page_id: INT', '+ rev_id: BIGINT', '+ editor: VARCHAR [0..1]', '+ comment: TEXT [0..1]', '+ bytes: INT [0..1]',
                                      '+ text_rev_id: BIGINT', '- row_start: TIMESTAMP {readOnly}', '- row_end: TIMESTAMP {readOnly}'],
          [('+ asOf(t: TIMESTAMP): Article [0..1]', 'u'), ('+ between(t1, t2: TIMESTAMP): Article [*]', 'u'), ('+ all(): Article [*]', 'u')], stereo='system-versioned')
    s.box(16, 215, 250, 'ArticlePeriod', ['+ page_id: INT', '+ rev_id: BIGINT', '+ bytes: INT [0..1]', '+ valid_from: DATETIME', '+ valid_to: DATETIME'],
          [('+ forPortionOf(from, to: DATETIME)', 'u')], stereo='bitemporal')
    s.box(790, 215, 204, 'RevisionText', ['+ rev_id: BIGINT {unique}', '+ page_id: INT', '+ body: MEDIUMTEXT'])
    s.box(790, 372, 204, 'ExactText', ['+ rev_id: BIGINT {unique}', '+ body: MEDIUMTEXT', '+ fetched_at: TIMESTAMP'], stereo='cache')
    # composition diamonds at the Page end
    s.diamond(505, 143, 'down'); s.diamond(405, 80, 'left'); s.diamond(605, 80, 'right')
    # navigability
    s.arrow(790, 262, 'right'); s.arrow(790, 426, 'right')
    # multiplicities and roles
    s.text(514, 172, '1'); s.text(514, 208, '1..*'); s.text(497, 208, '+versions', size=11, anchor='end')
    s.text(378, 73, '1', anchor='end'); s.text(149, 208, '1..*'); s.text(134, 208, '+periods', size=11, anchor='end')
    s.text(631, 73, '1'); s.text(900, 208, '1..*'); s.text(885, 208, '+storedTexts', size=11, anchor='end')
    s.text(637, 255, '*'); s.text(771, 255, '1', anchor='end'); s.text(680, 255, 'points at', size=11); s.reading(729, 256); s.text(784, 278, '+storedText', size=11, anchor='end')
    s.text(637, 419, '1'); s.text(771, 419, '0..1', anchor='end'); s.text(784, 442, '+exactText', size=11, anchor='end')
    # constraint and note
    s.text(141, 406, '{periods of one page never overlap}', size=11, anchor='middle')
    s.note(16, 432, 284, ['Underlined = class operations. They are asked', 'of the table, as SQL clauses, not of one row.'])
    return s

def object_diagram(theme):
    s = Svg(1010, 196, theme, 'UML object diagram: what AS OF 1 January 2010 returns for Rabat')
    s.line([(226, 60), (300, 60)])
    s.line([(640, 50), (740, 50)])
    s.line([(640, 146), (740, 146)])
    s.box(16, 16, 210, 'rabat:Page', ['page_id = 57400', 'title = "Rabat"', 'revisions = 1878'], obj=True)
    s.box(300, 16, 340, 'v447:Article', ['rev_id = 331806877', 'editor = "SieBot"', 'bytes = 16676', 'text_rev_id = 318993384',
                                         'row_start = 2009-12-15 13:52:06', 'row_end = 2010-01-10 22:01:11'], obj=True)
    s.box(740, 16, 254, ':RevisionText', ['rev_id = 318993384', 'page_id = 57400'], obj=True)
    s.box(740, 112, 254, ':ExactText', ['rev_id = 331806877'], obj=True)
    return s

def sequence_diagram(theme):
    """What happens when you pick Rabat and 1 January 2010 (app/server.py, app/db.py, app/exact.py)."""
    s = Svg(1010, 572, theme, 'UML sequence diagram: what the page asks MariaDB and Wikipedia when you pick Rabat and 1 January 2010')
    YOU, PAGE, DB, WIKI = 60, 270, 690, 920
    END = 560
    # lifeline heads
    s.actor(YOU, 10); s.text(YOU, 70, 'You', anchor='middle')
    for x, name, w in ((PAGE, 'page: Python server', 170), (DB, 'MariaDB 12.3.3', 150), (WIKI, 'Wikipedia', 120)):
        s.box(x - w / 2, 22, w, name)
    # lifelines
    for x, top in ((YOU, 80), (PAGE, 52), (DB, 52), (WIKI, 52)):
        s.line([(x, top), (x, END)], dashed=True)
    # activation bars, drawn before the messages
    t = s.t
    def bar(x, y1, y2):
        s.add('<rect x="%s" y="%s" width="10" height="%s" fill="%s" stroke="%s" stroke-width="1.2"/>' % (x - 5, y1, y2 - y1, t['fill'], t['stroke']))
    bar(PAGE, 100, 534)
    bar(DB, 128, 162); bar(DB, 196, 230); bar(DB, 300, 334); bar(DB, 454, 470)
    bar(WIKI, 394, 428)
    # fragments
    s.fragment(150, 254, 840, 236, 'opt', '[the stored text belongs to an older revision]', gx=PAGE + 15)
    s.fragment(170, 346, 800, 132, 'opt', '[the exact text is not kept yet]', gx=PAGE + 15)
    # messages
    s.call(YOU, PAGE - 5, 100, 'Rabat, 1 January 2010')
    s.call(PAGE + 5, DB - 5, 128, "SELECT ... FOR SYSTEM_TIME AS OF '2010-01-01 23:59:59.999999'")
    s.call(DB - 5, PAGE + 5, 162, 'revision 331806877, SieBot, 16,676 bytes, and its stored text', reply=True)
    s.call(PAGE + 5, DB - 5, 196, 'EXPLAIN PARTITIONS and ANALYZE of the same query')
    s.call(DB - 5, PAGE + 5, 230, '18 of 27 partitions opened, 1,432 rows read', reply=True)
    s.call(PAGE + 5, DB - 5, 300, 'SELECT body FROM exact_text WHERE rev_id = 331806877')
    s.call(DB - 5, PAGE + 5, 334, 'the exact text, or nothing', reply=True)
    s.call(PAGE + 5, WIKI - 5, 394, 'the text of revision 331806877')
    s.call(WIKI - 5, PAGE + 5, 428, 'wikitext', reply=True)
    s.call(PAGE + 5, DB - 5, 454, 'INSERT IGNORE INTO exact_text')
    s.call(PAGE - 5, YOU, 534, 'the article as it stood,\nand how MariaDB found it', reply=True)
    return s

if __name__ == '__main__':
    for theme in THEMES:
        class_diagram(theme).save(os.path.join(HERE, 'data-model-%s.svg' % theme))
        object_diagram(theme).save(os.path.join(HERE, 'snapshot-%s.svg' % theme))
        sequence_diagram(theme).save(os.path.join(HERE, 'request-%s.svg' % theme))
    print('wrote 6 files in', HERE)

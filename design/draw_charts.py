"""Draws the three pictures of the README that are not UML.

timeline   Rabat around New Year 2010, read like the timeline of a video editor:
           each clip is one version, AS OF is the playhead.
build      how the data gets from Wikipedia to the page.
old-dates  rows read to answer about an old date, AS OF against the first-row query.

The numbers are real: the versions come from the article table, the rows read
from docs/measurements.md. Run:  python3 design/draw_charts.py
It writes a light and a dark SVG of each picture into design/charts/.
"""
import os
from datetime import datetime
from draw_uml import Svg, THEMES

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'charts')

# colours of the page (app/style.css): majorelle and saffron
COLOURS = {
    'light': dict(panel='#f3f4f6', lane='#e8e9ee', clip='#d3d6de', clipline='#8f96a3', accent='#4436c8', ontext='#ffffff',
                  play='#c98a12', grid='#d0d3da', muted='#5d6283'),
    'dark':  dict(panel='#161b22', lane='#1f252e', clip='#3a414b', clipline='#6b7480', accent='#5a4fd6', ontext='#ffffff',
                  play='#f0b94a', grid='#30363d', muted='#9599bc'),
}


def rect(s, x, y, w, h, fill, stroke='none', rx=0, sw=1.2, dash=False):
    s.add('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%s" fill="%s" stroke="%s" stroke-width="%s"%s/>'
          % (x, y, w, h, rx, fill, stroke, sw, ' stroke-dasharray="5,4"' if dash else ''))


def fits(text, width, size=12):
    """Cut a label to the width of its clip, like an editor does."""
    per = size * 0.56
    if len(text) * per <= width:
        return text
    n = int(width / per) - 1
    return text[:n] + '…' if n >= 3 else ''


# ---------------------------------------------------------------- timeline

# Rabat (page 57400): SELECT rev_id, editor, row_start, row_end FROM article FOR SYSTEM_TIME ALL
VERSIONS = [
    (328345134, 'Dyscti', '2009-11-28 08:28:37', '2009-11-30 02:09:05'),
    (328712545, 'Xqbot', '2009-11-30 02:09:05', '2009-12-08 01:24:59'),
    (330361460, '99.182.80.152', '2009-12-08 01:24:59', '2009-12-08 01:26:27'),
    (330361757, '99.182.80.152', '2009-12-08 01:26:27', '2009-12-08 01:42:31'),
    (330364385, 'Marek69', '2009-12-08 01:42:31', '2009-12-14 21:48:38'),
    (331687240, '24.218.169.145', '2009-12-14 21:48:38', '2009-12-14 21:53:01'),
    (331688014, 'Jovianeye', '2009-12-14 21:53:01', '2009-12-15 13:52:06'),
    (331806877, 'SieBot', '2009-12-15 13:52:06', '2010-01-10 22:01:11'),
    (337073822, 'Starzynka', '2010-01-10 22:01:11', '2010-01-12 15:36:57'),
    (337398972, 'YUL89YYZ', '2010-01-12 15:36:57', '2010-01-13 18:33:01'),
    (337641050, '216.49.170.46', '2010-01-13 18:33:01', '2010-01-13 18:34:55'),
    (337641401, 'Elockid', '2010-01-13 18:34:55', '2010-01-13 18:36:16'),
    (337641645, '216.49.170.46', '2010-01-13 18:36:16', '2010-01-13 18:36:24'),
    (337641668, 'The Thing That Should Not Be', '2010-01-13 18:36:24', '2010-01-13 18:38:41'),
    (337642103, '216.49.170.46', '2010-01-13 18:38:41', '2010-01-13 18:39:05'),
    (337642185, 'Alansohn', '2010-01-13 18:39:05', '2010-01-13 18:41:29'),
    (337642721, '216.49.170.46', '2010-01-13 18:41:29', '2010-01-13 18:41:46'),
    (337642775, 'The Thing That Should Not Be', '2010-01-13 18:41:46', '2010-01-20 12:20:51'),
    (338941750, '129.187.171.38', '2010-01-20 12:20:51', '2010-01-20 12:21:45'),
    (338941849, '129.187.171.38', '2010-01-20 12:21:45', '2010-01-29 00:10:44'),
]
ANSWER = 331806877
ASKED = '2010-01-01 23:59:59'


def timeline(theme):
    t, c = THEMES[theme], COLOURS[theme]
    s = Svg(1010, 262, theme, 'Rabat around New Year 2010 as an editing timeline: each clip is one version, AS OF is the playhead and returns the SieBot clip')
    when = lambda v: datetime.strptime(v, '%Y-%m-%d %H:%M:%S')
    t0, t1 = datetime(2009, 11, 29), datetime(2010, 1, 21)
    X0, X1 = 130, 994
    days = (t1 - t0).total_seconds() / 86400
    x = lambda d: X0 + (min(max(d, t0), t1) - t0).total_seconds() / 86400 * (X1 - X0) / days
    TOP, LANE, LH = 50, 96, 56
    rect(s, 0, 0, 1010, 262, c['panel'], rx=8, sw=0)
    s.text(16, 26, 'Rabat, one track: every clip is one version of the article', size=13, bold=True)
    # ruler: a tick per day, a label per week
    rect(s, X0, TOP, X1 - X0, 30, c['lane'], sw=0)
    d = t0
    while d <= t1:
        xx = x(d)
        week = d.weekday() == 1  # 1 Dec 2009 was a Tuesday
        s.add('<line x1="%.1f" y1="%s" x2="%.1f" y2="%s" stroke="%s" stroke-width="1"/>'
              % (xx, TOP + 30, xx, TOP + (14 if week else 22), t['soft']))
        if week:
            label = d.strftime('%-d %b') + (d.strftime(' %Y') if d.day <= 7 and d.month in (12, 1) else '')
            s.text(xx + 3, TOP + 13, label, size=11, color=c['muted'])
        d = d.fromordinal(d.toordinal() + 1)
    # the track: header and lane
    rect(s, 16, LANE, X0 - 24, LH, c['lane'], rx=4, sw=0)
    s.text(26, LANE + 24, 'article', size=12, bold=True)
    s.text(26, LANE + 42, 'page_id 57400', size=11, color=c['muted'])
    rect(s, X0, LANE, X1 - X0, LH, c['lane'], sw=0)
    for rev, editor, start, end in VERSIONS:
        a, b = x(when(start)), x(when(end))
        w = max(b - a, 1.6)
        mine = rev == ANSWER
        rect(s, a, LANE + 4, w, LH - 8, c['accent'] if mine else c['clip'],
             stroke=c['accent'] if mine else c['clipline'], rx=3 if w > 8 else 0, sw=1 if w > 4 else 0.6)
        if mine:
            s.text(a + 10, LANE + 23, 'SieBot, revision %s' % rev, size=12, bold=True, color=c['ontext'])
            s.text(a + 10, LANE + 41, 'row_start 15 Dec 13:52', size=11, color=c['ontext'])
            s.text(b - 10, LANE + 41, 'row_end 10 Jan 22:01', size=11, anchor='end', color=c['ontext'])
        elif w > 40:
            s.text(a + 7, LANE + 23, fits(editor, w - 12), size=12)
            s.text(a + 7, LANE + 41, fits(str(rev), w - 12, 11), size=11, color=c['muted'])
    # names of the short clips, under the track, on steps so they do not touch
    below = LANE + LH
    for at, label, row in (('2010-01-13 18:33:01', '7 edits in 9 minutes', 0), ('2010-01-12 15:36:57', 'YUL89YYZ', 1),
                           ('2010-01-10 22:01:11', 'Starzynka', 2), ('2009-12-14 21:48:38', 'Jovianeye, after a 4-minute edit', 1),
                           ('2009-12-08 01:24:59', '2 short edits', 0)):
        xx = x(when(at)) + 3
        y = below + 18 + row * 16
        s.add('<line x1="%.1f" y1="%s" x2="%.1f" y2="%s" stroke="%s" stroke-width="1"/>' % (xx, below, xx, y - 10, c['muted']))
        s.text(xx + 3, y, label, size=11, color=c['muted'])
    # the playhead
    px = x(when(ASKED))
    s.add('<line x1="%.1f" y1="%s" x2="%.1f" y2="%s" stroke="%s" stroke-width="2"/>' % (px, TOP + 4, px, LANE + LH + 6, c['play']))
    s.add('<polygon points="%.1f,%s %.1f,%s %.1f,%s %.1f,%s %.1f,%s" fill="%s"/>'
          % (px - 7, TOP, px + 7, TOP, px + 7, TOP + 10, px, TOP + 17, px - 7, TOP + 10, c['play']))
    rect(s, px + 12, 10, 196, 24, c['play'], rx=4, sw=0)
    s.text(px + 20, 27, "AS OF '2010-01-01 23:59:59'", size=12, bold=True, color='#111111')
    # legend
    y = 238
    rect(s, 16, y - 11, 22, 13, c['accent'], rx=2, sw=0); s.text(44, y, 'the version AS OF returns', size=11)
    rect(s, 216, y - 11, 22, 13, c['clip'], stroke=c['clipline'], rx=2, sw=1); s.text(244, y, 'other versions; a clip starts at row_start and ends at row_end', size=11)
    s.add('<line x1="610" y1="%s" x2="610" y2="%s" stroke="%s" stroke-width="2"/>' % (y - 12, y + 3, c['play']))
    s.text(620, y, 'the playhead: the moment you ask about', size=11)
    return s


# ---------------------------------------------------------------- build

def build(theme):
    t, c = THEMES[theme], COLOURS[theme]
    s = Svg(1010, 300, theme, 'How the data gets from Wikipedia to the page: fetch, prepare, load, use')

    def box(x, y, w, h, lines, rx=0, stack=False):
        if stack:  # a pile of files
            rect(s, x + 8, y - 8, w, h, t['fill'], t['stroke'], rx=rx)
            rect(s, x + 4, y - 4, w, h, t['fill'], t['stroke'], rx=rx)
        rect(s, x, y, w, h, t['fill'], t['stroke'], rx=rx)
        top = y + h / 2 - (len(lines) - 1) * 8 + 4
        for i, ln in enumerate(lines):
            s.text(x + w / 2, top + i * 16, ln, size=12.5 if i == 0 else 11.5, anchor='middle', bold=i == 0,
                   color=None if i == 0 else t['soft'])

    def arrow(pts, label=None, at=None, dashed=False, side='above'):
        s.line(pts, dashed=dashed)
        (ax, ay), (bx, by) = pts[-2], pts[-1]
        s.arrow(bx, by, 'right' if bx > ax else 'left' if bx < ax else 'down' if by > ay else 'up')
        if label:
            lx, ly = at
            s.text(lx, ly, label, size=11.5, anchor='middle', color=t['soft'])

    # step titles over what each step makes, the same four steps as the list under the picture
    for x, step in ((293, '1. Fetch'), (525, '2. Prepare'), (745, '3. Load'), (925, '4. Use')):
        s.text(x, 26, step, size=13, bold=True, anchor='middle')
    s.add('<line x1="16" y1="38" x2="994" y2="38" stroke="%s" stroke-width="1"/>' % c['grid'])

    box(16, 130, 130, 50, ['Wikipedia API', 'every revision'], rx=24)
    arrow([(146, 155), (214, 155)], 'fetch.py', (180, 147))
    box(218, 128, 150, 54, ['45 JSON files', '31,179 revisions'], stack=True)
    # prepare.py makes two things
    s.line([(376, 155), (405, 155)])
    arrow([(405, 155), (405, 93), (446, 93)])
    arrow([(405, 155), (405, 229), (446, 229)])
    s.text(413, 159, 'prepare.py', size=11.5, color=t['soft'])
    box(450, 66, 150, 54, ['TSV files', 'real edit times'], stack=True)
    box(450, 202, 150, 54, ['220 expected answers', 'worked out in Python'], stack=True)
    # the database, as a cylinder
    cx, cy, rw, rh, h = 745, 76, 66, 12, 108
    s.add('<path d="M%s %s v%s a%s %s 0 0 0 %s 0 v-%s" fill="%s" stroke="%s" stroke-width="1.2"/>'
          % (cx - rw, cy, h, rw, rh, 2 * rw, h, t['fill'], t['stroke']))
    s.add('<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="%s" stroke="%s" stroke-width="1.2"/>' % (cx, cy, rw, rh, t['fill'], t['stroke']))
    s.text(cx, cy + 56, 'MariaDB 12.3.3', size=12.5, bold=True, anchor='middle')
    s.text(cx, cy + 72, 'system-versioned', size=11.5, anchor='middle', color=t['soft'])
    arrow([(608, 93), (677, 93)], '02_load.sql', (642, 85))
    arrow([(608, 229), (745, 229), (745, 198)], dashed=True)
    s.text(676, 247, 'the tests compare', size=11.5, anchor='middle', color=t['soft'])
    # what reads the tables
    for y, lines in ((60, ['The page', 'pick a city and a date']), (138, ['13 queries', 'and 6 examples']), (216, ['Measurements', 'rows read, time'])):
        box(856, y, 138, 50, lines)
        arrow([(811, 140), (833, 140), (833, y + 25), (854, y + 25)])
    return s


# ---------------------------------------------------------------- old dates

# docs/measurements.md, section 4: rows read for one answer about Rabat
OLD_DATES = [('June 2005', 1845, 1), ('June 2010', 1385, 1), ('June 2026', 60, 1)]


def old_dates(theme):
    t, c = THEMES[theme], COLOURS[theme]
    s = Svg(1010, 270, theme, 'Rows read to give one answer about Rabat: AS OF reads 1,845, 1,385 and 60 rows; the first-row query reads 1 every time')
    X0, X1, top = 130, 900, 64
    scale = (X1 - X0) / 2000
    s.text(16, 26, 'Rows read to give one answer about Rabat', size=13, bold=True)
    rect(s, 16, 40, 14, 12, c['accent'], rx=2, sw=0); s.text(36, 50, 'AS OF', size=11.5)
    rect(s, 96, 40, 14, 12, c['play'], rx=2, sw=0); s.text(116, 50, 'the first-row query', size=11.5)
    base = top + 3 * 54
    for v in range(0, 2001, 500):
        xx = X0 + v * scale
        s.add('<line x1="%.1f" y1="%s" x2="%.1f" y2="%s" stroke="%s" stroke-width="1"/>' % (xx, top, xx, base, c['grid']))
        s.text(xx, base + 18, '{:,}'.format(v), size=11, anchor='middle', color=c['muted'])
    s.text((X0 + X1) / 2, base + 36, 'rows read', size=11.5, anchor='middle', color=c['muted'])
    for i, (label, asof, first) in enumerate(OLD_DATES):
        y = top + 8 + i * 54
        s.text(X0 - 12, y + 24, label, size=12.5, anchor='end', bold=True)
        w = asof * scale
        rect(s, X0, y, w, 18, c['accent'], rx=2, sw=0)
        s.text(X0 + w + 8, y + 14, '{:,}'.format(asof), size=12, bold=True)
        rect(s, X0, y + 22, max(first * scale, 2.5), 18, c['play'], rx=1, sw=0)
        s.text(X0 + 10, y + 36, '1', size=12, bold=True)
    s.line([(X0, top), (X0, base)])
    return s


if __name__ == '__main__':
    os.makedirs(HERE, exist_ok=True)
    for theme in THEMES:
        timeline(theme).save(os.path.join(HERE, 'timeline-%s.svg' % theme))
        build(theme).save(os.path.join(HERE, 'build-%s.svg' % theme))
        old_dates(theme).save(os.path.join(HERE, 'old-dates-%s.svg' % theme))
    print('wrote 6 files in', HERE)

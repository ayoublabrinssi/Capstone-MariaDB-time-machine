"""Draws the pictures of the README and the docs that are not UML.

timeline      Rabat around New Year 2010, read like the timeline of a video editor:
              each clip is one version, AS OF is the playhead.
build         how the data gets from Wikipedia to the page (README).
build-detail  the same with the file names (docs/details.md).
old-dates     rows read to answer about an old date, AS OF against the first-row query.
clock-back    finding 2: the price of tea before and after the clock is set back.
overlap       finding 6: two imported versions of one key that overlap.

The numbers are real: the versions come from the article table, the rows read
from docs/measurements.md. Run:  python3 design/draw_charts.py
It writes a light and a dark SVG of each picture into design/charts/.
"""
import os
from datetime import datetime
from draw_uml import Svg, THEMES

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'charts')

# The colours of the page (app/style.css): majorelle blue, saffron, the red of removed
# text, on the navy and plaster of the page. THEMES gets two more entries for the
# boxes, lines and text of these pictures; the UML diagrams keep their grey.
COLOURS = {
    'light': dict(panel='#edeef2', lane='#e1e3eb', clip='#fbfbfd', clipline='#c3c7d6', accent='#4436c8', ontext='#ffffff',
                  play='#c98a12', onplay='#1c1f3b', grid='#d6d9e4', muted='#5d6283', red='#b03e33', onred='#ffffff'),
    'dark':  dict(panel='#121429', lane='#191c37', clip='#252a4d', clipline='#3a3f6b', accent='#9a90ff', ontext='#121429',
                  play='#f0b94a', onplay='#121429', grid='#2c3053', muted='#9599bc', red='#f08a7e', onred='#121429'),
}
THEMES['brand-light'] = dict(fill='#e3e0fb', stroke='#4436c8', text='#1c1f3b', line='#5d6283', note='#fbfbfd', soft='#5d6283')
THEMES['brand-dark'] = dict(fill='#2a2668', stroke='#9a90ff', text='#e6e7f2', line='#9599bc', note='#191c37', soft='#9599bc')


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
    t, c = THEMES['brand-' + theme], COLOURS[theme]
    s = Svg(1010, 262, 'brand-' + theme, 'Rabat around New Year 2010 as an editing timeline: each clip is one version, AS OF is the playhead and returns the SieBot clip')
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
    s.text(px + 20, 27, "AS OF '2010-01-01 23:59:59'", size=12, bold=True, color=c['onplay'])
    # legend
    y = 238
    rect(s, 16, y - 11, 22, 13, c['accent'], rx=2, sw=0); s.text(44, y, 'the version AS OF returns', size=11)
    rect(s, 216, y - 11, 22, 13, c['clip'], stroke=c['clipline'], rx=2, sw=1); s.text(244, y, 'other versions; a clip starts at row_start and ends at row_end', size=11)
    s.add('<line x1="610" y1="%s" x2="610" y2="%s" stroke="%s" stroke-width="2"/>' % (y - 12, y + 3, c['play']))
    s.text(620, y, 'the playhead: the moment you ask about', size=11)
    return s


# ---------------------------------------------------------------- build

BUILD = dict(
    fetch='fetch.py', prepare='prepare.py', load='02_load.sql', tests='the tests compare',
    raw=['45 JSON files', '31,179 revisions'], tsv=['TSV files', 'real edit times'],
    answers=['220 expected answers', 'worked out in Python'], db=['MariaDB 12.3.3', 'system-versioned'],
    uses=[['The page', 'pick a city and a date'], ['13 queries', 'and 6 examples'], ['Measurements', 'rows read, time']],
    exact=None)
BUILD_DETAIL = dict(
    fetch='fetch.py', prepare='fetch/prepare.py', load='02_load.sql', tests='tests/tests.sql compares',
    raw=['data/raw/', 'one JSON per article'], tsv=['data/load/', 'TSV files'],
    answers=['220 expected answers', 'computed in Python'], db=['MariaDB 12.3.3', 'page, revision_text,', 'article, article_period'],
    uses=[['app/', 'the page'], ['sql/queries.sql', 'sql/examples/'], ['scripts/measure.py', 'scratch database']],
    exact='app/exact.py: the text of one revision, when it is first opened')


def build(theme, L=BUILD, title='How the data gets from Wikipedia to the page: fetch, prepare, load, use'):
    t, c = THEMES['brand-' + theme], COLOURS[theme]
    s = Svg(1010, 300, 'brand-' + theme, title)
    rect(s, 0, 0, 1010, 300, c['panel'], rx=8, sw=0)

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
    arrow([(146, 155), (214, 155)], L['fetch'], (180, 147))
    box(218, 128, 150, 54, L['raw'], stack=True)
    # prepare.py makes two things
    s.line([(376, 155), (405, 155)])
    arrow([(405, 155), (405, 93), (446, 93)])
    arrow([(405, 155), (405, 229), (446, 229)])
    s.text(413, 159, L['prepare'], size=11.5, color=t['soft'])
    box(450, 66, 150, 54, L['tsv'], stack=True)
    box(450, 202, 150, 54, L['answers'], stack=True)
    # the database, as a cylinder
    cx, cy, rw, rh, h = 745, 76, 66, 12, 108
    s.add('<path d="M%s %s v%s a%s %s 0 0 0 %s 0 v-%s" fill="%s" stroke="%s" stroke-width="1.2"/>'
          % (cx - rw, cy, h, rw, rh, 2 * rw, h, t['fill'], t['stroke']))
    s.add('<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="%s" stroke="%s" stroke-width="1.2"/>' % (cx, cy, rw, rh, t['fill'], t['stroke']))
    for i, ln in enumerate(L['db']):
        s.text(cx, cy + 56 + i * 16 - (len(L['db']) - 2) * 8, ln, size=12.5 if i == 0 else 11.5, anchor='middle', bold=i == 0,
               color=None if i == 0 else t['soft'])
    arrow([(608, 93), (677, 93)], L['load'], (642, 85))
    arrow([(608, 229), (745, 229), (745, 198)], dashed=True)
    s.text(676, 247, L['tests'], size=11.5, anchor='middle', color=t['soft'])
    # what reads the tables
    for y, lines in zip((60, 138, 216), L['uses']):
        box(856, y, 138, 50, lines)
        arrow([(811, 140), (833, 140), (833, y + 25), (854, y + 25)])
    if L['exact']:  # the page asks Wikipedia for one text and keeps it
        arrow([(81, 130), (81, 54), (745, 54), (745, 62)], dashed=True)
        s.text(260, 50, L['exact'], size=11.5, color=t['soft'])
    return s


# ---------------------------------------------------------------- old dates

# docs/measurements.md, section 4: rows read for one answer about Rabat
OLD_DATES = [('June 2005', 1845, 1), ('June 2010', 1385, 1), ('June 2026', 60, 1)]


def old_dates(theme):
    t, c = THEMES['brand-' + theme], COLOURS[theme]
    s = Svg(1010, 270, 'brand-' + theme, 'Rows read to give one answer about Rabat: AS OF reads 1,845, 1,385 and 60 rows; the first-row query reads 1 every time')
    rect(s, 0, 0, 1010, 270, c['panel'], rx=8, sw=0)
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


# ---------------------------------------------------------------- editor helpers, for the findings

def editor_ruler(s, c, x, t0, t1, top, marks, small, X0, X1):
    """A ruler: a long tick and a label at each mark, a short tick at each small one."""
    t = s.t
    rect(s, X0, top, X1 - X0, 30, c['lane'], sw=0)
    for d in small:
        if t0 <= d <= t1:
            s.add('<line x1="%.1f" y1="%s" x2="%.1f" y2="%s" stroke="%s" stroke-width="1"/>' % (x(d), top + 30, x(d), top + 22, t['soft']))
    for d, label in marks:
        if t0 <= d <= t1 and x(d) < X1 - 40:
            s.add('<line x1="%.1f" y1="%s" x2="%.1f" y2="%s" stroke="%s" stroke-width="1"/>' % (x(d), top + 30, x(d), top + 14, t['soft']))
            s.text(x(d) + 3, top + 13, label, size=11, color=c['muted'])


def clip(s, c, a, b, y, h, label, kind='plain'):
    """One clip: plain (grey), red, or ghost (dashed outline, not kept)."""
    if kind == 'ghost':
        rect(s, a, y, b - a, h, 'none', stroke=c['clipline'], rx=3, sw=1.2, dash=True)
        s.text(a + 8, y + h / 2 + 4, label, size=12, color=c['muted'])
        return
    fill, line, ink = (c['red'], c['red'], c['onred']) if kind == 'red' else (c['clip'], c['clipline'], None)
    rect(s, a, y, b - a, h, fill, stroke=line, rx=3, sw=1)
    s.text(a + 8, y + h / 2 + 4, fits(label, b - a - 12), size=12, bold=kind == 'red', color=ink)


def hatch(s, c, a, b, y, h, pid):
    """The overlap: red diagonal lines over the lanes it covers."""
    s.add('<defs><pattern id="%s" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
          '<line x1="0" y1="0" x2="0" y2="8" stroke="%s" stroke-width="3" stroke-opacity="0.45"/></pattern></defs>' % (pid, c['red']))
    rect(s, a, y, b - a, h, 'url(#%s)' % pid, stroke=c['red'], sw=1.2, dash=True)


def playhead(s, c, x, top, bottom, label, side='right'):
    s.add('<line x1="%.1f" y1="%s" x2="%.1f" y2="%s" stroke="%s" stroke-width="2"/>' % (x, top + 4, x, bottom, c['play']))
    s.add('<polygon points="%.1f,%s %.1f,%s %.1f,%s %.1f,%s %.1f,%s" fill="%s"/>'
          % (x - 7, top, x + 7, top, x + 7, top + 10, x, top + 17, x - 7, top + 10, c['play']))
    if label:
        w = len(label) * 7.2 + 16
        bx = x + 12 if side == 'right' else x - 12 - w
        rect(s, bx, top - 34, w, 24, c['play'], rx=4, sw=0)
        s.text(bx + 8, top - 17, label, size=12, bold=True, color=c['onplay'])


def lane_head(s, c, y, h, name, sub=None):
    rect(s, 16, y, 106, h, c['lane'], rx=4, sw=0)
    s.text(26, y + h / 2 + (0 if sub else 4), name, size=12, bold=True)
    if sub:
        s.text(26, y + h / 2 + 17, sub, size=11, color=c['muted'])


# ---------------------------------------------------------------- finding 2

def clock_back(theme):
    t, c = THEMES['brand-' + theme], COLOURS[theme]
    s = Svg(1010, 318, 'brand-' + theme, 'Finding 2 as an editing timeline: the price of tea before and after one UPDATE with the clock set back to 2020')
    D = lambda v: datetime.strptime(v, '%Y-%m-%d')
    t0, t1, X0, X1 = D('2019-01-01'), D('2027-01-01'), 130, 994
    x = lambda d: X0 + (min(max(d, t0), t1) - t0).days * (X1 - X0) / (t1 - t0).days
    now = D('2026-11-13')
    rect(s, 0, 0, 1010, 318, c['panel'], rx=8, sw=0)
    s.text(16, 26, 'The price of tea, before and after one UPDATE with the clock set back to 2020', size=13, bold=True)
    TOP = 62
    editor_ruler(s, c, x, t0, t1, TOP, [(D('%d-01-01' % y), str(y)) for y in range(2019, 2028)],
                 [D('%d-%02d-01' % (y, m)) for y in range(2019, 2027) for m in (4, 7, 10)], X0, X1)
    # before: one track
    BY, H = 104, 34
    lane_head(s, c, BY, H, 'Before')
    rect(s, X0, BY, X1 - X0, H, c['lane'], sw=0)
    for a, b, label in (('2019-03-01', '2021-06-01', '10.00'), ('2021-06-01', '2024-01-15', '12.50'), ('2024-01-15', None, '14.00, current')):
        clip(s, c, x(D(a)), x(D(b)) if b else x(now), BY + 3, H - 6, label)
    # after: two tracks, because two lines cover the same days
    AY = 152
    lane_head(s, c, AY, 2 * H + 4, 'After', 'two tracks')
    rect(s, X0, AY, X1 - X0, H, c['lane'], sw=0)
    rect(s, X0, AY + H + 4, X1 - X0, H, c['lane'], sw=0)
    hatch(s, c, x(D('2020-01-01')), x(D('2024-01-15')), AY, 2 * H + 4, 'h2' + theme)
    clip(s, c, x(D('2019-03-01')), x(D('2021-06-01')), AY + 3, H - 6, '10.00')
    clip(s, c, x(D('2021-06-01')), x(D('2024-01-15')), AY + 3, H - 6, '12.50')
    clip(s, c, x(D('2024-01-15')), x(now), AY + 3, H - 6, '14.00 is not kept', kind='ghost')
    clip(s, c, x(D('2020-01-01')), x(now), AY + H + 7, H - 6, '11.00, saved with the clock set to 1 January 2020', kind='red')
    # three dates asked, as in the table under the picture
    bottom = AY + 2 * H + 10
    for d, label in (('2020-06-01', '1 June 2020: two answers'), ('2022-06-01', '1 June 2022: two answers'), ('2025-06-01', '1 June 2025: 14.00 is gone')):
        xx = x(D(d))
        s.add('<line x1="%.1f" y1="%s" x2="%.1f" y2="%s" stroke="%s" stroke-width="1.5" stroke-dasharray="4,3"/>' % (xx, TOP + 30, xx, bottom, c['play']))
        s.text(xx - 4, bottom + 16, label, size=11, color=c['muted'])
    y = 298
    rect(s, 16, y - 11, 22, 13, c['clip'], stroke=c['clipline'], rx=2, sw=1); s.text(44, y, 'a price, from its row_start to its row_end', size=11)
    rect(s, 300, y - 11, 22, 13, 'url(#h2%s)' % theme, stroke=c['red'], sw=1, dash=True); s.text(328, y, 'two prices for the same days', size=11)
    s.add('<line x1="530" y1="%s" x2="530" y2="%s" stroke="%s" stroke-width="1.5" stroke-dasharray="4,3"/>' % (y - 12, y + 3, c['play']))
    s.text(540, y, 'a date you ask about', size=11)
    return s


# ---------------------------------------------------------------- finding 6

def overlap(theme):
    t, c = THEMES['brand-' + theme], COLOURS[theme]
    s = Svg(1010, 256, 'brand-' + theme, "Finding 6 as an editing timeline: two imported versions of id 4 overlap, so AS OF '2020-09-01' stands on both")
    D = lambda v: datetime.strptime(v, '%Y-%m-%d')
    t0, t1, X0, X1 = D('2019-10-01'), D('2022-04-01'), 130, 994
    x = lambda d: X0 + (min(max(d, t0), t1) - t0).days * (X1 - X0) / (t1 - t0).days
    rect(s, 0, 0, 1010, 256, c['panel'], rx=8, sw=0)
    s.text(16, 26, 'Two imported versions of id 4', size=13, bold=True)
    TOP = 62
    months = [D('%d-%02d-01' % (y, m)) for y in range(2019, 2023) for m in range(1, 13)]
    editor_ruler(s, c, x, t0, t1, TOP, [(d, d.strftime('%b %Y')) for d in months if d.month in (1, 4, 7, 10)], months, X0, X1)
    Y, H = 104, 34
    lane_head(s, c, Y, 2 * H + 4, 'id 4', 'two tracks')
    rect(s, X0, Y, X1 - X0, H, c['lane'], sw=0)
    rect(s, X0, Y + H + 4, X1 - X0, H, c['lane'], sw=0)
    hatch(s, c, x(D('2020-06-01')), x(D('2021-01-01')), Y, 2 * H + 4, 'h6' + theme)
    clip(s, c, x(D('2020-01-01')), x(D('2021-01-01')), Y + 3, H - 6, 'version 1, January 2020 to January 2021')
    clip(s, c, x(D('2020-06-01')), x(D('2022-01-01')), Y + H + 7, H - 6, 'version 2, June 2020 to January 2022', kind='red')
    px = x(D('2020-09-01'))
    playhead(s, c, px, TOP, Y + 2 * H + 10, "AS OF '2020-09-01'")
    s.text(px + 6, Y + 2 * H + 26, 'stands on both clips: two rows for one key', size=11.5, bold=True)
    y = 238
    rect(s, 16, y - 11, 22, 13, c['clip'], stroke=c['clipline'], rx=2, sw=1); s.text(44, y, 'a version, from its row_start to its row_end', size=11)
    rect(s, 320, y - 11, 22, 13, 'url(#h6%s)' % theme, stroke=c['red'], sw=1, dash=True); s.text(348, y, 'two versions for the same months', size=11)
    s.add('<line x1="570" y1="%s" x2="570" y2="%s" stroke="%s" stroke-width="2"/>' % (y - 12, y + 3, c['play']))
    s.text(580, y, 'the playhead: the moment you ask about', size=11)
    return s


if __name__ == '__main__':
    os.makedirs(HERE, exist_ok=True)
    for theme in ('light', 'dark'):
        timeline(theme).save(os.path.join(HERE, 'timeline-%s.svg' % theme))
        build(theme).save(os.path.join(HERE, 'build-%s.svg' % theme))
        old_dates(theme).save(os.path.join(HERE, 'old-dates-%s.svg' % theme))
        build(theme, BUILD_DETAIL, 'How the project is built, with the file of each step').save(os.path.join(HERE, 'build-detail-%s.svg' % theme))
        clock_back(theme).save(os.path.join(HERE, 'clock-back-%s.svg' % theme))
        overlap(theme).save(os.path.join(HERE, 'overlap-%s.svg' % theme))
    print('wrote 12 files in', HERE)

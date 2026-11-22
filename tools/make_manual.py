#!/usr/bin/env python3
"""Build the PDF manual (docs/PPPCCC-MC-Mods-<version>-Manual.pdf) from the documentation in this repository.

Sources: README.md (intro, status, credits, license), docs/USER_GUIDE.md (quick reference, what is saved where),
docs/patches/NN-*.md (one chapter per patch, without the technical part), docs/BUILD.md (patch ids), assets/titles/.
Installation and troubleshooting texts are written below.

Needs: Python 3.8+, `pip install markdown pypdf playwright` and `playwright install chromium`.
    python3 tools/make_manual.py [--out FILE] [--html FILE]
"""
import argparse, base64, html, io, json, pathlib, re, sys, tempfile

import markdown
from pypdf import PdfReader, PdfWriter
from playwright.sync_api import sync_playwright

R = pathlib.Path(__file__).resolve().parent.parent
VERSION = json.load(open(R / 'patches' / 'manifest.json')).get('version', '2.3.1')
TITLE = 'PPPCCC M:C Mods'
PAGE = 'https://gialloinfuso.github.io/PPPCCC-M-S-Mods/'
GH = 'https://github.com/gialloinfuso/PPPCCC-M-S-Mods'

# ---------------------------------------------------------------- Markdown -> HTML

KEYWORD = re.compile(r"^[A-Z0-9][A-Z0-9 .'/:–\-]*$")


def keys(s):
    """**FUNC + DECAY** -> <kbd>FUNC</kbd> + <kbd>DECAY</kbd>; other bold text stays bold."""
    def one(m):
        t = m.group(1)
        parts = [p.strip() for p in t.split('+')]
        if all(KEYWORD.match(p) and any(c.isalpha() for c in p) or re.fullmatch(r'T1–T6|1–6', p) for p in parts if p):
            return ' + '.join(f'<kbd>{p}</kbd>' for p in parts)
        return f'<strong>{t}</strong>'
    return re.sub(r'<strong>(.*?)</strong>', one, s)


def md(text, inline=False):
    # internal links (to other .md files or anchors) -> plain text; external links stay
    text = re.sub(r'\[([^\]]+)\]\((?!https?://)[^)]*\)', r'\1', text)
    h = markdown.markdown(text, extensions=['tables'])
    h = keys(h)
    h = h.replace('<table>', '<table class="t">')
    if inline:
        h = re.sub(r'^<p>(.*)</p>$', r'\1', h.strip(), flags=re.S)
    return h


def sections(text):
    """'## ' sections of a Markdown file -> (head, {name: body})"""
    parts = re.split(r'^## (.+)$', text, flags=re.M)
    return parts[0], {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts), 2)}


def section(text, name, level='##'):
    m = re.search(rf'^{level} {re.escape(name)}\s*$(.*?)(?=^#{{1,{len(level)}}} |\Z)', text, flags=re.M | re.S)
    return m.group(1).strip() if m else ''


def img(path, cls=''):
    b = base64.b64encode(pathlib.Path(path).read_bytes()).decode()
    return f'<img class="{cls}" src="data:image/png;base64,{b}" alt="">'


# ---------------------------------------------------------------- sources

README = (R / 'README.md').read_text()
GUIDE = (R / 'docs' / 'USER_GUIDE.md').read_text()
BUILD = (R / 'docs' / 'BUILD.md').read_text()
PATCHES = sorted((R / 'docs' / 'patches').glob('[0-9][0-9]-*.md'))

# tags (NEW / UPDATE) and short titles from the README's patch list
TAGS = {}
for m in re.finditer(r'^### (\d\d) · (.+?) \(\[details\].*?\)(.*)$', README, flags=re.M):
    t = re.search(r'`(NEW|UPDATE) v[\d.]+`', m.group(3))
    TAGS[m.group(1)] = t.group(1) if t else ''
TAGS['00'] = 'UPDATE'


def intro_text():
    body = README.split('\n', 1)[1]
    body = body[:body.index('**[☕')]
    status = re.search(r'^> \*\*Status:.*?(?=\n\n)', README, flags=re.M | re.S).group(0)
    status = '\n'.join(l[2:] for l in status.splitlines())
    return body.strip(), status


# ---------------------------------------------------------------- chapters

def cover():
    tiles = ''.join(f'<div class="tile">{img(R / "assets" / "titles" / f"{n}.png")}</div>' for n in
                    ('15', '04', '17', '12', '16', '19'))
    return f'''
<section class="cover">
  <div class="band"></div>
  <div class="ctext">
    <div class="eyebrow">Manual · v{VERSION}</div>
    <h1 class="ctitle">{TITLE}</h1>
    <p class="csub">Extra features for the <b>Elektron Model:Cycles OS 1.13</b><br>— also on a <b>Model:Samples</b> running the Cycles OS</p>
  </div>
  <div class="tiles">{tiles}</div>
  <div class="cfoot">{PAGE}<br>Not affiliated with Elektron. As with any firmware mod: use at your own risk.</div>
</section>'''


def toc(pages):
    rows = []
    for kind, anchor, label in TOC:
        p = pages.get(anchor, '')
        rows.append(f'<a class="toc {kind}" href="#{anchor}"><span class="tl">{label}</span><span class="dots"></span>'
                    f'<span class="pg">{p}</span></a>')
    return f'<section class="chap" id="contents"><h1>Contents</h1><nav class="tocbox">{"".join(rows)}</nav></section>'


TOC = []


def chapter(anchor, title, body, kind='c'):
    TOC.append((kind, anchor, title))
    return f'<section class="chap" id="{anchor}"><h1>{html.escape(title)}</h1>{body}</section>'


def ch_intro():
    body, status = intro_text()
    return chapter('intro', 'Introduction', f'''
{md(body)}
<div class="note">{md(status)}</div>
<h2 class="sub">About this manual</h2>
<p>This manual covers the full build with all patches. <i>Installation</i> shows how to build and flash the mods,
the <i>Quick reference</i> lists every key combination on two pages, and then every patch has its own chapter with its controls, what it stores and what it
needs. The technical side of each patch (hooks, memory, tests) is not in here; it is in the repository
(<code>docs/patches/</code> and <code>docs/TECHNICAL.md</code>).</p>
<p>Keys are written like this: <kbd>FUNC</kbd> + <kbd>DECAY</kbd> means <i>hold FUNC and turn DECAY</i> (or press it,
for a key). <kbd>T1–T6</kbd> are the six track keys, <i>trig 1–16</i> the trig keys. Every patch can be built on its
own; a patch that needs another one gets it automatically. Patches marked <span class="tag NEW">NEW</span> were added
in v2.3, <span class="tag UPDATE">UPDATE</span> means they changed in v2.3 or v2.3.1 (see the changelog).</p>''')


def ch_install():
    ids = section(BUILD, 'Choosing patches')
    ids = ids[ids.index('| Patch'):]
    ids = '\n'.join(l for l in ids.splitlines() if l.startswith('|'))
    return chapter('install', 'Installation', f'''
<p>No firmware file is distributed: a firmware file contains Elektron's operating system. You build the modded
firmware yourself, from your own copy of the official file. The repository only holds the bytes each patch writes and a
checksum of what they replace; every write is checked against your file, and the complete result against a published
checksum.</p>

<h2 class="sub">Before you start</h2>
<ul>
<li>Download the official <code>model-cycles_OS1.13.syx</code> from <a href="https://www.elektron.se">elektron.se</a>
(Support › Downloads). For a Model:Samples also <code>model-samples_OS1.13.syx</code>.</li>
<li><b>Back up</b> your projects and samples with Elektron Transfer.</li>
<li>The firmware writes its device settings when you switch off. A USB OS update restarts without saving them, so
after changing a device setting (for example the CONTROL ALL mode), switch off once before you flash.</li>
</ul>

<h2 class="sub">With the flasher (in the browser)</h2>
<p>The flasher at <a href="{PAGE}flasher/">{PAGE}flasher/</a> does everything on your computer; no file is uploaded. It
builds exactly the same file as the build tool.</p>
<ol class="steps">
<li><b>Your device.</b> Choose Model:Cycles or Model:Samples. On a Model:Samples, choose <i>First time</i> (it still
runs the Samples OS) or <i>Update</i> (it already runs a Cycles OS).</li>
<li><b>Your official firmware.</b> Give the page your official file(s). It checks them by SHA-256 and refuses anything
else. On a Model:Samples: both official files, or a Cycles OS for the Model:Samples made with Modded-Cycles'
<code>crossflash.py --to samples</code>.</li>
<li><b>Patches.</b> Tick what you want. What a patch needs is ticked with it; the core is added automatically.</li>
<li><b>Build and flash.</b> The page builds and checks the file and shows its SHA-256. Download it, or send it directly
over Web MIDI (Chrome, Edge or Opera on a desktop computer; Safari and Firefox: download it and send it with Elektron
Transfer). Confirm the backup checkbox, choose the device and press Send.</li>
</ol>

<h2 class="sub">Which file goes where</h2>
<table class="t">
<thead><tr><th>Device</th><th>File</th><th>Send it</th></tr></thead>
<tbody>
<tr><td>Model:Cycles</td><td><code>…_cyc-os.syx</code></td><td>like any OS update: from the running OS, or in the start-up menu
(hold <kbd>FUNC</kbd> while switching on, then OS UPGRADE)</td></tr>
<tr><td>Model:Samples, first flash</td><td><code>…_smp-os.syx</code></td><td>from the Samples OS or its start-up menu</td></tr>
<tr><td>Model:Samples, later updates</td><td><code>…_cyc-os.syx</code></td><td>it already runs a Cycles OS with the Samples key</td></tr>
</tbody></table>

<h2 class="sub">With the build tool (Python)</h2>
<p>You need Python 3 and the official file; the firmware container code comes with the repository
(<code>tools/vendor/</code>). Details: <code>docs/BUILD.md</code>.</p>
<pre>python3 tools/build.py --in model-cycles_OS1.13.syx --out cycles-mods</pre>
<p>For a Model:Samples, first make the Cycles OS for the Model:Samples, then build both files:</p>
<pre>python3 tools/vendor/crossflash.py --cycles model-cycles_OS1.13.syx \\
        --samples model-samples_OS1.13.syx --to samples -o cycles-for-samples.syx
python3 tools/build.py --in cycles-for-samples.syx --out cycles-mods --smp</pre>
<p>To build only some patches, name them by id; what they need is added:</p>
<pre>python3 tools/build.py --in model-cycles_OS1.13.syx --out my-mods mute-solo reverb-fx groove</pre>
<div class="cols2">{md(ids)}</div>

<h2 class="sub">Back to the official firmware</h2>
<ul>
<li><b>Model:Cycles:</b> send the official <code>model-cycles_OS1.13.syx</code> like any OS update.</li>
<li><b>Model:Samples:</b> the official Samples OS goes back over USB in the Cycles transport:
<code>python3 tools/vendor/crossflash.py --cycles model-cycles_OS1.13.syx --samples model-samples_OS1.13.syx
--back-samples</code> makes that file (see Modded-Cycles' notes/41). The start-up menu of the Model:Samples (MIDI IN)
always remains as a fallback.</li>
</ul>''')


def ch_quickref():
    mod = section(GUIDE, 'Modifier keys')
    tail = mod[mod.index('\n\n', mod.index('| **PATTERN**')):].strip() if '| **PATTERN**' in mod else ''
    mod_table = mod[:len(mod) - len(tail)].strip()
    ov = section(README, 'Controls overview')
    ov = '\n'.join(l for l in ov.splitlines() if l.startswith('|'))
    return chapter('quickref', 'Quick reference', f'''
<p class="lead">Every key combination of the full build. The page after this one lists them patch by patch.</p>
<h2 class="sub">Modifier keys</h2>
{md(mod_table)}
<div class="note">{md(tail)}</div>
<h2 class="sub pb">All controls by patch</h2>
<div class="compact">{md(ov)}</div>''')


def ch_patch(f):
    text = f.read_text()
    head, sec = sections(text)
    m = re.match(r'# (\d\d) · (.+)', head)
    num, title = m.group(1), m.group(2).strip()
    intro = '\n'.join(l for l in head.splitlines()[1:] if not l.startswith('Patch id ')).strip()
    dep = sec.get('Dependencies', '')
    req = re.search(r'Requires: (.*?)\.\s*$', dep, flags=re.M)
    req = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', req.group(1)) if req else 'nothing'
    need = re.search(r'Needed by: (.*?)\.\s*$', dep, flags=re.M)
    need = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', need.group(1)) if need else ''
    ctl = sec.get('Controls', '')
    tag = TAGS.get(num, '')
    pic = R / 'assets' / 'titles' / f'{num}.png'
    meta = f'<span><b>Needs:</b> {html.escape(req)}</span>' + (f'<span><b>Needed by:</b> {html.escape(need)}</span>' if need else '')
    body = f'''
<div class="phead"><span class="num">{num}</span><h1>{html.escape(title)}</h1>{f'<span class="tag {tag}">{tag}</span>' if tag else ''}</div>
<div class="meta">{meta}</div>
<div class="pintro{' withpic' if pic.exists() else ''}"><div>{md(intro)}</div>{img(pic, 'pic') if pic.exists() else ''}</div>
<h2 class="sub">Controls</h2>
{md(ctl)}'''
    if sec.get('Good to know'):
        body += f'<h2 class="sub">Good to know</h2>{md(sec["Good to know"])}'
    if sec.get('What is stored'):
        body += f'<h2 class="sub">What is stored</h2>{md(sec["What is stored"])}'
    TOC.append(('p', f'p{num}', f'{num} · {title}'))
    return f'<section class="chap patch" id="p{num}">{body}</section>'


def ch_machines():
    mach = section(GUIDE, 'Machines')
    return chapter('machines', 'The three new machines', f'''
<p class="lead">Patches 15, 16 and 17 add three machines after CHORD: <b>Grit</b> (a sampler), <b>Vlvt</b> (a string
ensemble) and <b>Monom</b> (a monophonic synth). They only work together: Vlvt needs Grit, Monom needs Grit and Vlvt.
Choose them on the MACHINES screen like the others; their parameters are real parameters (p-locks, LFO and velocity
destinations, saved with the sound).</p>
<div class="wide">{md(mach)}</div>
<p>Use the track filter (patch 12) as the filter of all three.</p>''')


def ch_saved():
    s = section(GUIDE, 'What is saved where')
    return chapter('saved', 'What is saved where', md(s))


def ch_help():
    q = [
        ('The flasher says my file is not the official one',
         'Only the official OS 1.13 files are accepted (checked by SHA-256). Download them again from elektron.se, and do '
         'not use a file that was already modified.'),
        ('“Find MIDI devices” finds nothing, or Send is not available',
         'Web MIDI with SysEx works in Chrome, Edge and Opera on a desktop computer; allow MIDI access when the browser '
         'asks. Connect the device over USB and close other programs that use it (Elektron Transfer, other music '
         'software). In Safari and Firefox, download the file and send it with Elektron Transfer.'),
        ('The transfer stopped or the device shows an error',
         'Nothing is lost: switch the device off and on, open the start-up menu (hold FUNC while switching on, then OS '
         'UPGRADE) and send the file again, with a higher “Speed” value in the flasher. With a Model:Samples on the first '
         'flash, send the <code>_smp-os</code> file.'),
        ('Which file do I need on a Model:Samples?',
         '<b>First flash</b> (still on the Samples OS): the <code>_smp-os.syx</code>. <b>Later updates</b> (a Cycles OS '
         'with the Samples key already runs): the <code>_cyc-os.syx</code>.'),
        ('A setting I changed is gone after the update',
         'The firmware writes its device settings when you switch off; a USB OS update restarts without saving them. '
         'Switch off once after changing a setting, then flash.'),
        ('Grit plays nothing / the browser shows no samples',
         'Grit plays samples from the +Drive. Upload them with Elektron Transfer after switching Device Config > Transfer '
         'to SMP (every start begins with CYC), reconnect Transfer, then choose them with FUNC + MACHINES on a Grit track.'),
        ('Projects from the stock OS or v2.2',
         'Patterns and sounds of the stock OS and of v2.2.0 load as before. Strum settings of v2.2 patterns are not '
         'carried over (strum is now per sound).'),
        ('Can I check the file myself?',
         'Yes: <code>tools/build.py</code> of the repository builds the same file from the same patches, byte for byte, '
         'and both show the SHA-256 of the result.'),
        ('Where do I report a bug?',
         f'In the issues of the repository ({GH}). There is no support beyond bug fixes as time allows.'),
    ]
    body = ''.join(f'<div class="qa"><h3>{a}</h3><p>{b}</p></div>' for a, b in q)
    return chapter('help', 'Troubleshooting', body)


def ch_credits():
    cr = section(README, 'Credits')
    lic = section(README, 'License')
    return chapter('credits', 'Credits and license', f'''{md(cr)}
<h2 class="sub">License</h2>{md(lic)}
<p class="small">Model:Cycles and Model:Samples are products of Elektron Music Machines. This project is not
affiliated with or endorsed by Elektron. As with any firmware mod: use at your own risk.</p>
<p class="small">Project page: <a href="{PAGE}">{PAGE}</a> · Repository: <a href="{GH}">{GH}</a> ·
<a href="https://ko-fi.com/pppccc">ko-fi.com/pppccc</a></p>''')


CSS = r'''
@page { size: A4; margin: 17mm 16mm 18mm 16mm; }
:root { --accent:#d9620f; --text:#18181d; --muted:#5f5f6c; --line:#dcdce4; --soft:#f4f4f7; --kbd:#ececf2; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: 'Inter', sans-serif; font-size: 9.4pt; line-height: 1.5; color: var(--text); margin: 0;
       font-feature-settings: 'cv11', 'ss01'; }
a { color: var(--accent); text-decoration: none; }
p { margin: 0 0 2.4mm; }
ul, ol { margin: 0 0 3mm; padding-left: 5mm; }
li { margin-bottom: 1mm; }
code, pre { font-family: 'DejaVu Sans Mono', monospace; font-size: 0.86em; }
code { background: var(--soft); padding: 0 1mm; border-radius: 1mm; }
pre { background: #18181d; color: #ececf1; padding: 3mm 4mm; border-radius: 2mm; white-space: pre-wrap; margin: 0 0 3mm;
      font-size: 8pt; line-height: 1.45; }
kbd { font-family: 'Inter', sans-serif; font-weight: 600; font-size: 0.82em; letter-spacing: .02em; background: var(--kbd);
      border: 0.3mm solid #c9c9d3; border-bottom-width: 0.6mm; border-radius: 1.2mm; padding: 0 1.1mm; white-space: nowrap; }
.chap { break-before: page; }
h1 { font-size: 20pt; line-height: 1.15; margin: 0 0 5mm; letter-spacing: -0.01em; font-weight: 750; }
.chap > h1 { border-bottom: 0.8mm solid var(--accent); padding-bottom: 2.5mm; }
h2.sub { font-size: 11.5pt; margin: 5.5mm 0 2.2mm; color: var(--text); font-weight: 700; break-after: avoid; }
h2.sub.pb { break-before: page; margin-top: 0; }
h3 { font-size: 10pt; margin: 4mm 0 1.2mm; break-after: avoid; }
.lead { font-size: 10.2pt; color: var(--muted); }
.small { font-size: 8pt; color: var(--muted); }
table.t { width: 100%; border-collapse: collapse; margin: 0 0 3mm; font-size: 8.7pt; line-height: 1.42; }
table.t th { text-align: left; font-weight: 700; color: var(--muted); font-size: 7.6pt; text-transform: uppercase;
             letter-spacing: .05em; border-bottom: 0.5mm solid var(--text); padding: 1.3mm 2mm; }
table.t td { border-bottom: 0.25mm solid var(--line); padding: 1.5mm 2mm; vertical-align: top; }
table.t tr { break-inside: avoid; }
table.t td:first-child { width: 38%; }
.note { background: #fff4ec; border-left: 1mm solid var(--accent); padding: 2.5mm 4mm; border-radius: 0 1.5mm 1.5mm 0;
        margin: 3mm 0; font-size: 8.9pt; }
.note p:last-child { margin: 0; }
.tag { display: inline-block; font-size: 7pt; font-weight: 700; letter-spacing: .08em; padding: 0.4mm 1.8mm;
       border-radius: 5mm; vertical-align: middle; }
.tag.NEW { background: var(--accent); color: #fff; }
.tag.UPDATE { background: #18181d; color: #fff; }
ol.steps { padding-left: 6mm; }
ol.steps li { margin-bottom: 2mm; }
.cols2 table.t td:first-child { width: auto; }
.compact table.t { font-size: 7.9pt; line-height: 1.32; }
.compact table.t td { padding: 1.05mm 1.6mm; }
.compact table.t td:first-child { width: 17%; }
.wide table.t td:first-child { width: auto; white-space: nowrap; }
table.t code { white-space: nowrap; }
.cols2 { columns: 2; column-gap: 8mm; }
.cols2 table.t { font-size: 8pt; }
/* patches */
.phead { display: flex; align-items: center; gap: 3.5mm; border-bottom: 0.8mm solid var(--accent); padding-bottom: 2.5mm;
         margin-bottom: 2mm; }
.phead h1 { margin: 0; font-size: 17pt; flex: 1; }
.phead .num { font-size: 17pt; font-weight: 800; color: var(--accent); font-variant-numeric: tabular-nums; }
.meta { font-size: 8pt; color: var(--muted); margin-bottom: 4mm; display: flex; gap: 6mm; }
.pintro.withpic { display: grid; grid-template-columns: 1fr 66mm; gap: 6mm; align-items: start; }
.pintro { font-size: 9.8pt; margin-bottom: 1mm; }
img.pic { width: 66mm; border-radius: 2mm; display: block; }
/* contents */
.tocbox { display: block; }
a.toc { display: flex; align-items: baseline; color: var(--text); padding: 1.15mm 0; }
a.toc.c { font-weight: 700; font-size: 10.5pt; margin-top: 2.6mm; }
a.toc.p { font-size: 9.2pt; padding-left: 6mm; }
a.toc .dots { flex: 1; border-bottom: 0.3mm dotted #b8b8c4; margin: 0 2mm; transform: translateY(-1mm); }
a.toc .pg { font-variant-numeric: tabular-nums; min-width: 7mm; text-align: right; }
/* help */
.qa { break-inside: avoid; margin-bottom: 2mm; }
/* cover */
.cover { height: 297mm; width: 210mm; position: relative; overflow: hidden; background: #141418; color: #ececf1; }
.cover .band { position: absolute; left: 0; top: 0; width: 210mm; height: 6mm; background: var(--accent); }
.cover .ctext { position: absolute; left: 18mm; top: 34mm; right: 18mm; }
.cover .eyebrow { color: #ff8a3d; font-weight: 700; letter-spacing: .16em; text-transform: uppercase; font-size: 10pt; }
.cover .ctitle { font-size: 44pt; font-weight: 800; letter-spacing: -0.02em; margin: 3mm 0 5mm; border: 0; }
.cover .csub { font-size: 13pt; line-height: 1.45; color: #c4c4cf; }
.cover .tiles { position: absolute; left: 18mm; right: 18mm; top: 118mm; display: grid; grid-template-columns: 1fr 1fr;
                gap: 5mm; }
.cover .tile img { width: 100%; display: block; border-radius: 2.5mm; }
.cover .cfoot { position: absolute; left: 18mm; bottom: 14mm; font-size: 8.5pt; color: #9a9aa8; line-height: 1.6; }
'''


def page(body, cover=False):
    css = CSS + ('@page { margin: 0; }' if cover else '')
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{TITLE} – Manual v{VERSION}</title>' \
           f'<style>{css}</style></head><body>{body}</body></html>'


FOOT = '''<div style="font-family: Inter, sans-serif; font-size: 7.5pt; color: #8a8a96; width: 100%; padding: 0 16mm;
display: flex; justify-content: space-between;"><span>PPPCCC M:C Mods · Manual v@V@</span>
<span class="pageNumber"></span></div>'''


def render(pw, html_text, out, cover=False):
    b = pw.chromium.launch()
    p = b.new_page()
    p.set_content(html_text, wait_until='load')
    p.evaluate('document.fonts.ready')
    kw = dict(path=str(out), format='A4', print_background=True, outline=True, tagged=True)
    if cover:
        kw.update(margin=dict(top='0', bottom='0', left='0', right='0'))
    else:
        kw.update(display_header_footer=True, header_template='<span></span>',
                  footer_template=FOOT.replace('@V@', VERSION), prefer_css_page_size=True)
    p.pdf(**kw)
    b.close()


def outline_pages(pdf):
    """anchors -> page numbers (1-based, of the body), from the PDF outline: h1 text -> TOC entry"""
    r = PdfReader(str(pdf))
    got = {}

    def walk(items):
        for it in items:
            if isinstance(it, list):
                walk(it)
            else:
                got.setdefault(it.title.strip(), r.get_destination_page_number(it) + 1)
    walk(r.outline)
    norm = lambda x: re.sub(r'\s+', '', x)
    pages = {}
    for kind, anchor, label in TOC:
        title = norm(label.split(' · ', 1)[1] if kind == 'p' else label)
        for t, n in got.items():
            if norm(t)[:min(18, len(title))] == title[:18]:          # Chromium's outline may repeat or cut a wrapped heading
                pages[anchor] = n
                break
    return pages


def build(out, html_out=None):
    TOC.clear()
    chapters = [ch_intro(), ch_install(), ch_quickref()]
    pats = [ch_patch(f) for f in PATCHES]
    chapters += pats[:15]
    chapters.append(ch_machines())
    chapters += pats[15:]
    # the machines chapter belongs before patch 15 in the contents too
    i = next(k for k, t in enumerate(TOC) if t[1] == 'machines')
    m = TOC.pop(i)
    TOC.insert(next(k for k, t in enumerate(TOC) if t[1] == 'p15'), m)
    chapters += [ch_saved(), ch_help(), ch_credits()]
    tmp = pathlib.Path(tempfile.mkdtemp())
    with sync_playwright() as pw:
        body = toc({}) + ''.join(chapters)
        render(pw, page(body), tmp / 'pass1.pdf')
        pages = outline_pages(tmp / 'pass1.pdf')
        missing = [a for _, a, _ in TOC if a not in pages]
        assert not missing, missing
        body = toc(pages) + ''.join(chapters)
        if html_out:
            pathlib.Path(html_out).write_text(page(cover() + body))
        render(pw, page(body), tmp / 'body.pdf')
        assert outline_pages(tmp / 'body.pdf') == pages, 'page numbers moved between the passes'
        render(pw, page(cover(), cover=True), tmp / 'cover.pdf', cover=True)
    w = PdfWriter()
    w.append(str(tmp / 'cover.pdf'), import_outline=False)
    w.append(str(tmp / 'body.pdf'), import_outline=False)
    # own outline (bookmarks): chapters, the patches under "Patches"; body page n = PDF page n (the cover is page 0)
    w.add_outline_item('Contents', 1)
    parent = None
    for kind, anchor, label in TOC:
        if kind == 'p':
            if parent is None:
                parent = w.add_outline_item('Patches', pages[anchor])
            w.add_outline_item(label, pages[anchor], parent=parent)
        elif anchor == 'machines' and parent is not None:
            w.add_outline_item(label, pages[anchor], parent=parent)
        else:
            w.add_outline_item(label, pages[anchor])
    w.add_metadata({'/Title': f'{TITLE} – Manual v{VERSION}', '/Author': 'PPPCCC',
                    '/Subject': 'Extra features for the Elektron Model:Cycles OS 1.13'})
    w.page_mode = '/UseOutlines'
    with open(out, 'wb') as f:
        w.write(f)
    return len(w.pages)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=str(R / 'docs' / f'PPPCCC-MC-Mods-{VERSION}-Manual.pdf'))
    ap.add_argument('--html', help='also write the HTML (for checking)')
    a = ap.parse_args()
    n = build(a.out, a.html)
    print(f'ok: {a.out} ({n} pages)')

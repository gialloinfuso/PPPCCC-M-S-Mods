# Core-Popup (v2): echter ViewController-Zeichenlauf 0x40076c1a mit Haken OVT, echte Schriften und Firmware-Zeichenfunktionen.
# Pixel fuer Pixel gegen dieselben Firmware-Aufrufe direkt aus Python (wie ParameterPageView::draw). Dazu Art 3 (eigene
# Zeichenfunktion der Lastanzeige) gegen die Python-Vorlage aus v1, Ablauf nach 1.5 s, Magic, Ueberlauf, Muell, Art 0.
import struct
from rig import *
import gen_overlay_113 as ov

img = v2_image(); CS = V2SYM['core']; OVS, OVT = CS['OVS'], CS['OVT']
e = Emu(img); uc = e.u; w32, r32 = e.w32, e.r32
RENDER, CLEAR, LOCK, UNLOCK = 0x40076C1A, 0x4007133C, 0x400E8684, 0x400D08CE
VC, NODE, VIEW, VTAB, DRAWSTUB, BMP, DATA = 0x4F020000, 0x4F020100, 0x4F020200, 0x4F020300, 0x4E000100, 0x4F020400, 0x4F021000
uc.mem_write(BMP, struct.pack('>IIIII', 0, 128, 64, 2, DATA))
w32(VC + 0x1C, NODE); w32(NODE, VC + 0x14); w32(NODE + 8, VIEW); w32(VIEW, VTAB); w32(VTAB + 0x10, DRAWSTUB)
VIEWPIX = {(x, y) for x in range(0, 128, 3) for y in range(0, 64, 2)}
calls = []
def setpix(x, y):
    a = DATA + (x * 2 + y // 32) * 4; w32(a, r32(a) | (1 << (31 - (y & 31))))
def hk(u, a, s, _):
    sp = u.reg_read(mk.UC_M68K_REG_A7); ret = r32(sp)
    if a == CLEAR: u.mem_write(DATA, bytes(1024)); calls.append('clear')
    elif a == DRAWSTUB:
        calls.append(('draw', r32(sp + 4), r32(sp + 8)))
        for x, y in VIEWPIX: setpix(x, y)
    elif a in (LOCK, UNLOCK): calls.append(a)
    for r in (mk.UC_M68K_REG_D0, mk.UC_M68K_REG_D1, mk.UC_M68K_REG_A0, mk.UC_M68K_REG_A1): u.reg_write(r, 0xBAD0BAD0)
    u.reg_write(mk.UC_M68K_REG_PC, ret); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
for t in (CLEAR, DRAWSTUB, LOCK, UNLOCK): uc.hook_add(UC_HOOK_CODE, hk, begin=t, end=t)
def call(entry, args=(), regs=None):
    return e.call(entry, *args, regs={k: v & 0xffffffff for k, v in (regs or {}).items()}, count=400000)[1]
def screen():
    raw = bytes(uc.mem_read(DATA, 1024)); px = set()
    for x in range(128):
        for wd in range(2):
            v = struct.unpack('>I', raw[(x * 2 + wd) * 4:(x * 2 + wd) * 4 + 4])[0]
            for bit in range(32):
                if v >> (31 - bit) & 1: px.add((x, wd * 32 + bit))
    return px
dirty = lambda: uc.mem_read(VC + 0x20, 1)[0]
def render(force=True):
    if force: uc.mem_write(VC + 0x20, b'\1')
    calls.clear(); return call(RENDER, [VC, BMP])
STR = 0x4F03F800
def cs_(t, at): uc.mem_write(at, t.encode('latin-1') + b'\0'); return at
def native(n1, n2, val, text=False):
    uc.mem_write(DATA, bytes(1024))
    call(ov.FILL_F, [BMP, 0, 0, 63, 63, 1]); call(ov.FRAME_F, [BMP, 0, 0, 63, 63, 0]); call(ov.FILL_F, [BMP, 64, 0, 127, 63, 0])
    call(ov.TXT_F, [BMP, ov.F_NAME, 32, 47, 2, cs_(n1, STR)])
    if n2: call(ov.TXT_F, [BMP, ov.F_NAME, 32, 34, 2, cs_(n2, STR + 64)])
    if text: call(ov.TXT_F, [BMP, ov.F_NAME, 96, 34, 2, ov.FMT_S, cs_(val, STR + 128)])
    else: call(ov.TXT_F, [BMP, ov.F_VAL, 96, 34, 2, ov.FMT_D, val])
    call(ov.FILL_F, [BMP, 0, 0, 63, 63, -1])
    return screen()
def find(s):                                   # Text in einer Mod-Maske des Images
    i = img.find(s.encode() + b'\0', 0x40140000 - BASE); assert i > 0, s; return BASE + i
call(0x400E7D50)                               # Schriften wie beim Start

chk('Haken 0x40076c88 = jsr OVT', img[0x40076C88 - BASE:0x40076C88 - BASE + 6] == C.jsr(OVT))
uc.mem_write(C.VARS, b'\xAA' * 64); w32(C.TIMER, 1000)
call(OVS, regs={mk.UC_M68K_REG_D0: 1, mk.UC_M68K_REG_D1: 64, mk.UC_M68K_REG_A0: find('Strum'), mk.UC_M68K_REG_A1: 0})
uc.mem_write(VC + 0x20, b'\0')
chk('OVS vor dem ersten Zeichnen (kein Magic): VC unbekannt, nichts angefasst', dirty() == 0)
good = render()
chk('erstes Zeichnen: View gezeichnet, Magic gesetzt, kein Popup, PEND/MPEND geloescht, Register/Stack ok',
    ('draw', VIEW, BMP) in calls and screen() == VIEWPIX and dirty() == 0 and r32(C.VARS + C.V_VC) == VC
    and r32(C.VARS + C.V_PEND) == 0 and r32(C.VARS + C.V_MPEND) == 0 and good)
calls.clear(); good = call(RENDER, [VC, BMP])
chk('nicht markiert: Zeichenlauf tut nichts (wie Original)', calls == [] and good)
CASES = [('VIBDEL', 'Speed', 64, False), ('CHODEL', 'Speed', 0, False), ('Delay', 'Speed', 127, False), ('Strum', None, -80, False),
         ('Strum', None, 80, False), ('Strum', None, 0, False), ('Groove', None, 'Swing', True), ('Groove', None, 'Boom Bap', True),
         ('Groove', None, 'Highlife', True), ('Groove', None, 'Kuduro', True), ('Groove', None, 'Caixixi', True),
         ('Hum Time', 'Track', 37, False), ('Hum Time', 'All', 100, False), ('Hum Vel', 'Track', 12, False), ('Hum Vel', 'All', 0, False)]
last = None
for n1, n2, val, text in CASES:
    exp = native(n1, n2, val, text)
    uc.mem_write(VC + 0x20, b'\0')
    ok_ = call(OVS, regs={mk.UC_M68K_REG_D0: 2 if text else 1, mk.UC_M68K_REG_D1: find(val) if text else val,
                          mk.UC_M68K_REG_A0: find(n1), mk.UC_M68K_REG_A1: find(n2) if n2 else 0})
    d1 = dirty(); good = render(force=False); got = screen(); last = got
    chk('%-8s / %-5s %8s: Popup wie die Firmware-Aufrufe (%d Pixel), bleibt markiert, Register ok' % (n1, n2 or '-', val, len(exp)),
        d1 == 1 and got == exp and dirty() == 1 and good and ok_)
w32(C.TIMER, r32(C.VARS + C.V_DL) - 10); render(force=False); chk('kurz vor 1.5 s: noch sichtbar', screen() == last and dirty() == 1)
w32(C.TIMER, r32(C.VARS + C.V_DL) + 5); render(force=False)
chk('nach 1.5 s: Bild ohne Popup, Art geloescht, Markierung weg', screen() == VIEWPIX and r32(C.VARS + C.V_KIND) == 0 and dirty() == 0)
w32(C.TIMER, 0xFFFFFF00); call(OVS, regs={mk.UC_M68K_REG_D0: 1, mk.UC_M68K_REG_D1: 5, mk.UC_M68K_REG_A0: find('Strum'), mk.UC_M68K_REG_A1: 0})
w32(C.TIMER, 0x100); render(force=False)
chk('Zeitgeber-Ueberlauf: Popup weiter sichtbar', screen() == native('Strum', None, 5))
call(OVS, regs={mk.UC_M68K_REG_D0: 0}); d = dirty(); render(force=False)
chk('Art 0 (weg): markiert, danach Bild ohne Popup', d == 1 and screen() == VIEWPIX)
for kind in (0x55, 7):
    w32(C.VARS + C.V_KIND, kind); w32(C.VARS + C.V_L1, find('Strum')); w32(C.VARS + C.V_L2, 0)
    w32(C.VARS + C.V_DL, r32(C.TIMER) + 1000); good = render()
    chk('Muell-Art %#x: Zahl-Popup, kein Haenger, Register ok' % kind, good)

# ---- Art 3: Lastanzeige (Zeichenfunktion der Mod 'load-meter')
LM = V2SYM['load-meter']; MV = 0x4A33C3D0
import g2_loadmeter as glm
x0, y0, x1, y1 = glm.BOX
def settext(t):
    uc.mem_write(MV + glm.BUF, bytes(glm.ORDER.index(c) for c in t).ljust(8, b'\0')); w32(MV + glm.BUFN, len(t))
    call(OVS, regs={mk.UC_M68K_REG_D0: 3, mk.UC_M68K_REG_A0: LM['LDRAW'], mk.UC_M68K_REG_A1: 0})
def expect(t):
    box = {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
    return (VIEWPIX - box) | ov.render_py(3, t)
w32(C.TIMER, 5000)
for t in ('87/62', '103/99', '5/3', '--'):
    settext(t); uc.mem_write(VC + 0x20, b'\0'); render()
    chk('LOAD %-6s: Pixel wie die v1-Vorlage, danach nicht weiter markiert' % t, screen() == expect(t) and dirty() == 0)
for n in (0, 9, 0xFFFFFFFF):
    settext('12/3'); w32(MV + glm.BUFN, n); good = render()
    chk('LOAD mit Muell-Laenge %d: nur Rahmen + LOAD, Register ok' % (n if n < 99 else -1),
        screen() == (VIEWPIX - {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}) | ov.render_py(3, '') and good)
try:
    from PIL import Image
    sc = 4; out = Image.new('RGB', (128 * sc + 16, (64 * sc + 16) * 4 + 16), (40, 40, 40))
    for i, (n1, n2, val, text) in enumerate([CASES[0], CASES[8], CASES[12], ('Strum', None, -35, False)]):
        px = native(n1, n2, val, text); im = Image.new('RGB', (128, 64), (20, 20, 30))
        for (x, y) in px: im.putpixel((x, 63 - y), (230, 230, 240))
        out.paste(im.resize((128 * sc, 64 * sc), Image.NEAREST), (8, 8 + i * (64 * sc + 16)))
    out.save('popup_preview.png')
except ImportError:
    pass
done()

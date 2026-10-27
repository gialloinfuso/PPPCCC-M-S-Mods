# SETTINGS als Modifier (SP / SP2 in 70 und 71): echte Tastenkette der 1.13 (Anti-Rebond-Interrupt 0x40059e64, 120-Hz-Uhr
# 0x4007f914, Ereignisse 0x4007fbde) aus Modded-Cycles test_trig_hold.Rig, dazu die echte consume-Funktion 0x400723e0.
# Prueft: SETTINGS ist Code 13; ohne consume kommen Halten, langes Halten (533 ms, = Projekt speichern) und Loslassen
# (= Einstellungsmenue); nach consume(13), wie SP/SP2 es bei der ersten Rastung aufrufen, kommt davon nichts mehr,
# und das naechste Druecken von SETTINGS funktioniert wieder normal.
# Dazu Fall 13 des Hauptbildschirms (Menue / langes Halten = Projekt speichern / FUNC = Muster speichern), Original gegen Image.
# Aufruf: python3 test_settings_key_113.py [image]   (Standard: Stock-1.13 + 65..70)
import struct, sys
sys.path.insert(0, 'Modded-Cycles/tools/emu'); sys.path.insert(0, 'Modded-Cycles/tools'); sys.path.insert(0, 'uni/bindings/python')
import test_trig_hold as T
if len(sys.argv) > 1: img = open(sys.argv[1], 'rb').read()
else:
    import json as _j
    _b = bytearray(open('out/section_3_MAIN_OS.bin', 'rb').read())
    for _p in ('65-delay-notes', '66-chorus', '67-phaser', '68-digi-delay', '69-razer', '70-mod-delays', '71-strum', '72-load-meter', '73-groove'):
        for _w in _j.load(open(f'solo/{_p}.json'))['writes']:
            _o = bytes.fromhex(_w['old']); assert _b[_w['off']:_w['off'] + len(_o)] == _o; _b[_w['off']:_w['off'] + len(_o)] = bytes.fromhex(_w['new'])
    img = bytes(_b)
SET, CONSUME = 13, 0x400723E0
ok = True
def chk(n, c):
    global ok; ok &= bool(c); print('ok  ' if c else 'FAIL', n)

class Rig(T.Rig):
    def step_ms(self):                      # wie T.Rig, aber Ereignisse nur mitschreiben (keine Grid-Ansicht)
        self.w32(0xfc07000c, self.t0 + self.now * (T.DTIM_HZ // 1000))
        self.uc.mem_write(T.RAW, bytes(self.raw)); self.call(T.ISR_KEYS)
        while self.next_tick <= self.now:
            self.call(T.TICK); self.next_tick += 1000 / 120
        while self.queue:
            code, flags, ts = self.queue.pop(0); self.log.append((self.now, code, flags))
        self.now += 1

def run(consume_at=None, until=1200, press=(10, 1000)):
    r = Rig(img); ev = {press[0]: [(SET, True)], press[1]: [(SET, False)]}
    for _ in range(30): r.step_ms()
    r.log.clear(); start = r.now
    for t in range(until):
        for e in ev.get(t, ()): r.key(*e)
        if t == consume_at: r.call(CONSUME, SET)
        r.step_ms()
    return r, [(t - start, c, f) for t, c, f in r.log if c == SET]

chk('Tastentabelle: SETTINGS = Code 13 hat eine Taste (0x4010ae5c)', struct.unpack('>i', img[0x4010AE5C - T.BASE + 4 * SET:][:4])[0] >= 0)
_, lg = run()
long_ = [t for t, c, f in lg if f & 0x20]; rel = [t for t, c, f in lg if f & 0x10]; prs = [t for t, c, f in lg if f & 1 and not f & 8]
chk('ohne consume: Druecken bei 10 ms, langes Halten bei ~%s ms, Loslassen bei ~%s ms' % (long_[:1], rel), prs[:1] == [10] and long_ and 530 <= long_[0] <= 560 and rel and rel[0] >= 1000)
_, lg = run(consume_at=300)
chk('consume(13) nach 300 ms (erste Rastung): danach kein Halten, kein langes Halten, kein Loslassen (%d Ereignisse nach 300 ms)'
    % len([1 for t, c, f in lg if t > 300]), [x for x in lg if x[0] > 300] == [] and any(f & 1 for t, c, f in lg))
r, lg = run(consume_at=300, until=1200)
# zweites Druecken in derselben Rig: Loslassen muss wieder kommen
r.log.clear(); r.key(SET, True)
for _ in range(100): r.step_ms()
r.key(SET, False)
for _ in range(60): r.step_ms()
chk('naechstes Druecken danach: Druecken und Loslassen wieder normal', any(f & 1 for _, c, f in r.log if c == SET) and any(f & 0x10 for _, c, f in r.log if c == SET))

# ---- Hauptbildschirm, Fall 13 (echter MainScreenView::consumeKeyEvent 0x4001c0d2, echter KeyEvent 0x4007238c):
#      Original gegen Image. Abgefangen: Projekt speichern 0x40039570, Muster/Kit speichern 0x4001040e, View oeffnen 0x40077da8.
import json
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn import m68k_const as mk
sys.path.insert(0, '.'); from ramalias import map_ram
stock = open('out/section_3_MAIN_OS.bin', 'rb').read()
SY = {k: int(v, 16) for k, v in json.load(open('solo/70-mod-delays.json'))['symbols'].items()}
PEND = 0x4A33C380 + 32
class MS:
    def __init__(s, im):
        u = s.u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); u.ctl_set_cpu_model(mk.UC_CPU_M68K_CFV4E)
        u.mem_map(0x40000000, 0x2330000); u.mem_map(0x42340000, 0xC0000); u.mem_write(T.BASE, im); map_ram(u)
        u.mem_map(0x4E000000, 0x1000); u.mem_map(0x4F000000, 0x40000)
        s.log = []
        stubs = {0x40039570: 'SAVE', 0x4001040e: 'QSAVE', 0x40077da8: 'OPEN', 0x400d807e: None, 0x400cf23c: None,
                 0x400cfd0e: None, 0x4006a96c: None, 0x400cf866: None, 0x400a22b0: 'DRUMSEL', 0x400802e0: None, 0x400cf044: None,
                 0x400cf9a8: None, 0x4006b736: None, 0x40075f3c: 'DEFAULT', 0x400a68fc: 'FUNCVIEW'}
        def hk(uu, a, sz, _):
            sp = uu.reg_read(mk.UC_M68K_REG_A7); ret = struct.unpack('>I', bytes(uu.mem_read(sp, 4)))[0]
            if stubs[a]: s.log.append(stubs[a])
            uu.reg_write(mk.UC_M68K_REG_D0, 0x4F020000 if a == 0x400802e0 else 0); uu.reg_write(mk.UC_M68K_REG_PC, ret); uu.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        for a in stubs: u.hook_add(UC_HOOK_CODE, hk, begin=a, end=a)
        s.this, s.ev = 0x4F010000, 0x4F011000
        u.mem_write(s.this, bytes(0x200)); u.mem_write(s.this + 0x2C, struct.pack('>I', 0x4F012000))
    def call(s, fn, *args):
        sp = 0x4F030000; s.u.mem_write(sp, struct.pack('>I', 0x4E000000) + b''.join(struct.pack('>I', x & 0xffffffff) for x in args))
        s.u.reg_write(mk.UC_M68K_REG_A7, sp)
        for i, r in enumerate((mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D3, mk.UC_M68K_REG_D4, mk.UC_M68K_REG_D5, mk.UC_M68K_REG_D6,
                               mk.UC_M68K_REG_A2, mk.UC_M68K_REG_A3, mk.UC_M68K_REG_A4, mk.UC_M68K_REG_A5, mk.UC_M68K_REG_A6)):
            s.u.reg_write(r, 0xC0DE0000 + i)
        s.u.emu_start(fn, 0x4E000000, count=200000)
        good = s.u.reg_read(mk.UC_M68K_REG_A7) == sp + 4 and all(
            s.u.reg_read(r) == 0xC0DE0000 + i for i, r in enumerate((mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D3, mk.UC_M68K_REG_D4, mk.UC_M68K_REG_D5,
                mk.UC_M68K_REG_D6, mk.UC_M68K_REG_A2, mk.UC_M68K_REG_A3, mk.UC_M68K_REG_A4, mk.UC_M68K_REG_A5, mk.UC_M68K_REG_A6)))
        return s.u.reg_read(mk.UC_M68K_REG_D0) & 0xff, good
    def key(s, flags, code=SET):
        s.call(0x4007238C, s.ev, code, flags, 1234, 0x7F); s.log.clear()
        d0, good = s.call(0x4001C0D2, s.this, s.ev); return list(s.log), d0, good
    def pend(s): return struct.unpack('>I', bytes(s.u.mem_read(PEND, 4)))[0]
    def setpend(s, v): s.u.mem_write(PEND, struct.pack('>I', v))
PRESS, HOLD, LONG, REL, FREL = 0x1, 0x9, 0x29, 0x10, 0x12
for name, im in (('Original', stock), ('Image', img)):
    m = MS(im); res = {}
    if name == 'Image': m.setpend(0)
    res['kurz'] = [m.key(PRESS)[0], m.key(HOLD)[0], m.key(REL)[0]]
    res['lang'] = [m.key(PRESS)[0], m.key(LONG)[0], m.key(HOLD)[0], m.key(REL)[0]]
    res['func'] = [m.key(PRESS)[0], m.key(FREL)[0]]
    if name == 'Image': m.setpend(1)                         # alt gebliebenes PEND (z. B. nach Neustart)
    res['alt'] = [m.key(PRESS)[0], m.key(REL)[0]]
    goods = [m.key(f)[2] for f in (PRESS, LONG, REL, FREL)]
    print('  %-8s %s' % (name, res))
    if name == 'Original':
        chk('Original: kurz -> Menue; lang -> sofort Projekt speichern (+ Menue beim Loslassen); FUNC -> Muster/Kit speichern',
            res['kurz'] == [[], [], ['OPEN']] and res['lang'][1] == ['SAVE'] and res['func'][1] == ['QSAVE'])
    else:
        chk('Image: kurz -> Menue wie Original', res['kurz'] == [[], [], ['OPEN']])
        chk('Image: lang -> beim Halten nichts, beim Loslassen Projekt speichern statt Menue', res['lang'] == [[], [], [], ['SAVE']] and m.pend() == 0)
        chk('Image: FUNC + SETTINGS -> Muster/Kit speichern wie Original', res['func'] == [[], ['QSAVE']])
        chk('Image: altes PEND wird beim Druecken geloescht -> Menue', res['alt'] == [[], ['OPEN']])
        chk('Image: Register/Stack von consumeKeyEvent in allen Faellen ok', all(goods))
# MACHINE (Code 5): Original oeffnet das Maschinen-Menue (DrumSelect) beim Druecken; Image erst beim Loslassen
import json as _jj
mp = int(_jj.load(open('solo/73-groove.json'))['params']['mpend'], 16) if len(sys.argv) < 2 or True else 0
for name, im in (('Original', stock), ('Image', img)):
    m = MS(im)
    if name == 'Image': m.u.mem_write(mp, bytes(4))
    a = m.key(PRESS, 5)[0]; b2 = m.key(REL, 5)[0]
    c = m.key(PRESS, 5)[0]; m.u.mem_write(mp, bytes(4)) if name == 'Image' else None   # Geste: consume + Merker weg
    d2 = m.key(REL, 5)[0]
    print('  %-8s MACHINE: Druecken %s, Loslassen %s ; Druecken %s, (Geste) Loslassen %s' % (name, a, b2, c, d2))
    if name == 'Original': chk('Original: MACHINE oeffnet das Menue beim Druecken', 'OPEN' in a and 'OPEN' not in b2)
    else:
        chk('Image: MACHINE oeffnet das Menue erst beim Loslassen', 'OPEN' not in a and 'OPEN' in b2)
        chk('Image: nach der Geste (Merker geloescht) kein Menue', 'OPEN' not in c and 'OPEN' not in d2)
print('GESAMT', 'ok' if ok else 'FEHLER')

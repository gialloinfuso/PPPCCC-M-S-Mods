# latching-mute (Teil von 01 mute-solo, v2.3, eigener Code g2_latch.py): echter Code der Firmware im Emulator
# (Tasten-Ereignis 0x4007240c / 0x400724a0 / 0x40072470, Tasten der Mute-Ansicht 0x400234b6, Track-Tasten 0x4002350a,
# LED-Stelle 0x400233a0); Grundklasse, Mute-Umschalten und LED-Funktionen gestubbt (mitgeschrieben).
# 1. Mute-Ansicht: einrasten (TRACK + FUNC), kurz antippen = aus, lange / mit anderer Taste = bleibt, ohne Einrasten wie Stock.
# 2. Track-Tasten: FUNC -> umschalten, TRACK / PATTERN / RETRIG -> Firmware, UI-Zustand -> Firmware, sonst umschalten.
# 3. LEDs: FUNC-LED an + beansprucht, danach der Originalbefehl.
# Ist drumkillas Tweak (elektron-model-tweaks) vorhanden, laufen alle Faelle zusaetzlich gegen ihn (gleiches Verhalten).
import json, struct
from rig import *
import g2_latch as L

KEYS = {'FUNC': C.KEY_FUNC, 'TRACK': C.KEY_TRACK, 'PATTERN': L.KEY_PATTERN, 'RETRIG': C.KEY_RETRIG, 'T1': 16}
VIEW, VTAB, EV, UISB, MASK = 0x4F040000, 0x4F040100, 0x4F040200, 0x4F041000, 0x4F042000
STUBS = {0x40075F3C: 'base', 0x40074114: 'base2', 0x40013904: 'toggle', L.UIS: 'uis', 0x400CF866: 'p', 0x4000EB90: 'kit',
         L.LED_CTRL: 'ledctrl', L.LED_SET: 'ledset', 0x4E000F00: 'close'}


class Rig:
    def __init__(s, img, flag):
        s.e = Emu(img); s.flag = flag; s.log = []
        for a in STUBS:
            s.e.u.hook_add(UC_HOOK_CODE, s._stub, begin=a, end=a)
        s.e.w32(VIEW, VTAB); s.e.w32(VTAB + 0x28, 0x4E000F00)
        s.e.w32(0x4E000F00, 0x4E754E75)
    def _stub(s, u, addr, size, _):
        e = s.e; sp = u.reg_read(mk.UC_M68K_REG_A7); ret = e.r32(sp); name = STUBS[addr]; d0 = 0
        if name == 'uis': d0 = UISB
        elif name in ('p', 'kit'): d0 = 0x4F043000
        elif name == 'ledctrl': d0 = 0x4F044000
        elif name == 'ledset': s.log.append(('ledset', e.r32(sp + 4), e.r32(sp + 8), e.r32(sp + 12), e.r32(sp + 16))); d0 = 0
        else: s.log.append((name,))
        if name == 'base': d0 = 0x55
        u.reg_write(mk.UC_M68K_REG_D0, d0); u.reg_write(mk.UC_M68K_REG_PC, ret); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    def key(s, k, fl, held=(), tick=0):
        """Ereignis an die Mute-Ansicht (Vtable-Eintrag), fl: 1 gedrueckt, 0 losgelassen, 9 Wiederholung"""
        e = s.e; e.held = {KEYS[h] for h in held}; e.w32(L.TICK, tick)
        e.u.mem_write(EV, struct.pack('>5I', 0, 0, 0, KEYS[k], fl))
        s.log = []
        d0, good = e.call(e.r32(L.MV_VT), VIEW, EV)
        return d0 & 0xff, tuple(x[0] for x in s.log), e.r8(s.flag), good
    def trk(s, held=(), busy=0):
        e = s.e; e.held = {KEYS[h] for h in held}; e.w8(UISB + 0x185, busy)
        e.u.mem_write(EV, struct.pack('>5I', 0, 0, 0, 16, 1)); s.log = []
        e.u.mem_write(VIEW + 0x74, bytes(8))
        d0, good = e.call(0x4002350A, VIEW, EV)
        return tuple(x[0] for x in s.log), good
    def led(s):
        e = s.e; e.u.mem_write(MASK, bytes(8)); s.log = []
        e.u.reg_write(mk.UC_M68K_REG_A2, MASK); e.u.reg_write(mk.UC_M68K_REG_A7, STACK - 0x100)
        e.u.emu_start(L.LED_HOOK, L.LED_BACK, count=10000)
        return tuple(s.log), e.r32(MASK), e.u.reg_read(mk.UC_M68K_REG_A7) == STACK - 0x100


def scenario(r):
    """Ablauf; Rueckgabe Liste der Ergebnisse (fuer den Vergleich) und benannte Pruefungen"""
    out = []; c = {}
    k = r.key
    # Stock-Ablauf: FUNC gehalten (Ansicht offen), losgelassen ohne TRACK -> schliessen
    out.append(k('FUNC', 1, held=['FUNC'], tick=100)); out.append(k('FUNC', 0, tick=200))
    c['ohne TRACK: Loslassen schliesst (wie Stock), nicht eingerastet'] = out[-1][1] == ('close',) and out[-1][2] == 0
    # Einrasten: TRACK gehalten, FUNC antippen
    out.append(k('FUNC', 1, held=['TRACK', 'FUNC'], tick=300)); out.append(k('FUNC', 0, held=['TRACK'], tick=350))
    c['TRACK + FUNC: eingerastet, Ansicht bleibt (verbraucht)'] = out[-1][0] == 1 and out[-1][1] == () and out[-1][2] == 1
    # andere Taste geht an die Firmware
    out.append(k('T1', 1, tick=400))
    c['andere Taste: Grundklasse der Firmware'] = out[-1][1] == ('base',) and out[-1][2] == 1
    # FUNC lange halten -> bleibt
    out.append(k('FUNC', 1, held=['FUNC'], tick=1000)); out.append(k('FUNC', 0, tick=1000 + L.TAP + 10))
    c['FUNC lange gehalten: bleibt eingerastet'] = out[-1][0] == 1 and out[-1][2] == 1
    # FUNC + andere Taste (Solo) -> bleibt
    out.append(k('FUNC', 1, held=['FUNC'], tick=3000)); out.append(k('T1', 1, held=['FUNC'], tick=3010))
    out.append(k('T1', 0, held=['FUNC'], tick=3020)); out.append(k('FUNC', 0, tick=3030))
    c['FUNC mit anderer Taste benutzt: bleibt eingerastet'] = out[-1][0] == 1 and out[-1][2] == 1
    # Wiederholung zaehlt nicht als Druck
    out.append(k('FUNC', 1, held=['FUNC'], tick=5000)); out.append(k('T1', 9, held=['FUNC'], tick=5005)); out.append(k('FUNC', 0, tick=5010))
    c['kurz antippen (Wiederholung einer anderen Taste zaehlt nicht): aus, Ansicht schliesst'] = out[-1][1] == ('close',) and out[-1][2] == 0
    # wieder einrasten, dann kurz antippen mit TRACK gehalten -> bleibt
    out.append(k('FUNC', 1, held=['TRACK', 'FUNC'], tick=6000)); out.append(k('FUNC', 0, held=['TRACK'], tick=6010))
    out.append(k('FUNC', 1, held=['TRACK', 'FUNC'], tick=6100)); out.append(k('FUNC', 0, held=['TRACK'], tick=6110))
    c['eingerastet, kurz antippen mit TRACK: bleibt'] = out[-1][0] == 1 and out[-1][2] == 1
    out.append(k('FUNC', 1, held=['FUNC'], tick=6200)); out.append(k('FUNC', 0, tick=6210))
    c['kurz antippen allein: aus'] = out[-1][1] == ('close',) and out[-1][2] == 0
    c['Register und Stapel jedes Aufrufs'] = all(x[3] for x in out)
    # Track-Tasten
    t = {tuple(h): r.trk(held=h) for h in ([], ['FUNC'], ['TRACK'], ['PATTERN'], ['RETRIG'], ['FUNC', 'TRACK'])}
    t['busy'] = r.trk(busy=1)
    out += sorted(t.items(), key=str)
    c['Track-Taste: umschalten ohne Modifier und mit FUNC (auch FUNC + TRACK)'] = all(
        'toggle' in t[h][0] for h in (tuple(), ('FUNC',), ('FUNC', 'TRACK')))
    c['Track-Taste mit TRACK / PATTERN / RETRIG oder UI-Zustand: Firmware'] = all(
        'toggle' not in t[h][0] and 'base2' in t[h][0] for h in (('TRACK',), ('PATTERN',), ('RETRIG',), 'busy'))
    c['Track-Tasten: Register und Stapel'] = all(v[1] for v in t.values())
    # LEDs
    lg, m, spok = r.led()
    out.append((lg, m, spok))
    c['LED: FUNC-LED an (Ebene, Zustand 2), beansprucht, Originalbefehl, Stapel'] = (
        lg[:1] == (('ledset', 0x4F044000, L.LED_FUNC, L.LED_ON, L.LED_LAYER),) and m == 1 << L.LED_FUNC and spok)
    return out, c


lw = [w for w in json.load(open(V2 / 'out' / '01-mute-solo.json'))['writes'] if w.get('part') == 'latching-mute']
img = apply(STOCK, {'id': 'latching-mute', 'writes': lw})
chk('Writes = g2_latch (01 mute-solo, Teil latching-mute)', [(w['off'], w['new']) for w in lw] ==
    [(w['off'], w['new']) for w in L.tweak(STOCK)['writes']])
res, c = scenario(Rig(img, L.LATCH))
for name, v in c.items():
    chk(name, v)
dk = ROOT / 'elektron-model-tweaks/tweaks/model-cycles_OS1.13/01-latching-mute.json'
if dk.exists():
    ref, _ = scenario(Rig(apply(STOCK, json.load(open(dk))), 0x401487ED))
    norm = lambda rs: [tuple(x[:3]) if len(x) == 4 else x for x in rs]
    chk('gleiches Verhalten wie drumkillas latching-mute in allen Faellen', norm(res) == norm(ref))
else:
    print('(drumkillas Tweak nicht vorhanden: kein Vergleich)')
done()

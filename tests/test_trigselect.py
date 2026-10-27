# trig-select (v2): Auswahlmodus fuer Trigs.
# 1. TSK statt PatternGridView::consumeKeyEvent: echte UIStates-Methoden (gehaltene Steps, Halte-Merker, Fokus) auf einem
#    UIStates-Objekt im Speicher, echter KeyEvent, echter Core (OVS, GEST); nachgebaut: Projekt/Track/Seite/Laenge, Trigs
#    der Steps, das Original (protokolliert, was es sieht). Modus an/aus, Trigs waehlen, alle/keine, PAGE mit verdeckter
#    Auswahl, Tasten ausserhalb des Grid-Bearbeitens, Register/Stack.
# 2. TSF (Hauptbildschirm FUNC + PAGE): ab dem Haken 0x4001c4a6 ausgefuehrt, mit der echten Flag-Funktion.
# 3. TSL (LED-Schleife): ab dem Haken 0x40021f56 bis nach dem Aufruf von 0x40005f86 ausgefuehrt, Stock gegen Image.
# 4. PL (ParameterPageView vt[0x74]) und NVW (NoteVelocityView): relativ = Original, absolut = Wert des Fokus-Steps.
import struct, sys
from rig import *

TS = V2SYM['trig-select']; CS = V2SYM['core']
import g2_trigselect as G
IMG = v2_image(['core', 'trig-select']) if '--alone' in sys.argv else v2_image()   # --alone: nur core + trig-select
e = Emu(IMG); u = e.u
UISB, FAKE, TRKO, VIEW, VVT, OBJ, OVT_ = 0x4F048000, 0x4F049000, 0x4F04A000, 0x4F04B000, 0x4F04B100, 0x4F04C000, 0x4F04C100
EV = 0x4F04D000
u.mem_write(UISB, bytes(0x200)); u.mem_write(UISB + 0x165, b'\1\1')
ST = {n: 0x4E000400 + 0x10 * i for i, n in enumerate(['VT60', 'VT80', 'VT24', 'VT28'])}
S = dict(page=0, length=64, trigs={}, log=[], grid_ret=0x55, locks={}, nudge={}, nv=[{}, {}, {}], orig=[])
sg = lambda v: struct.unpack('>i', struct.pack('>I', v & 0xffffffff))[0]
def mask(): return (e.r32(UISB + 0x15C) << 32) | e.r32(UISB + 0x160)
def steps(): m = mask(); return [i for i in range(64) if m >> i & 1]
def hold(): return e.r8(UISB + 0x164)
def focus(): return sg(e.r32(0x4014924C))

def stub(uu, addr, size, n):
    sp = uu.reg_read(mk.UC_M68K_REG_A7); arg = lambda i: e.r32(sp + 4 + 4 * i)
    r = 0
    if n == 'UIS': r = UISB
    elif n == 'PROJ': r = FAKE
    elif n == 'TRK': r = TRKO
    elif n == 'PG_A': r = FAKE + 0x30
    elif n == 'PG_B': r = S['page']
    elif n == 'LEN': r = S['length']
    elif n in ('HAS0', 'HAS1', 'HAS2'): r = int(S['trigs'].get(arg(1)) == int(n[3]))
    elif n == 'NOTIFY': r = 0
    elif n == 'GRID':
        ev = arg(1); S['orig'].append((e.r32(ev + 12), e.r32(ev + 16), mask(), hold())); r = S['grid_ret']
    elif n == 'VT60': r = 0 if (arg(1), arg(2)) in S['locks'] else 0xFFFFFFFF
    elif n == 'VT80': r = OBJ
    elif n == 'VT24': r = S['locks'].get((arg(2), arg(1)), 1111)
    elif n == 'VT28': S['locks'][(arg(3), arg(1))] = sg(arg(2)); S['log'].append(('lock', arg(3), sg(arg(2))))
    elif n == 'PLO':                                      # Original vt[0x74]: relativ je gehaltenem Step
        p, d = arg(1), sg(arg(2))
        for s in steps():
            if (s, p) in S['locks'] or not S.get('nocreate'): S['locks'][(s, p)] = S['locks'].get((s, p), 1000) + d
        r = 1
    elif n == 'NGET': r = S['nudge'].get(arg(1), 0) & 0xff
    elif n == 'NSET': S['nudge'][arg(1)] = sg(arg(2)) if sg(arg(2)) < 128 else sg(arg(2)) - 256
    elif n.startswith('NVG'): r = S['nv'][int(n[3])].get(arg(1), 0xff) & 0xff
    elif n.startswith('NVS'): v = arg(2) & 0xff; S['nv'][int(n[3])][arg(1)] = v if v < 128 else v - 256; S['log'].append(('nv', int(n[3]), arg(1)))
    elif n == 'NVA':                                      # Original 0x400296c4(view, Drehung): relativ je gehaltenem Step
        f = e.r32(arg(0) + 0x68); d = sg(arg(1))
        for s in (steps() if f < 3 else []): S["nv"][f][s] = max(0, min(127, S["nv"][f].get(s, 60) + d))
    for x in (mk.UC_M68K_REG_D1, mk.UC_M68K_REG_A0, mk.UC_M68K_REG_A1): uu.reg_write(x, 0xBAD0BAD0)
    uu.reg_write(mk.UC_M68K_REG_D0, r & 0xffffffff)
    uu.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); uu.reg_write(mk.UC_M68K_REG_A7, sp + 4)
HOOKS = {G.UIS: 'UIS', G.PROJ: 'PROJ', G.TRK: 'TRK', G.PG_A: 'PG_A', G.PG_B: 'PG_B', G.LEN: 'LEN', G.HAS[0]: 'HAS1',
         G.HAS[1]: 'HAS2', G.HAS[2]: 'HAS0', 0x40069B84: 'NOTIFY', G.GRID_KEY: 'GRID', G.PL_ORIG: 'PLO',
         G.NUD_GET: 'NGET', G.NUD_SET: 'NSET', G.NV_APPLY: 'NVA'}
for i in range(3): HOOKS[G.NV_GET[i]] = 'NVG%d' % i; HOOKS[G.NV_SET[i]] = 'NVS%d' % i
HOOKS.update({a: n for n, a in ST.items()})
for a, n in HOOKS.items(): u.hook_add(UC_HOOK_CODE, stub, begin=a, end=a, user_data=n)
# Trig-Arten: 1 Note-Trig (0x40015c20), 2 Lock-Trig (0x40015c7c), 0 nur P-Locks (0x400158ca)
e.w32(C.TIMER, 1000)

PRESS, HOLD, REL, FPRESS = 0x1, 0x9, 0x10, 0x3
def key(code, flags, held=()):
    e.held = set(held); e.consumed = []; S['orig'] = []
    e.call(0x4007238C, EV, code, flags, 1234, 0x7F)
    d0, good = e.call(e.r32(G.GRID_VT), 0x4F04E000, EV)
    return d0 & 0xff, good, list(e.consumed), list(S['orig'])
def popup():
    V = C.VARS; rd = lambda a: e.cstr(a) if a else ''
    return (e.r32(V + C.V_KIND), rd(e.r32(V + C.V_VAL)), rd(e.r32(V + C.V_L1)), rd(e.r32(V + C.V_L2)))
on = lambda: int(e.r32(G.TS_ON) == G.TS_MAGIC)

chk('vtable 0x40100af0 = TSK, vt[0x74] 0x401005a0 = PL, Haken TSF/TSL/NVW',
    e.r32(G.GRID_VT) == TS['TSK'] and e.r32(G.PL_VT) == TS['PL'] and IMG[G.TSF_HOOK - BASE:][:8] == C.jsr(TS['TSF']) + b'\x4e\x71'
    and IMG[G.TSL_HOOK - BASE:][:10] == C.jsr(TS['TSL']) + b'\x4e\x71' * 2 and IMG[G.NVW_HOOK - BASE:][:8] == C.jsr(TS['NVW']) + b'\x4e\x71')
S['trigs'] = {0: 1, 3: 2, 4: 1, 7: 0, 12: 1, 18: 1, 33: 2, 63: 1}
good = True
for junk in (1, 0xFF, 0xFFFFFFFF, 0x5453454D):              # RAM nach dem Einschalten: beliebiger Inhalt -> Modus aus
    e.w32(G.TS_ON, junk); good &= key(20, PRESS)[3] != [] and key(16, PRESS)[3] != []
chk('nach dem Einschalten (TS_ON = Zufall, nicht TSEL): Modus aus, Trig-Tasten ans Original', good)
e.w32(G.TS_ON, 0)
# ---- Modus aus: alles geht ans Original
r = [key(20, PRESS), key(15, PRESS), key(15, PRESS, (2,)), key(9, PRESS, (13,))]
chk('Modus aus: Trig, PAGE, TRACK + PAGE, SETTINGS + Taste 9 -> Original, Rueckgabe des Originals, Register ok',
    all(x[0] == 0x55 and x[1] and len(x[3]) == 1 and not x[2] for x in r) and on() == 0)
# ---- SETTINGS + PAGE: an
d0, g, cons, orig = key(15, PRESS, (13,))
chk('SETTINGS + PAGE: Modus an, Popup %s, SETTINGS und PAGE verbraucht %s, Original nicht gerufen' % (popup(), cons),
    on() == 1 and d0 == 1 and g and orig == [] and cons == [13, 15] and popup() == (C.OV_TEXT, 'On', 'Trig', 'Select'))
# ---- Trigs waehlen
res = []
for code, fl in ((16, PRESS), (16, HOLD), (16, REL), (19, PRESS), (19, REL), (23, PRESS), (21, PRESS), (17, PRESS)):
    res.append(key(code, fl))
chk('Trig-Tasten im Modus: Steps 1, 4, 8 (P-Locks) gewaehlt, 6 (leer) und 2 (leer) nicht; Halten/Loslassen verbraucht, '
    'Original nie gerufen (%s)' % steps(), steps() == [0, 3, 7] and all(x[0] == 1 and x[1] and x[3] == [] for x in res))
chk('Halte-Merker gesetzt, Fokus = niedrigster Step (%d)' % focus(), hold() == 1 and focus() == 0)
key(16, PRESS)
chk('nochmal Step 1: abgewaehlt, Fokus -> 4 (%s, %d)' % (steps(), focus()), steps() == [3, 7] and focus() == 3)
S['page'] = 2; key(17, PRESS); S['page'] = 0
chk('Seite 3, Taste 2 -> Step 34 (Lock-Trig) gewaehlt (%s)' % steps(), steps() == [3, 7, 33])
u.mem_write(UISB + 0x166, b'\0'); d0, g, _, orig = key(20, PRESS); u.mem_write(UISB + 0x166, b'\1')
chk('nicht im Grid-Bearbeiten (0x4006b978 = 0): Trig-Taste ans Original', d0 == 0x55 and len(orig) == 1)
# ---- PAGE im Modus: Original mit verdeckter Auswahl
m0, h0 = mask(), hold()
res = [key(15, PRESS), key(15, HOLD), key(15, REL)]
chk('PAGE im Modus (Druecken, Halten, Loslassen): Original sieht keine gehaltenen Steps (%s), danach Auswahl wieder da'
    % [(o[2], o[3]) for x in res for o in x[3]], all(len(x[3]) == 1 and x[3][0][2:] == (0, 0) and x[0] == 0x55 and x[1] for x in res)
    and mask() == m0 and hold() == h0)
r = key(15, PRESS, (2,))
chk('TRACK + PAGE im Modus: ebenfalls Original (verdeckt)', len(r[3]) == 1 and r[3][0][2] == 0 and mask() == m0)
# ---- FUNC + PAGE: alle / keine
S['length'] = 64; d0, g, cons, orig = key(15, FPRESS)
chk('FUNC + PAGE: alle waehlbaren Steps (%s), Popup %s, PAGE verbraucht, Original nicht' % (steps(), popup()[1]),
    steps() == sorted(S['trigs']) and popup()[1] == 'All' and cons == [15] and orig == [] and d0 == 1 and g and hold() == 1)
key(15, FPRESS)
chk('FUNC + PAGE nochmal (schon alle): keine (%s), Popup %s, Halte-Merker 0, Fokus -1' % (steps(), popup()[1]),
    steps() == [] and popup()[1] == 'None' and hold() == 0 and focus() == -1)
S['length'] = 16; key(15, FPRESS)
chk('Patternlaenge 16: nur Steps < 16 (%s)' % steps(), steps() == [0, 3, 4, 7, 12])
S['length'] = 200; key(15, FPRESS)
chk('Auswahl teilweise, Laenge 200 (> 64): FUNC + PAGE waehlt den Rest dazu, kein Ueberlauf (%s, %s)' % (steps(), popup()[1]),
    steps() == sorted(S['trigs']) and popup()[1] == 'All')
S['length'] = 64
# ---- andere Tasten im Modus: Original (mit Auswahl, z. B. Locks kopieren / einfuegen)
r = key(9, PRESS | 2)
chk('andere Tasten im Modus (FUNC + Taste 9): Original, sieht die Auswahl', len(r[3]) == 1 and r[3][0][2] == mask() and mask() != 0)
# ---- SETTINGS + PAGE: aus
d0, g, cons, orig = key(15, PRESS, (13,))
chk('SETTINGS + PAGE im Modus: aus, Auswahl geloescht, Popup Off, SETTINGS + PAGE verbraucht',
    on() == 0 and steps() == [] and hold() == 0 and popup()[1] == 'Off' and cons == [13, 15] and orig == [] and d0 == 1 and g)
r = key(16, PRESS)
chk('danach: Trig-Tasten wieder normal (Original)', len(r[3]) == 1 and steps() == [])

# ------------------------------------------------------------------ 2. TSF (Hauptbildschirm, FUNC + PAGE)
def tsf(ts, flags):
    e.w32(G.TS_ON, G.TS_MAGIC if ts else 0x01010101); e.call(0x4007238C, EV, 15, flags, 1, 0x7F)
    sp = STACK - 0x300; u.reg_write(mk.UC_M68K_REG_A7, sp); u.reg_write(mk.UC_M68K_REG_D3, EV)
    u.emu_start(G.TSF_HOOK, G.TSF_HOOK + 10, count=2000)
    return u.reg_read(mk.UC_M68K_REG_D0) & 0xff, u.reg_read(mk.UC_M68K_REG_A7) == sp, u.reg_read(mk.UC_M68K_REG_D3) == EV
chk('TSF: Modus aus -> FUNC-Bit wie Firmware (FUNC + PAGE: %d, PAGE: %d), Stack ok' % (tsf(0, FPRESS)[0], tsf(0, PRESS)[0]),
    tsf(0, FPRESS) == (1, True, True) and tsf(0, PRESS) == (0, True, True))
chk('TSF: Modus an -> 0 (Ereignis geht ans Grid), Stack ok', tsf(1, FPRESS) == (0, True, True))

# ------------------------------------------------------------------ 3. TSL (LED-Schleife)
LEDSTUB = 0x4E000600; SETLED = []
def ledstub(uu, a, s, _):
    sp = uu.reg_read(mk.UC_M68K_REG_A7); SETLED.append(struct.unpack('>4I', bytes(uu.mem_read(sp + 4, 16))))
    uu.reg_write(mk.UC_M68K_REG_PC, struct.unpack('>I', bytes(uu.mem_read(sp, 4)))[0]); uu.reg_write(mk.UC_M68K_REG_A7, sp + 4)
def tsl(emu, step, state, ts=1, timer=0):
    uu = emu.u; SETLED.clear(); emu.w32(G.TS_ON, G.TS_MAGIC if ts else 0xFFFFFFFF); emu.w32(C.TIMER, timer)
    sp = STACK - 0x400; emu.w32(sp + 0x38, (step // 16) * 16)
    for r_, v in ((mk.UC_M68K_REG_A7, sp), (mk.UC_M68K_REG_D3, step % 16), (mk.UC_M68K_REG_A5, state), (mk.UC_M68K_REG_D2, 0x4F04F000),
                  (mk.UC_M68K_REG_A4, 0x4000608C), (mk.UC_M68K_REG_A6, LEDSTUB)):
        uu.reg_write(r_, v)
    uu.emu_start(G.TSL_HOOK, 0x40021F68, count=5000)
    return SETLED[0], uu.reg_read(mk.UC_M68K_REG_A7) == sp - 0x14
es = Emu(STOCK); es.u.hook_add(UC_HOOK_CODE, ledstub, begin=LEDSTUB, end=LEDSTUB)
for em in (e, es):                                  # Tabelle Step -> LED (0x4000608c liest *0x404a8bdc)
    em.w32(0x404A8BDC, 0x4F04F800); em.u.mem_write(0x4F04F800, b''.join(struct.pack('>I', 100 + i) for i in range(16)))
u.hook_add(UC_HOOK_CODE, ledstub, begin=LEDSTUB, end=LEDSTUB)
u.mem_write(UISB + 0x15C, struct.pack('>II', 1 << (40 - 32), (1 << 5) | (1 << 17)))     # gewaehlt: 5, 17, 40
good = True
for step in (0, 5, 17, 40, 63):
    for st in (2, 3, 4):
        ref = tsl(es, step, st, ts=0)
        good &= tsl(e, step, st, ts=0) == ref and tsl(e, step, st, ts=1) == ref if step not in (5, 17, 40) else tsl(e, step, st, ts=0) == ref
chk('TSL: Modus aus, und nicht gewaehlte Steps im Modus: LED-Aufruf und Stack wie Stock', good)
r1 = [tsl(e, s, 3, 1, 0)[0][2] for s in (5, 17, 40)]; r2 = [tsl(e, s, 3, 1, 1 << 24)[0][2] for s in (5, 17, 40)]
lg = all(tsl(e, s, 3, 1, t)[0][1] == tsl(es, s, 3, 0)[0][1] and tsl(e, s, 3, 1, t)[1] for s in (5, 17, 40) for t in (0, 1 << 24))
chk('TSL: gewaehlte Steps 6, 18, 41 blinken (Zeitgeber-Bit 24: %s / %s), LED und Stack wie Stock' % (r1, r2), r1 == [1, 1, 1] and r2 == [2, 2, 2] and lg)

# ------------------------------------------------------------------ 4. PL / NVW: absolut
u.mem_write(VVT, bytes(0x100)); e.w32(VVT + 0x60, ST['VT60']); e.w32(VVT + 0x80, ST['VT80']); e.w32(VIEW, VVT)
u.mem_write(OVT_, bytes(0x40)); e.w32(OVT_ + 0x24, ST['VT24']); e.w32(OVT_ + 0x28, ST['VT28']); e.w32(OBJ, OVT_)
def select(ss):
    e.call(0x4006B8D6, UISB)
    for s in ss: e.call(0x4006B836, UISB, s, 1)
P = 47
for mode in (0, C.CTRL_ABS):
    e.w8(C.CTRL_MODE, mode); select([2, 9, 30, 50])
    S['locks'] = {(2, P): 500, (9, P): 9000, (30, P): 20000, (50, P): 100, (9, 52): 7}
    for d in (256, 256, -768):
        d0, g = e.call(TS['PL'], VIEW, P, d)
    vals = [S['locks'][(s, P)] for s in (2, 9, 30, 50)]
    exp = [244, 8744, 19744, -156] if mode == 0 else [244] * 4
    chk('PL %s: P-Locks der gewaehlten Steps %s, Rueckgabe 1, Register ok, anderer Parameter unberuehrt' % ('relativ' if mode == 0 else 'absolut', vals),
        vals == exp and d0 & 0xff == 1 and g and S['locks'][(9, 52)] == 7)
e.w8(C.CTRL_MODE, C.CTRL_ABS); select([4, 6]); S['locks'] = {(4, P): 300}; S['nocreate'] = True
e.call(TS['PL'], VIEW, P, 256); S['nocreate'] = False
chk('PL absolut: Step ohne Lock (z. B. Locks voll) wird nicht angelegt (%s)' % S['locks'], S['locks'] == {(4, P): 556})
select([3, 8, 20]); S['nudge'] = {3: -5, 8: 10, 20: 0}
e.call(TS['PL'], VIEW, G.NUDGE, 256)
chk('PL absolut, Nudge (Parameter 0x12): alle = Fokus-Step %s' % S['nudge'], S['nudge'][8] == S['nudge'][20] == S['nudge'][3] == -5)
e.w8(C.CTRL_MODE, 0); select([]); e.call(TS['PL'], VIEW, P, 256)
# NVW: ab dem Aufruf in NoteVelocityView
def nvw(field, d):
    e.w32(VIEW + 0x68, field); sp = STACK - 0x500
    for r_, v in ((mk.UC_M68K_REG_A7, sp), (mk.UC_M68K_REG_A2, VIEW), (mk.UC_M68K_REG_D0, d & 0xffffffff), (mk.UC_M68K_REG_D2, 0xC0DE0002),
                  (mk.UC_M68K_REG_D3, 0xC0DE0003)):
        u.reg_write(r_, v)
    u.emu_start(G.NVW_HOOK, G.NVW_HOOK + 8, count=20000)
    return (u.reg_read(mk.UC_M68K_REG_A7) == sp - 8 and e.r32(sp - 8) == VIEW and e.r32(sp - 4) == d & 0xffffffff
            and u.reg_read(mk.UC_M68K_REG_D2) == 0xC0DE0002 and u.reg_read(mk.UC_M68K_REG_D3) == 0xC0DE0003 and u.reg_read(mk.UC_M68K_REG_A2) == VIEW)
for mode in (0, C.CTRL_ABS):
    e.w8(C.CTRL_MODE, mode); select([1, 5, 9])
    S['nv'] = [{1: 60, 5: 70, 9: 40}, {1: 100, 5: 20, 9: 127}, {1: -1, 5: 10, 9: 30}]
    ok_ = nvw(0, 3) and nvw(1, -10) and nvw(2, 5)
    got = [[S['nv'][f][s] for s in (1, 5, 9)] for f in range(3)]
    exp = [[63, 73, 43], [90, 10, 117], [4, 15, 35]] if mode == 0 else [[63] * 3, [90] * 3, [4] * 3]
    chk('NVW %s: Note/Velocity/Laenge %s, Stapel wie das Original (a2, Drehung), Register ok' % ('relativ' if mode == 0 else 'absolut', got),
        got == exp and ok_)
e.w8(C.CTRL_MODE, C.CTRL_ABS); select([1, 5]); S['nv'] = [{1: 60, 5: 70}, {}, {}]
nvw(7, 3)
chk('NVW: anderes Feld (7) -> keine Angleichung', S['nv'][0] == {1: 60, 5: 70})
done()

# Core (v2): Encoder-Verteiler CED mit Slots (echter Haken 0x400081b8), GEST, SLOW + MODESW, Pattern-Speicher HL/HI.
# Core allein: jedes Encoder-Ereignis geht unveraendert durch.
import struct
from rig import *

S = V2SYM['core']
img = v2_image(['core'])
e = Emu(img)

# ---- Core allein: alles geht durch
good = True
for enc in (1, 5, 8, 9, 12, 14, 15):
    for d in (1, -1, 5):
        for held in ((), (2,), (13,), (1,), (5,), (2, 13)):
            r = e.enc(enc, d, held); good &= r['passed'] == d and r['sp'] and r['regs'] and not r['consumed']
chk('Core allein: alle Encoder-Ereignisse unveraendert weitergegeben, Register/Stack ok', good)

# ---- Fake-Handler in den Slots
CODE = 0x4F040000
def handler(at, ret, mark):        # addq.l #1,mark ; moveq #ret,d0 ; Scratch zerstoeren ; rts
    c = bytes.fromhex('52b9') + struct.pack('>I', mark) + bytes([0x70, ret]) + bytes.fromhex('72ff91c893c9') + bytes.fromhex('4e75')
    e.u.mem_write(at, c)
MARK = 0x4F041000
NEXT = [CODE]
def setup(rets):                   # jedes Mal neue Code-Adressen (Unicorn haelt uebersetzte Bloecke im Cache)
    e.u.mem_write(S['SLOTS'], bytes(4 * C.NSLOT)); e.u.mem_write(MARK, bytes(64))
    for i, r in enumerate(rets):
        if r is None: continue
        at = NEXT[0]; NEXT[0] += 0x20
        handler(at, r, MARK + 4 * i); e.w32(S['SLOTS'] + 4 * i, at)
def marks(n): return [e.r32(MARK + 4 * i) for i in range(n)]
setup([0, None, 0]); r = e.enc(14, 3)
chk('Handler geben 0 zurueck: alle gerufen, Ereignis unveraendert weiter (%s, Drehung %s)' % (marks(3), r['passed']), marks(3) == [1, 0, 1] and r['passed'] == 3 and r['sp'] and r['regs'])
setup([0, 1, 0]); r = e.enc(14, 3)
chk('Handler gibt 1 zurueck: Ereignis verworfen (Stack +12, Sprung 0x400081e0), spaetere Slots nicht gerufen (%s)' % marks(3), r['skipped'] and r['sp'] and marks(3) == [1, 1, 0] and r['regs'])
setup([2, 0]); r = e.enc(14, -3)
chk('Handler gibt 2 zurueck: Ereignis mit Drehung 0 weiter (%s), spaetere nicht gerufen' % r['passed'], r['passed'] == 0 and r['sp'] and marks(2) == [1, 0] and r['regs'])
setup([None] * 7 + [1]); r = e.enc(5, 1)
chk('letzter Slot (7) wird erreicht', r['skipped'] and marks(8)[7] == 1)

# ---- GEST
e.w32(C.VARS + C.V_PEND, 1); e.consumed = []
_, g = e.call(S['GEST'], regs={mk.UC_M68K_REG_D0: 13})
chk('GEST(13): consume(13), PEND geloescht, Register ok', e.consumed == [13] and e.r32(C.VARS + C.V_PEND) == 0 and g)

# ---- SLOW + MODESW
CB = 0x4F042000; CBN = 0x4F042100
e.u.mem_write(CB, bytes.fromhex('52b9') + struct.pack('>I', CBN) + bytes.fromhex('70ff72ff4e75'))   # Rueckruf zaehlt, zerstoert d0/d1
BYTE = e.hdr(60)
def modesw(delta, mx=3, cb=CB, t=1000):
    e.w32(C.TIMER, t)
    e.u.mem_write(EVT, struct.pack('>IIiI', 0, 14, 0, 0)); e.u.mem_write(EVT + 8, bytes([delta & 0xff]))
    return e.call(S['MODESW'], regs={mk.UC_M68K_REG_A0: BYTE, mk.UC_M68K_REG_D1: mx, mk.UC_M68K_REG_A1: cb, mk.UC_M68K_REG_A2: EVT})
e.w8(BYTE, 0); e.w32(CBN, 0); e.u.mem_write(C.ACC, bytes(12))
seq = []; rets = set(); goods = True
for i in range(18):
    d0, g = modesw(1); seq.append(e.r8(BYTE)); rets.add(d0); goods &= g
chk('MODESW rechts: 4 Rastungen je Stufe, bis Max 3 (%s), d0 = 2, Register ok' % seq,
    seq == [0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3] and rets == {2} and goods)
chk('Rueckruf nur bei Aenderung (3 mal)', e.r32(CBN) == 3)
seq = []
for i in range(3): modesw(1); seq.append(e.r8(BYTE))
for i in range(4): modesw(-1); seq.append(e.r8(BYTE))
chk('Richtungswechsel setzt den Zaehler zurueck (%s)' % seq, seq == [3, 3, 3, 3, 3, 3, 2])
e.w8(BYTE, 9); e.u.mem_write(C.ACC, bytes(12))
for i in range(4): modesw(-1)
chk('ungueltiger Wert 9 gilt als 0 (links: bleibt 0, %d)' % e.r8(BYTE), e.r8(BYTE) == 0)
e.w8(BYTE, 1); e.u.mem_write(C.ACC, bytes(12))
modesw(1, t=1000); modesw(1, t=1000); modesw(1, t=1000); modesw(1, t=1000 + 60000000)
chk('Pause > 0.4 s setzt zurueck (3 + 1 Rastung: keine Stufe)', e.r8(BYTE) == 1)
e.w8(BYTE, 1); e.u.mem_write(C.ACC, bytes(12)); modesw(30)
chk('ein schneller Dreh (+30 in einem Ereignis): genau eine Stufe', e.r8(BYTE) == 2)
e.w8(BYTE, 1); e.u.mem_write(C.ACC, bytes(12))
for i in range(4): modesw(1, cb=0)
chk('ohne Rueckruf (a1 = 0) ok', e.r8(BYTE) == 2)
d0, g = modesw(0)
chk('Drehung 0: nichts, d0 = 2', d0 == 2 and e.r8(BYTE) == 2 and g)

# ---- KCALL (Tasten-Slots fuer SETTINGS): Handler bekommen a0 = Ereignis, d1 = Art; erster Rueckgabewert != 0 zaehlt
KH = 0x4F045000; KLOG = 0x4F046000
def khandler(at, ret, mark):       # mark: (a0, d1) ablegen ; moveq #ret,d0 ; Scratch zerstoeren ; rts
    c = bytes.fromhex('23c8') + struct.pack('>I', mark) + bytes.fromhex('23c1') + struct.pack('>I', mark + 4)
    c += bytes([0x70, ret]) + bytes.fromhex('72ff91c893c9') + bytes.fromhex('4e75')
    e.u.mem_write(at, c)
for i, (ret, slot) in enumerate(((0, 0), (1, 1))):
    khandler(KH + 0x40 * i, ret, KLOG + 16 * i); e.w32(S['KSLOTS'] + 4 * slot, KH + 0x40 * i)
e.u.mem_write(KLOG, bytes(64))
d0, g = e.call(S['KCALL'], regs={mk.UC_M68K_REG_A0: 0x4F047000, mk.UC_M68K_REG_D1: 1})
chk('KCALL: beide Slots mit a0 = Ereignis, d1 = 1 gerufen, Ergebnis des zweiten (1), Register ok',
    d0 == 1 and g and [e.r32(KLOG), e.r32(KLOG + 4), e.r32(KLOG + 16), e.r32(KLOG + 20)] == [0x4F047000, 1, 0x4F047000, 1])
e.w32(S['KSLOTS'] + 4, 0)
d0, g = e.call(S['KCALL'], regs={mk.UC_M68K_REG_A0: 0x4F047000, mk.UC_M68K_REG_D1: 0})
chk('KCALL: leerer Slot uebersprungen, alle 0 -> d0 = 0', d0 == 0 and g and e.r32(KLOG + 4) == 0)
e.w32(S['KSLOTS'], 0)

# ---- HL / HI (Pattern-Speicher, Kennung 'PCv2' in 60..63)
SRC, DST = 0x4F043000, 0x4F044000
SIG = bytes.fromhex('50437632')
src = bytearray(range(1, 65)); src[60:64] = SIG
e.u.mem_write(SRC, bytes(src)); e.u.mem_write(DST, b'\xEE' * 64)
d0, g = e.call(S['HL'], regs={mk.UC_M68K_REG_A3: SRC, mk.UC_M68K_REG_A2: DST, mk.UC_M68K_REG_D0: 1})
d = bytes(e.u.mem_read(DST, 64))
chk('HL mit Kennung: Byte 38 und 40..63 kopiert, 0..37 und 39 unberuehrt, d0 bleibt', d[38] == 39 and d[40:] == bytes(src[40:]) and d[:38] == b'\xEE' * 38 and d[39] == 0xEE and d0 == 1 and g)
e.u.mem_write(SRC, bytes(range(1, 65))); e.u.mem_write(DST, b'\xEE' * 64)
d0, g = e.call(S['HL'], regs={mk.UC_M68K_REG_A3: SRC, mk.UC_M68K_REG_A2: DST, mk.UC_M68K_REG_D0: 1})
d = bytes(e.u.mem_read(DST, 64))
chk('HL ohne Kennung (Pattern der Original-Firmware / v1): 40..51 kopiert (Humanize), 52..59 = 0, Kennung gesetzt',
    d[40:52] == bytes(range(41, 53)) and d[52:60] == bytes(8) and d[60:] == SIG and d[38] == 39 and d0 == 1 and g)
e.u.mem_write(DST, b'\xEE' * 64)
d0, g = e.call(S['HI'], regs={mk.UC_M68K_REG_A0: DST, mk.UC_M68K_REG_D0: 0x12345678})
d = bytes(e.u.mem_read(DST, 64))
chk('HI: Byte 38 und 40..59 = 0, Kennung, Rest unberuehrt, d0.b = 0', d[38] == 0 and d[40:60] == bytes(20) and d[60:] == SIG and d[:38] == b'\xEE' * 38 and d[39] == 0xEE and d0 & 0xff == 0 and g)
from g2_core import L_HOOK, I_HOOK
chk('Haken: Laden 0x4005b4b0 -> jsr HL, neues Pattern 0x4006155e -> jsr HI, Encoder 0x400081b8 -> jsr CED',
    img[L_HOOK - BASE:L_HOOK - BASE + 6] == C.jsr(S['HL']) and img[I_HOOK - BASE:I_HOOK - BASE + 6] == C.jsr(S['HI'])
    and img[C.H_HOOK - BASE:C.H_HOOK - BASE + 6] == C.jsr(S['CED']))
# ---- SETTINGS (Taste 13) loslassen nach langem Halten: speichern nur ohne andere Taste dazwischen (01.11.2026)
import g2_core as GC
UIP7, VIEW7, EV7, FVT7 = 0x4F046000, 0x4F043000, 0x4F043200, 0x4F044800
def release13(last, pend=1):
    e7 = Emu(img); saved = []
    e7.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (u.reg_write(mk.UC_M68K_REG_D0, UIP7), u.reg_write(mk.UC_M68K_REG_PC, e7.r32(u.reg_read(mk.UC_M68K_REG_A7))),
                  u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)), begin=0x400CF9A8, end=0x400CF9A8)
    def sv(u, a, z, _):
        saved.append(a); sp = u.reg_read(mk.UC_M68K_REG_A7); u.reg_write(mk.UC_M68K_REG_PC, e7.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    for t in (0x40039570, 0x40077DA8): e7.u.hook_add(UC_HOOK_CODE, sv, begin=t, end=t)
    e7.u.mem_write(0x4F044F00, b'\x4e\x75'); e7.u.mem_write(FVT7, struct.pack('>I', 0x4F044F00) * 64); e7.w32(VIEW7, FVT7)
    e7.w32(VIEW7 + 0x74, 0xFFFFFFFF); e7.w32(EV7 + 0x0C, 13); e7.w32(EV7 + 0x10, 0x10); e7.w32(C.TIMER, 1000)
    e7.w32(C.VARS + C.V_PEND, pend); e7.w32(GC.KEY_LAST, last)
    _, good = e7.call(0x4001C0D2, VIEW7, EV7, count=50000)
    return saved, e7.r32(C.VARS + C.V_PEND), good
s1, p1, g1 = release13(0xFFFFFFFF); s2, p2, g2 = release13(6)        # -1: seit dem langen Halten keine Taste
chk('SETTINGS lange gehalten, losgelassen: speichert (%s); mit anderer Taste dazwischen: weder Speichern noch Menue (%s); PEND geloescht'
    % ([hex(x) for x in s1], [hex(x) for x in s2]), s1 == [0x40039570] and s2 == [] and p1 == 0 and p2 == 0 and g1 and g2)
# ---------------- smp22: FUNC + Knopf ohne Grobschritte: echter Knopf-Handler 0x4001f4f0 ab der Parameter-Wahl (0x4001f770)
#   mit echten Anzeige-Objekten (statische Konstruktoren 0x400e7aa8 / 0x400de244), Schrittmaschine und HELD; Ansicht gestubbt
#   (Vtable +0x54 = Wert anwenden: Delta mitschreiben). Stock: mit FUNC wird keine Drehung uebernommen (Sprung spaeter).
import g2_core as GC9
VIEW9, VT9, EV9, FR9, ST9 = 0x4F044000, 0x4F045000, 0x4F046000, 0x4F03F000, 0x4F047000
def knob_emu(im):
    e = Emu(im); e.call(0x400E7AA8, count=3000000); e.call(0x400DE244, count=20000000)
    if len(im) > len(STOCK): e.call(V2SYM['core']['DTINIT'], count=200000)
    e.u.mem_write(VIEW9, bytes(0x400)); e.w32(VIEW9, VT9); ap = []
    def stub(rec):
        def f(u, a, z, _):
            sp = u.reg_read(mk.UC_M68K_REG_A7)
            if rec is not None: rec.append(struct.unpack('>i', struct.pack('>I', e.r32(sp + 12)))[0])
            u.reg_write(mk.UC_M68K_REG_D0, 0); u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        return f
    for va, rec in ((0x4006BDFE, None), (0x4005A5CC, None), (0x4006BA76, None), (ST9, ap), (ST9 + 0x10, None),
                    (0x40076082, None), (0x4006B71C, None)):
        e.u.mem_write(va, b'\x4e\x75'); e.u.hook_add(UC_HOOK_CODE, stub(rec), begin=va, end=va)
    for off in range(0, 0x100, 4): e.w32(VT9 + off, ST9 + 0x10)
    e.w32(VT9 + 0x54, ST9)
    return e, ap
def knob_turn(im, param, knob, func, n=10):
    e, ap = knob_emu(im); e.held = {C.KEY_FUNC} if func else set()
    for _ in range(n):
        e.u.mem_write(EV9, bytes(0x20)); e.w32(EV9 + 0xC, knob + 2); e.w32(EV9 + 0x10, 1)
        sp = FR9 - 0x100; e.u.mem_write(sp, bytes(0x100)); e.u.reg_write(mk.UC_M68K_REG_A7, sp); e.u.reg_write(mk.UC_M68K_REG_A6, FR9)
        for r, v in ((mk.UC_M68K_REG_D2, EV9), (mk.UC_M68K_REG_D3, param), (mk.UC_M68K_REG_D5, 0), (mk.UC_M68K_REG_D6, 0),
                     (mk.UC_M68K_REG_D7, knob), (mk.UC_M68K_REG_A2, VIEW9), (mk.UC_M68K_REG_A3, 0x4006F762), (mk.UC_M68K_REG_A4, C.HELD)):
            e.u.reg_write(r, v)
        e.u.emu_start(0x4001F770, 0x4001F96A, count=200000)
    return ap
chk('Firmware: Knopf allein 1 Wert je Raster; mit FUNC wird keine Drehung uebernommen (springt spaeter)',
    knob_turn(STOCK, 12, 4, 0) == [256] * 10 and knob_turn(STOCK, 12, 4, 1) == [])
IMGF = v2_image()
res = [knob_turn(IMGF, p, k, f) for p, k in ((12, 4), (84, 2), (85, 7), (6, 3)) for f in (0, 1)]
chk('Core: FUNC + Knopf = 1 Wert je Raster wie ohne FUNC (SHAPE, Monom Glide / Noise, Attack) %s' % [len(r) for r in res],
    all(r == [256] * 10 for r in res))
chk('Core: Stelle 0x4001f81e gepatcht (moveq #0,d0 statt jsr HELD), smp19-Stellen wieder Stock',
    all(img[va - BASE:][:len(nw)] == nw for va, _, nw in GC9.FUNC_FLAT)
    and all(img[va - BASE:][:n] == STOCK[va - BASE:][:n] for va, n in ((0x4001F778, 4), (0x4001F7B4, 2), (0x4001F7D6, 2))))
done()

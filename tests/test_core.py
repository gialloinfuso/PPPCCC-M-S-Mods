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
done()

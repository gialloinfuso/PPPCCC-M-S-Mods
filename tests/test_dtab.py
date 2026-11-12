# smp18: Deskriptor-Tabelle in der Nutzlast des Cores (g2_dtab). Echter Start (BSS-Loeschung mit Haken -> BOOT -> DTINIT),
# Verweise / Grenzen, Zugriffe der Firmware fuer 0..95 gegen dasselbe Image ohne die Verlegung (0..75) bzw. die Kopie (76..),
# Anzeige-Objekte (DONOR), Maschine des Deskriptors (MACHMAP), LKX (FUNC-Knoepfe).
import struct, sys
from rig import *
import g2_dtab as DT
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN

IMG = v2_image()
CORE = V2P['core']; S = V2SYM['core']
# Vergleichs-Image: dieselben Patches, aber die Verlegung (Verweise, Grenzen, Umleitungen des Cores) zurueckgenommen
DTW = set(DT.BOUNDS) | set(DT.HOOKS) | {x for old in DT.NREF for x in DT.refs32(STOCK, old)}
ref = bytearray(IMG)
for w in CORE['writes']:
    if w['off'] + BASE in DTW:
        o = bytes.fromhex(w['old']); ref[w['off']:w['off'] + len(o)] = o
REF = bytes(ref)
D0 = DT.DESC0

# ---------------- 1 Start mit dem echten Code (wie test_reverbs)
u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); u.ctl_set_cpu_model(mk.UC_CPU_M68K_CFV4E)
u.mem_map(0x40000000, 0x2400000); u.mem_map(0x43000000, 0x200000); u.mem_map(RET, 0x1000); u.mem_map(STACK - 0x10000, 0x20000)
u.mem_write(BASE, IMG); u.mem_write(0x43000000, b'\x5a' * C.PAYSZ)
sp = STACK - 0x100; u.mem_write(sp, struct.pack('>I', RET)); u.reg_write(mk.UC_M68K_REG_A7, sp)
for i, r in enumerate(KEEP): u.reg_write(r, 0xC0DE0000 + i)
u.emu_start(0x400004B2, RET, count=60000000)
dt = bytes(u.mem_read(C.DTAB, C.NDESC * 0x38)); old = IMG[D0 - BASE:D0 - BASE + 76 * 0x38]
ext = [dt[0x38 * k:0x38 * k + 0x38] for k in range(76, C.NDESC)]
own = {k for k in range(76, C.NDESC) if IMG[C.PIMG(C.DTD(k)) - BASE + 0x2C:C.PIMG(C.DTD(k)) - BASE + 0x30] != bytes(4)}
chk('Start: 76 Eintraege der Firmware (mit den Mods im Image) nach DTAB, eigene %s aus der Nutzlast, die freien = Eintrag 0'
    % sorted(own), dt[:76 * 0x38] == old and all(ext[k - 76] == dt[:0x38] for k in range(76, C.NDESC) if k not in own)
    and all(ext[k - 76] == IMG[C.PIMG(C.DTD(k)) - BASE:][:0x38] for k in own)
    and u.reg_read(mk.UC_M68K_REG_A7) == sp + 4 and all(u.reg_read(r) == 0xC0DE0000 + i for i, r in enumerate(KEEP)))
del u
# ---------------- 2 Verweise, Grenzen
rs = {old: DT.refs32(STOCK, old) for old in DT.NREF}
chk('Verweise: %s auf die Kopie, keiner mehr auf die alte Tabelle'
    % {hex(k): len(v) for k, v in rs.items()}, all(struct.unpack('>I', IMG[va - BASE:va - BASE + 4])[0] == old - D0 + C.DTAB
                                                for old, v in rs.items() for va in v)
    and not any(DT.refs32(IMG[:len(STOCK)], old) for old in DT.NREF))
chk('Grenzen: %d x moveq #76 / #75 -> #%d / #%d' % (len(DT.BOUNDS), C.NDESC, C.NDESC - 1),
    all(IMG[va - BASE + 1] == {76: C.NDESC, 75: C.NDESC - 1}[STOCK[va - BASE + 1]] for va in DT.BOUNDS))
chk('Alte Tabelle im Image unveraendert durch die Verlegung (nur Mods schreiben dort, wie vorher)', IMG[D0 - BASE:][:76 * 0x38] == REF[D0 - BASE:][:76 * 0x38])
# ---------------- 3 Zugriffe der Firmware, 0..99
e1, e0 = Emu(IMG), Emu(REF)
e0.u.mem_write(C.DTAB, bytes(C.NDESC * 0x38))      # die Kopie gibt es im Vergleichs-Image nicht
FUNCS = {0x4005A556: 'Maschine?', 0x4005A580: 'Gruppe', 0x4005A5CC: 'Sorte 10..12', 0x4005A5FE: 'Slot 18?', 0x4005A628: 'Flags',
         0x4005A50A: 'Maschine (DMACH)', 0x4004DF40: 'Anzeige-Objekt (ST_AT)'}
bad = []
for f, nm in FUNCS.items():
    for k in range(100):
        a_, g1 = e1.call(f, k); b_, g0 = e0.call(f, k)
        if not (g1 and g0): bad.append((nm, k, 'Register')); continue
        if k < 76 and a_ != b_: bad.append((nm, k, hex(a_), hex(b_)))
chk('Zugriffe (%s) fuer 0..75 wie ohne Verlegung, Register ok %s' % (', '.join(FUNCS.values()), bad[:4]), not bad)
nmf = {0x4000B208: 0x34, 0x4000B22A: 0x2C}
bad = []
for f, off in nmf.items():
    for k in range(100):
        a_, g1 = e1.call(f, 0x4F04C000, k)
        want = struct.unpack('>I', dt[0x38 * (k if k < C.NDESC else 0) + off:][:4])[0]
        if a_ != want or not g1: bad.append((hex(f), k, hex(a_), hex(want)))
chk('Namen (kurz 0x4000b208, lang 0x4000b22a) fuer 0..99 aus der Kopie (ab %d: Eintrag 0) %s' % (C.NDESC, bad[:3]), not bad)
mm = [e1.call(0x4005A50A, k)[0] for k in range(76, C.NDESC)]
mp = bytes(e1.u.mem_read(C.MACHMAP, C.NDESC - 76))
chk('Maschine der Deskriptoren 76..: MACHMAP, sonst Feld 0 der Kopie %s' % mm[:12],
    all(m == (mp[i] if mp[i] != 0xFF else struct.unpack('>I', dt[0x38 * (76 + i):][:4])[0]) for i, m in enumerate(mm)))
st = [e1.call(0x4004DF40, k)[0] for k in (5, 75, 76, 77, 80, 95, 96, 200)]
dn = bytes(e1.u.mem_read(C.DONOR, C.NDESC - 76))
chk('Anzeige-Objekte: 0..75 wie Firmware, 76.. = Spender (DONOR %s), ab %d Objekt 0' % (list(dn[:10]), C.NDESC),
    st == [DT.OBJ_BASE + 100 * x for x in (5, 75, dn[0], dn[1], dn[4], dn[19], 0, 0)])
chk('BOOT ruft DTINIT, LKP2 springt nach LKX', IMG[S['BOOT'] - BASE:].find(C.jsr(S['DTINIT'])) in range(0, 40)
    and IMG[S['LKP2'] - BASE:S['LKP2'] - BASE + 6] == C.jmp(S['LKX']))
done()

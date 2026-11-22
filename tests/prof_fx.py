# Lastprofil der Effekte (kein Test): je Effekt Befehle pro Block (32 Frames), Speicherzugriffe nach Bereich
# (SRAM / SDRAM gecacht / SDRAM ungecacht), 16-B-Zeilen (Code, Daten) und ein Zeitmodell wie Modded-Cycles notes/27 §2
# (1.54 Takte je Befehl, 15 Takte je Cache-Zeile, kalt = jede Zeile einmal je Block; ungecachter Zugriff: UNC Takte). Block = 666.7 us = 166 667 Takte bei 250 MHz.
# Aufruf (im testenv): python3 prof_fx.py [--hot]
import random, struct, sys, collections
from rig import *
import cfemac
sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools' / 'emu'))
import emac as MEMAC
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE

IN, OUT, PAR = 0x8000B990, 0x8000BB90, 0x4F020000
# UNC: aus der Hardware geschaetzt (gen_moddelay_113: Zustand ungecacht statt gecacht = +5 % VIBDEL / +10 % CHODEL,
# das sind ~170 / ~460 Zugriffe je Block -> 35..50 Takte je ungecachtem Zugriff)
CPI, LINE_CYC, UNC = 1.54, 15, 40
BLOCK_CYC = 250e6 * 32 / 48000
IMG = v2_image()
R2, MD2 = V2SYM['reverb-fx']['R'], V2SYM['delay-fx']['MD']
OPS = cfemac.ops()


def region(a):
    if 0x80000000 <= a < 0x80010000: return 'sram'
    if 0x4E000000 <= a < 0x50000000: return 'rig'          # Stack / Parameter des Pruefstands (auf der Maschine heiss im Cache)
    if 0x40000000 <= a < 0x48000000: return 'cached'
    if 0x48000000 <= a < 0x50000000: return 'uncached'
    if a >= 0xFC000000: return 'io'
    return 'other'


class Cache:
    """8 KB, 16-B-Zeilen, 4 Wege, LRU"""
    def __init__(s, size=8192, ways=4):
        s.sets = size // 16 // ways; s.ways = ways; s.t = [collections.OrderedDict() for _ in range(s.sets)]; s.miss = 0
    def acc(s, a):
        ln = a >> 4; st = s.t[ln % s.sets]
        if ln in st: st.move_to_end(ln); return
        s.miss += 1; st[ln] = 1
        if len(st) > s.ways: st.popitem(last=False)


# Unicorn (m68k) meldet keine Lesezugriffe: Adressen aller Speicheroperanden vor jedem Befehl aus Capstone + Registern
import re, capstone as CS
from capstone import m68k as CM
DIS = CS.Cs(CS.CS_ARCH_M68K, CS.CS_MODE_BIG_ENDIAN | CS.CS_MODE_M68K_040); DIS.detail = True
UREG = {CM.M68K_REG_D0 + i: getattr(mk, 'UC_M68K_REG_D%d' % i) for i in range(8)}
UREG.update({CM.M68K_REG_A0 + i: getattr(mk, 'UC_M68K_REG_A%d' % i) for i in range(8)})
_dec = {}
def decode(e, a):
    if a in _dec: return _dec[a]
    out = []
    if a in e.mac.ops:                                       # EMAC (Capstone kennt es nicht): %aN@, %aN@+, %aN@-, %aN@(d)
        out = [('emac', t) for t in re.findall(r'%(?:a[0-7]|fp|sp)@(?:\+|-|\(-?\d+\))?&?', e.mac.ops[a][2])]
    else:
        ins = next(DIS.disasm(bytes(e.u.mem_read(a, 12)), a, 1), None)
        try: ops_ = ins.operands if ins is not None else None
        except CS.CsError: ops_ = None                       # EMAC ohne Eintrag / Daten
        if ops_ is not None:
            mn = ins.mnemonic; sz = {'b': 1, 'w': 2}.get(mn[-1] if '.' in mn else 'l', 4)
            nreg = 1
            for o in ins.operands:
                if o.type == CM.M68K_OP_REG_BITS: nreg = bin(o.register_bits).count('1')
            for o in ins.operands:
                if o.type != CM.M68K_OP_MEM: continue
                m = o.address_mode; n = sz * (nreg if mn.startswith('movem') else 1)
                if m in (CM.M68K_AM_REGI_ADDR, CM.M68K_AM_REGI_ADDR_POST_INC): out.append(('r', o.reg, 0, n))
                elif m == CM.M68K_AM_REGI_ADDR_PRE_DEC: out.append(('r', o.reg, -sz, n))
                elif m == CM.M68K_AM_REGI_ADDR_DISP: out.append(('r', o.mem.base_reg, o.mem.disp, n))
                elif m in (CM.M68K_AM_AREGI_INDEX_8_BIT_DISP, CM.M68K_AM_AREGI_INDEX_BASE_DISP):
                    out.append(('x', o.mem.base_reg, o.mem.disp, o.mem.index_reg, max(1, o.mem.scale), o.mem.index_size, n))
                elif m in (CM.M68K_AM_ABSOLUTE_DATA_LONG, CM.M68K_AM_ABSOLUTE_DATA_SHORT): out.append(('a', o.imm & 0xffffffff, n))
    _dec[a] = out
    return out


def eas(e, a):
    rr = e.u.reg_read
    for d in decode(e, a):
        k = d[0]
        if k == 'r': yield (rr(UREG[d[1]]) + d[2]) & 0xffffffff, d[3]
        elif k == 'x':
            b = rr(UREG[d[1]]) if d[1] else 0; x = rr(UREG[d[3]])
            if d[5] == 0: x = ((x & 0xffff) ^ 0x8000) - 0x8000
            yield (b + d[2] + x * d[4]) & 0xffffffff, d[6]
        elif k == 'a': yield d[1], d[2]
        else: yield e.mac._ea(d[1])[0], 4


def mkemu():
    e = Emu(IMG)
    e.u.mem_map(0x43200000, 0x600000)                        # Reverb-Leitungen bis 0x43800000
    m = MEMAC.EMAC(e.u); m.install(OPS); e.mac = m
    def rev(u, a, z, _):                 # Reverb der Firmware (EMAC, im Pruefstand nicht lauffaehig): Ersatz out = in/2, Kosten 0
        sp = u.reg_read(mk.UC_M68K_REG_A7); ret, out, inp = struct.unpack('>III', bytes(u.mem_read(sp, 12)))
        d = bytes(u.mem_read(inp, 256))
        u.mem_write(out, b''.join(struct.pack('>i', struct.unpack('>i', d[i:i + 4])[0] >> 1) for i in range(0, 256, 4)))
        u.reg_write(mk.UC_M68K_REG_PC, ret); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    e.u.hook_add(UC_HOOK_CODE, rev, begin=0x400579C4, end=0x400579C4)
    return e


def run_block(e, entry, frames, p0, p1, prof=None):
    e.u.mem_write(IN, b''.join(struct.pack('>ii', l, r) for l, r in frames)); e.u.mem_write(PAR, struct.pack('>HH', p0, p1))
    sp = STACK - 0x40; e.u.mem_write(sp, struct.pack('>IIII', RET, OUT, IN, PAR)); e.u.reg_write(mk.UC_M68K_REG_A7, sp)
    e.mac.macsr = 0
    hs = []
    if prof is not None:
        def code(u, a, z, _):
            prof['ins'] += 1; prof['pc'][a] += 1; prof['cl'].add(a >> 4); prof['ic'].acc(a)
            if z > 2 and (a >> 4) != ((a + z - 1) >> 4): prof['ic'].acc(a + z - 1)
            pc = a
            for ea, n in eas(e, pc):
                r = region(ea); prof['m'][r] += max(1, n // 4)
                if r == 'uncached': prof['unc_pc'][pc] += 1
                if r == 'cached':
                    for x in range(ea >> 4, ((ea + n - 1) >> 4) + 1): prof['dl'].add(x); prof['dc'].acc(x << 4)
        hs = [e.u.hook_add(UC_HOOK_CODE, code)]
    e.u.emu_start(entry, RET, count=5000000)
    for h in hs: e.u.hook_del(h)


def newprof():
    return dict(ins=0, pc=collections.Counter(), cl=set(), dl=set(), m=collections.Counter(), unc_pc=collections.Counter(),
                ic=Cache(), dc=Cache())


CASES = [  # Name, Platz, Typ, p0, p1
    ('Chorus I', 'r', 1, 64 << 8, 64 << 8), ('Chorus II', 'r', 2, 64 << 8, 64 << 8),
    ('Phaser', 'r', 3, 64 << 8, 64 << 8), ('Razr (ohne FW-Rev)', 'r', 4, 64 << 8, 64 << 8), ('Hall', 'r', 5, 100 << 8, 64 << 8),
    ('Room', 'r', 6, 100 << 8, 64 << 8), ('Plate', 'r', 7, 100 << 8, 64 << 8),
    ('Digital', 'd', 1, 8192, 20000), ('ViDel', 'd', 2, 8192, 20000), ('ChDel', 'd', 3, 8192, 20000)]
NWARM, NMEAS = 700, 20
hot = '--hot' in sys.argv
only = [a for a in sys.argv[1:] if not a.startswith('--')]
print('%-18s %7s %6s %6s %6s %5s %5s %6s %6s %7s' % ('Effekt', 'Befehle', 'SRAM', 'gecach', 'UNGEC', 'Code', 'Daten', 'I-miss', 'D-miss', 'Modell'))
for name, slot, t, p0, p1 in CASES:
    if only and name.split()[0] not in only: continue
    e = mkemu(); random.seed(1)
    if slot == 'r': e.w8(e.hdr(C.P_RFX), t); e.w8(e.hdr(C.P_DFX), 0); entry = R2
    else: e.w8(e.hdr(C.P_DFX), t); e.w8(e.hdr(C.P_RFX), 0); e.w8(e.hdr(C.P_DSPD), 64 ^ 64); entry = MD2
    fr = lambda: [(random.randint(-2**29, 2**29), random.randint(-2**29, 2**29)) for _ in range(32)]
    P = newprof()
    try:
        for _ in range(NWARM): run_block(e, entry, fr(), p0, p1)          # Reverbs: Leitungen geloescht, eingeschwungen
        for i in range(NMEAS):
            if i == NMEAS - 1: P['cl'], P['dl'] = set(), set()            # Zeilen: nur der letzte Block (kalt)
            run_block(e, entry, fr(), p0, p1, P)
    except Exception as x:
        print('%-18s laeuft im Pruefstand nicht (%s)' % (name, x)); continue
    ins = P['ins'] / NMEAS; m = {k: v / NMEAS for k, v in P['m'].items()}
    cl, dl = len(P['cl']), len(P['dl'])
    model = ins * CPI + (cl + dl) * LINE_CYC + m.get('uncached', 0) * UNC     # kalt: jede Zeile einmal je Block
    print('%-18s %7d %6d %6d %6d %5d %5d %6d %6d %6.1f%%' % (name, ins, m.get('sram', 0), m.get('cached', 0), m.get('uncached', 0),
          cl, dl, P['ic'].miss / NMEAS, P['dc'].miss / NMEAS, 100 * model / BLOCK_CYC))
    if hot:
        for pc, n in P['pc'].most_common(12): print('      %#x  %6d' % (pc, n / NMEAS))
        for pc, n in P['unc_pc'].most_common(8): print('   UNC %#x  %6d' % (pc, n / NMEAS))

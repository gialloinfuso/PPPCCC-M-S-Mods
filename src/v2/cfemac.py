"""ColdFire-EMAC-Befehle fuer die Hand-Kodierung (Klasse A aus gen_solo), eigener Code.

Kodierung (Registerform ohne Laden), geprueft am Verhalten von Unicorn und an der Statistik der EMAC-Befehle der Firmware
(Akkumulator-Nummer = Bit 7 des ersten Worts | Bit 4 des Erweiterungsworts << 1):
  MAC/MSAC.L Ry,Rx[,<<|>>],ACCn : 1010 Rx 0 n0 Rx.A 00 Ry(4)  |  0000 1 sf(2) msac 000 n1 0000
  MOVCLR.L ACCn,Rx : 0xa1c0 | n<<9 | Rx       MOVE.L ACCn,Rx : 0xa180 | n<<9 | Rx
  MOVE.L <ea>,ACCn : 0xa100 | n<<9 | ea       MOVE.L <ea>,MACSR : 0xa900 | ea      MOVE.L MACSR,Rx : 0xa980 | Rx
Jeder Befehl wird in LOG mitgeschrieben (Adresse, Laenge, Mnemonic und Operanden in objdump-Schreibweise): die Tests
fuehren damit die EMAC-Befehle exakt aus (Unicorns EMAC ist im fraktionalen Modus falsch)."""
import struct

LOG = []


def rn(r):
    """'d0'..'d7', 'a0'..'a7' -> 0..15"""
    return (8 if r[0] == 'a' else 0) + int(r[1])


def _log(a, size, mn, ops):
    LOG.append((a.org + len(a.b), size, mn, ops))


def mac(a, ry, rx, acc, shift=0, sub=False):
    nx, ny = rn(rx), rn(ry)
    sh = {0: '', 1: '<<,', -1: '>>,'}[shift]
    _log(a, 4, 'msacl' if sub else 'macl', f"%{ry},%{rx},{sh}%acc{acc}")
    w1 = 0xA000 | (nx & 7) << 9 | (acc & 1) << 7 | (nx >> 3) << 6 | ny
    w2 = 0x0800 | {0: 0, 1: 0x200, -1: 0x600}[shift] | (0x100 if sub else 0) | (acc >> 1) << 4
    a.w(w1, w2)


def msac(a, ry, rx, acc, shift=0):
    mac(a, ry, rx, acc, shift, True)


def movclr(a, acc, r):
    _log(a, 2, 'movclrl', f"%acc{acc},%{r}")
    a.w(0xA1C0 | acc << 9 | rn(r))


def acc_to(a, acc, r):
    _log(a, 2, 'movel', f"%acc{acc},%{r}")
    a.w(0xA180 | acc << 9 | rn(r))


def to_acc(a, src, acc):
    """src = Registername oder Zahl (#imm)"""
    if isinstance(src, int):
        _log(a, 6, 'movel', f"#{src - (1 << 32) if src & 0x80000000 else src},%acc{acc}")
        a.w(0xA13C | acc << 9); a.l32(src & 0xFFFFFFFF)
    else:
        _log(a, 2, 'movel', f"%{src},%acc{acc}")
        a.w(0xA100 | acc << 9 | rn(src))


def to_macsr(a, src):
    if isinstance(src, int):
        _log(a, 6, 'movel', f"#{src},%macsr")
        a.w(0xA93C); a.l32(src)
    else:
        _log(a, 2, 'movel', f"%{src},%macsr")
        a.w(0xA900 | rn(src))


def macsr_to(a, r):
    _log(a, 2, 'movel', f"%macsr,%{r}")
    a.w(0xA980 | rn(r))


def spans(lo, hi):
    """EMAC-Befehle im Bereich [lo, hi): {Adresse: Laenge}"""
    return {x[0]: x[1] for x in LOG if lo <= x[0] < hi}


def ops(lo=0, hi=1 << 32):
    """fuer Modded-Cycles tools/emu/emac.py EMAC.install: {Adresse: (Laenge, Mnemonic, Operanden)}"""
    return {x[0]: (x[1], x[2], x[3]) for x in LOG if lo <= x[0] < hi}


def check(code, base):
    """wie check_cf (Befehle <= 6 Byte), aber EMAC-Befehle (Capstone kennt sie nicht) werden uebersprungen."""
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'cap' / 'bindings' / 'python'))
    from capstone import Cs, CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_040
    cs = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_040)
    sk = spans(base, base + len(code))
    i = 0
    while i < len(code):
        if base + i in sk:
            i += sk[base + i]; continue
        ins = next(cs.disasm(code[i:i + 12], base + i, 1), None)
        if ins is None:
            i += 2; continue
        assert ins.size <= 6, (hex(base + i), ins.mnemonic, ins.op_str, ins.size)
        i += ins.size

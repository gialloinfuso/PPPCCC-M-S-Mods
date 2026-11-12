"""Kleiner ColdFire-Assembler (eigener Code) fuer lesbare Patches: Text-Zeilen -> Woerter in einer gen_solo.A.

    asm(a, '''
        lbl:    move.l  4(sp),d0
                cmpi.l  #0x40,d0
                bne     lbl            ; Bcc immer .W (A.bcc)
                mac     d0,d4,acc0,<<  ; EMAC ueber cfemac (LOG fuer die Tests)
    ''', SYM=0x40001234)

Operanden: dN aN sp, (aN) (aN)+ -(aN), d16(aN), d8(aN,dX.l*S), Zahl (abs.l; abs.w mit .w-Suffix: 0x12.w), #Zahl,
Namen aus kw (Python-Werte) oder Labels (nur fuer Spruenge / lea / pea / jsr / jmp / abs.l: 32-Bit-Feld wird in
done() aufgeloest). Groessen .b .w .l (Standard .l). Kommentare mit ';'. Nur ColdFire-gueltige Formen (check_cf prueft
zusaetzlich Laengen)."""
import re, struct
import cfemac as E

REG = {**{f'd{i}': ('d', i) for i in range(8)}, **{f'a{i}': ('a', i) for i in range(8)}, 'sp': ('a', 7), 'fp': ('a', 6)}
CC = {'ra': 0, 'bra': 0, 'bsr': 1, 'bhi': 2, 'bls': 3, 'bcc': 4, 'bhs': 4, 'bcs': 5, 'blo': 5, 'bne': 6, 'beq': 7,
      'bvc': 8, 'bvs': 9, 'bpl': 10, 'bmi': 11, 'bge': 12, 'blt': 13, 'bgt': 14, 'ble': 15}
SCC = {'st': 0, 'sf': 1, 'shi': 2, 'sls': 3, 'scc': 4, 'scs': 5, 'sne': 6, 'seq': 7, 'svc': 8, 'svs': 9, 'spl': 10, 'smi': 11,
       'sge': 12, 'slt': 13, 'sgt': 14, 'sle': 15}
SZ = {'b': 1, 'w': 2, 'l': 4}


class Ea:
    def __init__(s, mode, reg, ext=b'', fix=None, kind=None, val=None):
        s.mode, s.reg, s.ext, s.fix, s.kind, s.val = mode, reg, ext, fix, kind, val
    @property
    def bits(s): return s.mode << 3 | s.reg


def num(t, kw, labels_ok=True):
    t = t.strip()
    try:
        return int(eval(t, {}, kw)), None
    except NameError:
        if labels_ok and re.fullmatch(r'[A-Za-z_.][\w.]*', t):
            return 0, t
        raise


def ea(t, kw, size=4):
    t = t.strip()
    if t in REG:
        k, n = REG[t]; return Ea(0 if k == 'd' else 1, n)
    m = re.fullmatch(r'\((a\d|sp|fp)\)', t)
    if m: return Ea(2, REG[m[1]][1])
    m = re.fullmatch(r'\((a\d|sp|fp)\)\+', t)
    if m: return Ea(3, REG[m[1]][1])
    m = re.fullmatch(r'-\((a\d|sp|fp)\)', t)
    if m: return Ea(4, REG[m[1]][1])
    m = re.fullmatch(r'(.*)\((a\d|sp|fp),\s*([da]\d)(?:\.l)?(?:\*(\d))?\)', t)
    if m:
        d, _ = num(m[1] or '0', kw, False); x = REG[m[3]]; sc = {None: 0, '1': 0, '2': 1, '4': 2, '8': 3}[m[4]]
        assert -128 <= d < 128, t
        return Ea(6, REG[m[2]][1], struct.pack('>H', (x[0] == 'a') << 15 | x[1] << 12 | 0x800 | sc << 9 | (d & 0xff)))
    m = re.fullmatch(r'(.*)\((a\d|sp|fp)\)', t)
    if m:
        d, _ = num(m[1] or '0', kw, False); assert -32768 <= d < 32768, t
        return Ea(5, REG[m[2]][1], struct.pack('>h', d))
    if t.startswith('#'):
        v, lab = num(t[1:], kw)
        if lab: return Ea(7, 4, b'\0\0\0\0', fix=lab, kind='imm')
        if size == 4: return Ea(7, 4, struct.pack('>I', v & 0xffffffff), val=v)
        return Ea(7, 4, struct.pack('>H', v & 0xffff), val=v)
    if t.endswith('.w'):
        v, _ = num(t[:-2], kw, False); return Ea(7, 0, struct.pack('>h', v))
    v, lab = num(t, kw)
    return Ea(7, 1, struct.pack('>I', v & 0xffffffff), fix=lab, kind='abs')


def split_ops(s):
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur); cur = ''
        else:
            cur += ch
    if cur.strip(): out.append(cur)
    return [o.strip() for o in out]


class Asm:
    def __init__(s, a, kw):
        s.a, s.kw, s.fix = a, kw, []
    def w(s, *ws): s.a.w(*ws)
    def put_ea(s, e):
        if e.fix:
            s.fix.append((len(s.a.b), e.fix))
        s.a.b += e.ext
    def line(s, ln):
        ln = ln.split(';')[0].rstrip()
        if not ln.strip(): return
        m = re.match(r'\s*([A-Za-z_.][\w.]*):(.*)', ln)
        if m:
            assert m[1] not in s.a.lab, f"Label doppelt: {m[1]}"; s.a.label(m[1]); ln = m[2]
            if not ln.strip(): return
        parts = ln.strip().split(None, 1)
        op, rest = parts[0].lower(), (parts[1] if len(parts) > 1 else '')
        ops = split_ops(rest)
        base, _, sz = op.partition('.')
        size = SZ.get(sz, 4)
        at = len(s.a.b)
        getattr(s, 'op_' + base, s.unknown)(base, size, ops, op)
        if base not in ('dc', 'orig'):
            n = len(s.a.b) - at
            assert n <= 6, f'ColdFire: Befehl laenger als 6 Byte: {ln.strip()} ({n})'
    def unknown(s, base, size, ops, op):
        if base in CC and base not in ('ra',) and op.endswith('.s'):      # Bcc.S (8-Bit-Verschiebung, in done() aufgeloest)
            s.w(0x6000 | CC[base] << 8)
            if not hasattr(s.a, 'sfix'): s.a.sfix = []
            s.a.sfix.append((len(s.a.b) - 1, ops[0])); return
        if base in CC and base not in ('ra',):
            s.a.bcc(CC[base], ops[0]); return
        if base in SCC:
            r = REG[ops[0]]; assert r[0] == 'd'; s.w(0x50C0 | SCC[base] << 8 | r[1]); return
        raise ValueError(f'unbekannt: {op} {ops}')
    # ---- Daten
    def op_move(s, base, size, ops, op):
        if ops[0].startswith('acc') or ops[1].startswith('acc') or 'macsr' in ops:
            return s.emac(op, ops)
        src, dst = ea(ops[0], s.kw, size), ea(ops[1], s.kw, size)
        # ColdFire: Quelle (d8,An,Xi) / abs / #imm -> Ziel nur Dn An (An) (An)+ -(An); Quelle (d16,An) -> Ziel nicht (d8,An,Xi) / abs
        if src.mode == 6 or src.mode == 7:
            assert dst.mode <= 4, f'ColdFire-MOVE nicht erlaubt: {op} {ops}'
        if src.mode == 5:
            assert dst.mode not in (6, 7), f'ColdFire-MOVE nicht erlaubt: {op} {ops}'
        code = {1: 1, 2: 3, 4: 2}[size]
        s.w(code << 12 | dst.reg << 9 | dst.mode << 6 | src.bits)
        s.put_ea(src); s.put_ea(dst)
    def op_movea(s, base, size, ops, op): s.op_move(base, size, ops, op)
    def op_lea(s, base, size, ops, op):
        src = ea(ops[0], s.kw); r = REG[ops[1]]; assert r[0] == 'a'
        s.w(0x41C0 | r[1] << 9 | src.bits); s.put_ea(src)
    def op_pea(s, base, size, ops, op):
        src = ea(ops[0], s.kw); s.w(0x4840 | src.bits); s.put_ea(src)
    def op_clr(s, base, size, ops, op):
        d = ea(ops[0], s.kw); s.w(0x4200 | {1: 0, 2: 1, 4: 2}[size] << 6 | d.bits); s.put_ea(d)
    def op_tas(s, base, size, ops, op):
        d = ea(ops[0], s.kw, 1); s.w(0x4AC0 | d.bits); s.put_ea(d)
    def op_tst(s, base, size, ops, op):
        d = ea(ops[0], s.kw, size); s.w(0x4A00 | {1: 0, 2: 1, 4: 2}[size] << 6 | d.bits); s.put_ea(d)
    def _dn(s, t):
        r = REG[t]; assert r[0] == 'd', t; return r[1]
    def op_neg(s, b, z, o, op): s.w(0x4480 | s._dn(o[0]))
    def op_not(s, b, z, o, op): s.w(0x4680 | s._dn(o[0]))
    def op_swap(s, b, z, o, op): s.w(0x4840 | s._dn(o[0]))
    def op_ext(s, b, z, o, op): s.w((0x48C0 if z == 4 else 0x4880) | s._dn(o[0]))
    def op_extb(s, b, z, o, op): s.w(0x49C0 | s._dn(o[0]))
    def op_moveq(s, b, z, o, op):
        v, _ = num(o[0].lstrip('#'), s.kw, False); assert -128 <= v < 128, op
        s.w(0x7000 | s._dn(o[1]) << 9 | (v & 0xff))
    def _mv(s, z, o, zero):
        src = ea(o[0], s.kw, 2); s.w(0x7100 | s._dn(o[1]) << 9 | zero << 7 | (z == 2) << 6 | src.bits); s.put_ea(src)
    def op_mvs(s, b, z, o, op): s._mv(z, o, 0)
    def op_mvz(s, b, z, o, op): s._mv(z, o, 1)
    def _q(s, sub, z, o):
        v, _ = num(o[0].lstrip('#'), s.kw, False); assert 1 <= v <= 8
        d = ea(o[1], s.kw); s.w(0x5000 | (v & 7) << 9 | sub << 8 | 2 << 6 | d.bits); s.put_ea(d)
    def op_addq(s, b, z, o, op): s._q(0, z, o)
    def op_subq(s, b, z, o, op): s._q(1, z, o)
    def _alu(s, hi, z, o, op):
        if o[0].startswith('#') and o[1] in REG and REG[o[1]][0] == 'd':
            imm = {0xD: 0x0680, 0x9: 0x0480, 0xC: 0x0280, 0x8: 0x0080, 0xB: 0x0C80}[hi]
            v, lab = num(o[0][1:], s.kw); assert z == 4, op
            s.w(imm | s._dn(o[1])); s.a.l32(v & 0xffffffff); return
        if o[1] in REG and REG[o[1]][0] == 'a':                                   # adda / suba / cmpa
            src = ea(o[0], s.kw); s.w(hi << 12 | REG[o[1]][1] << 9 | 7 << 6 | src.bits); s.put_ea(src); return
        if o[1] in REG:                                                           # ea,Dn
            src = ea(o[0], s.kw, z)
            opm = {1: 0, 2: 1, 4: 2}[z] if hi == 0xB else 2
            assert hi == 0xB or z == 4, op
            s.w(hi << 12 | s._dn(o[1]) << 9 | opm << 6 | src.bits); s.put_ea(src); return
        assert z == 4 and hi != 0xB, op                                           # Dn,ea
        d = ea(o[1], s.kw); s.w(hi << 12 | s._dn(o[0]) << 9 | 6 << 6 | d.bits); s.put_ea(d)
    def op_add(s, b, z, o, op): s._alu(0xD, z, o, op)
    def op_adda(s, b, z, o, op): s._alu(0xD, z, o, op)
    def op_sub(s, b, z, o, op): s._alu(0x9, z, o, op)
    def op_suba(s, b, z, o, op): s._alu(0x9, z, o, op)
    def op_and(s, b, z, o, op): s._alu(0xC, z, o, op)
    def op_or(s, b, z, o, op): s._alu(0x8, z, o, op)
    def op_cmp(s, b, z, o, op): s._alu(0xB, z, o, op)
    def op_cmpa(s, b, z, o, op): s._alu(0xB, z, o, op)
    def op_eor(s, b, z, o, op):
        d = ea(o[1], s.kw); s.w(0xB000 | s._dn(o[0]) << 9 | 6 << 6 | d.bits); s.put_ea(d)
    def _imm(s, code, o, op):
        v, lab = num(o[0].lstrip('#'), s.kw); s.w(code | s._dn(o[1])); s.a.l32(v & 0xffffffff)
    def op_addi(s, b, z, o, op): s._imm(0x0680, o, op)
    def op_subi(s, b, z, o, op): s._imm(0x0480, o, op)
    def op_andi(s, b, z, o, op): s._imm(0x0280, o, op)
    def op_ori(s, b, z, o, op): s._imm(0x0080, o, op)
    def op_eori(s, b, z, o, op): s._imm(0x0A80, o, op)
    def op_cmpi(s, b, z, o, op):
        assert z == 4, op; s._imm(0x0C80, o, op)
    def _sh(s, typ, left, o):
        d = s._dn(o[1])
        if o[0].startswith('#'):
            v, _ = num(o[0][1:], s.kw, False); assert 1 <= v <= 8
            s.w(0xE000 | (v & 7) << 9 | left << 8 | 2 << 6 | typ << 3 | d)
        else:
            s.w(0xE000 | s._dn(o[0]) << 9 | left << 8 | 2 << 6 | 1 << 5 | typ << 3 | d)
    def op_asl(s, b, z, o, op): s._sh(0, 1, o)
    def op_asr(s, b, z, o, op): s._sh(0, 0, o)
    def op_lsl(s, b, z, o, op): s._sh(1, 1, o)
    def op_lsr(s, b, z, o, op): s._sh(1, 0, o)
    def _mul(s, sgn, z, o, op):
        src = ea(o[0], s.kw, z)
        if z == 2:
            s.w(0xC000 | s._dn(o[1]) << 9 | (7 if sgn else 3) << 6 | src.bits); s.put_ea(src); return
        assert src.mode != 7 or src.reg != 4, 'muls.l #imm gibt es nicht'
        s.w(0x4C00 | src.bits, s._dn(o[1]) << 12 | sgn << 11); s.put_ea(src)
    def op_muls(s, b, z, o, op): s._mul(1, z, o, op)
    def op_mulu(s, b, z, o, op): s._mul(0, z, o, op)
    def _div(s, sgn, z, o, op, rem=False):
        src = ea(o[0], s.kw, z)
        assert src.mode != 7 or src.reg != 4, 'div #imm gibt es nicht'
        if z == 2 and not rem:
            s.w(0x8000 | s._dn(o[1]) << 9 | (7 if sgn else 3) << 6 | src.bits); s.put_ea(src); return
        if rem:                                                                   # rems/remu.l ea,Dw:Dx  (Dw = Rest)
            dw, dx = [s._dn(x) for x in o[1].split(':')]
            s.w(0x4C40 | src.bits, dx << 12 | sgn << 11 | dw)
        else:
            q = s._dn(o[1]); s.w(0x4C40 | src.bits, q << 12 | sgn << 11 | q)
        s.put_ea(src)
    def op_divs(s, b, z, o, op): s._div(1, z, o, op)
    def op_divu(s, b, z, o, op): s._div(0, z, o, op)
    def op_rems(s, b, z, o, op): s._div(1, 4, o, op, True)
    def op_remu(s, b, z, o, op): s._div(0, 4, o, op, True)
    def _bit(s, code_imm, code_reg, o):
        d = ea(o[1], s.kw)
        if o[0].startswith('#'):
            # ColdFire: Bit-Befehle mit #imm nur auf Dn, (An), (An)+, -(An), d16(An) (smp21-Absturz: btst #1,0(a0,d2.l))
            assert d.mode <= 5, f'ColdFire: {o} (Bit-Befehl mit #imm und diesem Ziel nicht erlaubt)'
            v, _ = num(o[0][1:], s.kw, False); s.w(code_imm | d.bits, v); s.put_ea(d)
        else:
            s.w(code_reg | s._dn(o[0]) << 9 | d.bits); s.put_ea(d)
    def op_btst(s, b, z, o, op): s._bit(0x0800, 0x0100, o)
    def op_bset(s, b, z, o, op): s._bit(0x08C0, 0x01C0, o)
    def op_bclr(s, b, z, o, op): s._bit(0x0880, 0x0180, o)
    def op_bchg(s, b, z, o, op): s._bit(0x0840, 0x0140, o)
    def op_jsr(s, b, z, o, op):
        d = ea(o[0], s.kw); s.w(0x4E80 | d.bits); s.put_ea(d)
    def op_jmp(s, b, z, o, op):
        d = ea(o[0], s.kw); s.w(0x4EC0 | d.bits); s.put_ea(d)
    def op_rts(s, b, z, o, op): s.w(0x4E75)
    def op_link(s, b, z, o, op):
        r = REG[o[0]]; assert r[0] == 'a'; v, _ = num(o[1].lstrip('#'), s.kw, False); s.w(0x4E50 | r[1], v & 0xffff)
    def op_nop(s, b, z, o, op): s.w(0x4E71)
    def op_unlk(s, b, z, o, op):
        r = REG[o[0]]; assert r[0] == 'a'; s.w(0x4E58 | r[1])
    def op_movem(s, b, z, o, op):
        def mask(t):
            m = 0
            for part in t.split('/'):
                if '-' in part:
                    x, y = part.split('-'); kx, nx = REG[x]; ky, ny = REG[y]
                    for i in range(nx, ny + 1): m |= 1 << (i + (8 if kx == 'a' else 0))
                else:
                    k, n = REG[part]; m |= 1 << (n + (8 if k == 'a' else 0))
            return m
        if '(' in o[1]:
            d = ea(o[1], s.kw); assert d.mode in (2, 5); s.w(0x48C0 | d.bits, mask(o[0])); s.put_ea(d)
        else:
            d = ea(o[0], s.kw); assert d.mode in (2, 5); s.w(0x4CC0 | d.bits, mask(o[1])); s.put_ea(d)
    def op_sats(s, b, z, o, op):
        """sats.l Dn (ColdFire ISA_B: nach Ueberlauf V auf 0x7fffffff / 0x80000000 saettigen)"""
        s.w(0x4C80 | s._dn(o[0]))
    def op_orig(s, b, z, o, op):
        """orig VA,N: N Original-Bytes der Firmware ab VA (verschobene Befehle eines Hakens; aus dem Image, nie im Quelltext)"""
        s.a.orig(num(o[0], s.kw, False)[0], num(o[1], s.kw, False)[0])
    def op_dc(s, b, z, o, op):
        for x in o:
            v, lab = num(x, s.kw)
            if z == 4:
                if lab: s.fix.append((len(s.a.b), lab))
                s.a.l32(v & 0xffffffff)
            elif z == 2: s.w(v & 0xffff)
            else: s.a.b += bytes([v & 0xff])
    # ---- EMAC (cfemac, damit die Tests die Befehle kennen)
    def emac(s, op, ops):
        acc = lambda t: int(t[3:])
        if op.startswith('move'):
            if ops[1] == 'macsr':
                return E.to_macsr(s.a, int(num(ops[0][1:], s.kw, False)[0]) if ops[0].startswith('#') else ops[0])
            if ops[0] == 'macsr': return E.macsr_to(s.a, ops[1])
            if ops[0].startswith('acc'): return E.acc_to(s.a, acc(ops[0]), ops[1])
            src = int(num(ops[0][1:], s.kw, False)[0]) if ops[0].startswith('#') else ops[0]
            return E.to_acc(s.a, src, acc(ops[1]))
    def op_movclr(s, b, z, o, op): E.movclr(s.a, int(o[0][3:]), o[1])
    def _mac(s, sub, o):
        sh = 0
        if len(o) > 3: sh = {'<<': 1, '>>': -1}[o[3]]
        E.mac(s.a, o[0], o[1], int(o[2][3:]), shift=sh, sub=sub)
    def op_mac(s, b, z, o, op): s._mac(False, o)
    def op_msac(s, b, z, o, op): s._mac(True, o)


def asm(a, text, kw=None, **more):
    """Zeilen assemblieren; kw: Namen fuer Ausdruecke (auch ein defaultdict fuer den ersten Durchgang). 32-Bit-Felder
    mit unbekannten Namen werden in done() aus den Labels der Maske oder ext aufgeloest."""
    import collections
    s = Asm(a, collections.ChainMap(more, kw) if kw is not None else more)
    for ln in text.splitlines():
        s.line(ln)
    pend = getattr(a, 'abs_fix', [])
    pend += s.fix
    a.abs_fix = pend
    return s


def done(a, ext=None):
    """wie a.done(), plus absolute Label-Felder (Labels der Maske, sonst ext)"""
    code = bytearray(a.done())
    for pos, lab in getattr(a, 'sfix', []):
        disp = a.lab[lab] - (a.org + pos + 1)
        assert -128 <= disp < 128 and disp != 0, (lab, disp)
        code[pos] = disp & 0xff
    for pos, lab in getattr(a, 'abs_fix', []):
        v = a.lab[lab] if lab in a.lab else ext[lab]
        code[pos:pos + 4] = struct.pack('>I', v)
    return bytes(code)


def op_addx(s, b, z, o, op):
    s.w(0xD180 | s._dn(o[1]) << 9 | s._dn(o[0]))
Asm.op_addx = op_addx


def op_subx(s, b, z, o, op):
    s.w(0x9180 | s._dn(o[1]) << 9 | s._dn(o[0]))
Asm.op_subx = op_subx

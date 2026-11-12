# sampler smp20: Transfer-Kennung CYC / SMP (Methode nach Model-TG, MIT). Echter Firmware-Code im Emulator, Ausschnitte.
# 1. Kennungs-Antwort (0x40084b8e .. 0x40084be6): CYC = Liste, Laenge, Name wie die Firmware (Vergleich mit dem Stock-Image);
#    SMP = Liste aus der der Firmware (roh -> Sample-Familie, 0x13 hinter 0x10), 'Model Samples'; Stapel wie die Firmware.
# 2. Produktnummer (0x40084c14): 27 / 25, Stapel +40.
# 3. Eingehend (0x4009249a): Typ-Byte; SMP: Sample-Familie -> roher Zwilling, auch in der Nachricht; sonst unveraendert.
# 4. Ausgehend (0x40094c9a): Antwort-Typ; SMP: roh | 0x80 -> Sample | 0x80; sonst unveraendert; Stapel +32.
# 5. Device Config (0x40032aee): eine Zeile mit vier Closures (Firmware-Aufrufe gestubbt), Register, Ruecksprung;
#    Drehen rechts / links = SMP / CYC + Neuzeichnen, Beschriftung 'Transfer', Wert-Namen.
# 6. Andere Patches schreiben keine dieser Stellen (nur mit dem Sampler aktiv).
import struct
from rig import *
import g2_sampler as SM

IMG = v2_image()
S = V2SYM['sampler']
B = lambda img, va, n: bytes(img[va - BASE:va - BASE + n])
chk('Haken: XID, XPR, XRT, XOT, XCFG', B(IMG, SM.X_ID, 6) == C.jmp(S['XID']) and B(IMG, SM.X_PR, 6) == C.jmp(S['XPR'])
    and B(IMG, SM.X_RT, 6) == C.jsr(S['XRT']) and B(IMG, SM.X_OT, 8) == C.jmp(S['XOT']) + b'\x4e\x71'
    and B(IMG, SM.X_CFG, 6) == C.jmp(S['XCFG']))
NOSMP = v2_image([i for i in V2_IDS if i not in ('sampler', 'strings', 'mono')])
chk('ohne Sampler: alle 5 Stellen wie Stock', all(B(NOSMP, va, n) == B(STOCK, va, n) for va, n in
    ((SM.X_ID, 0x58), (SM.X_PR, 6), (SM.X_RT, 6), (SM.X_OT, 8), (SM.X_CFG, 6))))

FRAME, BUF, ALLOC = 0x4F048000, 0x4F04A000, 0x4F04C000
XMAP = SM.X_MAP


def ident(img, mode):
    """Stueck 0x40084b8e .. 0x40084be6 mit a0 = Zuteiler (Stub: BUF), a6 = Rahmen. -> (Liste, Laenge, Name, Stapel, ok)"""
    e = Emu(img)
    if mode is not None: e.w32(S['TMODE'], mode)
    e.u.mem_write(ALLOC, b'\x20\x3c' + struct.pack('>I', BUF) + b'\x4e\x75')      # move.l #BUF,d0 ; rts
    e.u.mem_write(BUF, b'\xee' * 64)
    sp0 = STACK - 0x300; e.u.reg_write(mk.UC_M68K_REG_A7, sp0)
    e.u.reg_write(mk.UC_M68K_REG_A6, FRAME); e.u.reg_write(mk.UC_M68K_REG_A0, ALLOC)
    for r in (mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D3, mk.UC_M68K_REG_D4, mk.UC_M68K_REG_D5, mk.UC_M68K_REG_A2, mk.UC_M68K_REG_A3):
        e.u.reg_write(r, 0xC0DE0000 + r)
    e.u.emu_start(SM.X_ID, 0x40084BE6, count=20000)
    sp = e.u.reg_read(mk.UC_M68K_REG_A7)
    st = [e.r32(sp + 4 * i) for i in range(7)]          # Name, d6, begin, end, buf, n (nach jsr (a4): begin, end, dst bleiben)
    n = st[5]
    good = (sp == sp0 - 24 and st[4] == BUF and e.r32(FRAME - 0x24) == BUF and e.r32(FRAME - 0x1C) == BUF + n
            and e.r32(FRAME - 0x60) == ALLOC and st[1] == FRAME - 44 and e.u.reg_read(mk.UC_M68K_REG_D7) == FRAME - 68
            and e.u.reg_read(mk.UC_M68K_REG_A4) == SM.X_COPY and e.u.reg_read(mk.UC_M68K_REG_A5) == SM.X_FMT
            and all(e.u.reg_read(r) == 0xC0DE0000 + r for r in (mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D3, mk.UC_M68K_REG_D4,
                                                                 mk.UC_M68K_REG_D5, mk.UC_M68K_REG_A2, mk.UC_M68K_REG_A3)))
    return bytes(e.u.mem_read(BUF, n)), n, e.cstr(st[0]), bytes(e.u.mem_read(BUF + n, 1)), good


ls, ns, nms, _, gs = ident(STOCK, None)
lc, nc, nmc, tc, gc = ident(IMG, 0)
chk('Kennung CYC = Firmware: %d Befehle, "%s", Stapel / Rahmen / Register' % (nc, nmc),
    (lc, nc, nmc) == (ls, ns, nms) and nms == 'Model Cycles' and gs and gc and tc == b'\xee')
raw2smp = {XMAP[i + 1]: XMAP[i] for i in range(0, len(XMAP) - 2, 2)}
want = bytearray()
for x in ls:
    want.append(raw2smp.get(x, x))
    if raw2smp.get(x) == 0x10: want.append(SM.X_EXTRA)
lm, nm_, nmm, tm, gm = ident(IMG, 1)
chk('Kennung SMP: %d Befehle (roh -> Sample-Familie, 0x13 hinter 0x10), "%s", Stapel / Rahmen / Register' % (nm_, nmm),
    lm == bytes(want) and nm_ == len(ls) + 1 == 35 and nmm == 'Model Samples' and gm and tm == b'\xee'
    and not any(x in lm for x in raw2smp) and all(x in lm for x in raw2smp.values()))
lm2 = ident(IMG, 1)[0]
chk('  zweimal SMP: gleiche Liste (SLIST wird neu gebaut, nicht verlaengert)', lm2 == lm)


def prod(mode):
    e = Emu(IMG); e.w32(S['TMODE'], mode)
    sp0 = STACK - 0x300; e.u.reg_write(mk.UC_M68K_REG_A7, sp0)
    e.u.emu_start(SM.X_PR, SM.X_PR_RET, count=1000)
    return e.u.reg_read(mk.UC_M68K_REG_D1), e.u.reg_read(mk.UC_M68K_REG_A7) - sp0
chk('Produkt: CYC %s, SMP %s, Stapel +40' % (prod(0), prod(1)), prod(0) == (27, 40) and prod(1) == (25, 40))

MSG = 0x4F04E000
e = Emu(IMG); bad = []
for mode in (0, 1):
    e.w32(S['TMODE'], mode)
    for t in range(256):
        e.u.mem_write(MSG, bytes(16)); e.w8(MSG + 8, t)
        d0, good = e.call(S['XRT'], MSG)
        w = XMAP[XMAP.index(t) + 1] if mode and t in XMAP[0:-2:2] else t
        if d0 != w or e.r8(MSG + 8) != w or not good: bad.append((mode, t, d0))
    e.w32(S['TMODE'], mode)
chk('Eingehend: CYC alles unveraendert, SMP Sample-Familie -> roh (auch in +8), Rest unveraendert %s' % bad[:3], not bad)
bad = []
for mode in (0, 1):
    e.w32(S['TMODE'], mode)
    for t in range(256):
        e.u.mem_write(MSG, bytes(16)); e.w8(MSG + 8, t)
        sp0 = STACK - 0x300; e.u.reg_write(mk.UC_M68K_REG_A7, sp0); e.u.reg_write(mk.UC_M68K_REG_A2, MSG)
        e.u.emu_start(SM.X_OT, SM.X_OT_RET, count=1000)
        d0 = e.u.reg_read(mk.UC_M68K_REG_D0)
        rawr = {r | 0x80: s_ | 0x80 for r, s_ in raw2smp.items()}
        w = rawr.get(t, t) if mode else t
        if d0 != w or e.u.reg_read(mk.UC_M68K_REG_A7) != sp0 + 32 or e.r8(MSG + 8) != t: bad.append((mode, t, d0))
chk('Ausgehend: CYC unveraendert, SMP roh | 0x80 -> Sample | 0x80, Stapel +32 %s' % bad[:3], not bad)

# ---------------- 5 Device Config
e = Emu(IMG); calls = []
def stub(name, ret=0):
    def f(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); calls.append((name, [e.r32(sp + 4 + 4 * i) for i in range(7)]))
        r = ret() if callable(ret) else ret
        u.reg_write(mk.UC_M68K_REG_D0, r)
        for rr in (mk.UC_M68K_REG_D1, mk.UC_M68K_REG_A0, mk.UC_M68K_REG_A1): u.reg_write(rr, 0xBADBAD00)
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    return f
heap = [0x4F040000]
def alloc():
    heap[0] += 0x100; return heap[0]
for va, nm, r in ((SM.X_ALLOC, 'alloc', alloc), (SM.X_ITEM, 'item', 0), (SM.X_ADD, 'add', 0), (SM.X_FREECL, 'free', 0),
                  (SM.X_REDRAW, 'redraw', 0), (SM.X_FMT, 'fmt', 0)):
    e.u.hook_add(UC_HOOK_CODE, stub(nm, r), begin=va, end=va)
MENU = 0x4F047000
sp0 = STACK - 0x300
regs = {r: 0xC0DE0000 + i for i, r in enumerate(KEEP)}
e.u.mem_write(sp0, bytes(0x60))
for i in range(10): e.w32(sp0 + 24 + 4 * i, 0x5A5A0000 + i)                         # movem.l 24(sp),d2-d6/a2-a6
for r, v in regs.items(): e.u.reg_write(r, v)
e.u.reg_write(mk.UC_M68K_REG_A2, MENU); e.u.reg_write(mk.UC_M68K_REG_A7, sp0)
for r, v in ((mk.UC_M68K_REG_D0, 0x11), (mk.UC_M68K_REG_D1, 0x22), (mk.UC_M68K_REG_A0, 0x33), (mk.UC_M68K_REG_A1, 0x44)): e.u.reg_write(r, v)
e.u.emu_start(S['XCFG'], SM.X_CFG_RET, count=20000)
it = [c for c in calls if c[0] == 'item']; ad = [c for c in calls if c[0] == 'add']
okr = (e.u.reg_read(mk.UC_M68K_REG_A7) == sp0 and [e.u.reg_read(r) for r in (mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D3, mk.UC_M68K_REG_D4,
       mk.UC_M68K_REG_D5, mk.UC_M68K_REG_D6, mk.UC_M68K_REG_A2, mk.UC_M68K_REG_A3, mk.UC_M68K_REG_A4, mk.UC_M68K_REG_A5,
       mk.UC_M68K_REG_A6)] == [0x5A5A0000 + i for i in range(10)]
       and [e.u.reg_read(r) for r in (mk.UC_M68K_REG_D0, mk.UC_M68K_REG_D1, mk.UC_M68K_REG_A0, mk.UC_M68K_REG_A1)] == [0x11, 0x22, 0x33, 0x44])
cl = []
if it:
    a = it[0][1]
    cl = [tuple(e.r32(a[i] + 4 * j) for j in range(4)) for i in range(1, 5)]
good5 = (len(it) == 1 and len(ad) == 1 and ad[0][1][0] == MENU and ad[0][1][1] == it[0][1][0] and it[0][1][5:7] == [0xFFFFFFFF, 8]
         and [c[2:] for c in cl] == [(SM.X_GEN, S['XLAB']), (SM.X_SLOT2, S['XPRS']), (SM.X_GEN, S['XVAL']), (SM.X_SLOT2, S['XROT'])]
         and e.r32(cl[1][0]) == MENU and e.r32(cl[3][0]) == MENU and len([c for c in calls if c[0] == 'free']) == 4
         and [c[1][0] for c in calls if c[0] == 'alloc'] == [1, 4, 1, 4, 0x54])
chk('Device Config: eine Zeile (4 Closures: Beschriftung, Druecken, Wert, Drehen; Menue in den Daten), 4x freigegeben, Register / Stapel', good5 and okr)
# Drehen
calls.clear(); res = []
CLO = 0x4F046000; e.w32(CLO, CLO + 0x10); e.w32(CLO + 0x10, MENU)
for d, wm in ((1, 1), (5, 1), (0, 1), (-1, 0), (-3, 0)):
    e.call(S['XROT'], CLO, 0, d); res.append(e.r32(S['TMODE']) == wm)
rd = [c[1][0] for c in calls if c[0] == 'redraw']
chk('Drehen: rechts SMP, links CYC, 0 nichts; Neuzeichnen der Menue-Ansicht (Menue + 0x38) %s' % [hex(x) for x in rd],
    all(res) and rd == [MENU + 0x38] * 4)
calls.clear(); e.u.reg_write(mk.UC_M68K_REG_A0, 0x4F045000); e.call(S['XLAB'], 0, 0)
f = [c for c in calls if c[0] == 'fmt']
chk('Beschriftung: "%s"' % (e.cstr(f[0][1][1]) if f else '?'), f and f[0][1][0] == 0x4F045000 and e.cstr(f[0][1][1]) == 'Transfer')
tn = [e.cstr(e.r32(S['TNAMES'] + 4 * i)) for i in range(2)]
chk('Wert-Namen %s, nach dem Start CYC' % tn, tn == ['CYC', 'SMP'] and Emu(IMG).r32(S['TMODE']) == 0)
done()

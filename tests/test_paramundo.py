# param-undo (v2, Patch 20; smp29: 3x so lang statt endlos): echter Takt der ParameterPageView (0x4001efaa).
import struct
from rig import *
import g2_paramundo as G

IMG = v2_image()
chk('Patch: 0x4001f760 jsr PUT (Maske), Firmware 6 Bytes ersetzt', IMG[G.HOOK - BASE:][:6] == C.jsr(G.M_PUT)
    and IMG[G.M_PUT - BASE:][:12] == G.put_code())
VIEW = 0x4F040000
def ticks(img, start, n):
    e = Emu(img); e.u.mem_write(VIEW, bytes(0x300)); e.w32(VIEW + 0x238, start & 0xffffffff); closed = []
    UIP = 0x4F041000; e.u.mem_write(UIP, bytes(0x200))
    def st(ret, rec=None):
        def f(u, a, z, _):
            sp = u.reg_read(mk.UC_M68K_REG_A7)
            if rec is not None: rec.append(1)
            u.reg_write(mk.UC_M68K_REG_D0, ret); u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        return f
    e.u.hook_add(UC_HOOK_CODE, st(UIP), begin=0x400CF9A8, end=0x400CF9A8)
    e.u.hook_add(UC_HOOK_CODE, st(1, closed), begin=0x4001EF0E, end=0x4001EF0E)
    ok_ = True
    for _ in range(n):
        _, g = e.call(0x4001EFAA, VIEW, count=200000); ok_ &= g
    return e.r32(VIEW + 0x238), len(closed), ok_
VIEW0 = 0x4F040000
e = Emu(IMG); e.u.mem_write(VIEW0, bytes(0x300)); e.u.reg_write(mk.UC_M68K_REG_A2, VIEW0)
e.u.reg_write(mk.UC_M68K_REG_A7, STACK - 0x100); e.u.emu_start(G.HOOK, G.HOOK + 6, count=100)
set_ = e.r32(VIEW0 + 0x238); a2ok = e.u.reg_read(mk.UC_M68K_REG_A2) == VIEW0 and e.u.reg_read(mk.UC_M68K_REG_A7) == STACK - 0x100
r1 = ticks(IMG, set_, 179); r2 = ticks(IMG, set_, 181); r3 = ticks(STOCK, 60, 61)
chk('Drehen setzt %d Takte (Firmware 60), a2 / Stapel erhalten; offen nach 179 Takten %s, zu nach 180 %s (Stock 60: %s)'
    % (set_, r1, r2, r3), set_ == 180 and a2ok and r1[1] == 0 and r1[0] == 1 and r2[1] == 1 and r3[1] == 1 and r1[2] and r2[2])
done()

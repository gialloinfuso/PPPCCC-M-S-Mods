# browser-keys (v2, Patch 19, smp24): im Browser oeffnet RETRIG das Speicher-Menue statt FUNC. Echter Tasten-Handler des
# Browsers 0x400a6d5c bis zur Verzweigung (Menue-Weg 0x400a6da2 / Grundklasse 0x400a7120), Stock gegen v2.
import struct
from rig import *
import g2_browserkeys as G

IMG = v2_image()
ALONE = v2_image(['browser-keys'], latch=False)
EV, BRW = 0x4F043200, 0x4F043400


def route(img, code, bits):
    e = Emu(img); e.u.mem_write(BRW, bytes(0x400))
    e.w32(EV + 0x0C, code); e.w32(EV + 0x10, bits)
    hit = []
    for x in (G.BR_MENU, G.BR_DEFAULT, 0x400A70EE, 0x400A6F38, 0x400A6F02):
        e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (hit.append(a), u.emu_stop()), begin=x, end=x)
    sp = STACK - 0x100
    e.u.mem_write(sp, struct.pack('>III', RET, BRW, EV)); e.u.reg_write(mk.UC_M68K_REG_A7, sp)
    e.u.emu_start(0x400A6D5C, RET, count=2000)
    return hit[0] if hit else None


chk('smp40: Hinweis unten rechts: pea auf eigenen Text %r (Firmware: %r)' % (bytes(IMG[V2SYM['browser-keys']['BK_HINT'] - BASE:][:8]),
    bytes(STOCK[G.HINT_FW - BASE:][:8])), IMG[G.HINT_REF - 2 - BASE:][:6] == b'\x48\x79' + struct.pack('>I', V2SYM['browser-keys']['BK_HINT'])
    and IMG[V2SYM['browser-keys']['BK_HINT'] - BASE:][:8] == b'RT=MENU\0' and STOCK[G.HINT_REF - 2 - BASE:][:6] == b'\x48\x79' + struct.pack('>I', G.HINT_FW))
chk('Haken 0x400a6d80 = jmp BRK ; nop', IMG[G.BRK_HOOK - BASE:][:8] == C.jmp(V2SYM['browser-keys']['BRK']) + b'\x4e\x71')
bad = []
for img in (IMG, ALONE):
    for code in range(0, 34):
        for bits in (1, 0, 16, 1 | 8, 2, 0 | 2):
            s, m = route(STOCK, code, bits), route(img, code, bits)
            want = G.BR_MENU if code == 4 else G.BR_DEFAULT if code == 1 else s
            if code == 4: s_ok = s == G.BR_DEFAULT
            else: s_ok = True
            if m != want or not s_ok: bad.append((code, bits, hex(s or 0), hex(m or 0)))
chk('Browser: RETRIG -> Menue-Weg (vorher Grundklasse), FUNC -> Grundklasse (vorher Menue-Weg), alle anderen Tasten wie Stock %s'
    % bad[:4], not bad and route(STOCK, 1, 16) == G.BR_MENU)
done()

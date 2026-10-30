# Knopf-LEDs im Filter-Modus (Patch 13, FLED): Haken 0x40021e0e im Frame der PatternGridView. Geprueft mit der echten
# LED-Funktion 0x40005f86 (Anspruchs-Tabelle Steuerung +0x28 + 4 * LED, erster Anspruch gilt) und der echten Knopf-LED-Schleife
# der Firmware (0x400220ac..0x400220f0, bei gehaltenem Trig), Stock-Image als Vergleich.
# Aufruf: test_filterleds.py [--alone]   (--alone: nur Core + track-filter)
import struct, sys
from rig import *
import g2_trackfilter as TF

ALONE = '--alone' in sys.argv
IMG = v2_image(['core', 'track-filter'], latch=False) if ALONE else v2_image()
REF = apply(STOCK, LATCH)
CTL = 0x4F048000                          # LED-Steuerung (Anspruchs-Tabelle ab +0x28)
VEC = 0x4F049000                          # Knopf-LED-Vektor (wie zur Laufzeit aus 0x400fbc90 gebaut)
FREE = 0x400CFC5E                         # Vektor-Freigabe (Argument auf dem Stapel)
KNOBS = list(struct.unpack('>12I', STOCK[0x400FBC90 - BASE:0x400FBC90 - BASE + 48]))
chk('Knopf-LED-Tabelle der Firmware = LED 36..47', KNOBS == list(range(36, 48)))


def emu(img, mode):
    e = Emu(img)
    e.u.mem_write(CTL, bytes(0x2000))                        # liegt im Rig-Bereich 0x4F020000..
    e.u.mem_write(VEC, struct.pack('>12I', *KNOBS))
    e.w32(TF.LED_VEC, VEC); e.w32(TF.LED_VEC + 4, VEC + 48)
    if mode: e.w32(TF.MODE, TF.MAGIC)
    e.freed = []
    def free(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); e.freed.append(e.r32(sp + 4))
        for r in (mk.UC_M68K_REG_D0, mk.UC_M68K_REG_D1, mk.UC_M68K_REG_A0, mk.UC_M68K_REG_A1): u.reg_write(r, 0xBADBAD00)
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    e.u.hook_add(UC_HOOK_CODE, free, begin=FREE, end=FREE)
    return e


def claims(e): return {led: e.r32(CTL + 0x28 + 4 * led) for led in range(64) if e.r32(CTL + 0x28 + 4 * led)}


def frame_start(img, mode):
    """Frame-Stelle 0x40021e0e (jsr Vektor-Freigabe, Argument d6 auf dem Stapel) bis 0x40021e14."""
    e = emu(img, mode); sp = STACK - 0x200
    e.u.mem_write(sp, struct.pack('>I', 0xD6D6D6D6) + bytes(0x80))
    e.u.reg_write(mk.UC_M68K_REG_A7, sp)
    for i, r in enumerate(KEEP): e.u.reg_write(r, 0xC0DE0000 + i)
    e.u.reg_write(mk.UC_M68K_REG_D2, CTL)
    e.u.emu_start(0x40021E0E, 0x40021E14, count=20000)
    good = (e.u.reg_read(mk.UC_M68K_REG_PC) == 0x40021E14 and e.u.reg_read(mk.UC_M68K_REG_A7) == sp
            and e.r32(sp) == 0xD6D6D6D6 and e.u.reg_read(mk.UC_M68K_REG_D2) == CTL
            and all(e.u.reg_read(r) == 0xC0DE0000 + i for i, r in enumerate(KEEP) if r != mk.UC_M68K_REG_D2))
    return e, good


def knob_loop(e, mask):
    """Knopf-LED-Schleife der Firmware bei gehaltenem Trig: Maske in 40(sp), d7 = 0, a5 = LED-Funktion, d2 = Steuerung."""
    sp = STACK - 0x400
    e.u.mem_write(sp, bytes(0x40) + struct.pack('>I', mask) + bytes(0x40))
    e.u.reg_write(mk.UC_M68K_REG_A7, sp); e.u.reg_write(mk.UC_M68K_REG_D7, 0)
    e.u.reg_write(mk.UC_M68K_REG_A5, TF.LED_SET); e.u.reg_write(mk.UC_M68K_REG_D2, CTL)
    e.u.emu_start(0x400220AC, 0x400220F0, count=20000)
    return e.u.reg_read(mk.UC_M68K_REG_A7) == sp


ON = {36: 2, 37: 2, 38: 2, 39: 2}
for mode in (0, 1):
    e1, g1 = frame_start(IMG, mode); e0, g0 = frame_start(REF, mode)
    nm = 'Filter-Modus an' if mode else 'Filter-Modus aus'
    chk(f'{nm}: Register, Stapel, Ruecksprung ok (Stock {g0}, neu {g1})', g0 and g1)
    chk(f'{nm}: Vektor-Freigabe wie Stock mit demselben Argument {e1.freed}', e1.freed == e0.freed == [0xD6D6D6D6])
    chk(f'{nm}: Stock beansprucht hier keine LED', claims(e0) == {})
    chk(f'{nm}: LEDs {claims(e1)}', claims(e1) == (ON if mode else {}))
    for mask in (0, 0x5A5, 0xFFF):                               # gehaltener Trig mit p-locks danach im selben Frame
        f1, _ = frame_start(IMG, mode); f0, _ = frame_start(REF, mode)
        s1, s0 = knob_loop(f1, mask), knob_loop(f0, mask)
        exp = {36 + i: (2 if mask >> i & 1 else 1) for i in range(12)}
        if mode: exp.update(ON)
        chk(f'{nm}, Trig gehalten, p-lock-Maske {mask:#05x}: Knopf-LEDs {"".join(str(claims(f1)[36 + i]) for i in range(12))}',
            s1 and s0 and claims(f0) == {36 + i: (2 if mask >> i & 1 else 1) for i in range(12)} and claims(f1) == exp)

# Ohne Filter-Modus ist der Frame bitgleich zum Stock (bis auf den Sprung in FLED und zurueck)
chk('Haken-Stelle: jmp FLED', bytes(IMG[TF.LED_HOOK - BASE:TF.LED_HOOK - BASE + 2]) == b'\x4e\xf9')
done()

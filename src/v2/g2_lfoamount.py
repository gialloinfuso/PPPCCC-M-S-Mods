#!/usr/bin/env python3
"""Mod 'lfo-amount' (v2, Patch 14): eigener Parameter LFO Amount (0..127) hinter der LFO-Depth. Braucht den Core.

Idee (Pip 28.10.2026): Depth ist der groesste Ausschlag des LFO (bipolar); Amount sagt, wie stark Depth wirkt: 0 = der LFO
  wirkt gar nicht, 127 = Depth wirkt voll (Default, wie ohne die Mod). Amount aendert die LFO-Einstellungen selbst nicht.
  Amount ist ein echter Parameter (k 32, Deskriptor 5): p-lockbar, LFO- und Velocity-Ziel (der LFO kann seinen eigenen
  Amount modulieren), mit dem Sound gespeichert.
Bedienung: RETRIG halten + LFO-SPEED-Knopf drehen = Amount der Spur (Popup der Firmware). Ohne RETRIG bleibt der Knopf
  LFO Speed.
Firmware 1.13:
  LFO der Spuren: 0x40091ab2(obj, Tempo, Maske), Aufruf 0x400597c6 in der Audiofunktion; obj = geglaettete Worte (Track t:
    obj + 14 + 66 t + 2 k), Depth = k 8, Mitte 0x4000 (Modded-Cycles notes/56, MIT). Haken: jsr AMT. AMT setzt vor dem Aufruf
    Depth' = 0x4000 + (Depth - 0x4000) * Amount / 0x7f00 (nur wenn Amount < 127), ruft den LFO, setzt Depth zurueck und
    merkt sich Amount (nach dem LFO, also mit seiner Modulation) fuer den naechsten Block (1 Block = 0.67 ms Verzoegerung).
  Knopf -> Deskriptor: Prolog von 0x4001e814 (Vtable-Slot 124 der ParameterPageView) -> jmp W (Prolog aus dem Image
    nachgespielt), POST: Knopf 10 (LFO SPEED, Maschinen-Tabelle Eintrag 8 = Deskriptor 29) und HELD(4) (RETRIG) -> 5.
  Sound: Core-Sound-Slot AH, Satz +84 = (Amount >> 8) XOR 127 (Null = 127: alte Sounds unveraendert). p-locks k 32 und
    LFO-/Velocity-Ziel k 32: Core.
Speicher: Masken 0x4014a890 (W, POST), 0x401592bc (AMT), 0x4014aa34 (AH, Namen, RAM: Depth-Sicherung, Amount pro Track).
Aufruf: g2_lfoamount.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
from cfasm import asm, done as adone

M_A1, M_A2, M_A3 = 0x4014A890, 0x401592BC, 0x4014AA34
SIZE = {M_A1: 108, M_A2: 192, M_A3: 108}
LOOKUP, LOOKUP_CK, LOOKUP_CONT = 0x4001E814, (6, 'b806f010f13616a431043cb7fbc959a028b2fda3c89c9b829d70d30c346b9224'), 0x4001E81A
LFO_HOOK, LFO_FN = 0x400597C6, 0x40091AB2
ENC_LFO, KEY_RETRIG = 10, 4
D_AMT, K_AMT, K_DEP = 5, 32, 8
REC, FMT_INT = 0x40A71754, 0x400456C8
S_LFO = 0x40126725                    # Gruppenname "LFO" (wie die LFO-Deskriptoren)
TOP = 0x7F00


def build_a2(st):
    a = A(M_A2)
    asm(a, f'''
    ; ---------------- AMT: statt jsr LFO (obj, Tempo, Maske); Depth je Track mit Amount skalieren, LFO, Depth zurueck
    AMT:    lea     -16(sp),sp
            movem.l d2-d3/a2-a3,(sp)
            movea.l 20(sp),a2
            lea     14(a2),a2                ; a2 = obj + 14 ; a3 = Sicherung
            lea     {st:#x},a3
            moveq   #5,d2
            move.l  #{TOP:#x},d3
    pre:    move.w  {2 * K_DEP}(a2),(a3)     ; Depth sichern
            mvz.w   12(a3),d1                ; d1 = Amount (vom letzten Block)
            eori.l  #{TOP:#x},d1
            cmp.l   d3,d1
            bcc     sk
            mvs.w   {2 * K_DEP}(a2),d0
            subi.l  #0x4000,d0
            muls.l  d1,d0
            divs.l  d3,d0
            addi.l  #0x4000,d0
            move.w  d0,{2 * K_DEP}(a2)       ; Depth' = Mitte + (Depth - Mitte) Amount / 127
    sk:     lea     66(a2),a2
            addq.l  #2,a3
            subq.l  #1,d2
            bpl     pre
            move.l  28(sp),-(sp)
            move.l  28(sp),-(sp)
            move.l  28(sp),-(sp)
            jsr     {LFO_FN:#x}
            lea     12(sp),sp
            movea.l 20(sp),a2
            lea     14(a2),a2
            lea     {st:#x},a3
            moveq   #5,d2
    po:     move.w  (a3),{2 * K_DEP}(a2)     ; Depth zurueck
            mvz.w   {2 * K_AMT}(a2),d1       ; Amount (mit LFO-Modulation) merken, XOR 0x7f00
            eori.l  #{TOP:#x},d1
            move.w  d1,12(a3)
            lea     66(a2),a2
            addq.l  #2,a3
            subq.l  #1,d2
            bpl     po
            movem.l (sp),d2-d3/a2-a3
            lea     16(sp),sp
            rts
    ''')
    code = adone(a)
    check_cf(code, M_A2)
    return code, a.lab


def build_a3():
    a = A(M_A3)
    asm(a, f'''
    ; ---------------- AH: Sound-Slot (a0 Satz, a1 Sound, d1 = 0 Laden / 1 Speichern)
    AH:     tst.l   d1
            bne     sv
            mvz.b   84(a0),d0                ; Laden: Amount = (Byte ^ 127) << 8
            eori.l  #127,d0
            lsl.l   #8,d0
            move.w  d0,{20 + 2 * K_AMT}(a1)
            rts
    sv:     mvz.b   {20 + 2 * K_AMT}(a1),d0  ; Speichern: Byte = (Amount >> 8) ^ 127
            eori.l  #127,d0
            move.b  d0,84(a0)
            rts
    ''')
    code = bytearray(adone(a))
    check_cf(bytes(code), M_A3)
    while len(code) % 4: code += b'\0'
    st = M_A3 + len(code); code += bytes(24)                              # 6 Depth-Worte, 6 Amount-Worte (XOR 0x7f00)
    names = {}
    for n, s_ in (('S_AMT', 'LFO Amount'), ('S_AMTS', 'LAMT')):
        names[n] = M_A3 + len(code); code += s_.encode() + b'\0'
    return bytes(code), dict(a.lab, ST=st, **names)


def build_a1():
    a = A(M_A1)
    asm(a, f'''
    ; smp12: der Haken der Knopf-Suche (0x4001e814) gehoert jetzt dem Core (Attack); POST meldet sich in LKSLOT an
    ; ---------------- POST: d0 = Deskriptor der Firmware; LFO SPEED + RETRIG -> Amount
    POST:   move.l  4(sp),d1
            cmpi.l  #{ENC_LFO},d1
            bne     out
            move.l  d0,-(sp)
            pea     {KEY_RETRIG}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            move.l  d0,d1
            move.l  (sp)+,d0
            tst.l   d1
            beq     out
            move.l  #{FMT_INT:#x},d1         ; UI-Objekt 5
            move.l  d1,{REC + 100 * D_AMT + 0x20:#x}
            clr.l   {REC + 100 * D_AMT + 0x2C:#x}
            moveq   #{D_AMT},d0
    out:    lea     16(sp),sp
            rts
    ''')
    code = bytearray(adone(a))
    check_cf(bytes(code), M_A1)
    return bytes(code), a.lab


def build():
    c3, l3 = build_a3(); c1, l1 = build_a1(); c2, l2 = build_a2(l3['ST'])
    return {M_A1: c1, M_A2: c2, M_A3: c3}, dict(l1, **l2, **l3)


def desc_row(lab):
    return struct.pack('>14I', 7, K_AMT, 0, TOP, TOP, 0, 0xFFFFFFFF, 0xFFFFFFFF, 0, 0x600, 76, lab['S_AMT'], S_LFO, lab['S_AMTS'])


def tweak(img):
    base = apply(img, core.tweak(img))
    parts, lab = build()
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    core.lkslot_write(W, lab['POST'])
    W.hook(LFO_HOOK, jsr(LFO_FN), jsr(lab['AMT']))
    assert struct.unpack_from('>i', base, C.DESC(D_AMT) - BASE)[0] == -1, "Deskriptor 5 nicht frei"
    W.put(C.DESC(D_AMT), desc_row(lab))
    core.sslot_write(W, 'lfo-amount', lab['AH'])
    return patch('lfo-amount', 14, 'LFO amount',
                 ["New parameter LFO Amount (0..127) after LFO depth: 0 = the LFO has no effect, 127 = depth works fully (default).",
                  "Hold RETRIG and turn the LFO SPEED knob = LFO Amount of the track. p-locks, LFO and velocity target, saved with the sound.",
                  "Erzeugt von v2/g2_lfoamount.py."], W,
                 requires=['core'], hooks=[f"{x:#x}" for x in (LFO_HOOK,)],
                 memory=[{"va": f"{lab['ST']:#x}", "size": 24, "ram": True, "use": "depth backup + amount per track"}],
                 symbols={k: f"{lab[k]:#x}" for k in ('POST', 'AMT', 'AH', 'ST')},
                 params={"enc_lfo": ENC_LFO, "key_retrig": KEY_RETRIG, "desc": D_AMT, "k": K_AMT, "rec_byte": 84})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k.isupper()})

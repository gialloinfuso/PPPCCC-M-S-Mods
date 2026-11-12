"""Teil des Cores (smp18): Deskriptor-Tabelle der Firmware in die Nutzlast verlegt und auf C.NDESC Eintraege erweitert, damit
neue Maschinen eigene Knoepfe (Name, Bereich, Default, Anzeige) und Extra-Parameter bekommen.

Vorbild und Bestandsliste: Modded-Cycles notes/18 und 19 (MIT), dort auf der Hardware getestet; der Code hier ist eigener Code.
  - BOOT (Core) ruft nach der Kopie der Nutzlast DTINIT: die 76 Eintraege der Firmware (mit den Aenderungen der Mods im Image)
    nach DTAB, freie Eintraege der Erweiterung (Name 0) = Kopie von Eintrag 0 ('Error').
  - 34 + 1 + 2 Verweise auf die Tabelle (+0, +8, +0x20) -> DTAB; 42 Grenzen 'moveq #76 / #75' in den Zugriffen -> NDESC / NDESC-1.
  - Anzeige-Zustand (76 Objekte zu 100 B, 0x40a71754): ST_AT / ST_CN (0x4004df40 / 0x4004dfa2) bilden 76.. auf DONOR ab.
  - Maschine eines Deskriptors 0x4005a50a -> DMACH (MACHMAP, sonst Feld 0); Zeilen-Konstruktor 0x4005a340 -> BROW (Feld <= 6
    = Maschinen-Parameter, Zeile aus MACHMAP). Damit tragen Maschinen ab 7 das Feld 6 ('eine Maschine'), wie bei Modded-Cycles.
  - Knopf-Suche: LKP2 (Core) -> LKX: FUNC + Knopf auf einer Maschine laut LKXT -> eigener Deskriptor, dann LKSLOT wie bisher.
  - RBUILD(Ziel, Spender-Satz n, erster alter, erster neuer Deskriptor): Maschinen-Satz aus dem eines Spenders, 4 Knoepfe
    umgelegt (Texte ueber den Kopier-Konstruktor der Firmware, wie der Sampler)."""
import collections, struct
from common import *                 # noqa: F401,F403
import common as C
from cfasm import asm, done as adone

DESC0, DSTRIDE = 0x4010DCE0, 0x38
OBJ_BASE, OBJ_CN, OBJ_TMP, OBJ_FN = 0x40A71754, 0x40A71768, 0x40A71500, 0x400DDF60
REC_BASE, STRCOPY = 0x40A71540, 0x400F8F02
MACHOF = 0x4001E318                  # (Ansicht, -1) -> Maschine der Spur (Knopf-Suche)
# Grenzen 'moveq #76' / 'moveq #75' in den Funktionen, die die Tabelle lesen (Modded-Cycles gen_sdvintage_7th.BOUNDS ohne
# 0x4005a50a, der hier ganz umgeleitet wird; dort auch: 0x4004df68 / 0x4004df82 sind KEINE Grenzen, 76 B = Maschinen-Satz)
BOUNDS = (
    0x4000a93e, 0x4000a95e, 0x4000a984, 0x4000aa52, 0x4000b208, 0x4000b22a, 0x4000b3e4, 0x4000b476,
    0x4000b51a, 0x4000b65a, 0x4000b6ec, 0x4000b788, 0x4000b946, 0x4001d5e2, 0x4001d8ee, 0x4001d90e,
    0x4001e026, 0x4001f326, 0x40022a7c, 0x40022afe, 0x40029e78, 0x40029e98, 0x4002b430, 0x40046d5c,
    0x4004e31e, 0x4004e3ba, 0x4005a368, 0x4005a4e8, 0x4005a52c, 0x4005a556, 0x4005a582,
    0x4005a5cc, 0x4005a5fe, 0x4005a628, 0x4005a65c, 0x4005a76a, 0x4005a7aa, 0x4005a7d0, 0x4005a7f8,
    0x4005a81a, 0x4005a83c, 0x4005a85e,
)
NREF = {DESC0: 34, DESC0 + 8: 1, DESC0 + 0x20: 2}
HOOKS = {   # Stelle: (Laenge + SHA-256 der Originalbefehle, Label) -> jmp Label
    0x4004DF40: ((6, '9bcec80e6e10e813b1a9ab2ab5891b81fe56b6fdc1c03e765febc3f6f8f23a86'), 'ST_AT'),
    0x4004DFA2: ((6, '9bcec80e6e10e813b1a9ab2ab5891b81fe56b6fdc1c03e765febc3f6f8f23a86'), 'ST_CN'),
    0x4005A50A: ((6, 'c11396a3098d0b3d76124f292cfc985dfc89241745192cc098dce841a037dff2'), 'DMACH'),
    0x4005A340: ((6, '0c1831464988ef1e4ac8e03f34c0536dc527e3c41bfa3e127c3c5f763e9e7e21'), 'BROW'),
    0x40005F86: ((8, 'd43e64e0210fdd98e9dd8476d7cea57c93492ec611d50eddcbf6fd90ea80cef7'), 'LEDF'),   # smp27: LED_SET
    0x4001D8A8: ((6, '8c2739581033efd0cdf979173d1be16b0419827c5d393d65811585e1f8130571'), 'PFONT'),  # smp32: Schrift des Popup-Werts
    0x4005A6D0: ((10, 'dbe8cd680b65aba085b6231e533d89fdee52f813a9a201f14f061aec7b770dfa'), 'PSX'),   # smp37: Parameter-Suche (vorher strum)
}
NX = C.NDESC - C.NDESC0


def sty_text():
    """smp30: d0 = STYX-Eintrag 1.. -> STYLES[d0 - 1] ins Objekt (a1) +0x10"""
    return ''.join(f'''            subq.l  #1,d0
            bne     fy{n}
            move.l  #{st:#x},d0
            move.l  d0,0x10(a1)
            bra     fx2
    fy{n}:
''' for n, st in enumerate(C.STYLES))


def code_text():
    return f'''
    ; ---------------- Start: Tabelle kopieren (vor der BSS-Loeschung, Cache aus); freie Eintraege = 'Error'
    DTINIT: lea     {DESC0:#x},a0
            lea     {C.DTAB:#x},a1
            move.l  #{C.NDESC0 * DSTRIDE // 4 - 1},d0
    di1:    move.l  (a0)+,(a1)+
            subq.l  #1,d0
            bpl     di1
            lea     {C.DTD(C.NDESC0):#x},a1
            moveq   #{NX - 1},d1
    di2:    tst.l   0x2c(a1)
            bne     di4
            lea     {C.DTAB:#x},a0
            moveq   #{DSTRIDE // 4 - 1},d0
    di3:    move.l  (a0)+,(a1)+
            subq.l  #1,d0
            bpl     di3
            bra     di5
    di4:    lea     {DSTRIDE}(a1),a1
    di5:    subq.l  #1,d1
            bpl     di2
            rts
    ; d0 = Deskriptor -> d0 = Index des Anzeige-Objekts (76.. ueber DONOR, ausserhalb 0); zerstoert a0
    MAPK:   cmpi.l  #{C.NDESC0},d0
            bcs     mk9
            cmpi.l  #{C.NDESC},d0
            bcs     mk1
            moveq   #0,d0
            rts
    mk1:    lea     {C.DONOR - C.NDESC0:#x},a0
            mvz.b   0(a0,d0.l),d0
    mk9:    rts
    ; 0x4004df40: Zeiger auf das Anzeige-Objekt des Deskriptors
    ST_AT:  move.l  4(sp),d0
            jsr     MAPK
            moveq   #100,d1
            muls.l  d1,d0
            addi.l  #{OBJ_BASE:#x},d0
            move.l  4(sp),d1
            jsr     FXSET
            rts
    ; smp23: d0 = Anzeige-Objekt, d1 = Deskriptor: eigener Formatierer laut FMTX (76..) ins Objekt (+0x20, +0x2c = 0); d0 bleibt
    FXSET:  subi.l  #{C.NDESC0},d1
            cmpi.l  #{NX - 1},d1
            bhi     fx9
            movea.l d0,a1                    ; Objekt
            lea     {C.STYX:#x},a0           ; smp30: Darstellung (Schrift) des Werts laut STYX
            mvz.b   0(a0,d1.l),d0
            andi.l  #0x7f,d0                 ; Bit 7 = Schrift des Popups (PFONT)
            beq     fx2
{sty_text()}    fx2:    lea     {C.FMTX:#x},a0
            move.l  0(a0,d1.l*4),d1
            beq     fx8
            move.l  d1,0x20(a1)
            clr.l   0x2c(a1)
    fx8:    move.l  a1,d0
    fx9:    rts
    ; smp37 PSX: Parameter-Suche 0x4005a6a6, allgemeiner Parameter (a2 = k, d2 = Maschine; statt lea Tabelle,a0 ; move.l (a0,k*4),d0):
    ; Eintrag (Maschine, k) in PSXT -> eigener Deskriptor, sonst die Tabelle der Firmware (vorher Haken PS von strum)
    PSX:    lea     {C.PSXT:#x},a0
            moveq   #{C.NPSX - 1},d1
    px1:    mvz.b   (a0),d0
            cmp.l   d2,d0
            bne     px2
            mvz.b   1(a0),d0
            cmp.l   a2,d0
            bne     px2
            mvz.w   2(a0),d0
            jmp     0x4005A6FC
    px2:    addq.l  #4,a0
            subq.l  #1,d1
            bpl     px1
            lea     0x40A79394,a0
            move.l  0(a0,a2.l*4),d0
            jmp     0x4005A6FC
    ; smp32 PFONT (0x4001d8a8 im Popup-Zeichnen 0x4001d818, statt 'pea 0x401429ec'; d2 = Deskriptor): STYX Bit 7 -> schmale
    ; grosse Schrift (5 Zeichen passen statt 3), sonst die der Firmware
    PFONT:  move.l  d2,d0
            subi.l  #{C.NDESC0},d0
            cmpi.l  #{NX - 1},d0
            bhi     pq1
            lea     {C.STYX:#x},a0
            mvz.b   0(a0,d0.l),d0
            btst    #7,d0
            beq     pq1
            pea     {C.FONT_NARROW:#x}
            jmp     0x4001D8AE
    pq1:    pea     {C.FONT_BIG:#x}
            jmp     0x4001D8AE
    ; smp23 (aus g2_core verlegt, Platz): Sound-Slot 3: Satz +86 = Attack >> 8; smp23 auch +80 / +81 = k 24 / 27 (k 23 Attack des Cores; Monom Glide / Noise, CHORD / Vlvt Strum-Abstand /
    ; -Pattern; vorher Sound-Slot 4 von mono) (a0 Satz, a1 Sound, d1 = 0 Laden / 1 Speichern)
    ATH:    tst.l   d1
            bne     ah1
            mvz.b   86(a0),d0
            lsl.l   #8,d0
            move.w  d0,{20 + 2 * C.K_EXT0}(a1)
            mvz.b   80(a0),d0
            lsl.l   #8,d0
            move.w  d0,{20 + 2 * C.K_STIME}(a1)
            mvz.b   81(a0),d0
            lsl.l   #8,d0
            move.w  d0,{20 + 2 * C.K_SPAT}(a1)
            rts
    ah1:    move.b  {20 + 2 * C.K_EXT0}(a1),d0
            move.b  d0,86(a0)
            move.b  {20 + 2 * C.K_STIME}(a1),d0
            move.b  d0,80(a0)
            move.b  {20 + 2 * C.K_SPAT}(a1),d0
            move.b  d0,81(a0)
            rts
    ; 0x4004dfa2: wie die Firmware, mit dem Objekt aus MAPK
    ST_CN:  move.l  4(sp),d0
            jsr     MAPK
            moveq   #100,d1
            muls.l  d1,d0
            addi.l  #{OBJ_BASE:#x},d0
            move.l  4(sp),d1
            jsr     FXSET
            addi.l  #{OBJ_CN - OBJ_BASE},d0
            pea     {OBJ_TMP:#x}
            move.l  12(sp),-(sp)
            move.l  d0,-(sp)
            jsr     {OBJ_FN:#x}
            lea     12(sp),sp
            move.l  #{OBJ_TMP:#x},d0
            rts
    ; 0x4005a50a: Maschine des Deskriptors (fuer die Anwendbarkeit 0x4000aa9a)
    DMACH:  move.l  4(sp),d0
            cmpi.l  #{C.NDESC},d0
            bcs     dm1
            moveq   #0,d0
    dm1:    cmpi.l  #{C.NDESC0},d0
            bcs     dm2
            lea     {C.MACHMAP - C.NDESC0:#x},a0
            mvz.b   0(a0,d0.l),d1
            cmpi.l  #0xff,d1
            beq     dm2
            move.l  d1,d0
            rts
    dm2:    move.l  d0,d1
            lsl.l   #3,d1
            lsl.l   #6,d0
            sub.l   d1,d0
            lea     {C.DTAB:#x},a0
            move.l  0(a0,d0.l),d0
            rts
    ; 0x4005a340 (Zeilen-Konstruktor, d5 = Feld, d2 = Deskriptor): Feld <= 6 = eine Maschine, Zeile aus MACHMAP
    BROW:   moveq   #6,d0
            cmp.l   d5,d0
            bcs     br1
            cmpi.l  #{C.NDESC0},d2
            bcs     br0
            lea     {C.MACHMAP - C.NDESC0:#x},a0
            mvz.b   0(a0,d2.l),d0
            cmpi.l  #0xff,d0
            beq     br0
            move.l  d0,d5
    br0:    jmp     0x4005A384
    br1:    jmp     0x4005A346
    ; Knopf-Suche, nach dem Attack des Cores (Stapel: Ansicht, Knopf, FUNC, -1; d0 = Deskriptor): FUNC + Knopf auf der
    ; Maschine laut LKXT -> eigener Deskriptor; dann wie bisher LKSLOT (lfo-amount) bzw. Ende
    LKX:    tst.l   8(sp)
            beq     lx9
            lea     {C.LKXT:#x},a0           ; erst: gibt es einen Eintrag fuer diesen Knopf? (sonst keine Maschinen-Abfrage)
    lx0:    mvz.b   1(a0),d1
            cmp.l   4(sp),d1
            bne     lx3
            mvz.b   (a0),d1
            cmpi.l  #0xff,d1
            bne     lx4
    lx3:    addq.l  #4,a0
            cmpa.l  #{C.LKXT + 4 * C.NLKX:#x},a0
            bne     lx0
            bra     lx9
    lx4:    move.l  d2,-(sp)
            move.l  d0,-(sp)
            move.l  20(sp),-(sp)             ; -1
            move.l  12(sp),-(sp)             ; Ansicht
            jsr     {MACHOF:#x}
            addq.l  #8,sp
            move.l  d0,d1                    ; Maschine der Spur
            move.l  (sp)+,d0
            lea     {C.LKXT:#x},a0
    lx1:    mvz.b   (a0),d2
            cmp.l   d1,d2
            bne     lx2
            mvz.b   1(a0),d2
            cmp.l   8(sp),d2
            bne     lx2
            mvz.w   2(a0),d0
    lx2:    addq.l  #4,a0
            cmpa.l  #{C.LKXT + 4 * C.NLKX:#x},a0
            bne     lx1
            move.l  (sp)+,d2
    lx9:    move.l  {{LKSLOT}},d1
            beq     lxr
            movea.l d1,a0
            jmp     (a0)
    lxr:    lea     16(sp),sp
            rts
    ; RBUILD(Ziel, n, alt, neu): Satz des Spenders n (REC_BASE + 76 n) -> Ziel (76 B + 1 Byte 'gebaut'), Deskriptoren
    ; alt..alt+3 -> neu..neu+3; Texte ueber den Kopier-Konstruktor (Referenzzaehler). d0 = Ziel. C-Aufruf.
    RBUILD: movea.l 4(sp),a0
            tst.b   76(a0)
            bne     rb9
            lea     -12(sp),sp
            movem.l d2/a2-a3,(sp)
            movea.l 16(sp),a2                ; Ziel
            move.l  20(sp),d0
            moveq   #76,d1
            mulu.l  d1,d0
            addi.l  #{REC_BASE:#x},d0
            movea.l d0,a3                    ; Spender
            move.l  a3,-(sp)
            move.l  a2,-(sp)
            jsr     {STRCOPY:#x}
            addq.l  #8,sp
            pea     4(a3)
            pea     4(a2)
            jsr     {STRCOPY:#x}
            addq.l  #8,sp
            moveq   #0,d2
    rb1:    move.l  8(a3,d2.l*4),d0
            move.l  d0,d1
            sub.l   24(sp),d1
            cmpi.l  #3,d1
            bhi     rb2
            add.l   28(sp),d1
            move.l  d1,d0
    rb2:    move.l  d0,8(a2,d2.l*4)
            addq.l  #1,d2
            moveq   #17,d0
            cmp.l   d0,d2
            bne     rb1
            moveq   #1,d0
            move.b  d0,76(a2)
            movem.l (sp),d2/a2-a3
            lea     12(sp),sp
            movea.l 4(sp),a0
    rb9:    move.l  a0,d0
            rts
    ; smp27 LEDF: Anfang von LED_SET(ctx, LED, Zustand, Tabelle): LED-Filter der Mods (LSLOTS, Handler d0 = LED, d1 = Zustand
    ; -> d1), dann die Firmware (Prolog nachgespielt). LED_SET schreibt nur, wenn der Platz im Durchlauf frei ist (erster gewinnt).
    LEDF:   move.l  d2,-(sp)
            moveq   #0,d2
    lf1:    lea     {C.LSLOTS:#x},a0
            move.l  0(a0,d2.l*4),d0
            beq     lf2
            movea.l d0,a1
            move.l  12(sp),d0
            move.l  16(sp),d1
            jsr     (a1)
            move.l  d1,16(sp)
    lf2:    addq.l  #1,d2
            moveq   #{C.NLSLOT},d0
            cmp.l   d2,d0
            bne     lf1
            move.l  (sp)+,d2
            lea     -12(sp),sp
            movem.l d2-d3/a2,(sp)
            jmp     0x40005F8E
    ; smp28 TSVK(Ansicht, Ereignis): Tasten der TrackSelectionView (TRACK gehalten; Vtable 0x40100ee8): Handler der Mods
    ; (TKSLOTS, C-Aufruf, d0 != 0 = behandelt), sonst die Firmware 0x40024078
    TSVK:   move.l  d2,-(sp)
            moveq   #0,d2
    tv1:    lea     {C.TKSLOTS:#x},a0
            move.l  0(a0,d2.l*4),d0
            beq     tv2
            movea.l d0,a1
            move.l  12(sp),-(sp)
            move.l  12(sp),-(sp)
            jsr     (a1)
            addq.l  #8,sp
            tst.l   d0
            bne     tv8
    tv2:    addq.l  #1,d2
            moveq   #{C.NTKSLOT},d0
            cmp.l   d2,d0
            bne     tv1
            move.l  (sp)+,d2
            jmp     {C.TSV_KEY:#x}
    tv8:    move.l  (sp)+,d2
            moveq   #1,d0
            rts
'''


def build(lkslot):
    """-> (Bytes ab CORE_CODE, Labels)"""
    import re
    text = code_text().replace('{LKSLOT}', f'{lkslot:#x}')
    a = A(C.CORE_CODE); asm(a, text, collections.defaultdict(int)); lab = dict(a.lab)
    a = A(C.CORE_CODE); asm(a, text, lab); code = adone(a, lab)
    assert C.CORE_CODE + len(code) <= C.CORE_ORG + C.PAY_SLOT['core'][1]
    return code, dict(a.lab)


def tables():
    """Bytes ab CORE_ORG bis CORE_CODE: DTAB (leer, BOOT fuellt), DONOR 0, MACHMAP 0xff, LKXT frei (Maschine 0xff)"""
    b = bytearray(C.CORE_CODE - C.CORE_ORG)
    o = C.MACHMAP - C.CORE_ORG; b[o:o + NX] = b'\xff' * NX
    assert C.STYX + NX <= C.PSXT and C.PSXT + 4 * C.NPSX <= C.CORE_CODE and C.TKSLOTS + 4 * C.NTKSLOT <= C.STYX
    for i in range(C.NLKX):
        b[C.LKXT - C.CORE_ORG + 4 * i] = 0xFF
    for i in range(C.NPSX):
        b[C.PSXT - C.CORE_ORG + 4 * i] = 0xFF
    return bytes(b)


def refs32(img, v):
    p = struct.pack('>I', v); out, i = [], img.find(p)
    while i >= 0:
        if i % 2 == 0: out.append(BASE + i)
        i = img.find(p, i + 1)
    return out


def hook_all(W, img, lab):
    """Verweise, Grenzen, Umleitungen (gegen das Stock-Image geprueft)."""
    for old, n in NREF.items():
        rs = refs32(img, old)
        assert len(rs) == n, (hex(old), [hex(x) for x in rs])
        for va in rs:
            W.hook(va, struct.pack('>I', old), struct.pack('>I', old - DESC0 + C.DTAB))
    for va in BOUNDS:
        op, n = img[va - BASE], img[va - BASE + 1]
        assert op & 0xF1 == 0x70 and n in (76, 75), hex(va)
        W.put(va, bytes([op, {76: C.NDESC, 75: C.NDESC - 1}[n]]))
    for va, (ck, nm) in HOOKS.items():
        W.hook(va, ck, jmp(lab[nm]))
    return [x for old in NREF for x in refs32(img, old)] + list(BOUNDS) + list(HOOKS)


# Zugriffe fuer andere Mods
def desc_row(machine, slot, top, dflt, key, name, group, short, cc=False):
    """Eintrag wie die der Maschinen (Flags 0x600 = Knopf, ohne CC / NRPN)"""
    return struct.pack('>14I', machine & 0xFFFFFFFF, slot, 0, top, dflt, 0, 0xFFFFFFFF, 0xFFFFFFFF, 0, 0x600, key, name, group, short)

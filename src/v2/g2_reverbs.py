#!/usr/bin/env python3
"""Hall / Room / Plate (smp9) fuer den Reverb-Platz von 'reverb-fx' (Modi 5 / 6 / 7). Klang: rv_algos.py.

Code und Tabellen liegen in einer Nutzlast hinter dem MAIN OS (Section 3 waechst), die der Start in die SDRAM bei
0x43000000 kopiert (Haken am Anfang der BSS-Loeschung 0x400004b2, wie die Nutzlast der Syntakt-Mods von Modded-Cycles,
notes/17 §3: der Cache ist dort noch aus). Zustand 0x43100000, Leitungen ab 0x43110000 (unter dem Sample-Speicher
0x43801000 des Samplers).
Aufruf je Block (Haken R von reverb-fx, Stack wie das Reverb der Firmware: ret, out, in, params):
  in = 32 Frames Stereo (Q31) -> mono, 24 kHz (je 2 Frames), / 64 (Reserve); Programm des Modus (Operationen zu je 16
  Samples, Code aus rv_algos); Ausgang x 64 (gesaettigt), 48 kHz (Mitte linear, dann Wert).
  Size (params +0) = Abklingzeit, Tone (+2) = Daempfung, Send = Pegel in den Effekt (Mixer).
Moduswechsel / erster Aufruf: Zustand leer, Leitungen in Stuecken zu 4 KB je Block loeschen (Ausgang still).
Andere Modi des Platzes setzen SMODE = -1 (R in reverb-fx), damit eine Rueckkehr wieder leer beginnt."""
import math, struct
import rv_algos as RA
from common import *                 # noqa: F401,F403
from cfasm import asm, done as adone

PAY = 0x43000000 + PAY_SLOT['reverb-fx'][0]   # smp14: Platz 'reverb-fx' der Nutzlast des Cores (Start-Kopie: g2_core)
ST = 0x43100000
V = dict(SMODE=0, SCLR=4, T=8, PH=12, LPS=28, PREVL=76, PREVR=80, SZP=84, TONEA=88, LPA=96)   # LPA: g der Kuhschwaenze (12)
XB = ST + 0x100                       # Register 0..11 je 64 B
RINGS = 0x43110000
RING_LIMIT = 0x43800000
CHUNK = 4096
MODES = {5: 'hall', 6: 'room', 7: 'plate'}
ROWS = {5: (b"Hall Send", b"HALL", b"Hall Decay", b"DEC", b"Hall Tone", b"TON"),
        6: (b"Room Send", b"ROOM", b"Room Decay", b"DEC", b"Room Tone", b"TON"),
        7: (b"Plate Send", b"PLAT", b"Plate Decay", b"DEC", b"Plate Tone", b"TON")}


def X(r): return XB + 64 * r
def q31(x): return max(-0x80000000, min(0x7FFFFFFF, int(round(x * 2 ** 31))))
def q30(x): return max(-0x80000000, min(0x7FFFFFFF, int(round(x * 2 ** 30))))
def u32(x): return x & 0xFFFFFFFF


def layout(algo):
    """Leitungen -> (Basis, Maske), Gesamtgroesse"""
    A = RA.ALGOS[algo](); at = RINGS; out = {}
    for k, n in sorted(A['lines'].items(), key=lambda kv: -kv[1]):
        size = 1 << max(5, (n + RA.NB + 2).bit_length())
        out[k] = (at, size - 1); at += 4 * size
    assert at <= RING_LIMIT
    return A, out, at - RINGS


def tables(algo, A):
    """Abklingen (Q30) [Size 0..127][Leitung]; Tone: Tiefpass des Kuhschwanzes (Q31) [0..127]; XT [Size] / QT [Tone] (Q12);
    AJ: Anzahl - 1, dann je Zustand (Adresse LPA[k], aj) fuer g = exp(-aj XT QT)"""
    nl = len(A['loops']); g = []
    for s in range(128):
        for j in range(nl):
            v = RA.decay_gain(algo, A, j, s)
            g.append(q30(v * A['had'] * 4) if A['had'] != 1.0 else q30(v))
    tt = struct.pack('>128i', *[q31(RA.tone_lp(algo, t)) for t in range(128)])
    xt = struct.pack('>128I', *[RA.xt(algo, s) for s in range(128)])
    qt = struct.pack('>128I', *[RA.qt(algo, t) for t in range(128)])
    L = RA.lp_lengths(A)
    ajb = struct.pack('>I', len(L) - 1) + b''.join(struct.pack('>II', ST + V['LPA'] + 4 * k, RA.aj(n)) for k, n in sorted(L.items()))
    return struct.pack('>%di' % len(g), *g), tt, nl, xt, qt, ajb


OPS = r'''
    ; ---------------- Operationen auf Bloecken zu 16 Samples (a0 Leitung, d0 Maske, d1 Abstand, a1 Register ...)
    ; smp11: ohne Ueberlauf des Rings im Block (fast immer) mit Zeigern, sonst Index je Sample
    OP_DLR: move.l  {T},d2
            sub.l   d1,d2
            and.l   d0,d2
            moveq   #15,d3
            move.l  d2,d4
            add.l   d3,d4
            cmp.l   d0,d4
            bhi     dr1
            lea     0(a0,d2.l*4),a3
    dr2:    move.l  (a3)+,(a1)+
            subq.l  #1,d3
            bpl     dr2
            rts
    dr1:    move.l  d2,d4
            and.l   d0,d4
            move.l  0(a0,d4.l*4),d5
            move.l  d5,(a1)+
            addq.l  #1,d2
            subq.l  #1,d3
            bpl     dr1
            rts
    OP_DLW: move.l  {T},d2
            and.l   d0,d2
            moveq   #15,d3
            move.l  d2,d4
            add.l   d3,d4
            cmp.l   d0,d4
            bhi     dw1
            lea     0(a0,d2.l*4),a3
    dw2:    move.l  (a1)+,(a3)+
            subq.l  #1,d3
            bpl     dw2
            rts
    dw1:    move.l  d2,d4
            and.l   d0,d4
            move.l  (a1)+,d5
            move.l  d5,0(a0,d4.l*4)
            addq.l  #1,d2
            subq.l  #1,d3
            bpl     dw1
            rts
    ; Modulation: d1 = Abstand << 16, d2 = Tiefe (Q8), a2 = Phase (Q32) -> d1 = ganzer Abstand, a2 = Bruch (Q31)
    OP_MOD: move.l  (a2),d3
            swap    d3
            andi.l  #0xffff,d3               ; u = Phase >> 16
            add.l   d3,d3
            add.l   d3,d3                    ; 4 u
            cmpi.l  #0x20000,d3
            bcc     md1
            subi.l  #0x10000,d3              ; 4p - 1
            bra     md2
    md1:    move.l  #0x30000,d4
            sub.l   d3,d4
            move.l  d4,d3                    ; 3 - 4p
    md2:    muls.l  d2,d3                    ; Dreieck (Q16) * Tiefe (Q8)
            asr.l   #8,d3                    ; m (Q16)
            add.l   d3,d1
            move.l  d1,d3
            andi.l  #0xffff,d3
            moveq   #15,d4
            lsl.l   d4,d3
            movea.l d3,a2                    ; Bruch Q31
            swap    d1
            ext.l   d1
            rts
    OP_DLRM: move.l {T},d2
            sub.l   d1,d2
            moveq   #15,d3
    dm1:    move.l  d2,d4
            and.l   d0,d4
            move.l  0(a0,d4.l*4),d5          ; a = [t - d]
            subq.l  #1,d4
            and.l   d0,d4
            move.l  0(a0,d4.l*4),d7          ; b = [t - d - 1]
            move.l  d5,acc0
            mac     a2,d7,acc0
            msac    a2,d5,acc0
            movclr  acc0,d5                  ; a + f (b - a)
            move.l  d5,(a1)+
            addq.l  #1,d2
            subq.l  #1,d3
            bpl     dm1
            rts
    ; Allpass: w = [t - d], v = x - g w, y = w + g v, [t] = v   (d5 = g Q31)
    OP_AP:  move.l  {T},d2
            and.l   d0,d2
            move.l  d2,d4
            sub.l   d1,d4
            and.l   d0,d4                    ; Lesen ab t - d
            moveq   #15,d3
            move.l  d4,d6
            add.l   d3,d6
            cmp.l   d0,d6
            bhi     ap1
            move.l  d2,d6
            add.l   d3,d6
            cmp.l   d0,d6
            bhi     ap1
            lea     0(a0,d4.l*4),a3
            lea     0(a0,d2.l*4),a4
    ap3:    move.l  (a3)+,d7                 ; w
            move.l  (a1),d6
            move.l  d6,acc0
            msac    d5,d7,acc0
            movclr  acc0,d6                  ; v
            move.l  d7,acc1
            mac     d5,d6,acc1
            movclr  acc1,d7                  ; y
            move.l  d7,(a1)+
            move.l  d6,(a4)+
            subq.l  #1,d3
            bpl     ap3
            rts
    ap1:    move.l  d2,d4
            sub.l   d1,d4
            and.l   d0,d4
            move.l  0(a0,d4.l*4),d7          ; w
            jmp     APC
    OP_APM: move.l  {T},d2
            moveq   #15,d3
    am1:    move.l  d2,d4
            sub.l   d1,d4
            and.l   d0,d4
            move.l  0(a0,d4.l*4),d7
            subq.l  #1,d4
            and.l   d0,d4
            movea.l 0(a0,d4.l*4),a3
            move.l  d7,acc0
            mac     a2,a3,acc0
            msac    a2,d7,acc0
            movclr  acc0,d7                  ; w (moduliert)
    APC:    move.l  (a1),d6
            move.l  d6,acc0
            msac    d5,d7,acc0
            movclr  acc0,d6                  ; v
            move.l  d7,acc1
            mac     d5,d6,acc1
            movclr  acc1,d7                  ; y
            move.l  d7,(a1)+
            move.l  d2,d4
            and.l   d0,d4
            move.l  d6,0(a0,d4.l*4)
            addq.l  #1,d2
            subq.l  #1,d3
            bmi     apx
            move.l  a2,d6
            beq     ap1                      ; a2 = 0: nicht moduliert
            bra     am1
    apx:    rts
    ; r += g [t - d]
    OP_TAP: move.l  {T},d2
            sub.l   d1,d2
            and.l   d0,d2
            moveq   #15,d3
            move.l  d2,d4
            add.l   d3,d4
            cmp.l   d0,d4
            bhi     tp1
            lea     0(a0,d2.l*4),a3
    tp2:    move.l  (a3)+,d7
            move.l  (a1),d6
            move.l  d6,acc0
            mac     d5,d7,acc0
            movclr  acc0,d6
            move.l  d6,(a1)+
            subq.l  #1,d3
            bpl     tp2
            rts
    tp1:    move.l  d2,d4
            and.l   d0,d4
            move.l  0(a0,d4.l*4),d7
            move.l  (a1),d6
            move.l  d6,acc0
            mac     d5,d7,acc0
            movclr  acc0,d6
            move.l  d6,(a1)+
            addq.l  #1,d2
            subq.l  #1,d3
            bpl     tp1
            rts
    ; Tiefpass: y += a (x - y) (a1 Register, a2 Zustand, d5 = a)
    OP_LPF: move.l  (a2),d7
            moveq   #15,d3
    lp1:    move.l  (a1),d6
            sub.l   d7,d6
            move.l  d7,acc0
            mac     d5,d6,acc0
            movclr  acc0,d7
            move.l  d7,(a1)+
            subq.l  #1,d3
            bpl     lp1
            move.l  d7,(a2)
            rts
    ; Kuhschwanz: lp += a (x - lp), x = lp + g (x - lp)   (a1 Register, a2 Zustand, d5 a, d1 g)
    OP_SHF: move.l  (a2),d7
            moveq   #15,d3
    sf1:    move.l  (a1),d4
            move.l  d4,d6
            sub.l   d7,d6
            move.l  d7,acc0
            mac     d5,d6,acc0
            movclr  acc0,d7
            sub.l   d7,d4
            move.l  d7,acc0
            mac     d1,d4,acc0
            movclr  acc0,d6
            move.l  d6,(a1)+
            subq.l  #1,d3
            bpl     sf1
            move.l  d7,(a2)
            rts
    ; Netz schreiben: x = g x + c s, [t] = x  (a1 x, a2 s, d5 g Q30, d6 c Q31). smp11: Q30 als zweimal dasselbe Produkt
    ; statt des Skalierungsfaktors '<<' der EMAC (auf dem Geraet waren die Fahnen zu kurz)
    OP_FWR: movclr  acc0,d4
            move.l  {T},d2
            and.l   d0,d2
            moveq   #15,d3
            move.l  d2,d4
            add.l   d3,d4
            cmp.l   d0,d4
            bhi     fw1
            lea     0(a0,d2.l*4),a3
    fw2:    move.l  (a1),d4
            mac     d5,d4,acc0
            mac     d5,d4,acc0
            move.l  (a2)+,d4
            mac     d6,d4,acc0
            movclr  acc0,d4
            move.l  d4,(a1)+
            move.l  d4,(a3)+
            subq.l  #1,d3
            bpl     fw2
            rts
    fw1:    move.l  (a1),d4
            mac     d5,d4,acc0
            mac     d5,d4,acc0
            move.l  (a2)+,d4
            mac     d6,d4,acc0
            movclr  acc0,d4
            move.l  d4,(a1)+
            move.l  d2,d7
            and.l   d0,d7
            move.l  d4,0(a0,d7.l*4)
            addq.l  #1,d2
            subq.l  #1,d3
            bpl     fw1
            rts
    ; x *= g (Q30)
    OP_G30: movclr  acc0,d4
            moveq   #15,d3
    g1:     move.l  (a1),d4
            mac     d5,d4,acc0
            mac     d5,d4,acc0
            movclr  acc0,d4
            move.l  d4,(a1)+
            subq.l  #1,d3
            bpl     g1
            rts
    ; r += g s: d5 = g Q31 (OP_GADD) / Q30 (OP_GA30)
    OP_GADD: moveq  #15,d3
    ga1:    move.l  (a1),d2
            move.l  d2,acc0
            move.l  (a2)+,d4
            mac     d5,d4,acc0
            movclr  acc0,d4
            move.l  d4,(a1)+
            subq.l  #1,d3
            bpl     ga1
            rts
    OP_GA30: moveq  #15,d3
    gb1:    move.l  (a1),d2
            move.l  d2,acc0
            move.l  (a2)+,d4
            mac     d5,d4,acc0
            mac     d5,d4,acc0
            movclr  acc0,d4
            move.l  d4,(a1)+
            subq.l  #1,d3
            bpl     gb1
            rts
    OP_MOV: moveq   #15,d3
    mv1:    move.l  (a2)+,(a1)+
            subq.l  #1,d3
            bpl     mv1
            rts
    OP_ZERO: moveq  #15,d3
    z1:     clr.l   (a1)+
            subq.l  #1,d3
            bpl     z1
            rts
'''


def had_asm():
    """smp47 (Last): Hadamard 8 (Register 0..7 ab a1), Stufen 1 und 2 halbiert: H x / 4; dazu Register 9 += Zeile 1,
    10 += Zeile 2 (Ausgang). Schmetterling in 3 statt 4 Befehlen ohne Hilfsregister: sub.l b,a (a-b) ; add.l b,b (2b) ;
    add.l a,b (a+b) - modulo 2^32 gleich wie add/sub vorher (bitgleich), danach tauschen die beiden Register die Rollen."""
    r = list(range(8))                     # logisch -> d-Register
    out = ['    ; Hadamard 8 (smp47: had_asm)',
           '    OP_HAD: moveq   #15,d3',
           '            movea.l d3,a4',
           '    hd1:    move.l  (a1),d0'] + [f'            move.l  {64 * k}(a1),d{k}' for k in range(1, 8)]
    for pairs, half in (([(0, 1), (2, 3), (4, 5), (6, 7)], True), ([(0, 2), (1, 3), (4, 6), (5, 7)], True),
                        ([(0, 4), (1, 5), (2, 6), (3, 7)], False)):
        for i, j in pairs:
            a, b = r[i], r[j]
            if half: out += [f'            asr.l   #1,d{a}', f'            asr.l   #1,d{b}']
            out += [f'            sub.l   d{b},d{a}', f'            add.l   d{b},d{b}', f'            add.l   d{a},d{b}']
            r[i], r[j] = b, a                  # d{b} = a + b (logisch i), d{a} = a - b (logisch j)
    out += [f'            move.l  d{r[0]},(a1)'] + [f'            move.l  d{r[k]},{64 * k}(a1)' for k in range(1, 8)]
    out += [f'            add.l   d{r[1]},576(a1)', f'            add.l   d{r[2]},640(a1)',
            '            addq.l  #4,a1', '            subq.l  #1,a4', '            move.l  a4,d0', '            bpl     hd1',
            '            rts', '']
    return '\n'.join(out)


def unroll4(text, label):
    """smp47 (Last): Schleife 'label: ... subq.l #1,d3 ; bpl label' ueber 16 Samples -> 4 Durchlaeufe mit 4-fachem
    Koerper (gleiche Befehle in gleicher Reihenfolge, nur 2 statt 8 Befehle Schleifenzaehlung je 4 Samples). Das Ausrollen
    nur x4 (nicht x16): der Befehls-Cache (8 KB) wird von den Stimmen jeden Block geleert, jede Zeile Code kostet."""
    ls = text.split('\n')
    k = next(n for n, x in enumerate(ls) if x.lstrip().startswith(label + ':'))
    e = next(n for n in range(k, len(ls)) if ls[n].split() == ['subq.l', '#1,d3'] and ls[n + 1].split() == ['bpl', label])
    first = ls[k].split(':', 1)[1]
    body = ['           ' + first] + ls[k + 1:e]
    pre = ls[:k]
    if pre[-1].split() == ['moveq', '#15,d3']: pre = pre[:-1]      # nur Zaehler: ersetzt
    return '\n'.join(pre + ['            moveq   #3,d3', f'    {label}:'] + body * 4 + ls[e:])


for _l in ('ap3', 'sf1', 'fw2', 'dm1', 'tp2'):
    OPS = unroll4(OPS, _l)
OPS += had_asm()


MAIN = r'''
    ; ---------------- Einsprung (Stack: ret, out 48, in 52, params 56 nach dem Sichern)
    RVB:    lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            move.l  #0xa0,macsr
            moveq   #0,d0
            move.b  {RMODE},d0
            cmp.l   {SMODE},d0
            beq     rv2
            move.l  d0,{SMODE}               ; neuer Modus: Zustand leer, Leitungen loeschen
            move.l  #0x40000000,d1           ; smp11 Probe: 0.5 * 0.5 mit '<<' = 0.5? Sonst 'Hall Send' -> 'Hall Send<'
            move.l  d1,d2
            movclr  acc0,d3                  ; smp13: Akku vorher leeren (ein Rest der Firmware koennte die Probe verfaelschen)
            mac     d1,d2,acc0,<<
            movclr  acc0,d3
            cmp.l   d1,d3
            beq     rq
            lea     PTAB,a0
            movea.l {5 * 32}(a0),a0
            moveq   #0x3c,d1
            move.b  d1,9(a0)
    rq:
            clr.l   {SCLR}
            lea     {ST + 8},a0
            move.l  #{(0x100 - 8) // 4 + 12 * 16 - 1},d1
    rz:     clr.l   (a0)+
            subq.l  #1,d1
            bpl     rz
    rv2:    lea     RSZ,a0
            move.l  -20(a0,d0.l*4),d1        ; Groesse der Leitungen des Modus
            move.l  {SCLR},d2
            cmp.l   d1,d2
            bcc     rv3
            lea     {RINGS},a0
            adda.l  d2,a0
            addi.l  #{CHUNK},d2
            move.l  d2,{SCLR}
            move.l  #{CHUNK // 16 - 1},d1
    rc:     clr.l   (a0)+
            clr.l   (a0)+
            clr.l   (a0)+
            clr.l   (a0)+
            subq.l  #1,d1
            bpl     rc
            movea.l 48(sp),a0                ; still
            moveq   #63,d1
    rs:     clr.l   (a0)+
            subq.l  #1,d1
            bpl     rs
            jmp     RVX
    rv3:    movea.l 56(sp),a0                ; Size -> Abklingen, Tone -> Daempfung
            mvz.w   (a0),d1
            lsr.l   #8,d1
            moveq   #127,d2
            cmp.l   d2,d1
            bls     rp1
            move.l  d2,d1
    rp1:    lea     RGT,a1
            movea.l -20(a1,d0.l*4),a1
            lea     RNL,a2
            move.l  -20(a2,d0.l*4),d3        ; Leitungen * 4
            move.l  d1,d4
            muls.l  d3,d4
            adda.l  d4,a1
            move.l  a1,{SZP}
            lea     RXT,a1
            movea.l -20(a1,d0.l*4),a1
            move.l  0(a1,d1.l*4),d6          ; XT[Size]
            mvz.w   2(a0),d1
            lsr.l   #8,d1
            cmp.l   d2,d1
            bls     rp2
            move.l  d2,d1
    rp2:    lea     RTT,a1
            movea.l -20(a1,d0.l*4),a1
            move.l  0(a1,d1.l*4),d4
            move.l  d4,{TONEA}
            jsr     SHG
            movea.l 52(sp),a0                ; Eingang -> Register 8 (mono, 24 kHz, / 64: Reserve fuer lange Fahnen)
            lea     {X(8)},a1
            moveq   #15,d3
    ri:     move.l  (a0)+,d1
            asr.l   #8,d1
            move.l  (a0)+,d2
            asr.l   #8,d2
            add.l   d2,d1
            move.l  (a0)+,d2
            asr.l   #8,d2
            add.l   d2,d1
            move.l  (a0)+,d2
            asr.l   #8,d2
            add.l   d2,d1
            move.l  d1,(a1)+
            subq.l  #1,d3
            bpl     ri
            lea     RPG,a0
            movea.l -20(a0,d0.l*4),a0
            jmp     (a0)
    ; ---------------- Ende: Register 9 / 10 -> Ausgang (x 128 * Pegel des Modus, gesaettigt; Frame 2i = Mitte, 2i + 1 = Wert)
    RVEND:  movea.l 48(sp),a0
            lea     {X(9)},a1
            lea     {X(10)},a2
            move.l  {PREVL},d6
            move.l  {PREVR},d7
            moveq   #0,d0
            move.b  {RMODE},d0
            lea     ROG,a3
            move.l  -20(a3,d0.l*4),d5
            movclr  acc0,d1
            moveq   #15,d3
    ro:     move.l  (a1)+,d1
            mac     d5,d1,acc0               ; OG inline (smp47): d1 * Pegel * 128, gesaettigt
            movclr  acc0,d1
            move.l  d1,d2
            asl.l   #7,d1
            move.l  d1,d4
            asr.l   #7,d4
            cmp.l   d2,d4
            beq     oga
            move.l  #0x7fffffff,d1
            tst.l   d2
            bpl     oga
            addq.l  #1,d1
    oga:
            move.l  d6,d0
            asr.l   #1,d0
            move.l  d1,d6
            asr.l   #1,d1
            add.l   d1,d0
            move.l  d0,(a0)
            move.l  d6,8(a0)
            move.l  (a2)+,d1
            mac     d5,d1,acc0               ; OG inline (smp47): d1 * Pegel * 128, gesaettigt
            movclr  acc0,d1
            move.l  d1,d2
            asl.l   #7,d1
            move.l  d1,d4
            asr.l   #7,d4
            cmp.l   d2,d4
            beq     ogb
            move.l  #0x7fffffff,d1
            tst.l   d2
            bpl     ogb
            addq.l  #1,d1
    ogb:
            move.l  d7,d0
            asr.l   #1,d0
            move.l  d1,d7
            asr.l   #1,d1
            add.l   d1,d0
            move.l  d0,4(a0)
            move.l  d7,12(a0)
            lea     16(a0),a0
            subq.l  #1,d3
            bpl     ro
            move.l  d6,{PREVL}
            move.l  d7,{PREVR}
            move.l  {T},d0
            addi.l  #{NB},d0
            move.l  d0,{T}
            moveq   #0,d0
            move.b  {RMODE},d0
            lea     RLF,a0                   ; Phasenschritte (2 je Modus)
            subq.l  #5,d0
            lsl.l   #3,d0
            adda.l  d0,a0
            lea     {ST + V['PH']},a1
            move.l  (a0)+,d1
            add.l   d1,(a1)+
            move.l  (a0)+,d1
            add.l   d1,(a1)+
    RVX:    movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            rts
    ; SHG: g der Kuhschwaenze je Zustand: c = aj * ((XT * QT) >> 13) >> 7 (Q16), g = exp(-c) aus EB (linear)
    ;      (d0 Modus, d1 Tone, d6 XT; haelt d0 / a0)
    SHG:    lea     RQT,a1
            movea.l -20(a1,d0.l*4),a1
            move.l  0(a1,d1.l*4),d4
            mulu.l  d4,d6
            moveq   #13,d4
            lsr.l   d4,d6                    ; P >> 5
            lea     RAJ,a1
            movea.l -20(a1,d0.l*4),a1
            move.l  (a1)+,d7
    sg1:    movea.l (a1)+,a2
            move.l  (a1)+,d4
            mulu.l  d6,d4
            lsr.l   #7,d4                    ; c (Q16)
            move.l  d4,d5
            moveq   #11,d3
            lsr.l   d3,d5                    ; i
            andi.l  #2047,d4                 ; f
            cmpi.l  #256,d5
            bcs     sg2
            move.l  #256,d5
            moveq   #0,d4
    sg2:    lea     EB,a3
            move.l  0(a3,d5.l*4),d3
            move.l  4(a3,d5.l*4),d2
            sub.l   d3,d2
            asr.l   #8,d2
            asr.l   #3,d2
            muls.l  d4,d2
            add.l   d3,d2
            move.l  d2,(a2)
            subq.l  #1,d7
            bpl     sg1
            rts
'''


def oq(A):
    """Skala der Ausgangsregister 9 / 10 im Code: Modell = Code * OQ (Hadamard-Zeile / 4 * c * 4)"""
    h = [op for op in A['prog'] if op[0] == 'HAD']
    return 4 * h[0][4] if h else 1.0


def prog_asm(algo, mode):
    A, lay, total = layout(algo)
    out = ['    PRG%d:' % mode]
    e = out.append
    def line(ln): base, mask = lay[ln]; e(f'            lea     {base:#x},a0'); e(f'            move.l  #{mask:#x},d0')
    def mod(d, dep, k):
        e(f'            move.l  #{d << 16:#x},d1'); e(f'            move.l  #{int(round(dep * 256))},d2')
        e(f'            lea     {ST + V["PH"] + 4 * k:#x},a2'); e('            jsr     OP_MOD')
    OQ = oq(A)
    for op in A['prog']:
        o = op[0]
        if o == 'IN': assert op[1] == 8
        elif o == 'OUT': assert op[1:] == (9, 10, 1.0)
        elif o == 'DLW':
            line(op[1]); e(f'            lea     {X(op[2]):#x},a1'); e('            jsr     OP_DLW')
        elif o == 'DLR':
            line(op[1]); e(f'            move.l  #{op[3]},d1'); e(f'            lea     {X(op[2]):#x},a1'); e('            jsr     OP_DLR')
        elif o == 'DLRM':
            mod(op[3], op[4], op[5]); line(op[1]); e(f'            lea     {X(op[2]):#x},a1'); e('            jsr     OP_DLRM')
        elif o in ('AP', 'APM'):
            if o == 'APM': mod(op[4], op[5], op[6])
            else: e(f'            move.l  #{op[4]},d1'); e('            suba.l  a2,a2')
            line(op[1]); e(f'            move.l  #{u32(q31(op[3])):#x},d5'); e(f'            lea     {X(op[2]):#x},a1')
            e('            jsr     OP_APM' if o == 'APM' else '            jsr     OP_AP')
        elif o == 'TAP':
            gq = op[4] / OQ if op[3] in (9, 10) else op[4]     # Ausgangsregister in der Skala des Codes (x OQ am Ende)
            line(op[1]); e(f'            move.l  #{op[2]},d1'); e(f'            move.l  #{u32(q31(gq)):#x},d5')
            e(f'            lea     {X(op[3]):#x},a1'); e('            jsr     OP_TAP')
        elif o == 'LPF':
            e(f'            lea     {X(op[1]):#x},a1'); e(f'            lea     {ST + V["LPS"] + 4 * op[2]:#x},a2')
            if op[3] == 'tone':
                e(f'            move.l  {ST + V["TONEA"]:#x},d5'); e(f'            move.l  {ST + V["LPA"] + 4 * op[2]:#x},d1')
                e('            jsr     OP_SHF')
            else:
                e(f'            move.l  #{u32(q31(op[3])):#x},d5'); e('            jsr     OP_LPF')
        elif o == 'FWR':
            ln, r, j, c, src = op[1:]
            line(ln); e(f'            movea.l {ST + V["SZP"]:#x},a3'); e(f'            move.l  {4 * j}(a3),d5')
            e(f'            move.l  #{u32(q31(c)):#x},d6'); e(f'            lea     {X(r):#x},a1'); e(f'            lea     {X(src):#x},a2')
            e('            jsr     OP_FWR')
        elif o == 'GAIN':
            e(f'            movea.l {ST + V["SZP"]:#x},a3'); e(f'            move.l  {4 * op[2]}(a3),d5')
            e(f'            lea     {X(op[1]):#x},a1'); e('            jsr     OP_G30')
        elif o == 'GAINADD':
            e(f'            movea.l {ST + V["SZP"]:#x},a3'); e(f'            move.l  {4 * op[3]}(a3),d5')
            e(f'            lea     {X(op[1]):#x},a1'); e(f'            lea     {X(op[2]):#x},a2'); e('            jsr     OP_GA30')
        elif o == 'ADD':
            e(f'            move.l  #{u32(q31(op[3])):#x},d5'); e(f'            lea     {X(op[1]):#x},a1'); e(f'            lea     {X(op[2]):#x},a2')
            e('            jsr     OP_GADD')
        elif o == 'MOV':
            e(f'            lea     {X(op[1]):#x},a1'); e(f'            lea     {X(op[2]):#x},a2'); e('            jsr     OP_MOV')
        elif o == 'ZERO':
            e(f'            lea     {X(op[1]):#x},a1'); e('            jsr     OP_ZERO')
        elif o == 'HAD':
            assert op[1] == list(range(8)) and op[2:4] == (9, 10) and abs(op[4] * 4 - OQ) < 1e-12
            e(f'            lea     {X(0):#x},a1'); e('            jsr     OP_HAD')
        else:
            raise ValueError(op)
    e('            jmp     RVEND')
    return '\n'.join(out) + '\n', A, total


def payload(rmode_addr, rows_tab):
    """-> (Bytes ab PAY, Labels)"""
    kw = dict(T=ST + V['T'], SMODE=ST + V['SMODE'], SCLR=ST + V['SCLR'], PREVL=ST + V['PREVL'], PREVR=ST + V['PREVR'],
              SZP=ST + V['SZP'], TONEA=ST + V['TONEA'], RMODE=rmode_addr, ST=ST, RINGS=RINGS, CHUNK=CHUNK, NB=RA.NB, V=V, X=X)
    import re
    def fmt(t): return re.sub(r'\{([^{}]+)\}', lambda m: str(eval(m[1], {}, kw)), t)
    text = fmt(MAIN) + fmt(OPS)
    info = {}
    for m, algo in MODES.items():
        t, A, total = prog_asm(algo, m); text += t; info[m] = (A, total)
    # Daten: Groessen, Programme, Tabellen
    text += '    RSZ:\n' + ''.join(f'            dc.l    {info[m][1]:#x}\n' for m in MODES)
    text += '    RPG:\n' + ''.join(f'            dc.l    PRG{m}\n' for m in MODES)
    text += '    RNL:\n' + ''.join(f'            dc.l    {4 * len(info[m][0]["loops"])}\n' for m in MODES)
    text += '    RGT:\n' + ''.join(f'            dc.l    GT{m}\n' for m in MODES)
    text += '    RTT:\n' + ''.join(f'            dc.l    TT{m}\n' for m in MODES)
    text += '    RXT:\n' + ''.join(f'            dc.l    XT{m}\n' for m in MODES)
    text += '    RQT:\n' + ''.join(f'            dc.l    QT{m}\n' for m in MODES)
    text += '    RAJ:\n' + ''.join(f'            dc.l    AJ{m}\n' for m in MODES)
    text += '    ROG:\n' + ''.join(f'            dc.l    {q31(oq(info[m][0]) / 2):#x}\n' for m in MODES)
    text += '    RLF:\n'
    for m in MODES:
        fs = info[m][0]['lfo'] + [0.0] * (2 - len(info[m][0]['lfo']))
        text += ''.join(f'            dc.l    {int(round(f * RA.NB / RA.FS * 2 ** 32)) & 0xffffffff:#x}\n' for f in fs)
    a = A_(PAY)
    asm(a, text, collections.defaultdict(int)); lab = dict(a.lab); code = bytes(a.b)
    blob = bytearray(code)
    while len(blob) % 4: blob += b'\0'
    for m, algo in MODES.items():
        A = info[m][0]; g, tt, nl, xt, qt, ajb = tables(algo, A)
        lab[f'GT{m}'] = PAY + len(blob); blob += g
        lab[f'TT{m}'] = PAY + len(blob); blob += tt
        lab[f'XT{m}'] = PAY + len(blob); blob += xt
        lab[f'QT{m}'] = PAY + len(blob); blob += qt
        lab[f'AJ{m}'] = PAY + len(blob); blob += ajb
    lab['EB'] = PAY + len(blob); blob += struct.pack('>258I', *RA.EB)
    # Namenszeilen (Tabelle wie reverb-fx, Zeilen 0..7) hinter die Tabellen
    lab['PTAB'] = PAY + len(blob); blob += rows_tab(PAY + len(blob))
    # zweiter Durchgang mit den Adressen der Tabellen
    a = A_(PAY); asm(a, text, lab); code = adone(a, lab)
    assert len(code) <= lab['GT5'] - PAY
    blob[:len(code)] = code
    lab.update({k: v for k, v in a.lab.items()})
    return bytes(blob), lab, {m: info[m][1] for m in MODES}


import collections
from common import A as A_

#!/usr/bin/env python3
"""Tweak 'load-meter' fuer die OFFIZIELLE Model:Cycles OS 1.13: Lastanzeige der Audio-Berechnung (seit 25.10.2026 festes Feature, Pips Wunsch).
Setzt die ganze Kette bis 'strum' voraus (Encoder-Kette SP3 -> SP2 -> SP -> H4, Anzeige aus mod-delays).

Anlass (25.10.2026): Pip meldet 'Bedienung traege, nur bei VIBDEL'. Im Emulator kostet VIBDEL weniger als CHODEL
(3 677 gegen 5 083 Befehle je Block), die echte Maschine zaehlt aber Speicherzugriffe mit (Modded-Cycles notes/23:
schon das Original braucht 77 % der Blockzeit). Also auf der Maschine messen.

Bedienung: SETTINGS + REVERB SEND nach rechts = Anzeige 'LOAD Spitze/Mittel' an, nach links = aus.
  Werte in % der Blockdauer (32 Samples = 90 112 Ticks des DMA-Zeitgebers 0 bei 135.168 MHz), alle 750 Bloecke (0.5 s)
  neu, Spitze und Mittel ueber diese 0.5 s. Ueber 100 = Audio laeuft hinterher. Die Bedienung bekommt nur, was die
  Audio-Berechnung uebrig laesst (100 - Mittel).
Messung (Vorbild syntakt-meter, notes/23 §5): der Aufruf der Audio-Funktion aus der Interruption (jsr 0x4005979e bei
  0x40059382) geht ueber PROBE. Aus: PROBE springt direkt weiter (2 Befehle). An: Ruecksprungadresse beiseite, Zeit
  vorher/nachher, Funktion mit unveraendertem Stack, d0 zurueck.
  Spitze% = (Ticks * 1164) >> 20, Mittel% = ((Summe >> 10) * 1589) >> 20 (beide auf 0.1 % genau bei 100 %).
Speicher: Masken 0x4016b6f8 (PROBE, NUM) und 0x4016b9e8 (SP3), je 47x47 376 B. RAM 0x4a33c3d0..0x4a33c3eb.
Aufruf: gen_loadmeter_113.py <section_3_MAIN_OS.bin der Cycles 1.13> <out.json>
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE, matches
from gen_chorusfx import check_cf, HELD
import gen_overlay_113 as ovl
import gen_moddelay_113 as md
import gen_strum_113 as st
import gen_digidelay_113 as dd

M_LM, M_LM2, SIZE = 0x4016B6F8, 0x4016B9E8, 376        # PROBE + NUM | SP3
P_HOOK, P_ORIG, AUDIO = 0x40059382, (6, 'bc2910c59a0d8e6999ccd601395bca9fd72e3e23d992899f38377b3b07ac2f81'), 0x4005979E   # jsr AUDIO (Laenge + SHA-256)
ENC_REVS = 9                                   # REVERB SEND
MV = 0x4A33C3D0
METER, PR_RET, PR_T0, PK, SUM, N = 0, 4, 8, 12, 16, 20
NBLK = 750
K_PK, K_AVG = 1164, 1589
SLASH = ovl.ORDER.index('/')
DASH = ovl.ORDER.index('-')
NE, EQ, PL, MI, CS, LS, BRA, BSR = 0x6, 0x7, 0xA, 0xB, 0x5, 0x3, 0x0, 0x1


def build(sp_next):
    a = A(M_LM); w, l = a.w, a.l32
    V = ovl.VARS
    def dirty():                                # VC+0x20 = 1, wenn die Anzeige schon einen ViewController kennt
        lab = f'nd{len(a.b)}'
        w(0x2039); l(V + ovl.MAGIC); w(0x0C80); l(ovl.OMAGIC); a.bcc(NE, lab)
        w(0x2039); l(V + ovl.VC); a.bcc(EQ, lab)
        w(0x2240, 0x7001, 0x1340, ovl.VC_DIRTY)
        a.label(lab)
    # ---------------- PROBE (statt jsr AUDIO in der Audio-Interruption)
    a.label('PROBE')
    w(0x4AB9); l(MV + METER); a.bcc(NE, 'pm')
    w(0x4EF9); l(AUDIO)                         # aus: unveraendert weiter
    a.label('pm')
    w(0x23DF); l(MV + PR_RET)                   # move.l (a7)+,PR_RET
    w(0x2039); l(ovl.TIMER); w(0x23C0); l(MV + PR_T0)   # PR_T0 = Zeitgeber
    a.orig(P_HOOK, 6)                           # verschobener Originalbefehl: jsr AUDIO
    w(0x2F00)                                   # Ergebnis merken
    w(0x2039); l(ovl.TIMER); w(0x90B9); l(MV + PR_T0)   # d0 = Dauer in Ticks
    w(0x41F9); l(MV)
    w(0xB0A8, PK); a.bcc(LS, 'p1'); w(0x2140, PK)        # cmp.l PK(a0),d0 ; bls ; move.l d0,PK(a0)
    a.label('p1')
    w(0xD1A8, SUM, 0x52A8, N)                   # add.l d0,SUM(a0) ; addq.l #1,N(a0)
    w(0x2028, N, 0x0C80); l(NBLK); a.bcc(CS, 'pout')
    w(0x4FEF, 0xFFF0, 0x48D7, 0x041C)           # lea -16(a7),a7 ; movem.l d2-d4/a2,(a7)
    w(0x2228, PK, 0x243C); l(K_PK); w(0x4C02, 0x1800, 0x7414, 0xE4A9)   # d1 = PK*1164 >> 20
    w(0x2628, SUM, 0x740A, 0xE4AB, 0x243C); l(K_AVG); w(0x4C02, 0x3800, 0x7414, 0xE4AB)   # d3 = ((SUM>>10)*1589) >> 20
    w(0x42A8, PK, 0x42A8, SUM, 0x42A8, N)
    w(0x45F9); l(V + ovl.BUF); w(0x7800)        # a2 = BUF ; d4 = 0
    w(0x2F03, 0x2001); a.bcc(BSR, 'NUM')        # Spitze
    w(0x7000 | SLASH, 0x14C0, 0x5284)           # '/'
    w(0x201F); a.bcc(BSR, 'NUM')                # Mittel
    w(0x23C4); l(V + ovl.BUFN)
    w(0x7003, 0x23C0); l(V + ovl.KIND)
    w(0x2039); l(ovl.TIMER); w(0x0680); l(ovl.DUR); w(0x23C0); l(V + ovl.DL)
    dirty()
    w(0x4CD7, 0x041C, 0x4FEF, 0x0010)
    a.label('pout')
    w(0x201F, 0x2F39); l(MV + PR_RET); w(0x4E75)   # move.l (a7)+,d0 ; move.l PR_RET,-(a7) ; rts
    # ---------------- NUM: d0 Wert -> Ziffern nach (a2)+, d4 += Anzahl ; veraendert d1-d3
    a.label('NUM')
    w(0x0C80); l(999); a.bcc(LS, 'n0'); w(0x203C); l(999)
    a.label('n0')
    w(0x7600, 0x7264); a.bcc(BSR, 'DIG')
    w(0x720A); a.bcc(BSR, 'DIG')
    w(0x7601, 0x7201); a.bcc(BSR, 'DIG')
    w(0x4E75)
    a.label('DIG')
    w(0x7400)
    a.label('dl'); w(0xB081); a.bcc(CS, 'dd'); w(0x9081, 0x5282); a.bcc(BRA, 'dl')
    a.label('dd'); w(0x4A82); a.bcc(NE, 'pr'); w(0x4A83); a.bcc(EQ, 'dr')
    a.label('pr'); w(0x14C2, 0x5284, 0x7601)
    a.label('dr'); w(0x4E75)
    code1 = a.done(); check_cf(code1, M_LM); assert len(code1) <= SIZE, len(code1); lab1 = dict(a.lab)
    a = A(M_LM2); w, l = a.w, a.l32
    # ---------------- SP3: SETTINGS + REVERB SEND -> Anzeige an/aus; sonst weiter an SP2
    a.label('SP3')
    w(0x202A, 0x0004, 0x0C80); l(ENC_REVS); a.bcc(NE, 'nx')
    w(0x712A, 0x0008); a.bcc(EQ, 'nx')
    w(0x4878, md.KEY_SET, 0x4EB9); l(HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'nx')
    w(0x4878, md.KEY_SET, 0x4EB9); l(md.CONSUME); w(0x588F)
    w(0x42B9); l(V + ovl.PEND)
    w(0x712A, 0x0008); a.bcc(MI, 'off')
    w(0x42B9); l(MV + PK); w(0x42B9); l(MV + SUM); w(0x42B9); l(MV + N)
    w(0x7001, 0x23C0); l(MV + METER)
    w(0x700A | 0, 0x13C0); l(V + ovl.BUF); w(0x13C0); l(V + ovl.BUF + 1)   # '--' bis zur ersten Messung
    w(0x7002, 0x23C0); l(V + ovl.BUFN)
    w(0x2039); l(ovl.TIMER); w(0x0680); l(ovl.DUR); w(0x23C0); l(V + ovl.DL)
    w(0x7003, 0x23C0); l(V + ovl.KIND)
    a.bcc(BRA, 'show')
    a.label('off')
    w(0x42B9); l(MV + METER); w(0x42B9); l(V + ovl.KIND)
    a.label('show')
    dirty()
    w(0x4FEF, 0x000C, 0x4EF9); l(md.ENC_SKIP)
    a.label('nx'); w(0x4EF9); l(sp_next)
    code2 = a.done(); check_cf(code2, M_LM2); assert len(code2) <= SIZE, len(code2)
    return (code1, code2), dict(lab1, **a.lab)


def tweak(img):
    assert DASH == 10
    base = img
    for t0 in (md.dn.tweak(img)[0], md.ch.tweak(img)[0], md.ph.tweak(img)[0], dd.tweak(img)[0], md.rz.tweak(img)[0],
               md.tweak(img)[0], st.tweak(img)[0]):
        base = dd.apply(base, t0)
    S = st.tweak(img)[0]; sp2 = int(S['symbols']['SP2'], 16)
    M = md.build(img)
    code, lab = build(sp2)
    jsr = lambda t: bytes.fromhex("4eb9") + struct.pack('>I', t)
    sw = lambda va, new: {"off": va - BASE, "old": bytes(base[va-BASE:va-BASE+len(new)]).hex(), "new": new.hex()}
    assert matches(base, P_HOOK, P_ORIG)
    assert base[md.H_HOOK-BASE:md.H_HOOK-BASE+6] == jsr(sp2)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    w = [sw(M_LM, code[0]), sprites.redirect_write(M_LM), sw(M_LM2, code[1]), sprites.redirect_write(M_LM2),
         sw(P_HOOK, jsr(lab['PROBE'])), sw(md.H_HOOK, jsr(lab['SP3']))]
    w.sort(key=lambda x: x["off"])
    t = {"id": "load-meter", "order": 72, "name": "LOAD-Anzeige (SETTINGS + REVERB SEND)",
         "description": ["SETTINGS + REVERB SEND rechts: 'LOAD Spitze/Mittel' in % der Blockzeit, alle 0.5 s neu; links: aus.",
                         "Erzeugt von gen_loadmeter_113.py."],
         "device": "Model:Cycles", "os": "1.13", "section": 3,
         "requires": ["delay-notes", "chorus", "phaser", "digi-delay", "razer", "mod-delays", "strum"],
         "hooks": [f"{P_HOOK:#x}", f"{md.H_HOOK:#x}"],
         "memory": [{"va": f"{M_LM:#x}", "size": SIZE}, {"va": f"{M_LM2:#x}", "size": SIZE}, {"va": f"{MV:#x}", "size": 24, "ram": True}],
         "symbols": {"PROBE": f"{lab['PROBE']:#x}", "SP3": f"{lab['SP3']:#x}", "SP2": f"{sp2:#x}", "NUM": f"{lab['NUM']:#x}"},
         "params": {"mv": f"{MV:#x}", "nblk": NBLK, "k_pk": K_PK, "k_avg": K_AVG, "block_ticks": 90112},
         "writes": w}
    return t, (code, lab)


if __name__ == "__main__":
    img = open(sys.argv[1], 'rb').read()
    t, (code, lab) = tweak(img)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print(len(code[0]), len(code[1]), t["symbols"])

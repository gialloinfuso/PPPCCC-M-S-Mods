#!/usr/bin/env python3
"""Tweak 'strum' fuer die OFFIZIELLE Model:Cycles OS 1.13: STRUM fuer die CHORD-Maschine (globaler Wert, Pips Idee 25.10.2026).
Setzt delay-notes, chorus, phaser, digi-delay, razer, mod-delays voraus (Encoder-Kette SP2 -> SP -> H4, Anzeige OVS aus mod-delays).

STRUM -80..80 (SETTINGS + SHAPE, Encoder 5; Anzeige 'STRUM nn' 1.5 s): 0 = alle Akkordtoene gleichzeitig (wie bisher),
  > 0 = von tief nach hoch (Op 0, 1, 2, 3), < 0 = von hoch nach tief (Op 3, 2, 1, 0), gleicher Abstand.
  Abstand = (|STRUM| * 96) >> 6 = 1.5 |STRUM| Bloecke (1 Block = 32 Samples = 0.67 ms) -> Wert = ms je Ton, bis 80 ms
  (Anschlag bis 240 ms). Erste Rastung ruft consume(SETTINGS): kein Einstellungsmenue, kein Speichern durch langes Halten.
  v1: 0..127 nur aufwaerts, bis 24.7 ms, TRACK + FUNC + SHAPE, ohne Anzeige. v2: -64..63, bis 50 ms, TRACK + SHAPE
  (nahm CONTROL ALL den Regler weg).
  Op 1..3: Pegel (Stimme +0x0c/+0x10/+0x14) vor dem Einsatz 0, dann 1/4, 1/2, voll; die Firmware blendet diese Pegel innerhalb
  jedes Blocks selbst vom alten Wert (+0x1c/+0x20/+0x24) zum neuen (0x400a9a32), also ohne Knacken.
  Op 0 (Grundton) hat keinen Pegel in der Stimme: der Render mischt ihn mit festem 0x20000000 (0x400ab2d2). Haken G0F liest
  stattdessen G0, das ST pro Block setzt: vor dem Einsatz 0, dann 8 Stufen (n+1)/8 (~5 ms), sonst 0x20000000.
  Die Huellkurve gehoert der Stimme (alle Toene teilen sie), spaete Toene setzen also im schon abfallenden Ton ein.
Gespeichert: Byte 0x404e9b64 (im gespeicherten 0x110-Bereich des Einstellungsblocks, ausserhalb der Pruefsumme, von der
  Firmware nicht benutzt; Werte ausserhalb -80..80 gelten als 0).
Funktionsweise (Modded-Cycles notes/42 §3 und eigene Analyse):
  - Stimmenschleife 0x400a7d4a: Stimme i = 0x42308828 + i*0x31c; +0x38 = Anschlag in diesem Block (dann setzt 0x400a7d16 die
    Phasen der Operatoren zurueck), danach update[Maschine](..., Stimme, Parameter) und render.
  - CHORD-Update 0x400aae88; Haken ST am Ende (0x400ab240, movem.l 8(a7),d2-d5/a2-a4 -> jmp ST), ST spielt den Epilog nach.
  - Vertraeglich mit der Akkord-Tastatur von Modded-Cycles (die haengt an 0x400aae88 und 0x400ab0e4).
Speicher: Masken 0x40192734 (ST + G0F) und 0x4018d4a8 (SP2), je 47x47 376 B | RAM: Zaehler 6 x 4 B 0x4a33c360, G0 0x4a33c378.
Aufruf: gen_strum_113.py <section_3_MAIN_OS.bin der Cycles 1.13> <out.json>
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE, matches
from gen_chorusfx import check_cf, COPY, HELD
import gen_moddelay_113 as md
import gen_digidelay_113 as dd

M_ST, M_SP2, SIZE = 0x40192734, 0x4018D4A8, 376
CNT = 0x4233C360                            # gecachter Alias von 0x4a33c360
STRUM = 0x404E9B64
ST_HOOK = 0x400AB240
ST_ORIG = (6, '13187a38965400f61edba5135ed74da994ac2d300bd2c82157be68165467475b')   # Laenge + SHA-256 (movem.l 8(a7),d2-d5/a2-a4)
VOICE0, VSTEP, NVOICE = 0x42308828, 0x31C, 6
ENC_SHAPE = 5
K_SP = 96                                   # Abstand = (|STRUM| * K_SP) >> 6 Bloecke = 1.5 |STRUM| = |STRUM| ms (v2: 75, v1: (STRUM*38)>>7)
SMAX = 80                                   # STRUM -80..80
G0 = 0x4233C378                             # Pegel des Grundtons fuer den folgenden Render (RAM)
G0_FULL = 0x20000000                        # Stock-Wert
R_HOOK = 0x400AB2D2                         # CHORD-Render: move.l #$20000000,d1
R_ORIG = (6, '37a77ef1bbd2879f9bea1730fa1954dbc1eeee9ce8c7474d97ef7f12d7a2614a')   # Laenge + SHA-256 (move.l #$20000000,d1)
SCRATCH = md.SCRATCH
NE, EQ, PL, MI, CS, CC, LS, LE, BRA, GT, GE = 0x6, 0x7, 0xA, 0xB, 0x5, 0x4, 0x3, 0xF, 0x0, 0xE, 0xC
ENC_SHAPE = 5


def build(sp_next, ovs):
    a = A(M_ST); w, l = a.w, a.l32
    # ---- ST: Ende des CHORD-Updates (a2 = Stimme). d2-d5/a2-a4 werden danach aus dem Stack geholt; d6/d7 NICHT anfassen.
    a.label('ST')
    w(0x200A, 0x0480); l(VOICE0)            # move.l a2,d0 ; subi.l #VOICE0,d0
    a.bcc(MI, 'full')
    w(0x0C80); l(NVOICE * VSTEP); a.bcc(CC, 'full')   # ausserhalb der 6 Stimmen: Schleife unten bleibt kurz
    w(0x7200)                               # moveq #0,d1   Stimmen-Index
    a.label('vi')
    w(0x0C80); l(VSTEP); a.bcc(CS, 'vf')
    w(0x0480); l(VSTEP); w(0x5281); a.bcc(BRA, 'vi')
    a.label('vf')
    w(0x4A80); a.bcc(NE, 'full')
    w(0x7006, 0xB081); a.bcc(LS, 'full')    # Index >= 6
    w(0xE589, 0x41F9); l(CNT); w(0xD1C1)    # a0 = &Zaehler
    w(0x4AAA, 0x0038); a.bcc(EQ, 'inc')     # Anschlag?
    w(0x4290); a.bcc(BRA, 'gate')
    a.label('inc')
    w(0x2010, 0x0C80); l(0xFFFF); a.bcc(CC, 'gate')
    w(0x5290)
    a.label('gate')
    w(0x7139); l(STRUM)                     # mvs.b STRUM,d0   (-80..80)
    w(0x0C80); l(SMAX); a.bcc(GT, 'bad')
    w(0x0C80); l(-SMAX & 0xFFFFFFFF); a.bcc(GE, 'sok')
    a.label('bad'); w(0x7000)
    a.label('sok')
    w(0x7A00, 0x4A80); a.bcc(PL, 'up'); w(0x4480, 0x7A01)    # d5 = Richtung (1 = von oben), d0 = |STRUM|
    a.label('up')
    w(0x7200 | K_SP, 0x4C00, 0x1800, 0xEC89)   # d1 = (|STRUM| * K) >> 6   Abstand in Bloecken
    a.bcc(EQ, 'full')
    w(0x2010, 0x43EA, 0x000C, 0x7601)       # d0 = Zaehler ; a1 = Pegel Op1 ; d3 = k = 1
    a.label('kl')
    w(0x2403, 0x4A85); a.bcc(EQ, 'su'); w(0x7403, 0x9483)    # d2 = k bzw. 3 - k
    a.label('su')
    w(0x4C01, 0x2800)                       # d2 *= Abstand  (Start)
    w(0x2800, 0x9882); a.bcc(MI, 'zero')
    a.bcc(EQ, 'quart')
    w(0x0C84); l(1); a.bcc(EQ, 'half')
    a.bcc(BRA, 'nk')
    a.label('zero'); w(0x4291); a.bcc(BRA, 'nk')
    a.label('quart'); w(0x2811, 0xE484, 0x2284); a.bcc(BRA, 'nk')    # (a1) >>= 2   (d4 als Zwischenspeicher)
    a.label('half'); w(0x2811, 0xE284, 0x2284)                         # (a1) >>= 1
    a.label('nk')
    w(0x5889, 0x5283, 0x0C83); l(4); a.bcc(NE, 'kl')
    # Grundton (Op 0): Start 0 bzw. 3 * Abstand; Einsatz in 8 Stufen
    w(0x7400, 0x4A85); a.bcc(EQ, 'o0'); w(0x2401, 0xD481, 0xD481)
    a.label('o0')
    w(0x2800, 0x9882); a.bcc(MI, 'g0z')
    w(0x0C84); l(7); a.bcc(GT, 'full')
    w(0x5284, 0x741A, 0xE5AC, 0x23C4); l(G0); a.bcc(BRA, 'out')       # G0 = (n+1) << 26
    a.label('g0z'); w(0x42B9); l(G0); a.bcc(BRA, 'out')
    a.label('full'); w(0x283C); l(G0_FULL); w(0x23C4); l(G0)
    a.label('out')
    a.orig(ST_HOOK, 12)                         # Epilog des CHORD-Updates (verschoben, aus dem Image)
    # ---- G0F: im CHORD-Render statt move.l #$20000000,d1 (Pegel des Grundtons)
    a.label('G0F'); w(0x2239); l(G0); w(0x4E75)
    code1 = a.done(); check_cf(code1, M_ST); assert len(code1) <= SIZE, len(code1); lab1 = dict(a.lab)
    # ---- SP2 (eigene Maske): SETTINGS + SHAPE -> STRUM (-80..80), Anzeige; sonst weiter an SP
    a = A(M_SP2); w, l = a.w, a.l32
    a.label('SP2')
    w(0x202A, 0x0004, 0x0C80); l(ENC_SHAPE); a.bcc(NE, 'nx')
    w(0x712A, 0x0008); a.bcc(EQ, 'nx')
    w(0x4878, md.KEY_SET, 0x4EB9); l(HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'nx')   # SETTINGS gehalten?
    w(0x4878, md.KEY_SET, 0x4EB9); l(md.CONSUME); w(0x588F)          # consume(SETTINGS): kein Menue beim Loslassen
    w(0x42B9); l(md.ovl.VARS + md.ovl.PEND)                          # und kein aufgeschobenes Speichern
    w(0x7139); l(STRUM)
    w(0x0C80); l(SMAX); a.bcc(GT, 'tz')
    w(0x0C80); l(-SMAX & 0xFFFFFFFF); a.bcc(GE, 'tv')
    a.label('tz'); w(0x7000)
    a.label('tv')
    w(0x732A, 0x0008, 0xD081)               # d0 += Drehung
    w(0x0C80); l(SMAX); a.bcc(LE, 't1'); w(0x7000 | SMAX)
    a.label('t1')
    w(0x0C80); l(-SMAX & 0xFFFFFFFF); a.bcc(GE, 't2'); w(0x7000 | (-SMAX & 0xFF))
    a.label('t2')
    w(0x13C0); l(SCRATCH)
    w(0x4878, 0x0001, 0x4879); l(SCRATCH); w(0x4879); l(STRUM)
    w(0x4EB9); l(COPY); w(0x4FEF, 0x000C)
    w(0x7002, 0x7339); l(STRUM); w(0x4EB9); l(ovs)   # Anzeige: OVS(2, STRUM)
    w(0x4FEF, 0x000C, 0x4EF9); l(md.ENC_SKIP)        # Ereignis ganz verschlucken (kein Popup der Firmware)
    a.label('nx'); w(0x4EF9); l(sp_next)
    code2 = a.done(); check_cf(code2, M_SP2); assert len(code2) <= SIZE, len(code2)
    return (code1, code2), dict(lab1, **a.lab)


def tweak(img):
    M = md.build(img)
    base = img
    for t0 in (md.dn.tweak(img)[0], md.ch.tweak(img)[0], md.ph.tweak(img)[0], dd.tweak(img)[0], md.rz.tweak(img)[0], md.tweak(img)[0]):
        base = dd.apply(base, t0)
    code, lab = build(M['sp'], M['ovs'])
    sw = lambda va, new: {"off": va - BASE, "old": bytes(base[va-BASE:va-BASE+len(new)]).hex(), "new": new.hex()}
    jsr = lambda t: bytes.fromhex("4eb9") + struct.pack('>I', t)
    jmp = lambda t: bytes.fromhex("4ef9") + struct.pack('>I', t)
    assert matches(base, ST_HOOK, ST_ORIG) and matches(base, R_HOOK, R_ORIG)
    assert base[md.H_HOOK-BASE:md.H_HOOK-BASE+6] == jsr(M['sp'])
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    w = [sw(M_ST, code[0]), sprites.redirect_write(M_ST), sw(M_SP2, code[1]), sprites.redirect_write(M_SP2),
         sw(ST_HOOK, jmp(lab['ST'])), sw(md.H_HOOK, jsr(lab['SP2'])),
         sw(R_HOOK, jsr(lab['G0F']))]
    w.sort(key=lambda x: x["off"])
    t = {"id": "strum", "order": 71, "name": "STRUM fuer CHORD (SETTINGS + SHAPE, -80..80 = ms je Ton)",
         "description": ["Akkordtoene nacheinander: 0 = gleichzeitig, + = von tief nach hoch, - = von hoch nach tief, Wert = ms je Ton (bis 80). Global.",
                         "Erzeugt von gen_strum_113.py."],
         "device": "Model:Cycles", "os": "1.13", "section": 3, "requires": ["delay-notes", "chorus", "phaser", "digi-delay", "razer", "mod-delays"],
         "hooks": [f"{ST_HOOK:#x}", f"{R_HOOK:#x}", f"{md.H_HOOK:#x}"], "settings": [f"{STRUM:#x} (vorzeichenbehaftet -80..80)"],
         "memory": [{"va": f"{M_ST:#x}", "size": SIZE}, {"va": f"{M_SP2:#x}", "size": SIZE}, {"va": f"{CNT:#x}", "size": 24, "ram": True}, {"va": f"{G0:#x}", "size": 4, "ram": True}],
         "symbols": {"ST": f"{lab['ST']:#x}", "SP2": f"{lab['SP2']:#x}", "SP": f"{M['sp']:#x}", "G0F": f"{lab['G0F']:#x}", "OVS": f"{M['ovs']:#x}"},
         "params": {"k": K_SP, "strum": f"{STRUM:#x}", "cnt": f"{CNT:#x}", "g0": f"{G0:#x}", "shift": 6, "smax": SMAX},
         "writes": w}
    return t, (code, lab)


if __name__ == "__main__":
    img = open(sys.argv[1], 'rb').read()
    t, (code, lab) = tweak(img)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print(len(code[0]), len(code[1]), t["symbols"])

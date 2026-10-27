#!/usr/bin/env python3
"""Tweak 'delay-notes' (Model:Cycles OS 1.13 / Modded Cycles 2.0): Delay Time als Notenwerte.

Der OS-Parameter Delay Time (Deskriptor 37, 0..127, 8.8) ist tempo-synchron: Laenge = (Wert+1)/128 einer ganzen Note;
angezeigt wird Wert+1 (1..128). Dieser Tweak
  * D (DSP, 0x400581b8): ersetzt 'addi.l #$100,d0' durch ein jsr; fuer die Werte 4, 9, 20, 41, 84 (Triolen 1/16T..1/1T)
    kommt die exakte Triolenlaenge heraus (+1/3 bzw. +2/3 Rasterschritt); alle anderen Werte bleiben unveraendert.
  * F (Anzeige, Thunk 0x4004dfda, nur fuer this = 0x40a725dc = Objekt 37 + 0x14): zeigt fuer Notenwert-Positionen drei
    Zeichen Text statt der Zahl: 1/1 1/2 1/4 1/8 /16 /32 /64 (gerade), 2. 4. 8. 16. 32. (punktiert), 1T 2T 4T 8T 16T (Triolen).
Code/Tabelle in den Sprite-Masken 0x401699a8 (F) und 0x4016aa28 (D).
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE, matches
MF, MD = 0x401699A8, 0x4016AA28
THUNK, DSP = 0x4004DFDA, 0x400581B8
DSP_CK, THUNK_CK = (6, '5e6408af00d1d51045ea95d4b8bc7b1e7f4da9efdaac918644d33450038db953'), (6, '654f8facf7eac4ec161985a6799bd95cb49fd0d49bda96644ee358f56e409db5')   # Laenge + SHA-256 der Originalbefehle
THIS37 = 0x40A71754 + 37 * 100 + 0x14
SPRINTF, FMT_S = 0x40000E6E, 0x40124B58
BNE, BEQ = 0x6, 0x7
# Wert -> Etikett (Wert = Parameter 0..127, Anzeige = Wert+1 = Vielfache von 1/128 Note)
LABELS = {127: "1/1", 63: "1/2", 31: "1/4", 15: "1/8", 7: "/16", 3: "/32", 1: "/64",
          95: "2.", 47: "4.", 23: "8.", 11: "16.", 5: "32.",
          84: "1T", 41: "2T", 20: "4T", 9: "8T", 4: "16T"}
TRIPLET_FIX = {4: 85, 9: 171, 20: 85, 41: 171, 84: 85}     # Anzeige = Wert+1 : +1/3 bzw +2/3 Schritt (in 1/256)

def build_d():
    a = A(MD)
    a.orig(DSP, 6)                                 # ersetzter Befehl (aus dem Image)
    a.w(0x2F02, 0x2400, 0x0282); a.l32(0xFF)       # move.l d2,-(a7) ; move.l d0,d2 ; andi.l #$ff,d2
    a.bcc(BNE, 'done')                             # Nachkommastellen -> unveraendert
    a.w(0x2400, 0xE08A)                            # move.l d0,d2 ; lsr.l #8,d2  (= Wert+1)
    for disp1, add in sorted((v + 1, x) for v, x in TRIPLET_FIX.items()):
        a.w(0x0C82); a.l32(disp1)                  # cmpi.l #disp1,d2
        a.bcc(BNE, f'n{disp1}')
        a.w(0x0680); a.l32(add)                    # addi.l #add,d0
        a.bcc(0x0, 'done')                         # bra done
        a.label(f'n{disp1}')
    a.label('done')
    a.w(0x241F, 0x4E75)                            # move.l (a7)+,d2 ; rts
    code = a.done(); assert len(code) <= 280, len(code); return code

def build_f():
    a = A(MF)
    a.w(0x202F, 0x0004, 0x0C80); a.l32(THIS37)     # move.l 4(a7),d0 ; cmpi.l #THIS37,d0   (nur Objekt 37)
    a.bcc(BNE, 'orig')
    a.w(0x202F, 0x0008, 0xE080)                    # move.l 8(a7),d0 ; asr.l #8,d0
    a.w(0x41F9); a.l32(0)                          # lea TABLE,a0   (Adresse wird unten eingesetzt)
    fix = len(a.b) - 4
    a.w(0x7200 | len(LABELS))                      # moveq #N,d1
    a.label('loop')
    a.w(0xB0A8, 0x0004)                            # cmp.l 4(a0),d0
    a.bcc(BEQ, 'found')
    a.w(0x41E8, 0x0008, 0x5381)                    # lea 8(a0),a0 ; subq.l #1,d1
    a.bcc(BNE, 'loop')
    a.label('orig')
    a.orig(THUNK, 6); a.w(0x4EF9); a.l32(THUNK + 6)             # Originalbefehl (aus dem Image), weiter im Thunk
    a.label('found')
    a.w(0x222F, 0x000C, 0x2F48, 0x000C, 0x2F41, 0x0004)          # d1=buf ; 12(a7)=Etikett ; 4(a7)=buf
    a.w(0x203C); a.l32(FMT_S); a.w(0x2F40, 0x0008)  # d0 = "%s" ; 8(a7) = d0
    a.w(0x4EF9); a.l32(SPRINTF)
    table = MF + len(a.b)
    a.b[fix:fix + 4] = struct.pack('>I', table)
    for v, s in sorted(LABELS.items()):
        a.b += s.encode().ljust(4, b'\0') + struct.pack('>I', v)
    code = a.done(); assert len(code) <= 280, len(code); return code

def tweak(stock):
    cd, cf = build_d(), build_f()
    sw = lambda va, new: {"off": va - BASE, "old": stock[va-BASE:va-BASE+len(new)].hex(), "new": new.hex()}
    assert matches(stock, DSP, DSP_CK)
    assert matches(stock, THUNK, THUNK_CK)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    jmp = lambda t: bytes.fromhex("4ef9") + struct.pack('>I', t)
    jsr = lambda t: bytes.fromhex("4eb9") + struct.pack('>I', t)
    w = [sw(MD, cd), sw(MF, cf), sprites.redirect_write(MD), sprites.redirect_write(MF),
         sw(DSP, jsr(MD)), sw(THUNK, jmp(MF))]
    w.sort(key=lambda x: x["off"])
    return {"id": "delay-notes", "order": 65, "name": "Delay Time als Notenwerte (inkl. Triolen)",
            "description": ["Delay Time zeigt Notenwerte (1/1 .. 1/64, punktiert, Triolen) statt Zahlen; Triolen sind exakt.",
                            "Erzeugt von gen_delaynotes.py."],
            "device": "Model:Cycles", "os": "1.13", "section": 3, "writes": w}, (cd, cf)

if __name__ == "__main__":
    img = open(sys.argv[1], 'rb').read()
    t, (cd, cf) = tweak(img)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print("D", len(cd), "F", len(cf))
    if len(sys.argv) > 3:
        out = bytearray(img)
        for x in t["writes"]:
            o = bytes.fromhex(x["old"]); assert out[x["off"]:x["off"]+len(o)] == o
            out[x["off"]:x["off"]+len(o)] = bytes.fromhex(x["new"])
        pathlib.Path(sys.argv[3]).write_bytes(bytes(out))

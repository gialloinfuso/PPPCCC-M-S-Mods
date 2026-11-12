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
    """D: statt 'addi.l #$100,d0' am DSP-Befehl: Triolen-Werte exakt (TRIPLET_FIX), sonst unveraendert"""
    from cfasm import asm, done as adone
    a = A(MD)
    tests = ''.join(f'''
            cmpi.l  #{disp1},d2
            bne     n{disp1}
            addi.l  #{add},d0
            bra     done
    n{disp1}:''' for disp1, add in sorted((v + 1, x) for v, x in TRIPLET_FIX.items()))
    asm(a, f'''
            orig    {DSP:#x},6               ; ersetzter Befehl (aus dem Image)
            move.l  d2,-(sp)
            move.l  d0,d2
            andi.l  #0xff,d2
            bne     done                     ; Nachkommastellen -> unveraendert
            move.l  d0,d2
            lsr.l   #8,d2                    ; = Wert + 1{tests}
    done:   move.l  (sp)+,d2
            rts
    ''')
    code = adone(a); assert len(code) <= 280, len(code); return code

def build_f():
    """F: Anzeige-Thunk 0x4004dfda, nur fuer Objekt 37 (Delay Time): Notenwerte als Text (Tabelle hinter dem Code)"""
    from cfasm import asm, done as adone
    a = A(MF)
    asm(a, f'''
            move.l  4(sp),d0
            cmpi.l  #{THIS37:#x},d0          ; nur Objekt 37
            bne     orig
            move.l  8(sp),d0
            asr.l   #8,d0                    ; Wert
            lea     TABLE,a0
            moveq   #{len(LABELS)},d1
    loop:   cmp.l   4(a0),d0
            beq     found
            lea     8(a0),a0
            subq.l  #1,d1
            bne     loop
    orig:   orig    {THUNK:#x},6             ; Originalbefehl (aus dem Image), weiter im Thunk
            jmp     {THUNK + 6:#x}
    found:  move.l  12(sp),d1                ; Puffer
            move.l  a0,12(sp)                ; Etikett
            move.l  d1,4(sp)
            move.l  #{FMT_S:#x},d0           ; "%s"
            move.l  d0,8(sp)
            jmp     {SPRINTF:#x}
    TABLE:  ; je Eintrag: Etikett (4 B) + Wert
    ''' + ''.join(f'''
            dc.b    {", ".join(str(c) for c in s.encode().ljust(4, bytes(1)))}
            dc.l    {v}''' for v, s in sorted(LABELS.items())))
    code = adone(a); assert len(code) <= 280, len(code); return code

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

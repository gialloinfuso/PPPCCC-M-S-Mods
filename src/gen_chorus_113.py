#!/usr/bin/env python3
"""Tweak 'chorus' fuer die OFFIZIELLE Model:Cycles OS 1.13: Chorus I / II (Juno-Vorbild) auf dem Reverb-Platz.

Port aus v21 (gen_v13 -> gen_v19). Der Klang-Code (Setup, Schleife, Abgriff + Modus-Tabelle) ist Byte fuer Byte der aus
v21 (geprueft in tools: Reproduktion an den OS-2.0-Adressen), nur an anderen Adressen. Bedienung wie v21:
  TRACK halten + Reverb Size drehen: Reverb -> Chorus I -> Chorus II (links zurueck). Namen im Display sofort.
Gespeichert im Einstellungsblock: Byte 0x404e9b5d (0 = Reverb, 1 = Chorus I, 2 = Chorus II). Die Stock-1.13 setzt es nur
beim Zuruecksetzen auf 0 und liest es nie.

Unterschiede zu v21:
  - Haken R direkt an der Reverb-Aufrufstelle des Mixers 0x40056a2c (jsr 0x400579c4); OS 2.0 ging ueber seinen FX-Wrapper,
    dessen Aufruf dieselbe Stack-Belegung hat (ret, out, in, params).
  - Encoder-Haken H4 an 0x400081b8 wie in v21 (tabellengesteuert, hier nur ein Eintrag: Encoder 14, TRACK).
    Spaetere Patches (Digital Delay, Grooves) koennen weitere Eintraege in die Tabelle schreiben (Platz fuer 1 direkt dahinter).
  - Phaser-Modus und Delay-Namen fehlen (eigene Patches).
  - Arbeitsspeicher im Loch hinter dem BSS (0x423380b0..0x4233ffff, ungecachter Spiegel 0x4a33....):
    Chorus-Zustand + Ring 0x4a33a000..0x4a33c02f (R leert 2060 Longs) (in v21 0x4a338100, das ueberdeckt 0x42339000 eines djd_oz-Mods),
    SCRATCH-Byte fuer COPY 0x4a33c040 (in v21 im Datenblock; der passt hier nicht in die kleinere Maske).
  - Masken (alle in keinem bekannten 1.13-Mod belegt, geprueft 25.10.2026):
      Setup 0x40171bc8 (46x31, 184) | Schleife 0x4016ea78 (52x22, 208) | Abgriff+Tabelle 0x401728f8 (46x31)
      Namen 0x40179140 (46x31)       | Daten+Anzeige F0 0x40184988 (46x31) | R+N 0x4018af88 (34x34, 272) | H4+Tabelle 0x4018b1a8 (34x34)
Aufruf: gen_chorus_113.py <section_3_MAIN_OS.bin der Cycles 1.13> <out.json>
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import BASE, matches
import gen_chorus3 as c3
import gen_chorusfx as cf
import gen_fx4 as fx

M_SETUP, M_LOOP, M_TAP = 0x40171BC8, 0x4016EA78, 0x401728F8
M_NAMES, M_DATA, M_UI, M_H4 = 0x40179140, 0x40184988, 0x4018AF88, 0x4018B1A8
SIZE = {M_SETUP: 184, M_LOOP: 208, M_TAP: 184, M_NAMES: 184, M_DATA: 184, M_UI: 272, M_H4: 272}
STATE = 0x4A33A000
SCRATCH = 0x4A33C040
R_HOOK, H_HOOK, REVERB = 0x40056A2C, 0x400081B8, 0x400579C4
ENC_SIZE, MODE = 14, 0x404E9B5D
ENTRY_SLOTS = 2                    # Tabelle: dieser Eintrag + 1 freier (weitere: Tabelle spaeter verlegen, lea in H4)

NAMES = [(b"Cho1 Send", b"CHO1", b"Cho1 Speed", b"Cho1 Depth"),
         (b"Cho2 Send", b"CHO2", b"Cho2 Speed", b"Cho2 Depth")]


def configure(phaser=None, nx=None, razer=None):
    """Konfiguration wie gen_v13 (v21-Klang), Adressen fuer 1.13. phaser = dict(addr=...) -> Modus 3 = Phaser (gen_phaser_113)."""
    c3.MODES = [(8948, 560, 11, 168), (17896, 923, 15, 192)]
    c3.DSHIFT = 5; c3.MAXIDX = 1; c3.EXTRA_OUT = False
    c3.MASK, c3.M_LOOP, c3.M_TAP, c3.STATE, c3.MODE = M_SETUP, M_LOOP, M_TAP, STATE, MODE
    tap0, _ = c3.build_tap()
    c3.M_TAB = (c3.M_TAP + len(tap0) + 3) & ~3
    cf.gc.MASK, cf.gc.STATE = M_SETUP, STATE
    cf.MAGIC = 0x43484F42                     # 'CHOB' wie v13..v21
    cf.KEYS = [2]; cf.PP = False; cf.CMAX = 2; cf.NAMETAB = M_NAMES; cf.NAMES3 = True
    cf.PHASER = (3, phaser['addr']) if phaser else None; cf.N_EXTRA = nx; cf.SWTAB = None; cf.G37 = None
    if phaser: cf.CMAX = 3
    cf.EXTRA_MODES = [(4, razer['addr'])] if razer else []
    if razer: cf.CMAX = 4
    cf.M_UI, cf.M_DATA, cf.SCRATCH, cf.REVERB, cf.MODE = M_UI, M_DATA, SCRATCH, REVERB, MODE
    fx.M_H4, fx.SCRATCH = M_H4, SCRATCH


def names_blob(phaser=None, razer=None):
    """Zeilen je Modus: [Send, Kurz, Speed, Kurz, Depth/Color, Kurz] (24 B). Mit Phaser 4 Zeilen (N maskiert mit 3):
    Zeile 3 Phaser (Strings im Phaser-Bereich phaser['str_at']), Zeile 4 = Kopie von Zeile 1 (nur fuer Muellwerte)."""
    nrows = 4 if phaser else len(NAMES)
    at = M_NAMES + 24 * nrows; strs = b''; pool = {}
    def put(sv):
        nonlocal strs
        if sv not in pool: pool[sv] = at + len(strs); strs += sv + b'\0'
        return pool[sv]
    rows = []
    for send, short, spd, dep in NAMES:
        rows += [put(send), put(short), put(spd), put(b"SPD"), put(dep), put(b"DEP")]
    pstrs = b''
    if phaser:
        pat = phaser['str_at']; ppool = {}
        for sv in phaser['row']:
            if sv in pool: rows.append(pool[sv]); continue
            if sv not in ppool: ppool[sv] = pat + len(pstrs); pstrs += sv + b'\0'
            rows.append(ppool[sv])
        if razer:                               # Zeile 4 = Razer (Strings im Razer-Bereich)
            rat = razer['str_at']; rpool = {}; rstrs = b''
            for sv in razer['row']:
                if sv in pool: rows.append(pool[sv]); continue
                if sv in ppool: rows.append(ppool[sv]); continue
                if sv not in rpool: rpool[sv] = rat + len(rstrs); rstrs += sv + b'\0'
                rows.append(rpool[sv])
            razer['strs'] = rstrs
        else:
            rows += rows[:6]
    return struct.pack('>%dI' % len(rows), *rows) + strs, pstrs


def build(img, phaser=None, nx=None, extra_entries=(), razer=None, h4_xor=False, h4_slow=None, ent_ext=None):
    """phaser: Modus 3 (gen_phaser_113); nx: Adresse der Delay-Namen (N springt am Ende dorthin, gen_digidelay_113);
    extra_entries: weitere H4-Zeilen [enc, Byte, Max, Tasten, invertiert]."""
    configure(phaser, nx, razer)
    cmax = 4 if razer else 3 if phaser else 2
    setup, loop, tap = c3.build()
    tap = tap + bytes(c3.M_TAB - c3.M_TAP - len(tap)) + c3.table()
    data, keys_at, f0 = cf.data_blob(img)
    ui, lab_r = cf.build_r()
    cf.N_ADDR = lab_r['N']
    ent_at = None
    ents = [(ENC_SIZE, MODE, cmax, [2])] + list(extra_entries)
    h4, h_entry, _ = fx.build_h4(ents, lab_r['N'], M_H4, h4_xor, h4_slow)   # Laenge der Codes bestimmen
    ent_at = ent_ext if ent_ext else (M_H4 + len(h4) + 3) & ~3
    h4, h_entry, table = fx.build_h4(ents, lab_r['N'], ent_at, h4_xor, h4_slow)
    h4blob = h4 if ent_ext else h4 + bytes(ent_at - M_H4 - len(h4)) + table
    names, pstrs = names_blob(phaser, razer)
    parts = {M_SETUP: setup, M_LOOP: loop, M_TAP: tap, M_NAMES: names, M_DATA: data, M_UI: ui, M_H4: h4blob}
    for va, b in parts.items():
        assert len(b) <= SIZE[va], (hex(va), len(b), SIZE[va])
    for va, b in ((M_SETUP, setup), (M_LOOP, loop), (M_TAP, tap[:c3.M_TAB - M_TAP]), (M_UI, ui), (M_H4, h4)):
        cf.check_cf(b, va)
    # Platz fuer weitere Eintraege: 20 B je Zeile + 2 B Tasten
    if not ent_ext: assert ent_at + len(table) + (ENTRY_SLOTS - 1 - len(extra_entries)) * 22 <= M_H4 + SIZE[M_H4]
    lab = dict(R=lab_r['R'], N=lab_r['N'], H=h_entry, ent_at=ent_at, f0=f0, keys_at=keys_at)
    if ent_ext: lab['table'] = table
    if phaser: return parts, lab, pstrs
    return parts, lab


def tweak(img):
    parts, lab = build(img)
    sw = lambda va, new: {"off": va - BASE, "old": img[va-BASE:va-BASE+len(new)].hex(), "new": new.hex()}
    jsr = lambda t: bytes.fromhex("4eb9") + struct.pack('>I', t)
    assert matches(img, H_HOOK, (6, '9bb3f43c614c29728d69125a337d8aa2786eb191967f271dfb2a735504ba1f66')), "Encoder-Haken nicht im Originalzustand"
    assert matches(img, R_HOOK, (6, '9bf530a055c2ee426f2dc52032e36ffaa32ea28d91180c12c92927481c159731')), "Reverb-Aufruf nicht im Originalzustand"
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    w = []
    for va, b in parts.items():
        w += [sw(va, b), sprites.redirect_write(va)]
    w += [sw(R_HOOK, jsr(lab['R'])), sw(H_HOOK, jsr(lab['H']))]
    w.sort(key=lambda x: x["off"])
    t = {"id": "chorus", "order": 66, "name": "Chorus I / II auf dem Reverb-Platz (TRACK + Reverb Size)",
         "description": ["TRACK halten + Reverb Size: Reverb -> Chorus I -> Chorus II. Juno-Vorbild, Stereo.",
                         "Einstellung gespeichert (Byte 0x404e9b5d). Erzeugt von gen_chorus_113.py (Klang-Code wie v21)."],
         "device": "Model:Cycles", "os": "1.13", "section": 3,
         "hooks": [f"{R_HOOK:#x}", f"{H_HOOK:#x}"],
         "memory": [{"va": f"{va:#x}", "size": SIZE[va]} for va in parts] +
                   [{"va": f"{STATE:#x}", "size": 0x2030, "ram": True}, {"va": f"{SCRATCH:#x}", "size": 1, "ram": True}],
         "settings": ["0x404e9b5d"],
         "symbols": {k: f"{v:#x}" for k, v in lab.items()},
         "writes": w}
    return t, (parts, lab)


if __name__ == "__main__":
    img = open(sys.argv[1], 'rb').read()
    t, (parts, lab) = tweak(img)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print({f"{va:#x}": len(b) for va, b in parts.items()}, t["symbols"])

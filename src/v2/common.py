"""Gemeinsame Konstanten und Helfer der v2-Generatoren (modulare Struktur, Pip 26.10.2026).

Struktur: 00 core (Dienste) | 01..04 unabhaengig (v1-Generatoren) | 05 reverb-fx, 06 delay-fx, 07 strum, 08 load-meter,
09 groove: jeweils nur core. Jede Mod belegt eigene Masken, eigene Haken und genau einen Platz in der Slot-Tabelle des
Cores (Encoder-Gesten). Gemeinsame Daten: Pattern-Kopf-Bytes 40..63 (Core kopiert/loescht sie), VARS (Popup, PEND).
"""
import json, struct, sys, pathlib, hashlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'solo'))
sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools'))
from gen_solo import A, BASE, orig_bytes, orig_span   # noqa: E402
import gen_solo                                  # noqa: E402
from gen_chorusfx import check_cf                # noqa: E402
import sprites                                   # noqa: E402

# ---- Bedingungen fuer A.bcc
BRA, BSR, HI, LS, CC, CS, NE, EQ, PL, MI, GE, LT, GT, LE = 0x0, 0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0xA, 0xB, 0xC, 0xD, 0xE, 0xF

# ---- Firmware 1.13
HELD, CONSUME, COPY = 0x4007FAF4, 0x400723E0, 0x40044B88
ENC_SKIP = 0x400081E0                 # Encoder-Nachricht verwerfen (Sprung mit lea 12(a7),a7 auf Haken-Ebene)
H_HOOK, H_ORIG = 0x400081B8, (6, '9bb3f43c614c29728d69125a337d8aa2786eb191967f271dfb2a735504ba1f66')   # Laenge + SHA-256 der Originalbefehle (mvs.b 8(a2),d1 ; move.l d1,-(a7))
CUR_PAT = 0x40A7887C                  # *(...) = laufendes Pattern B
HDR = 0x77B2                          # Pattern-Kopf in B (64 Byte)
SEL_A, SEL_B, SEL_C = 0x400CF866, 0x4000EB90, 0x40012412   # ausgewaehlter Track = C(B(A()))
DESC = lambda k: 0x4010DCE0 + 0x38 * k          # Parameter-Deskriptor k: +0x2c Name, +0x34 Kurzname
TIMER = 0xFC07000C                    # DMA-Zeitgeber 0, 135.168 MHz
KEY_FUNC, KEY_TRACK, KEY_MACH, KEY_SET = 1, 2, 5, 13
KEY_RETRIG = 4
ENC_SHAPE, ENC_DSEND, ENC_RSEND, ENC_SWING, ENC_RSIZE, ENC_DTIME = 5, 8, 9, 12, 14, 15

# ---- Pattern-Kopf: Belegung (Byte-Offset im 64-Byte-Kopf). Core kopiert 40..63 beim Laden und loescht sie fuer neue Patterns.
P_HUM_T, P_HUM_V = 40, 46             # groove: Humanize Zeit / Velocity, Track 1..6
P_RFX, P_DFX, P_DSPD, P_GROOVE, P_STRUM = 52, 53, 54, 55, 56
P_PAD = 57                            # smp27: PAD-Spuren (Bits 0..5), pad-mode
P_FSLOPE = 58                         # smp45: track-filter 24 dB (Bits 0..5 = Spur 1..6; 0 = 12 dB)
P_FIRST, P_LAST = 40, 63
P_SIG, SIG = 60, (0x5043, 0x7632)       # Kennung 'PCv2' in 60..63 (Core)

# ---- Core: RAM und Tabellen
VARS = 0x4A33C380                     # Popup + Tasten (ungecacht, UI und Audio)
V_MAGIC, V_KIND, V_VAL, V_DL, V_VC, V_L1, V_L2, V_FN, V_PEND, V_MPEND = 0, 4, 8, 12, 16, 20, 24, 28, 32, 36
ACC = 0x4A33C3C0                      # SLOW: +0 Summe, +4 Ziel, +8 Zeit
CA_SEL = 0x430077FC                   # Control-All-Spurauswahl: gueltig nur mit (Byte & 0xc0) == 0x80, dann Bits 0..5 = Spur ausgenommen;
                                      # sonst alle. smp29 (Pip: standardmaessig immer alle an): letztes Wort des Nutzlast-Platzes
                                      # 'control-mode' (RAM, beim Start 0 = alle; vorher 0x404e9b64 im Einstellungsblock, gespeichert)
CTRL_MODE = 0x404E9B5D                # global (Einstellungsblock, beim Ausschalten gespeichert): CONTROL ALL
CTRL_ABS = 0x5A                       # == CTRL_ABS: absolut; alles andere (0 nach Reset, v1-Reste 1..4): relativ = Firmware
NSLOT = 10
SLOT = {'reverb-fx': 0, 'delay-fx': 1, 'strum': 2, 'load-meter': 3, 'groove': 4, 'control-mode': 5, 'trig-select': 6, 'track-filter': 7,
        'sampler': 8}                      # smp12: sampler = FUNC + SAMPLE START (Fenster verschieben); 9 frei
NKSLOT = 2                            # SETTINGS-Tasten-Slots (Druecken / Loslassen im Hauptbildschirm)
KSLOT = {'control-mode': 0}
NLSLOT = 2                            # smp27: LED-Filter (Core LEDF am Anfang von LED_SET 0x40005f86): Handler(d0 = LED, d1 = Zustand)
LSLOT = {'control-mode': 0, 'pad-mode': 1}   # -> d1 = Zustand; darf d0 / d1 / a0 / a1 aendern
NTKSLOT = 2                           # smp28: Tasten der TrackSelectionView (TRACK gehalten; Core TSVK statt Vtable 0x40100ee8 ->
TKSLOT = {'pad-mode': 0, 'control-mode': 1}   # 0x40024078): Handler(Ansicht, Ereignis) C-Aufruf -> d0 != 0 = behandelt (Reihenfolge = Platz)
TSV_KEY_SLOT, TSV_KEY = 0x40100EE8, 0x40024078
NSSLOT = 5                            # Sound-Slots: Handler (a0 Satz, a1 Sound, d1 = 0 Laden / 1 Speichern) fuer eigene Parameter
SSLOT = {'track-filter': 0, 'lfo-amount': 1, 'sampler': 2, 'core-attack': 3}   # smp23: 4 frei (k 24 / 27 jetzt im Core-Slot 3)
K_EXT0, K_EXT1 = 23, 32               # k 23..32: Parameter ohne Platz in der Firmware (Core: p-locks, LFO-/Velocity-Ziel im Sound)
CM_SU, CM_SCR = 0x4A33C3A8, 0x4A33C3A9   # control-mode: SETTINGS benutzt (Druecken..Loslassen), Byte fuer COPY
# ---- Nutzlast hinter dem MAIN OS (smp14: gehoert dem Core). Der Core legt PAYSZ Nullen hinter das Image und kopiert sie beim
# Start nach PAY (Haken am Anfang der BSS-Loeschung 0x400004b2); jede Mod ueberschreibt nur ihren eigenen Platz.
PAY, IMG_END, PAYSZ = 0x43000000, 0x401AA140, 0x10000
BITMAP_VT = 0x401117C8                # Vtable der Bitmap-Klasse (Konstruktor 0x40070172: +4 Breite, +8 Hoehe, +12 Langworte je
#                                       Spalte, +16 Bild, +20 Maske, +24 Flag; Spalten zu (Hoehe + 31) / 32 Langworten, MSB oben)
PAY_SLOT = {'reverb-fx': (0x0000, 0x6000), 'track-filter': (0x6000, 0x1000), 'control-mode': (0x7000, 0x800), 'pad-mode': (0x7800, 0x800), 'strings': (0x8000, 0x3000), 'sampler': (0xB000, 0x1000), 'core': (0xC000, 0x2000),
            'mono': (0xE000, 0x2000)}
# ---- smp18: Deskriptor-Tabelle in der Nutzlast des Cores (Start-Kopie der 76 der Firmware + Erweiterung 76..NDESC-1), nach
# Modded-Cycles notes/18-19 (MIT; eigener Code). Maschinen-Mods schreiben ihre Eintraege (DESC_SLOT), Spender-Objekte (DONOR,
# Anzeige-Zustand eines Firmware-Deskriptors) und Maschine (MACHMAP, 0xff = Feld des Deskriptors) beim Bauen in die Tabellen.
NDESC0, NDESC = 76, 96
CORE_ORG = PAY + 0xC000
DTAB = CORE_ORG                       # NDESC x 0x38
DONOR = CORE_ORG + 0x1500             # (NDESC - 76) Bytes: Index des Anzeige-Objekts
MACHMAP = CORE_ORG + 0x1520           # (NDESC - 76) Bytes: Maschine (0xff = Feld 0 des Deskriptors)
LKXT = CORE_ORG + 0x1540              # 8 x (Maschine.b, Knopf.b, Deskriptor.w): FUNC + Knopf auf der Maschine -> Deskriptor
NLKX = 8
FMTX = CORE_ORG + 0x1560              # smp23: (NDESC - 76) Zeiger: Formatierer je eigenem Deskriptor (0 = der des Anzeige-Objekts);
                                      # ST_AT / ST_CN setzen ihn ins Anzeige-Objekt (+0x20, +0x2c = 0)
LSLOTS = CORE_ORG + 0x15C0              # smp27: NLSLOT Zeiger (LED-Filter)
TKSLOTS = CORE_ORG + 0x15C8             # smp28: NTKSLOT Zeiger (Tasten der TrackSelectionView)
STYX = CORE_ORG + 0x15D0                # smp30: (NDESC - 76) Bytes: Darstellung des Werts je eigenem Deskriptor (0 = die des Objekts,
STYLES = (0x40EA1478,)                  # Bits 0..6: 1.. = STYLES[n-1] ins Anzeige-Objekt +0x10; 0x40ea1478 = die von Trig Cond / Mult / Wave
                                        # (Text: Stil +8 = 6 statt 3 der Zahlen 0x40ea1494; wirkt nicht aufs Popup)
STY_PFONT = 0x80                        # smp32: Bit 7 = Popup-Wert (0x4001d818, Haken 0x4001d8a8) in der schmalen grossen Schrift
PSXT, NPSX = CORE_ORG + 0x15E4, 7     # smp37: Parameter-Suche (Core PSX, 0x4005a6d0): 7 x (Maschine.b, k.b, Deskriptor.w), Maschine 0xff = frei
PSX_SLOT = {'strum': (0, 4)}
FONT_BIG, FONT_NARROW = 0x401429EC, 0x40141B08   # Popup: 0x401429ec (Zeichen 16 px, nur 3 passen), 0x40141b08 (schmal, 5 passen)
CORE_CODE = CORE_ORG + 0x1600
DTD = lambda k: DTAB + 0x38 * k       # Deskriptor k in der Kopie (Laufzeit)
PIMG = lambda ram: IMG_END + ram - PAY   # Adresse in der Nutzlast (RAM) -> Lage im Image (zum Schreiben beim Bauen)
DESC_SLOT = {'strings': (76, 4), 'mono': (80, 6), 'strum': (86, 4)}
LKX_SLOT = {'mono': (0, 2), 'strum': (2, 4)}
K_STIME, K_SPAT = 24, 27              # smp23: Strum-Abstand / -Pattern auf CHORD / Vlvt = k 24 / 27 (auf Monom Glide / Noise);
                                      # gespeichert vom Core (Satz +80 / +81, Sound-Slot 3)
# smp23: Strum (g2_strum fuer CHORD, g2_strings fuer Vlvt - jeder mit eigenem Code, nur die Werte sind gemeinsam)
TEMPO = 0x40149310                    # Tempo in 1/120 BPM (Modded-Cycles notes/38)
# smp36 (Pip: 'erst die Millisekunden und danach die Notenwerte hintendran'): 0 = OFF, 1..STRUM_NMS = ms (Anzeige Zahl, bis 250 ms),
# danach die 17 Notenwerte von Patch 04 delay-notes (aufsteigend, Laenge (p + 1) / 128 ganze Note, Triolen exakt), Anzeige deren
# Etikett. (smp33/34: versehentlich Tabelle der Trig-Laenge; smp35: alle 127 Werte der Delay Time.)
STRUM_LABELS = {127: "1/1", 63: "1/2", 31: "1/4", 15: "1/8", 7: "/16", 3: "/32", 1: "/64",
                95: "2.", 47: "4.", 23: "8.", 11: "16.", 5: "32.",
                84: "1T", 41: "2T", 20: "4T", 9: "8T", 4: "16T"}          # wie solo/gen_delaynotes.LABELS
STRUM_TRIP = {4: 2, 20: 2, 84: 2, 9: 4, 41: 4}                            # + 1/3 bzw. 2/3 Schritt (in 1/768 ganzer Note)
STRUM_PATS = ('UP', 'DOWN', 'RND', '1324', '1423', '4132', '4231', 'ROOT', 'TOP')   # smp37: ROOT = 1-234, TOP = 4-123
STRUM_RND = 2
STRUM_FADE_MIN = 0x100000              # smp39: Ton vor seinem Einsatz blendet * 3/4 je Block aus (statt sofort 0), darunter 0
STRUM_RANKS = {0: (0, 1, 2, 3), 1: (3, 2, 1, 0), 3: (0, 2, 1, 3), 4: (0, 2, 3, 1), 5: (1, 3, 2, 0), 6: (3, 1, 2, 0), 7: (0, 1, 1, 1), 8: (1, 1, 1, 0)}  # Rang je Ton
STRUM_NMS = 110                       # 1..110 = ms (je 250 / 110 ms; 3000 / 110 Achtel-Bloecke)
STRUM_NOTEP = tuple(sorted(STRUM_LABELS))   # 111..127 -> Delay-Wert p dieser Notenwerte (/64 .. 1/1)
assert STRUM_NMS + len(STRUM_NOTEP) == 127
STRUM_KC = 450000                     # 1/8 Bloecke je 1/768 ganze Note bei Tempo 1 (1/16 = 48 Einheiten = 21.6e6 / Tempo)



SEL_BLINK_BIT = 24                     # smp41: Auswahl-LEDs blinken schnell wie trig-select (Zeitgeber-Bit 24 = 4 Hz)


def blink_state(reg, u):
    """cfasm-Text: reg = LED-Zustand einer gewaehlten LED, schnell blinkend: 2 (an) / 1 (aus) nach Zeitgeber-Bit 24"""
    return f'''
            move.l  {TIMER:#x},{reg}
            btst    #{SEL_BLINK_BIT},{reg}
            beq     {u}o
            moveq   #2,{reg}
            bra     {u}d
    {u}o:   moveq   #1,{reg}
    {u}d:
'''


def ca_skip(dt, t1, t2, skip, u):
    """cfasm-Text: Spur dt laut CA_SEL ausgenommen -> bra skip (t1 / t2 werden zerstoert, u = eindeutiges Label-Kuerzel)"""
    return f'''
            mvz.b   {CA_SEL:#x},{t1}
            move.l  {t1},{t2}
            andi.l  #0xc0,{t2}
            cmpi.l  #0x80,{t2}
            bne     {u}ok
            btst    {dt},{t1}
            bne     {skip}
    {u}ok:
'''


def strum_units(p):
    """Delay-Wert p (wie Patch 04) -> Laenge in 1/768 ganzer Note"""
    p = min(p, 127)
    return 6 * (p + 1) + STRUM_TRIP.get(p, 0)


def strum_text(v):
    if v <= 0: return 'OFF'
    if v <= STRUM_NMS: return str((v * 250 + STRUM_NMS // 2) // STRUM_NMS)
    return STRUM_LABELS[STRUM_NOTEP[min(v, 127) - STRUM_NMS - 1]]


def strum_step8(v, tempo=14400):
    """Wert 0..127 -> Abstand in 1/8 Bloecken (32 Samples je Block) wie STEP8 / SSTEP"""
    if v <= 0: return 0
    if v <= STRUM_NMS: return v * 3000 // STRUM_NMS
    if not tempo: return 0
    return STRUM_KC * strum_units(STRUM_NOTEP[min(v, 127) - STRUM_NMS - 1]) // tempo


def strum_rtab():
    return b''.join(bytes(STRUM_RANKS.get(m, (0, 1, 2, 3))) for m in range(len(STRUM_PATS)))


def icon(path):
    """Eigene Grafik (BMP, 1 Bit; Schwarz = Pixel an) -> (Breite, Hoehe, Bild im Format der Firmware)"""
    from PIL import Image
    im = Image.open(path).convert('L'); w, h = im.size; n = (h + 31) // 32
    out = b''
    for x in range(w):
        col = 0
        for y in range(h):
            if im.getpixel((x, y)) < 128: col |= 1 << (32 * n - 1 - y)
        out += col.to_bytes(4 * n, 'big')
    return w, h, out


def bitmap(w, h, img, mask):
    """Bitmap-Objekt (28 B) wie der Konstruktor 0x40070172, statisch (Flag 0)"""
    return struct.pack('>6IB3x', BITMAP_VT, w, h, (h + 31) // 32, img, mask, 0)


# Popup-Arten fuer OVS
OV_HIDE, OV_NUM, OV_TEXT, OV_CUSTOM = 0, 1, 2, 3

jsr = lambda t: bytes.fromhex("4eb9") + struct.pack('>I', t)
jmp = lambda t: bytes.fromhex("4ef9") + struct.pack('>I', t)


def apply(img, t):
    """Patch (Entwicklungsformat mit 'old') auf ein Image anwenden, 'old' pruefen."""
    b = bytearray(img)
    for x in t['writes']:
        o = bytes.fromhex(x['old']); n = bytes.fromhex(x['new'])
        assert b[x['off']:x['off'] + len(o)] == o, (t['id'], hex(x['off'] + BASE))
        b[x['off']:x['off'] + len(n)] = n
    return bytes(b)


class Writes:
    """Sammelt Schreibstellen gegen ein Basis-Image (old = Bytes der Basis)."""
    def __init__(s, base):
        s.base, s.w, s.masks = base, [], []
    def put(s, va, new):
        s.w.append({"off": va - BASE, "old": bytes(s.base[va - BASE:va - BASE + len(new)]).hex(), "new": bytes(new).hex()})
    def mask(s, va, blob, size):
        assert len(blob) <= size, (hex(va), len(blob), size)
        assert sprites.MASKS[va][0] == size, hex(va)
        s.put(va, blob); s.w.append(sprites.redirect_write(va)); s.masks.append({"va": f"{va:#x}", "size": size})
    def hook(s, va, ck, new):
        """ck = (Laenge, SHA-256-Hex) der erwarteten Original-Bytes (keine Original-Bytes im Quelltext), oder Bytes, die nur
        aus einer Adresse gebaut sind (Vtable-Eintrag, jsr <Funktion>)."""
        if isinstance(ck, tuple):
            n, h = ck
            ok = hashlib.sha256(bytes(s.base[va - BASE:va - BASE + n])).hexdigest() == h
        else:
            ok = bytes(s.base[va - BASE:va - BASE + len(ck)]) == ck
        assert ok, f"Haken {va:#x} nicht im Originalzustand"
        s.put(va, new)
    def sorted(s):
        return sorted(s.w, key=lambda x: x["off"])


def patch(pid, order, name, desc, W, **kw):
    t = {"id": pid, "order": order, "name": name, "description": desc, "device": "Model:Cycles", "os": "1.13", "section": 3}
    t.update(kw)
    mem = list(W.masks) + kw.get('memory', [])
    t['memory'] = mem
    t['writes'] = W.sorted()
    return t


def annotate(t):
    """Dev-Format: jeder Write bekommt 'orig' = [[at, Quell-Offset, n], ...] fuer die Bytes, die Original-Bytes der Firmware
    sind (gen_solo.ORIGS). Der Export ersetzt sie durch Platzhalter."""
    # Code der Nutzlast laeuft an 0x43000000, liegt im Image aber hinter IMG_END: Ziel-VA umrechnen
    spans = sorted({(IMG_END + tv - PAY if PAY <= tv < PAY + PAYSZ else tv, sv, n) for tv, sv, n in gen_solo.ORIGS})
    for w in t['writes']:
        va = w['off'] + BASE; new = bytes.fromhex(w['new']); got = []
        for tv, sv, n in spans:
            if va <= tv and tv + n <= va + len(new) and new[tv - va:tv - va + n] == orig_bytes(sv, n):
                got.append([tv - va, sv - BASE, n])
        got = sorted({tuple(g) for g in got})
        for a, b in zip(got, got[1:]):
            assert a[0] + a[2] <= b[0], (t['id'], hex(va), a, b)
        if got: w['orig'] = [list(g) for g in got]
        elif 'orig' in w: del w['orig']
    return t


def stock():
    return open(ROOT / 'out' / 'section_3_MAIN_OS.bin', 'rb').read()


def save(t, path):
    pathlib.Path(path).write_text(json.dumps(t, indent=1) + "\n")


def asm2(org, text, tail=None):
    """cfasm zweimal: erst Laenge, dann mit den Adressen der Daten hinter dem Code (tail(Codeende) -> (Bytes, {Name: Adresse}))"""
    import collections
    from cfasm import asm, done as adone
    a = A(org); asm(a, text, collections.defaultdict(int)); n = len(a.b)
    data, ext = tail(org + n) if tail else (b'', {})
    a = A(org); asm(a, text, ext)
    code = adone(a, ext)
    check_cf(code, org)
    return code + data, dict(a.lab, **ext)

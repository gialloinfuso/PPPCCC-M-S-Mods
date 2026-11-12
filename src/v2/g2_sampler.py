#!/usr/bin/env python3
"""Mod 'sampler' (v2, Patch 16): 7. Maschine 'Sampl', ein einfacher Sampler im Stil der Model:Samples mit SP-1200-Charakter.
Braucht den Core (Sound-Slot fuer die Sample-Kennung).

Bedienung (Pip 30.10.2026, smp4 31.10.):
  MACHINES: 'Sampl' als 7. Maschine. FUNC + MACHINES (Preset-Browser) auf einer Sampl-Spur: eine Sample-Datei waehlen
    (Presets laden wie immer; Schritt halten = Sample-Lock). Der Sound heisst wie die Datei.
  PITCH, DECAY (Amp-Huellkurve der Firmware), COLOR = Sample Start, SHAPE = Sample End (smp12; FUNC + COLOR verschiebt beide), SWEEP frei, CONTOUR = Modell.
  PUNCH-Taste = Loop, GATE-Taste = Reverse (smp8, wie LOOP / REVERSE der Model:Samples; auf der Sampl-Spur kein Gate, kein Punch).
  Modell (smp4, feste Werte statt des Vintage-Knopfs): CLEAN (lineare Interpolation), SP (26 kHz fester Takt, Drop-Sample,
    12 Bit, heiss, 4-Pol 12 kHz), LM (28 kHz Takt mit der Tonhoehe, 8 Bit mu-law, 2-Pol 11 kHz). Die Wandler-Modelle nutzen das
    smp3-Raster (Wert zum genauen Takt-Zeitpunkt, polyBLEP-Kanten) und danach Biquads als Rekonstruktions-Filter.
  Wellenform (smp4, Pip: "nur beim Drehen sichtbar"): solange das Popup von COLOR / SHAPE offen ist, statt des Popups die
    Uebersicht des Samples (128 Spalten min / max, beim Laden berechnet), Linien bei Start und Ende, davor / dahinter gedimmt.
  smp5 (Pip 01.11.): Sample-Lock (Trig halten + Sample im Browser) lockt nur das Sample, alle anderen Parameter folgen der
    Spur, echte p-locks bleiben (SLK). Length = Anteil des Rests ab Start (smp10 zurueck, Pip: Start und Length unabhaengig:
    Length = Anteil des ganzen Samples, am Ende begrenzt, wie beim Model:Samples). Browser: auf einer Sampl-Spur ist die Datei unter dem Cursor sofort das Sample
    der Spur (zum Durchhoeren; YES wie bisher), nicht mit gehaltenem Trig. Die Kennung kommt jetzt aus dem Sound der Spur im Kit
    der Klangerzeugung (0x800017e4), mit Lock aus OVR.
Samples: Elektron-Format auf der +Drive (64-Byte-Kopf: +1 Stereo, +4 Bytes, +8 Rate; 16 Bit big endian; Stereo -> Mono).
  Kennung = Inhalts-Kennung des Dateisystems (Sound k 25/26 = +70, Satz +76..+79 ueber den Sound-Slot des Cores).
  Laden im UI-Task (Haken 0x400075f0, je Bild 64 KB) in den Speicher 0x43801000..0x46700000, bis 16 Samples, ohne
  Freigeben (bis zum Neustart). Im Browser Gewaehltes zuerst, sonst die Samples der 6 Spuren des Kits.
  Schutz (wie durchgemachts model27-SAMPLE, MIT, hardware-getestet): das Bild kommt auch aus einer zweiten Task -> TAS-
  Sperre BUSY; laeuft die Task schon im Dateisystem (Sperre 0x40fe6df0 haelt sie), keine Datei-Aufrufe (die Sperre
  zaehlt nicht); Index-Suche 0x4007dc30 nur unter der Sperre; nur ungerade Kennungen (Dateien).
Firmware 1.13 (eigene Analyse; Bestandsliste der Maschinen-Grenzen nach Modded-Cycles notes/18, MIT; eigener Code):
  Grenzen 5 -> 6 (Stimmen-Schleife 0x400a7dba / 0x400a7df4, Parameter-Suche 0x4005a6a6, 'Maschine?' 0x4005a572,
  Konstruktor 0x4005a340, Maschine setzen 0x400147a4, Rad 0x400148aa / 0x400148b2, MACHINES-Bild 0x400a25e0,
  7 Positionen 0x400a26e8), Algorithm-Max 6, Zeilen (BSS 0x40a79418, 5 Verweise) in eine Maske mit 7 Zeilen (Zeile 6:
  Decay = Deskriptor 24), update / render mit 7 Eintraegen, Byte 0x40118646 = 6, 8. Maschinen-Satz (0x4004df5c / 0x4004df76)
  beim ersten Gebrauch aus dem von SNARE, Knopf-Vektor (0x4001e8da), Namen (0x400a2614), Bilder (0x400a2638, die von SNARE).
  Deskriptoren 10, 11, 13 (frei: Maschine -1, nur MIDI-Notizen) = Start, Length, Modell (0..2, eigener Formatierer) fuer
  Maschine 6, ohne CC. Anzeige: Vtable 0x4010053c (Zeichnen der Parameter-Ansicht, 0x4001e40a), UI +0x58 / +0x164.
Aufruf: g2_sampler.py [out.json]
"""
import collections, math, struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import g2_dtab as DT
import cfemac as E
from cfasm import asm, done as adone

MACH = 6
MNAME = 'Grit'                       # Name im MACHINES-Menue (Pip 03.11.: 'Grit', vorher 'Sampl'; hoechstens 5 Zeichen)
# ---- Masken (frei; die des geparkten Hochpasses bleiben frei)
M_REG, M_REC, M_VOX, M_TRG, M_TRG2, M_BLK, M_BLK2, M_RND, M_CLN, M_RAS = (
    0x40168DA4, 0x4016BCD8, 0x4016DAB8, 0x4016FAE8, 0x40177F28, 0x40178708, 0x40183408, 0x401792B0, 0x40178FC0, 0x40184AF8)
M_BLK3, M_RAS2 = 0x40184C78, 0x40187528
M_RAS3, M_RAS4 = 0x401876A8, 0x40188F98                        # smp3: Raster-Takt, Ende / Loop
M_BQ, M_RAS5, M_BQ2 = 0x4018A608, 0x4018B9C8, 0x4018BB48          # smp4: Biquads, SP-Raster / mu-law, letzte Stufe
M_LOV, M_LOV2, M_KD, M_KD2, M_KD3 = 0x4018CBC8, 0x40190184, 0x4018D038, 0x4018D798, 0x4018F80C   # smp4: Uebersicht, Anzeige
M_SLK, M_BRT, M_BRN = 0x40190334, 0x4019089C, 0x40192A24        # smp5: Sample-Lock, Browser-Vorschau
M_BRP, M_BRL = 0x4016FD60, 0x40172510                            # smp5: dazu zwei 124-B-Masken (31x22)
# smp5: M_EV, M_EV2 = 0x40178888, 0x40179A20 (Platz freigeben, 124 B) - smp28 frei (LEVICT in der Nutzlast)
M_FL, M_FL2, M_FL3, M_FL4, M_FG = 0x401837D8, 0x401871A0, 0x40189838, 0x4018A510, 0x4018BCC8   # smp7: SWEEP-Filter
M_BSH, M_BSH2, M_BSH3 = 0x401698D0, 0x401630E4, 0x401638C0                                                    # smp12: FUNC + Start (108 / 104 B)
M_FL5, M_FL6, M_FL7, M_FL8 = 0x40160A94, 0x401617A8, 0x40161880, 0x401629DC                                       # smp8: Filter am Wandler, Blenden (108 B)
M_LD, M_LK, M_LS, M_LS2, M_LF, M_LC, M_LC2, M_BR, M_BR2 = (
    0x40170C48, 0x40179430, 0x40171A48, 0x401795B0, 0x40179B18, 0x40172BE8, 0x4017C97C, 0x401736C8, 0x401829B8)
M_ROWS, M_CT, M_VT, M_DAT, M_STR = 0x40186238, 0x4018B1A8, 0x4018D1B8, 0x40192BA4, 0x40184988
SIZE = {M_REG: 192, M_REC: 192, M_VOX: 192, M_TRG: 192, M_TRG2: 192, M_BLK: 192, M_BLK2: 192, M_BLK3: 192, M_RND: 192, M_CLN: 192, M_RAS: 192, M_RAS2: 192,
        M_RAS3: 192, M_RAS4: 192, M_BQ: 192, M_RAS5: 192, M_BQ2: 192, M_LOV: 192, M_LOV2: 192, M_SLK: 192, M_BRT: 192, M_BRN: 192, M_BRP: 124, M_BRL: 124, M_FL: 124, M_FL2: 124, M_FL3: 124, M_FL4: 124, M_FL5: 108, M_FL6: 108, M_FL7: 108, M_FL8: 108, M_BSH: 108, M_BSH2: 104, M_BSH3: 104, M_FG: 124, M_KD: 192, M_KD2: 192, M_KD3: 192,
        M_LD: 192, M_LK: 192, M_LS: 192, M_LS2: 192, M_LF: 192, M_LC: 192, M_LC2: 192, M_BR: 192, M_BR2: 192,
        M_ROWS: 272, M_CT: 272, M_VT: 376, M_DAT: 272, M_STR: 184}
# ---- Firmware 1.13
DESC0, DSTRIDE = 0x4010DCE0, 0x38
D_START, D_LEN, D_VIN, D_DEC = 10, 11, 13, 24        # Deskriptoren der Maschine 6
D_SWP = 12                                            # smp7: SWEEP = Filter (Mitte aus, links LP, rechts HP)
SNARE_GROUP = 0x4012996F
ROWS = 0x40A79418
ROW_REFS = (0x4005A2BE, 0x4005A322, 0x4005A390, 0x4005A6BA, 0x4005A6F0)   # 32-Bit-Feld (pea / lea)
NAMES, NAMES_REF = 0x401177E4, 0x400A2614
UPD_TAB, RND_TAB, UPD_REF, RND_REF, MAP6 = 0x40118628, 0x40118610, 0x400A7D6C, 0x400A7E16, 0x40118646
UPD_ORIG = (0x400AA08C, 0x400AB3B0, 0x400AA49C, 0x400AA998, 0x400AA7B8, 0x400AAE88)
RND_ORIG = (0x400AA3C4, 0x400AB6E8, 0x400AA712, 0x400AACC2, 0x400AA930, 0x400AB24C)
NAMES_ORIG = (0x401300D8, 0x401300DD, 0x401300E3, 0x401300E9, 0x40129960, 0x401300EE)
ALG_MAX = DESC0 + 41 * DSTRIDE + 0x0C
SH5 = 'c55bd639d8c368e737cdc6bb17522f91dbe1f51682d2433f4caa962e6ca77513'   # 2 B (moveq #5,d1)
SH5D0 = '63540692485e9982808a3ad2d9eda3ef9f9b6b45ea3d491ee894cc3f0b7579e9'  # 2 B (moveq #5,d0)
BOUNDS = ((0x4005A6A6, SH5, 0x7206), (0x4005A572, SH5, 0x7206), (0x400147A4, SH5D0, 0x7006),   # 0x4005a340: Core (BROW, smp18)
          (0x400148AA, SH5, 0x7206), (0x400148B2, SH5D0, 0x7006), (0x400A25E0, SH5D0, 0x7006), (0x400A7DBA, SH5, 0x7206),
          (0x400A7DF4, SH5D0, 0x7006),
          (0x400A26E8, 'ac3d4b0bb4df327dd5710a5d34c2e603f24f8a3ec2c916e5387afd0c746500a1', 0x7007))
MAP_CK = (1, '6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d')
IMG_HOOK, IMG_CK, IMG_RET = 0x400A2638, (6, '64407bcc1962da4bba1b9c7214692cabe14531e1f52f2ef396a8085feaef92e2'), 0x400A2680
RAT_HOOK, RAT_CK, RAT_RET = 0x4004DF5C, (6, '90d4add99e5a31399efe8b6d7879deb65375e21f97ebcdfd761b45d0fa6f5b13'), 0x4004DF68
ROF_HOOK, ROF_CK, ROF_RET = 0x4004DF76, (6, 'ee3af96091c4b93c7521b8497449ed07268395479720ba1a8e05987f14d25a60'), 0x4004DF7C
KV_HOOK, KV_CK = 0x4001E8DA, (8, 'bd86ecbf671d05230031fd85644b4bfabb6fe9e20eebfb116814426938e04091')
REC_BASE, OBJ_BASE = 0x40A71540, 0x40A71754
REC_SNARE = REC_BASE + 2 * 76
STRCOPY, SPRINTF = 0x400F8F02, 0x40000E6E
# Anzeige: Vtable-Eintrag 'zeichnen' der Parameter-Ansicht (einziger Verweis auf 0x4001e40a), UI-Zustand (+0x58 Deskriptor
# des Popups, +0x164 Trig gehalten), Zeichenfunktionen (Rechteck fuellen: Farbe 1 / 0 / -1 umkehren; Text: Flags 0 links,
# 4 rechts) und Schrift der Parameternamen
VT_KDRAW, KDRAW_ORIG, UIGET = 0x4010053C, 0x4001E40A, 0x400CF9A8
KDLAB = ('Start', 'End')
# smp5: Uebernahme eines Trigs in die Klangerzeugung (0x400590ce: a1 Kit, a2 Ereignis, a5 Sound, d2 Spur; danach nur d0 =
# Spur + 0x93 gebraucht, d1 / a0 / a1 frei), Kit der Klangerzeugung, Preset-Browser (Vtable 0x401183ec: +0x94 Takt; Liste
# +0x278 aktiv / +0x280 Dateien, Cursor +0x10 (vt+0x4c bekommt ihn als 2. Argument); Eintrag 0x4007cdd4(a0 = Ziel; Liste, Index), Liste vt+0x20 = Datei?)
SL_HOOK, SL_CK = 0x400590CE, (8, 'aa4df412ca3fdbdd8246404e89f87471eeafcf0a8e9e587f3170b1123af28055')
KITA = 0x800017E4
VT_CUR, BR_CUR, FL_ENTRY = 0x40118438, 0x400A64BE, 0x4007CDD4   # smp7: Cursor bewegt (vt[19]), statt des Takts (smp5)
HBUF = 0x43800300                    # Arbeitsbereich SCR + 0x300 (16 B Datei-Kopf)
FILL_F, TXT_F, F_NAME, FMT_S, FMT_D = 0x40070DEA, 0x40071A04, 0x40EA14D4, 0x40124B58, 0x4012A9EA
FMT_OFF = 0x40045BD6                 # Formatierer der Firmware: Mitte -> OFF, sonst Wert - 64 (wie Filter Env)
SPRITE, ICON_A, ICON_B = 0x40071DA4, 0x40FE32CC, 0x40FE384C
AMPENV, VCA, DECLUT = 0x400A9252, 0x400A9430, 0x4011D84C
VOICE0, VSTRIDE, TGT0 = 0x42308828, 0x31C, 0x800015AE
BR_HOOK, PARSE = 0x400A6602, 0x400A3052
TK_HOOK, VCRENDER = 0x400075F0, 0x40076BE4
ACT_TRACK, KITP = 0x40A700C4, 0x40A78888
FS_MOUNT, FS_FIND, FS_IDX, FS_STAT, FS_OPEN, FS_READ, FS_CLOSE, FS_PATH = (
    0x40F07CF4, 0x4007DC30, 0x401FB8A8, 0x4007DE78, 0x4007E4F4, 0x4007BAAA, 0x4007BC1C, 0x4007AFD4)
NEW, SPVT = 0x400802E0, 0x400FD048
# Sperre des Dateisystems (0x40001cc4 nehmen / 0x40001df6 freigeben; +0 Halter, nicht zaehlend: ein inneres Freigeben
# gibt sie ganz frei) und laufende Task (0x422fef30)
FS_LOCKO, FS_LOCK, FS_UNLOCK, RUNNING = 0x40FE6DF0, 0x40001CC4, 0x40001DF6, 0x422FEF30
# ---- Speicher
SCR = 0x43800000                     # Arbeitsbereich: +0 Pfad (256 B), +0x100 Kopf (64 B)
POOL0, POOL_END = 0x43801000, 0x46700000
NTAB = 32                            # Tabelle: +0 Kennung, +4 Daten, +8 Frames, +12 Rate (16.16, 48 kHz = 1.0); smp28: 32 (vorher 16)
NFAIL = 16                           # smp28: Fehl-Ring (vorher 4)
CHUNK = 0x10000
K_ID = 25                            # Sound +70 (k 25/26)
O_ID = 20 + 2 * K_ID
# ---- Stimme (Bereich der FM-Operatoren; die Firmware loescht +0x6c / +0xe4 beim Trig, nicht diese Felder)
V = dict(PTR=0x70, ST=0x74, SPAN=0x78, POS=0x7C, FRAC=0x80, INCI=0x84, INCF=0x88, PH=0x8C, TINC=0x90, HELD=0x94,
         MF=0x98, Q8=0x9C, FLAGS=0xA0, LEN=0xA4, RF=0xA8, GAIN=0xAC, MASK=0xB0, PG=0xB4, ROW=0xB8, VIN=0xBC,
         P=0xC0, KINV=0xC4, INC6=0xC8, H0=0xE8,
         FW=0x118, FI=0x11C, FA1=0x120, FA2=0x124, FA3=0x128, IC1=0x12C, IC2=0x130)   # smp7: SWEEP-Filter
# smp3: P = polyBLEP-Rest fuer das naechste Sample, KINV = 2^32 / (Raster-Schritt >> 16), INC6 = Schritt (16.16) >> 6.
# smp4: MF = Modell-Flags, Q8 = Raster des Wandlers in Datei-Samples (24.8, SP), ROW = Modell-Zeile, H0.. = Zustaende der
# Biquads (x1 x2 y1 y2 je Stufe, 3 Stufen = 0xe8..0x117; die Firmware schreibt im Betrieb nur 0x6c / 0xe4 / 0x15c / 0x1d4 und loescht beim
# Maschinenwechsel alles, geprueft)
F_LOOP, F_PLAY, F_REV = 0, 1, 2
KNOBS = ((D_START, 11, 0, 0x28, 'Sample Start', 'STRT'), (D_LEN, 12, 0x7F00, 0x32, 'Sample End', 'END'),
         (D_VIN, 14, 0, 0x46, 'Model', 'MODL'), (D_SWP, 13, 0x4000, 0x3C, 'Filter', 'FILT'))
NFG = 62                             # smp7: Grenzfrequenzen des SWEEP-Filters (20 Hz .. 16 kHz, logarithmisch)
K30 = int(round(math.sqrt(2) * 2 ** 30))
SHK = int(round(2 ** 6 / math.log2(800 ** (1 / (61)))))   # smp8: Stufen je Oktave * 64 (log2 Q16 * SHK >> 22)


# smp10 (Pip: "Namen der Vintage-Modelle zu lang / Schrift zu gross"): Anzeige mit hoechstens 3 Zeichen
MSHORT = ('CLN', 'SP', 'LM', 'MIR', 'TX', 'MPC')


def fg_values():
    return [min(int(round(math.tan(math.pi * 20 * 800 ** (i / (NFG - 1)) / 48000) * 32768)), 65535) for i in range(NFG)]


# ---------------- Modelle (smp4: CONTOUR = Modell, feste Werte; Pip 31.10.2026 "feste Werte fuer die Modelle")
# Clean = lineare Interpolation (SCLN). Die anderen: Wandler mit eigenem Takt (smp3-Raster: Wert am Takt-Zeitpunkt,
# polyBLEP-Kanten), Eingang / Clip / Bits oder mu-law, danach ein Rekonstruktions-Filter (Biquads, bilinear, Q30-Bereich).
#   SP: 26.04 kHz fester Takt (nicht mit der Tonhoehe), Drop-Sample (Position auf das Raster des Wandlers abgerundet),
#       12 Bit, +3 dB heiss in den Clip (ein Viertel ausgeglichen), 4-Pol-Butterworth 12 kHz.
#   LM: 28 kHz Takt mit der Tonhoehe (wie ein umgestimmter Takt), 8 Bit mu-law (8 Segmente zu 16 Stufen), 2 Pol 11 kHz.
#   MIRAGE (smp6): 29.4 kHz mit der Tonhoehe, 8 Bit linear, +2 dB, 2 Pol 8 kHz mit leichter Resonanz (Q 1.2).
#       (Der Emulator II wandelt companded wie LM; das rohe lineare 8 Bit ist der eigene Charakter.)
#   TX16W (smp6): 33.3 kHz fest + Drop-Sample (wie SP), 12 Bit Gleitkomma (12 Bit Mantisse: Schritt waechst mit dem Pegel),
#       +1 dB, 2 Pol 12.5 kHz (Q 1.0).
#   MPC60 (smp6): 40 kHz mit der Tonhoehe, 12 Bit Gleitkomma (nichtlineare Wandlung), +1.5 dB, 2 Pol 15 kHz (Q 0.6).
MF_TRACK, MF_GRID, MF_MULAW = 0, 1, 2
MODELS = (
    dict(name='CLEAN'),
    dict(name='SP', rate=26040, flags=1 << MF_GRID, bits=12, gain_db=3.0, filt=((0.5412, 12000), (1.3066, 12000))),
    dict(name='LM', rate=28000, flags=(1 << MF_TRACK) | (1 << MF_MULAW), bits=16, gain_db=0.0, filt=((0.7071, 11000),)),
    # smp6 (Pip: "die anderen Sampler-Typen auch bauen": Emulator II / Mirage, TX16W, MPC60)
    dict(name='MIRAGE', rate=29400, flags=1 << MF_TRACK, bits=8, gain_db=2.0, filt=((1.2, 8000),)),
    dict(name='TX16W', rate=33300, flags=(1 << MF_GRID) | (1 << MF_MULAW), seg=1, bits=16, gain_db=1.0, filt=((1.0, 12500),)),
    dict(name='MPC60', rate=40000, flags=(1 << MF_TRACK) | (1 << MF_MULAW), seg=1, bits=16, gain_db=1.5, filt=((0.6, 15000),)),
)
SEGN = 129                           # Segment-Tabellen (Betrag >> 8): 0 = mu-law (LM), 1 = 12-Bit-Gleitkomma (TX16W, MPC60)
SEGS = 129                           # Abstand der Tabellen (Zeile +14 = Tabelle * SEGS)
NMOD = len(MODELS)
ROWB, MAXST = 52, 3                  # Zeile: +0 R16, +2 Flags, +4 Gain 8.8, +6 Nachverst. Q15, +8 Maske, +12 Stufen, +14 Segment-Tab.,
#                                      +16 je Stufe b0 (Q31), a1 / 2 (Q31, mit <<), a2 (Q31)


def biquad(q, fc, fs=48000):
    """Tiefpass 2. Ordnung (bilinear, vorverzerrt): b0, b1 = 2 b0, b2 = b0, a1, a2"""
    k = math.tan(math.pi * fc / fs); n = 1 / (1 + k / q + k * k)
    return k * k * n, 2 * (k * k - 1) * n, (1 - k / q + k * k) * n


def q31(x):
    v = int(round(x * 2 ** 31)); assert -2 ** 31 <= v < 2 ** 31, x
    return v & 0xFFFFFFFF


def model_row(m):
    st = m['filt']; assert 1 <= len(st) <= MAXST
    r16 = int(round(m['rate'] / 48000 * 65536)); g = int(round(10 ** (m['gain_db'] / 20) * 256))
    pg = min(int(round(10 ** (-m['gain_db'] / 4 / 20) * 32768)), 32767)
    row = struct.pack('>HHHHIHH', r16, m['flags'], g, pg, (0xFFFFFFFF << (16 - m['bits'])) & 0xFFFFFFFF, len(st),
                      m.get('seg', 0) * SEGS)
    for q, fc in st:
        b0, a1, a2 = biquad(q, fc)
        row += struct.pack('>3I', q31(b0), q31(a1 / 2), q31(a2))
    return row.ljust(ROWB, b'\0')


def model_rows():
    return b''.join(model_row(m) for m in MODELS[1:])


def segt():
    """Betrag >> 8 (0..128) -> Schritt-Exponent. Tabelle 0 mu-law: Segment s (0..7, Grenzen 256 * 2^s) -> max(s, 1) + 3;
    Tabelle 1 Gleitkomma mit 12 Bit Mantisse: max(0, Bitlaenge - 12). Beide Grenzen liegen auf Vielfachen von 256."""
    t0, t1 = [], []
    for i in range(SEGN):
        m = i << 8; s = max(0, min(7, m.bit_length() - 8))
        t0.append(max(s, 1) + 3)
        t1.append(max(0, (m | 0xFF).bit_length() - 12))
    return bytes(t0).ljust(SEGS, b'\0') + bytes(t1)


def p12_values():
    return [int(round(65536 * 2 ** (i / 12))) for i in range(13)]


# ---------------- Code (jede Funktion: S = Symbole aller Masken; im ersten Durchgang 0)
def b_reg(S):
    a = A(M_REG)
    asm(a, f'''
    ; Maschinen-Satz n (0..6 Firmware, 7 = Sampl), Ersatz fuer den Anfang von 0x4004df5c
    RAT:    move.l  4(sp),d0
            moveq   #7,d1
            cmp.l   d1,d0
            bne     rat0
            jmp     REC8
    rat0:   moveq   #6,d1
            cmp.l   d0,d1
            bcc     rat1
            moveq   #-1,d0
    rat1:   jmp     {RAT_RET}
    ; Satz der Maschine m (0..5 ueber die Firmware-Tabelle, 6 = Sampl), Ersatz fuer den Anfang von 0x4004df76
    ROF:    move.l  4(sp),d0
            moveq   #6,d1
            cmp.l   d1,d0
            bne     rof0
            jmp     REC8
    rof0:   moveq   #5,d1
            jmp     {ROF_RET}
    ; Knopf -> Deskriptor (jsr von 0x4001e8da statt 'move.l 32(sp),d0 ; movea.l 104(a2),a1'): Maschine 6 -> Vektor [1..7]
    KV:     move.l  36(sp),d0
            movea.l 104(a2),a1
            moveq   #6,d1
            cmp.l   d1,d0
            bne     kv1
            lea     VEC7,a1
    kv1:    rts
    ''', S)
    return [(M_REG, adone(a, S))], a.lab


# ---------------- smp17: Nutzlast-Platz 'sampler' (Core): eigenes MACHINES-Icon (Pip, 34 x 34, v2/art/grit_klein.bmp)
PAY_OFF, PAY_ROOM = C.PAY_SLOT['sampler']
PAY_ORG = C.PAY + PAY_OFF
# smp28 (Pip: mehr als 3 Sample-Locks -> Trigs stumm / Locks ohne Wirkung): Lade-Verwaltung in der Nutzlast (RAM, beim Start 0)
PX_ORG, PX_END = PAY_ORG + 0x700, PAY_ORG + 0xDB0      # Code: LALLOC, LFIT, LEVICT, NEED, PLF, KSO2
LNEED_A, LFAIL_A, TAB_A = PAY_ORG + 0xDB0, PAY_ORG + 0xDC0, PAY_ORG + 0xE00
# smp41 (Pip: lange Samples / Vlvt-Akkorde knacken beim Retrigger): DCK nach dem VCA, Zustand je Spur 16 B (LAST, ACC, STEP, REM)
# am Ende des PX-Platzes (Nutzlast, beim Start 0); Ueberblendung NDK Samples (2 ms)
DCKS_A, NDK = PX_END - 0x60, 96
assert LFAIL_A + 4 * NFAIL <= TAB_A and TAB_A + 16 * NTAB <= PAY_ORG + PAY_ROOM
# Firmware 1.13: Sound-Locks. Spur t im Pattern = Pattern + 0x2d2 t, Lock-Index je Step (Byte, -1 = keiner) bei +0x284;
# Lock-Sounds im Kit ab +0x2b6 (64 x 100 B, gueltig wenn Byte +4 != 0) - Ereignisbau 0x400548ce (Pattern, Kit, Step)
T_STRIDE, T_LOCK, K_POOL, NPOOL = 0x2D2, 0x284, 0x2B6, 64
ICON_FILE = C.ROOT / 'v2' / 'art' / 'grit_klein.bmp'
ICON_MASK = 0x4017C20C               # Maske der kleinen Bilder der Firmware (34 x 34, voll), nur die Adresse


def mimg_text(L, mach, big, bm, other):
    """MACHINES-Bild (jmp von 0x400a2638, d3 = Maschine, d2 = Bild): fuer Maschine mach das grosse Bild der Maschine big
    und das eigene kleine Bitmap-Objekt bm (None: das kleine Bild der Maschine big), sonst other (gleicher Einsprung)."""
    small = (f'            pea     {bm}' if bm else
             f'            add.l   {ICON_B},d4\n            move.l  d4,-(sp)')
    return f'''
    {L}:    moveq   #{mach},d0
            cmp.l   d0,d3
            beq     {L}1
            jmp     {other}
    {L}1:   move.l  #{big * 28},d4
            pea     1.w
            pea     0x17.w
            pea     0x20.w
            lea     {SPRITE},a2
            movea.l {ICON_A},a1
            orig    0x400a2658,20            ; grosses Bild wie die Firmware (Befehle aus dem Image)
            pea     0x60.w
{small}
            move.l  d2,-(sp)
            jsr     (a2)
            lea     20(sp),sp
            jmp     {IMG_RET}
'''


XSYMS = ('XID', 'XBLD', 'XPR', 'XRT', 'XOT', 'XCFG', 'XROW', 'XLAB', 'XVAL', 'XROT', 'XPRS', 'XED', 'TMODE', 'SLEN', 'SLIST', 'XMAP', 'TNAMES')
# ---------------- smp20: Transfer-Kennung CYC / SMP (Pip 04.11.: Samples ueber Elektron Transfer laden)
# Methode nach Model-TG (TinyGregAudio, MIT, docs/INTERNALS.md 'Transfer identity'; eigener Code): Transfer entscheidet nach der
# Kennungs-Antwort (Nachricht 0x01: Produkt, Liste der Befehle, Name). Die Cycles-Firmware verteilt alle Befehle an dieselben
# Stellen wie die Samples, meldet und beantwortet aber nur die rohe Dateisystem-Familie. SMP meldet sich wie ein Model:Samples
# (Produkt 25, Liste mit der Sample-Familie, 'Model Samples'), uebersetzt eingehende Sample-Befehle in die rohen Zwillinge
# und die Antworten zurueck. Kein Stereo-Eintrag (9): Transfer rechnet Stereo-WAVs wie beim Model:Samples in Mono um.
# Die SMP-Liste entsteht zur Laufzeit aus der Liste der Firmware (keine Bytes im Patch). Schalter: Device Config > Transfer
# (CYC / SMP), nach jedem Start CYC; nach dem Umschalten Transfer neu verbinden.
X_ID, X_ID_CK, X_ID_RET = 0x40084B8E, (0x58, '19beeef16f8739cf2926e1133f1121a2f8d383b308b148f151299dac897f335d'), 0x40084BE6
X_PR, X_PR_CK, X_PR_RET = 0x40084C14, (6, '47de4ffe4c9cb848d44b1799b84fe52750ecafb579f37c78d06a6ea2e0125010'), 0x40084C1A
X_RT, X_RTFN = 0x4009249A, 0x400949D8                          # jsr Typ-Byte (Nachricht +8) im Verteiler
X_OT, X_OT_CK, X_OT_RET = 0x40094C9A, (8, 'b23da00179c0a4e6e3256d5002ec0db3cf0ffd50d05573fba45e443af630b369'), 0x40094CA2
X_CFG, X_CFG_CK, X_CFG_RET = 0x40032AEE, (6, '10552f30e94896a18c635b43b0f16452187a5e3db5b661ba3255c1ecb054fd50'), 0x40032AF4
X_LIST, X_NLIST, X_NAME = 0x40112D40, 0x22, 0x401285C9         # Befehlsliste und Name der Firmware (nur Adressen)
X_COPY, X_FMT = 0x400E9C0A, 0x400F980C
X_ALLOC, X_FREECL, X_ITEM, X_ADD = 0x40080064, 0x400CF044, 0x400734B0, 0x40072CE6   # Menue-Zeile (wie Model-TG)
X_GEN, X_SLOT2, X_REDRAW = 0x4002F136, 0x4002F188, 0x40076082
X_TSW, X_TSF, X_DFA, X_DFB, X_DTX, X_FONT, X_TSD = 0x400F85BC, 0x400F7D5C, 0x40072260, 0x40072080, 0x40071A04, 0x40140AB0, 0x40FE4278
X_EDA, X_EDB = 0x400732F8, 0x400732EC
P_CYC, P_SMP = 27, 25                                          # Produktnummern der Kennungs-Antwort
X_MAP = bytes([0x10, 0x14, 0x11, 0x15, 0x12, 0x16, 0x20, 0x24, 0x21, 0x25, 0x22, 0x26, 0x23, 0x27,
               0x30, 0x33, 0x31, 0x34, 0x32, 0x35, 0x36, 0x37, 0x40, 0x43, 0x41, 0x44, 0x42, 0x45, 0x46, 0x47, 0, 0])
X_EXTRA = 0x13                                                 # in der Samples-Liste hinter 0x10 (ohne rohen Zwilling)


def xfer_text():
    return f'''
    ; ---- Kennungs-Antwort: Liste, Laenge und Name je nach TMODE (ersetzt 0x40084b8e..0x40084be5)
    XID:    move.l  a0,-0x60(a6)             ; Zuteiler (wie die Firmware)
            tst.l   TMODE
            beq     xid1
            jsr     XBLD                     ; SMP-Liste aus der der Firmware
    xid1:   movea.l -0x60(a6),a0
            tst.l   TMODE
            beq     xid2
            move.l  SLEN,-(sp)
            bra     xid3
    xid2:   pea     {X_NLIST}.w
    xid3:   orig    0x40084b96,46            ; Liste anlegen, Register wie die Firmware (Befehle aus dem Image)
            tst.l   TMODE
            bne     xid4
            pea     {X_LIST + X_NLIST}
            lea     {X_NLIST}(a1),a1
            pea     {X_LIST}
            bra     xid5
    xid4:   move.l  SLEN,d1
            adda.l  d1,a1
            move.l  #SLIST,d1
            add.l   SLEN,d1
            move.l  d1,-(sp)
            pea     SLIST
    xid5:   move.l  a1,-0x1c(a6)
            move.l  d0,-0x24(a6)
            jsr     (a4)
            move.l  d6,-(sp)
            tst.l   TMODE
            bne     xid6
            pea     {X_NAME}
            jmp     {X_ID_RET}
    xid6:   pea     SNAME
            jmp     {X_ID_RET}
    ; XBLD: SLIST = Liste der Firmware, rohe Befehle -> Sample-Familie, hinter 0x10 noch {X_EXTRA:#x}; SLEN = Laenge
    XBLD:   move.l  a2,-(sp)
            lea     {X_LIST},a0
            lea     SLIST,a1
            moveq   #{X_NLIST},d1
    xb1:    moveq   #0,d0
            move.b  (a0)+,d0
            lea     XMAP,a2
    xb2:    tst.b   (a2)
            beq     xb4
            cmp.b   1(a2),d0
            beq     xb3
            addq.l  #2,a2
            bra     xb2
    xb3:    move.b  (a2),d0
    xb4:    move.b  d0,(a1)+
            cmpi.l  #0x10,d0
            bne     xb5
            move.b  #{X_EXTRA},(a1)+
    xb5:    subq.l  #1,d1
            bne     xb1
            suba.l  #SLIST,a1
            move.l  a1,SLEN
            movea.l (sp)+,a2
            rts
    ; ---- Produktnummer (ersetzt moveq #27,d1 ; lea 40(sp),sp bei 0x40084c14)
    XPR:    moveq   #{P_CYC},d1
            tst.l   TMODE
            beq     xpr1
            moveq   #{P_SMP},d1
    xpr1:   lea     40(sp),sp
            jmp     {X_PR_RET}
    ; ---- eingehend: Typ-Byte (Nachricht +8); SMP: Sample-Familie -> roher Zwilling (auch in der Nachricht)
    XRT:    movea.l 4(sp),a0
            moveq   #0,d0
            move.b  8(a0),d0
            tst.l   TMODE
            beq     xrt9
            lea     XMAP,a1
    xrt1:   moveq   #0,d1
            move.b  (a1),d1
            beq     xrt9
            cmp.l   d1,d0
            beq     xrt2
            addq.l  #2,a1
            bra     xrt1
    xrt2:   move.b  1(a1),d0
            move.b  d0,8(a0)
    xrt9:   rts
    ; ---- ausgehend: Typ der Antwort (ersetzt mvz.b 8(a2),d0 ; lea 32(sp),sp bei 0x40094c9a); SMP: roh | 0x80 -> Sample | 0x80
    XOT:    moveq   #0,d0
            move.b  8(a2),d0
            tst.l   TMODE
            beq     xot9
            lea     XMAP,a1
    xot1:   moveq   #0,d1
            move.b  1(a1),d1
            beq     xot9
            bset    #7,d1
            cmp.l   d1,d0
            beq     xot2
            addq.l  #2,a1
            bra     xot1
    xot2:   move.b  (a1),d0
            bset    #7,d0
    xot9:   lea     32(sp),sp
            jmp     {X_OT_RET}
    ; ---- Device Config: eine Zeile 'Transfer' anhaengen (ersetzt movem.l 24(sp),d2-d6/a2-a6 bei 0x40032aee, Menue in a2)
    XCFG:   lea     -16(sp),sp
            movem.l d0-d1/a0-a1,(sp)
            move.l  a2,-(sp)
            jsr     XROW
            addq.l  #4,sp
            movem.l (sp),d0-d1/a0-a1
            lea     16(sp),sp
            movem.l 24(sp),d2-d6/a2-a6
            jmp     {X_CFG_RET}
    ; XROW(menu): Zeile aus vier Closures {{Daten, 0, Verwalter, Aufruf}} wie die Zeilen der Firmware
    XROW:   link.w  a6,#-64
            lea     -16(sp),sp
            movem.l d4/a3-a5,(sp)
            lea     {X_ALLOC},a4
            lea     -64(a6),a5
            pea     1.w
            jsr     (a4)
            addq.l  #4,sp
            move.l  d0,(a5)
            clr.l   4(a5)
            move.l  #{X_GEN},d1
            move.l  d1,8(a5)
            move.l  #XLAB,d1
            move.l  d1,12(a5)
            pea     4.w
            jsr     (a4)
            addq.l  #4,sp
            movea.l d0,a0
            move.l  8(a6),(a0)
            move.l  d0,16(a5)
            clr.l   20(a5)
            move.l  #{X_SLOT2},d1
            move.l  d1,24(a5)
            move.l  #XPRS,d1
            move.l  d1,28(a5)
            pea     1.w
            jsr     (a4)
            addq.l  #4,sp
            move.l  d0,32(a5)
            clr.l   36(a5)
            move.l  #{X_GEN},d1
            move.l  d1,40(a5)
            move.l  #XVAL,d1
            move.l  d1,44(a5)
            pea     4.w
            jsr     (a4)
            addq.l  #4,sp
            movea.l d0,a0
            move.l  8(a6),(a0)
            move.l  d0,48(a5)
            clr.l   52(a5)
            move.l  #{X_SLOT2},d1
            move.l  d1,56(a5)
            move.l  #XROT,d1
            move.l  d1,60(a5)
            pea     0x54.w
            jsr     (a4)
            addq.l  #4,sp
            movea.l d0,a3
            pea     8.w
            pea     -1.w
            pea     48(a5)
            pea     32(a5)
            pea     16(a5)
            move.l  a5,-(sp)
            move.l  a3,-(sp)
            jsr     {X_ITEM}
            lea     28(sp),sp
            move.l  a3,-(sp)
            move.l  8(a6),-(sp)
            jsr     {X_ADD}
            addq.l  #8,sp
            lea     {X_FREECL},a4
            pea     48(a5)
            jsr     (a4)
            addq.l  #4,sp
            pea     32(a5)
            jsr     (a4)
            addq.l  #4,sp
            pea     16(a5)
            jsr     (a4)
            addq.l  #4,sp
            move.l  a5,-(sp)
            jsr     (a4)
            addq.l  #4,sp
            movem.l (sp),d4/a3-a5
            unlk    a6
            rts
    ; Beschriftung: a0 = Ausgabe-String
    XLAB:   link.w  a6,#-4
            move.l  d2,-(sp)
            pea     -1(a6)
            pea     SLAB
            orig    0x40030580,24            ; formatieren und zurueck wie die Firmware (Befehle aus dem Image)
    ; Wert: CYC / SMP (Zeichnen wie die Werte der Firmware-Zeilen)
    XVAL:   link.w  a6,#-48
            movem.l d2-d4/a2-a5,(sp)
            move.l  TMODE,d0
            lea     TNAMES,a1
            move.l  0(a1,d0.l*4),d0
            move.l  #{X_TSD},d1
            move.l  d1,-16(a6)
            lea     {X_TSF},a2
            move.l  a6,d2
            subq.l  #8,d2
            move.l  a6,d3
            addi.l  #-16,d3
            orig    0x40030334,90            ; zeichnen und zurueck wie die Werte der Firmware-Zeilen (Befehle aus dem Image)
    ; Drehen (Closure, Eintrag, Delta): rechts SMP, links CYC, Menue neu zeichnen (Daten der Closure = Menue)
    XROT:   move.l  12(sp),d0
            beq     xro9
            moveq   #1,d1
            tst.l   d0
            bgt     xro1
            moveq   #0,d1
    xro1:   move.l  d1,TMODE
            movea.l 4(sp),a0
            movea.l (a0),a0
            move.l  (a0),d0
            beq     xro9
            addi.l  #0x38,d0
            move.l  d0,-(sp)
            jsr     {X_REDRAW}
            addq.l  #4,sp
    xro9:   rts
    ; Druecken: Bearbeiten an / aus wie die Zeilen der Firmware
    XPRS:   move.l  8(sp),-(sp)
            move.l  8(sp),-(sp)
            jsr     XED
            addq.l  #8,sp
            rts
    XED:    orig    0x40029eba,38            ; Bearbeiten umschalten wie die Firmware (Befehle aus dem Image)
'''


def xfer_data(org):
    """Daten hinter dem Code (RAM der Nutzlast): TMODE, SLEN, SLIST, XMAP, Texte, TNAMES."""
    lab, b = {}, bytearray()
    def at(): return org + len(b)
    lab['TMODE'] = at(); b += bytes(4)
    lab['SLEN'] = at(); b += bytes(4)
    lab['SLIST'] = at(); b += bytes(48)
    lab['XMAP'] = at(); b += X_MAP
    for k, t in (('SLAB', 'Transfer'), ('SNAME', 'Model Samples'), ('SCYC', 'CYC'), ('SSMP', 'SMP')):
        lab[k] = at(); b += t.encode() + b'\0'
    while len(b) % 4: b += b'\0'
    lab['TNAMES'] = at(); b += struct.pack('>II', lab['SCYC'], lab['SSMP'])
    return bytes(b), lab


def b_pay():
    """-> (Bytes ab PAY_ORG, Labels): MIMG (Grit: grosses Bild von SNARE, eigenes kleines Icon; sonst die Bilder der
    Maschine wie die Firmware), Bitmap-Objekt GBM, Bild GICON."""
    w, h, pic = C.icon(ICON_FILE); assert (w, h) == (34, 34), (w, h)
    text = mimg_text('MIMG', MACH, 1, 'GBM', 'MIMGF') + f'''
    MIMGF:  move.l  d3,d4                    ; andere Maschinen: wie die Firmware
            move.l  d4,d0
            lsl.l   #2,d0
            lsl.l   #5,d4
            sub.l   d0,d4                    ; 28 * Maschine
            pea     1.w
            pea     0x17.w
            pea     0x20.w
            lea     {SPRITE},a2
            movea.l {ICON_A},a1
            orig    0x400a2658,40            ; grosses und kleines Bild wie die Firmware (Befehle aus dem Image)
            jmp     {IMG_RET}
'''
    lab = collections.defaultdict(int)
    for _ in range(2):
        a = A(PAY_ORG); asm(a, text, lab)
        n = (len(a.b) + 3) & ~3
        lab = dict(a.lab, GBM=PAY_ORG + n, GICON=PAY_ORG + n + 28)
    code = adone(a, lab)
    blob = code + bytes(-len(code) % 4) + C.bitmap(w, h, lab['GICON'], ICON_MASK) + pic
    blob += bytes(-len(blob) % 4)
    xorg = PAY_ORG + len(blob)                                      # smp20: Transfer-Kennung
    xl = collections.defaultdict(int)
    for _ in range(2):
        a = A(xorg); asm(a, xfer_text(), xl)
        dorg = xorg + ((len(a.b) + 3) & ~3)
        xd, dl = xfer_data(dorg)
        xl = dict(a.lab, **dl)
    xcode = adone(a, xl)
    blob += xcode + bytes(-len(xcode) % 4) + xd
    lab.update(xl)
    assert len(blob) <= PAY_ROOM, (len(blob), PAY_ROOM)
    return blob, lab


def b_rec(S):
    """REC8 -> d0 = 8. Maschinen-Satz (76 B, RAM), beim ersten Gebrauch aus dem von SNARE: Texte ueber den Kopier-
    Konstruktor der Firmware (Referenzzaehler), Deskriptoren 51, 52, 53, 54, 55 -> 10, 11, 0, 13, 24; UI-Objekte 10, 11, 13
    bekommen Formatierer und Sonderzeichnung der SNARE-Objekte 51, 52, 54. Erhaelt d2 / a2 (smp1 zerstoerte a2: der
    Maschinenwechsel 0x40014072 liest danach (a2) = Spur -> Absturz beim ersten Wechsel auf Sampl)."""
    a = A(M_REC)
    asm(a, f'''
    REC8:   tst.b   R8OK
            bne     r8x
            move.l  d2,-(sp)
            move.l  a2,-(sp)                 ; d2 / a2 gehoeren dem Aufrufer (0x40014072 liest a2 danach)
            pea     {REC_SNARE}
            pea     R8
            jsr     {STRCOPY}
            addq.l  #8,sp
            pea     {REC_SNARE + 4}
            pea     R8_4
            jsr     {STRCOPY}
            addq.l  #8,sp
            lea     {REC_SNARE + 8},a0
            lea     R8_8,a1
            moveq   #16,d2
    r8l:    move.l  (a0)+,d0
            moveq   #51,d1
            sub.l   d1,d0
            moveq   #4,d1
            cmp.l   d1,d0
            bhi     r8k                      ; nicht 51..55
            lea     R8MAP,a2
            move.b  0(a2,d0.l),d1
            mvz.b   d1,d0
            bra     r8s
    r8k:    move.l  -4(a0),d0
    r8s:    move.l  d0,(a1)+
            subq.l  #1,d2
            bpl     r8l
            lea     {OBJ_BASE + 100 * 51},a0
            lea     {OBJ_BASE + 100 * D_START},a1
            move.l  32(a0),32(a1)
            move.l  44(a0),44(a1)
            move.l  132(a0),132(a1)
            move.l  144(a0),144(a1)
            lea     {OBJ_BASE + 100 * D_VIN},a1  ; Modell: eigener Formatierer, keine Sonderzeichnung
            move.l  #MFMT,d0
            move.l  d0,32(a1)
            clr.l   44(a1)
            jsr     R8F
            moveq   #1,d0
            move.b  d0,R8OK
            movea.l (sp)+,a2
            move.l  (sp)+,d2
    r8x:    move.l  #R8,d0
            rts
    ''', S)
    return [(M_REC, adone(a, S))], a.lab


def b_vox(S):
    """SUPD = update[6] (pmod, Stimme, Parameter): Amp-Decay wie TONE, kein Gate; beim Trig STRIG, jeden Block SBLK."""
    a = A(M_VOX)
    asm(a, f'''
    SUPD:   lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            movea.l 52(sp),a2
            movea.l 56(sp),a3
            mvs.b   36(a3),d0
            lea     {DECLUT},a0
            move.l  0(a0,d0.l*4),d1
            move.l  d1,0x250(a2)
            clr.l   0x24c(a2)
            tst.l   0x38(a2)
            beq     nt
            jsr     STRIG
    nt:     mvz.w   26(a3),d0                ; SWEEP (Filter) fuer SRND
            move.l  d0,V_FW(a2)
            move.l  48(sp),d6                ; pmod
            jsr     SBLK
            movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            rts
    ; Formatierer des Modells (UI-Objekt 13 +32, wie die der Firmware: 8(sp) = Wert 8.8, 12(sp) = Puffer): Name des Modells
    ; ueber den sprintf der Firmware (die Namen enthalten kein %)
    MFMT:   move.l  8(sp),d0
            addi.l  #0x80,d0
            asr.l   #8,d0
            bpl     mf1
            moveq   #0,d0
    mf1:    moveq   #{NMOD - 1},d1
            cmp.l   d1,d0
            ble     mf2
            move.l  d1,d0
    mf2:    lea     MNAMES,a0
            move.l  0(a0,d0.l*4),d0
            move.l  12(sp),d1
            move.l  d1,4(sp)
            move.l  d0,8(sp)
            jmp     {SPRINTF}
    ; UI-Objekt 12 (Filter, smp7): Formatierer der Firmware fuer bipolare Werte (Mitte OFF), keine Sonderzeichnung
    R8F:    move.l  #{FMT_OFF},d0
            move.l  d0,{OBJ_BASE + 100 * D_SWP + 32}
            clr.l   {OBJ_BASE + 100 * D_SWP + 44}
            rts
    ''', S, **VK)
    return [(M_VOX, adone(a, S))], a.lab


def multi(S, text, masks, **kw):
    """Text in Stuecke (';@SEG') fuer mehrere Masken; Spruenge zwischen Stuecken nur mit jmp / jsr (globale Labels)."""
    out, labs = [], {}
    for va, piece in zip(masks, text.split(';@SEG')):
        a = A(va); asm(a, piece, S, **kw); out.append((va, adone(a, S))); labs.update(a.lab)
    assert len(text.split(';@SEG')) == len(masks)
    return out, labs


VK = {f'V_{k}': x for k, x in V.items()}


def b_trg(S):
    """STRIG (a2 Stimme, a3 Parameter): Kennung aus dem Zielblock der Spur (0x800015ae + 66 t + 50, roh, nicht geglaettet),
    Sample suchen, Bereich aus Start / Length, Loop (PUNCH) und Richtung (GATE)."""
    return multi(S, f'''
    STRIG:  move.l  a2,d0
            subi.l  #{VOICE0},d0
            move.l  #{VSTRIDE},d1
            divu.l  d1,d0                    ; Spur
            lea     OVR,a0                   ; Kennung: Sample-Lock des Trigs (SLK), sonst Sound der Spur im Kit
            move.l  0(a0,d0.l*4),d3
            bne     tk
            moveq   #0,d3
            move.l  {KITA},d1
            beq     tk
            movea.l d1,a0
            moveq   #100,d1
            muls.l  d1,d0
            move.l  {28 + O_ID}(a0,d0.l),d3
    tk:     clr.l   V_FLAGS(a2)
            clr.l   V_PTR(a2)
            tst.l   d3
            beq     tx
            lea     TAB,a0
            moveq   #{NTAB - 1},d1
    tl:     cmp.l   (a0),d3
            beq     tf
            lea     16(a0),a0
            subq.l  #1,d1
            bpl     tl
    tx:     rts
    tf:     jmp     STRIG2
    ;@SEG
    STRIG2: move.l  4(a0),d0
            move.l  d0,V_PTR(a2)
            move.l  8(a0),d4                 ; Frames
            move.l  d4,V_LEN(a2)
            move.l  12(a0),d0
            move.l  d0,V_RF(a2)
            moveq   #127,d6
            mvz.b   22(a3),d0                ; COLOR = Start 0..127
            move.l  d4,d5
            mulu.l  d0,d5
            divu.l  d6,d5                    ; Start-Frame
            mvz.b   24(a3),d0                ; SHAPE = Ende 0..127 (smp12, Pip: Start verschiebt das Ende nicht mehr;
            move.l  d4,d2                    ; Fenster verschieben = FUNC + Start), Laenge = Ende - Start, mind. 1
            mulu.l  d0,d2
            divu.l  d6,d2
            sub.l   d5,d2
            bgt     t2
            moveq   #1,d2
            bra     t2
    t1:     tst.l   d2
            bne     t2
            moveq   #1,d2
    t2:     move.l  d5,V_ST(a2)
            move.l  d2,V_SPAN(a2)
            moveq   #{1 << F_PLAY},d1
            mvz.b   30(a3),d0                ; PUNCH = Loop (smp8, Pip: wie Model:Samples)
            beq     t3
            bset    #{F_LOOP},d1
    t3:     mvz.b   32(a3),d0                ; GATE = Reverse
            beq     t4
            bset    #{F_REV},d1
            add.l   d2,d5
            subq.l  #1,d5                    ; rueckwaerts: am Ende beginnen
    t4:     move.l  d1,V_FLAGS(a2)
            move.l  d5,V_POS(a2)
            clr.l   V_FRAC(a2)
            moveq   #-1,d0
            move.l  d0,V_PH(a2)              ; der erste Ausgang holt sofort einen Wert
            clr.l   V_HELD(a2)
            clr.l   V_P(a2)
            lea     V_H0(a2),a0              ; Biquads leer
            moveq   #{4 * MAXST - 1},d0
    t5:     clr.l   (a0)+
            subq.l  #1,d0
            bpl     t5
            rts
    ''', [M_TRG, M_TRG2], **VK)


def b_blk(S):
    """SBLK (a2 Stimme, a3 Parameter, d6 = pmod): Modell aus CONTOUR (8.8, gerundet, 0 = Clean -> SCLN, Biquads leer),
    sonst die Werte der Modell-Zeile; SBLKP: Tonhoehe -> Schritt (16.16, mit Rate der Datei); SBLKI: Raster-Schritt (0.32,
    mit der Tonhoehe oder fest), KINV = 2^32 / (Raster-Schritt >> 16) fuer den Bruchteil am Takt, Q8 = Rate der Datei / Takt."""
    return multi(S, f'''
    SBLK:   mvz.w   28(a3),d0                ; CONTOUR = Modell
            addi.l  #0x80,d0
            lsr.l   #8,d0
            moveq   #{NMOD - 1},d1
            cmp.l   d1,d0
            bls     b1
            move.l  d1,d0
    b1:     move.l  d0,V_VIN(a2)
            bne     b2
            lea     V_H0(a2),a0              ; Clean: Biquads leer (Wechsel ohne alten Zustand)
            moveq   #{4 * MAXST - 1},d0
    b3:     clr.l   (a0)+
            subq.l  #1,d0
            bpl     b3
            jmp     SBLKP
    b2:     subq.l  #1,d0
            mulu.w  #{ROWB},d0
            lea     MODT,a0
            adda.l  d0,a0
            move.l  a0,V_ROW(a2)
            mvz.w   (a0),d7                  ; Takt (R16)
            mvz.w   2(a0),d0
            move.l  d0,V_MF(a2)
            mvz.w   4(a0),d0
            move.l  d0,V_GAIN(a2)
            mvz.w   6(a0),d0
            move.l  d0,V_PG(a2)
            move.l  8(a0),d0
            move.l  d0,V_MASK(a2)
            move.l  V_RF(a2),d0              ; Q8 = Rate der Datei / Takt (24.8)
            lsl.l   #8,d0
            divu.l  d7,d0
            move.l  d0,V_Q8(a2)
            move.l  V_RF(a2),d2              ; fester Takt (0.32) = Rate der Datei / Q8: genau Q8 pro Takt bei Note 60
            lsl.l   #8,d2
            remu.l  d0,d3:d2
            divu.l  d0,d2
            swap    d3
            clr.w   d3
            divu.l  d0,d3
            swap    d2
            clr.w   d2
            or.l    d3,d2
            move.l  d2,V_TINC(a2)
            jmp     SBLKP
    ;@SEG
    SBLKP:  mvs.w   20(a3),d0                ; PITCH
            subi.l  #0x4000,d0
            lsl.l   #8,d0
            mvs.w   34(a3),d1                ; FINE
            subi.l  #0x4000,d1
            lsl.l   #3,d1
            add.l   d1,d0
            add.l   d6,d0                    ; Note << 16
            subi.l  #{(60 - 72) << 16},d0    ; relativ zu Note 60, + 72 Halbtoene
            bpl     p1
            moveq   #0,d0
    p1:     cmpi.l  #{108 << 16},d0
            ble     p2
            move.l  #{108 << 16},d0
    p2:     move.l  #{12 << 16},d1
            move.l  d0,d2
            remu.l  d1,d3:d2                 ; im Ton (16.16)
            divu.l  d1,d2                    ; Oktave 0..9
            move.l  d3,d4
            swap    d4
            andi.l  #0xffff,d4               ; Halbton 0..11
            andi.l  #0xffff,d3               ; Bruchteil
            lea     P12,a0
            move.l  0(a0,d4.l*4),d5
            move.l  4(a0,d4.l*4),d0
            sub.l   d5,d0
            mulu.l  d3,d0
            swap    d0
            andi.l  #0xffff,d0
            add.l   d0,d5                    ; 2^(Ton / 12), 16.16
            subq.l  #6,d2
            bmi     p3
            lsl.l   d2,d5
            bra     p4
    p3:     neg.l   d2
            lsr.l   d2,d5                    ; Verhaeltnis 16.16 (1/64 .. 8)
    p4:     jmp     SBLKI
    ;@SEG
    SBLKI:  move.l  V_RF(a2),d0              ; Schritt = Verhaeltnis * Rate der Datei / 48 kHz
            move.l  d5,d1
            swap    d1
            andi.l  #0xffff,d1
            mulu.l  d0,d1
            move.l  d5,d2
            andi.l  #0xffff,d2
            lsr.l   #1,d0
            mulu.l  d0,d2
            moveq   #15,d0
            lsr.l   d0,d2
            add.l   d2,d1                    ; 16.16
            move.l  V_FLAGS(a2),d0
            btst    #{F_REV},d0
            beq     p5
            neg.l   d1
    p5:     move.l  d1,d0
            asr.l   #6,d0
            move.l  d0,V_INC6(a2)
            move.l  d1,d0
            swap    d0
            ext.l   d0
            move.l  d0,V_INCI(a2)
            swap    d1
            clr.w   d1
            move.l  d1,V_INCF(a2)
            tst.l   V_VIN(a2)                ; Raster: Phase pro Ausgang = Takt (* Verhaeltnis) (0.32)
            beq     p9
            move.l  V_MF(a2),d0
            btst    #{MF_TRACK},d0
            bne     p7
            move.l  V_TINC(a2),d1            ; fester Takt (SBLK)
            bra     pk
    p7:     move.l  d5,d1
            swap    d1
            andi.l  #0xffff,d1
            mulu.l  d7,d1
            cmpi.l  #0xffff,d1
            bhi     p8
            swap    d1
            clr.w   d1
            move.l  d5,d2
            andi.l  #0xffff,d2
            mulu.l  d7,d2
            add.l   d2,d1
            bcs     p8
            move.l  d1,V_TINC(a2)
            bra     pk
    p8:     moveq   #-1,d1
            move.l  d1,V_TINC(a2)
    pk:     swap    d1                       ; KINV = (2^32 - 1) / (Schritt >> 16)
            andi.l  #0xffff,d1
            beq     p9
            moveq   #-1,d0
            divu.l  d1,d0
            move.l  d0,V_KINV(a2)
    p9:     rts
    ''', [M_BLK, M_BLK2, M_BLK3], **VK)


def b_rnd(S):
    """SRND = render[6] (Ausgang, Stimme): 32 Samples (Clean: SCLN; Modelle: SRAS + SBQ), dann Amp-Huellkurve und VCA der
    Firmware (AMPT; die Akkus sind dann leer, wie die Firmware sie erwartet)."""
    return multi(S, f'''
    SRND:   lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            movea.l 48(sp),a1
            movea.l 52(sp),a2
            lea     128(a1),a6               ; Ende des Blocks
            move.l  V_FLAGS(a2),d0
            btst    #{F_PLAY},d0
            beq     SIL
            movea.l V_PTR(a2),a0
            move.l  a0,d0
            beq     SIL
            move.l  V_POS(a2),d2
            move.l  V_FRAC(a2),d3
            move.l  V_INCI(a2),d4
            move.l  V_INCF(a2),d5
            movea.l V_SPAN(a2),a4
            tst.l   V_VIN(a2)
            beq     r0
            jmp     SRAS
    r0:     jmp     SCLN
    STOP:   bclr    #{F_PLAY},d1
            move.l  d1,V_FLAGS(a2)
    SIL:    clr.l   (a1)+
            cmpa.l  a6,a1
            bne     SIL
            lea     V_H0(a2),a0              ; Biquads leer
            moveq   #{4 * MAXST - 1},d0
    sz:     clr.l   (a0)+
            subq.l  #1,d0
            bpl     sz
    AMPT:   jsr     SFLT                     ; SWEEP-Filter (smp7)
            move.l  a2,-(sp)
            jsr     {AMPENV}
            move.l  a2,(sp)
            move.l  52(sp),-(sp)
            jsr     {VCA}
            addq.l  #8,sp
            movea.l 48(sp),a0                ; smp41: Uebergang beim Retrigger glaetten
            jsr     DCK
            movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            rts
    ;@SEG
    ; ---------------- sauber: lineare Interpolation
    SCLN:   movea.l V_ST(a2),a5
    cl:     move.l  d2,d0
            sub.l   a5,d0
            cmp.l   a4,d0
            bcc     cb
            mvs.w   0(a0,d2.l*2),d0
            mvs.w   2(a0,d2.l*2),d1
            sub.l   d0,d1
            asr.l   #1,d1
            move.l  d3,d6
            swap    d6
            lsr.l   #1,d6
            muls.w  d6,d1
            asr.l   #7,d1
            asr.l   #7,d1
            add.l   d1,d0
            swap    d0
            clr.w   d0
            move.l  d0,(a1)+
            add.l   d5,d3
            addx.l  d4,d2
            cmpa.l  a6,a1
            bne     cl
            move.l  d2,V_POS(a2)
            move.l  d3,V_FRAC(a2)
            jmp     AMPT
    cb:     move.l  V_FLAGS(a2),d1
            btst    #{F_LOOP},d1
            bne     cbl
            jmp     STOP
    cbl:    tst.l   d0
            bmi     cbn
            sub.l   a4,d2
            bra     cl
    cbn:    add.l   a4,d2
            bra     cl
    ;@SEG
    ; ---------------- Raster (smp3): Wert am genauen Takt-Zeitpunkt (linear interpoliert), Kanten bandbegrenzt (polyBLEP,
    ; Ausgang 1 Sample verzoegert: a4 = Rest fuer dieses Sample); smp4: Ausgang Q30 in den Block, danach die Biquads (SBQ)
    SRAS:   move.l  V_PH(a2),d6
            move.l  V_TINC(a2),d7
            movea.l V_HELD(a2),a3
            movea.l V_P(a2),a4
    rl:     add.l   d5,d3
            addx.l  d4,d2
            move.l  a3,d0
            add.l   a4,d0                    ; gehaltener Wert + Rest der letzten Kante
            suba.l  a4,a4
            add.l   d7,d6
            bcc     SRF
            jmp     SRK                      ; Takt in diesem Sample
    SRF:    move.l  d0,(a1)+
            cmpa.l  a6,a1
            bne     rl
            move.l  d2,V_POS(a2)
            move.l  d3,V_FRAC(a2)
            move.l  d6,V_PH(a2)
            move.l  a3,V_HELD(a2)
            move.l  a4,V_P(a2)
            jmp     SBQ
    ;@SEG
    ; Takt: d0 = Ausgang bis jetzt; w = Phase nach dem Takt / Schritt = Anteil des Samples nach der Kante (Q16)
    SRK:    move.l  d2,d1
            sub.l   V_ST(a2),d1
            cmp.l   V_SPAN(a2),d1
            bcs     k0
            jmp     SRB                      ; Ende oder Loop
    k0:     lea     -24(sp),sp
            movem.l d0/d2-d5/d7,(sp)
            move.l  d6,d7
            clr.w   d7
            swap    d7
            mulu.l  V_KINV(a2),d7
            clr.w   d7
            swap    d7                       ; w
            move.l  V_INC6(a2),d4            ; Weg seit der Kante = w * Schritt (16.16)
            muls.l  d7,d4
            asr.l   #8,d4
            asr.l   #2,d4
            move.l  d4,d5
            swap    d5
            clr.w   d5
            asr.l   #8,d4
            asr.l   #8,d4
            sub.l   d5,d3
            subx.l  d4,d2                    ; Position zur Kante
            move.l  d2,d1
            sub.l   V_ST(a2),d1
            bmi     k1
            cmp.l   V_SPAN(a2),d1
            bcs     k2
            move.l  V_SPAN(a2),d1
            subq.l  #1,d1
            bra     k3
    k1:     moveq   #0,d1
    k3:     move.l  V_ST(a2),d2
            add.l   d1,d2
            moveq   #0,d3
    k2:     jmp     SRKQ
    ;@SEG
    SRK2:   mvs.w   0(a0,d2.l*2),d0          ; Wert zur Kante (linear)
            mvs.w   2(a0,d2.l*2),d1
            sub.l   d0,d1
            asr.l   #1,d1
            swap    d3
            andi.l  #0xffff,d3
            lsr.l   #1,d3
            muls.w  d3,d1
            asr.l   #7,d1
            asr.l   #7,d1
            add.l   d1,d0
            tst.b   V_FI+1(a2)               ; SWEEP am Anfang der Kette (smp8)
            beq     j0
            jsr     SFTK
    j0:     muls.w  V_GAIN+2(a2),d0          ; heiss, Clip, Bits, Nachverstaerkung
            asr.l   #8,d0
            cmpi.l  #32767,d0
            ble     j1
            move.l  #32767,d0
    j1:     cmpi.l  #-32768,d0
            bge     j2
            move.l  #-32768,d0
    j2:     move.l  V_MF(a2),d1
            btst    #{MF_MULAW},d1
            beq     j4
            jmp     JMU
    j4:     and.l   V_MASK(a2),d0
    J3:     muls.w  V_PG+2(a2),d0            ; Q30
            move.l  d0,d1
            sub.l   a3,d1                    ; Sprung
            movea.l d0,a3
            asr.l   #8,d1
            asr.l   #7,d1                    ; Sprung >> 15
            move.l  d7,d2                    ; voriges Sample (wird jetzt ausgegeben): + Sprung * w^2 / 2
            mulu.l  d2,d2
            moveq   #18,d3
            lsr.l   d3,d2
            muls.l  d1,d2
            move.l  #65535,d3                ; dieses Sample: - Sprung * (1 - w)^2 / 2
            sub.l   d7,d3
            mulu.l  d3,d3
            moveq   #18,d4
            lsr.l   d4,d3
            muls.l  d1,d3
            neg.l   d3
            movea.l d3,a4
            move.l  (sp),d0
            add.l   d2,d0
            movem.l 4(sp),d2-d5/d7
            lea     24(sp),sp
            jmp     SRF
    ;@SEG
    SRB:    movea.l d0,a4                    ; d0 = Ausgang, d1 = Position - Start (ausserhalb)
            move.l  V_FLAGS(a2),d0
            btst    #{F_LOOP},d0
            bne     rbl
            bclr    #{F_PLAY},d0             ; Ende: Wert 0, das Filter klingt im Block aus
            move.l  d0,V_FLAGS(a2)
            move.l  a4,d0
            suba.l  a3,a3
            suba.l  a4,a4
            moveq   #0,d4
            moveq   #0,d5
            moveq   #0,d7
            jmp     SRF
    rbl:    move.l  a4,d0
            suba.l  a4,a4
            tst.l   d1
            bmi     rbn
            sub.l   V_SPAN(a2),d2
            jmp     SRK
    rbn:    add.l   V_SPAN(a2),d2
            jmp     SRK
    ;@SEG
    ; SP (smp4): Drop-Sample, Position am Takt auf das Raster des Wandlers (naechster Punkt) (d1 = Position - Start, d2 / d3 = Position)
    SRKQ:   move.l  V_MF(a2),d4
            btst    #{MF_GRID},d4
            beq     q9
            cmpi.l  #0xfffff0,d1
            bhi     q9                       ; ueber 2^24 Frames (349 s): ohne Raster
            lsl.l   #8,d1
            move.l  d3,d4
            moveq   #24,d5
            lsr.l   d5,d4
            or.l    d4,d1                    ; 24.8
            move.l  V_Q8(a2),d5
            move.l  d5,d4
            lsr.l   #1,d4
            add.l   d4,d1                    ; + halbes Raster: naechster Punkt (die Takte liegen bei Note 60 genau
            remu.l  d5,d4:d1                 ; auf dem Raster, Rundungsfehler kippen so nicht)
            sub.l   d4,d1
            move.l  d1,d3
            moveq   #24,d5
            lsl.l   d5,d3
            lsr.l   #8,d1
            move.l  V_ST(a2),d2
            add.l   d1,d2
    q9:     jmp     SRK2
    ; LM / TX16W / MPC60: Segment-Raster (mu-law oder 12-Bit-Gleitkomma, Tabelle der Zeile), d0 = Wert (16 Bit, nach dem Clip): Betrag auf das Segment-Raster runden, Vorzeichen zurueck
    JMU:    move.l  d0,d1
            bpl     mu1
            neg.l   d0
    mu1:    move.l  d0,d2
            lsr.l   #8,d2
            movea.l V_ROW(a2),a5
            mvz.w   14(a5),d3                ; Tabelle der Zeile (mu-law / Gleitkomma)
            lea     SEGT,a5
            adda.l  d3,a5
            move.b  0(a5,d2.l),d2
            mvz.b   d2,d2                    ; Exponent 4..10
            moveq   #1,d3
            lsl.l   d2,d3
            lsr.l   #1,d3
            add.l   d3,d0
            lsr.l   d2,d0
            lsl.l   d2,d0
            cmpi.l  #32767,d0
            ble     mu2
            move.l  #32767,d0
    mu2:    tst.l   d1
            bpl     mu3
            neg.l   d0
    mu3:    jmp     J3
    ;@SEG
    ; ---------------- Rekonstruktions-Filter (smp4): Stufen der Modell-Zeile nacheinander ueber den Block (Q30, auf der
    ; Stelle), Direktform I, b1 = 2 b0 / a1 ueber << ; die letzte Stufe (SBQL) verdoppelt nach Q31 mit Saettigung
    SBQ:    movclr  acc0,d0                  ; leer (wie die Firmware ihn uebergibt)
            movea.l V_ROW(a2),a0
            mvz.w   12(a0),d7                ; Stufen (1..3)
            lea     16(a0),a0
            lea     V_H0(a2),a5
    bqs:    lea     -128(a6),a1
            movem.l (a0),d4-d6               ; b0, a1 / 2, a2
            lea     12(a0),a0
            movem.l (a5),d1-d3               ; x1, x2, y1
            movea.l 12(a5),a3                ; y2
            subq.l  #1,d7
            bne     bql
            jmp     SBQL
    bql:    move.l  (a1),d0
            mac     d4,d0,acc0
            mac     d4,d1,acc0
            mac     d4,d1,acc0                 ; statt '<<' (smp13)
            mac     d4,d2,acc0
            msac    d5,d3,acc0
            msac    d5,d3,acc0                 ; statt '<<' (smp13)
            msac    d6,a3,acc0
            move.l  d1,d2
            move.l  d0,d1
            movea.l d3,a3
            movclr  acc0,d3
            move.l  d3,(a1)+
            cmpa.l  a6,a1
            bne     bql
            movem.l d1-d3,(a5)
            move.l  a3,12(a5)
            lea     16(a5),a5                ; naechste Stufe (eigene Eingangs-Geschichte: der Block ist dann schon neu)
            bra     bqs
    ;@SEG
    SBQL:   move.l  (a1),d0
            mac     d4,d0,acc0
            mac     d4,d1,acc0
            mac     d4,d1,acc0                 ; statt '<<' (smp13)
            mac     d4,d2,acc0
            msac    d5,d3,acc0
            msac    d5,d3,acc0                 ; statt '<<' (smp13)
            msac    d6,a3,acc0
            move.l  d1,d2
            move.l  d0,d1
            movea.l d3,a3
            movclr  acc0,d3
            move.l  d3,d0
            add.l   d0,d0                    ; Q31
            bvs     bsat
    bs1:    move.l  d0,(a1)+
            cmpa.l  a6,a1
            bne     SBQL
            movem.l d1-d3,(a5)
            move.l  a3,12(a5)
            jmp     AMPT
    bsat:   move.l  #0x7fffffff,d0
            tst.l   d3
            bpl     bs1
            addq.l  #1,d0
            bra     bs1
    ''', [M_RND, M_CLN, M_RAS, M_RAS2, M_RAS3, M_RAS4, M_RAS5, M_BQ, M_BQ2], **VK)


def b_ld(S):
    """STICK (jsr von 0x400075f0 statt jsr 0x40076be4, UI-Task, jedes Bild): ein Lade-Schritt, dann weiter zur Firmware.
    LKNOWN(d0 = Kennung) -> d1 != 0: geladen oder zuletzt fehlgeschlagen."""
    return multi(S, f'''
    STICK:  lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            tas     BUSY                     ; laeuft schon (das Bild kommt auch aus einer zweiten Task)
            bne     kx2
            tst.l   {FS_MOUNT}
            beq     kx
            move.l  {FS_LOCKO},d0            ; diese Task ist schon im Dateisystem: jetzt nicht
            cmp.l   {RUNNING},d0
            beq     kx
            tst.l   LST
            bne     kread
            move.l  LREQ,d0                  ; im Browser gewaehlt: zuerst
            beq     ks
            clr.l   LREQ
            jsr     LSTART
            bra     kx
    ks:     move.l  {KITP},d0                ; sonst: Samples der 6 Spuren
            beq     kx
            movea.l d0,a3
            lea     28(a3),a3
            moveq   #5,d7
    ksl:    mvz.b   38(a3),d0
            moveq   #{MACH},d1
            cmp.l   d1,d0
            bne     ksn
            move.l  {O_ID}(a3),d0
            btst    #0,d0                    ; Kennungen von Dateien sind ungerade (0 = kein Sample)
            beq     ksn
            jsr     LKNOWN
            tst.l   d1
            bne     ksn
            jsr     LSTART
            bra     kx
    ksn:    lea     100(a3),a3
            subq.l  #1,d7
            bpl     ksl
            jsr     KSO
            bra     kx
    kread:  jsr     LCHUNK
    kx:     clr.b   BUSY
    kx2:    movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            jmp     {VCRENDER}
    ;@SEG
    LKNOWN: lea     TAB,a0
            moveq   #{NTAB - 1},d1
    lk1:    cmp.l   (a0),d0
            beq     lky
            lea     16(a0),a0
            subq.l  #1,d1
            bpl     lk1
            lea     LFAIL,a0
            moveq   #{NFAIL - 1},d1
    lk2:    cmp.l   (a0)+,d0
            beq     lky
            subq.l  #1,d1
            bpl     lk2
            moveq   #0,d1
            rts
    lky:    moveq   #1,d1
            rts
    ''', [M_LD, M_LK])


def b_ls(S):
    """LSTART(d0 = Kennung): Datei ueber den Index der Kennungen finden, oeffnen, Kopf pruefen (LSTART2), Platz holen;
    sonst in den Fehl-Ring (LFAILD; LFAILC schliesst vorher)."""
    return multi(S, f'''
    LSTART: move.l  d0,d6
            jsr     LKNOWN
            tst.l   d1
            beq     ls0
            rts
    ls0:    pea     {FS_LOCKO}               ; Index nur unter der Sperre (andere Tasks bauen ihn neu)
            jsr     {FS_LOCK}
            move.l  d6,(sp)
            jsr     {FS_FIND}
            moveq   #-1,d7
            tst.l   d0
            bmi     ls5
            lsl.l   #3,d0
            lea     {FS_IDX},a0
            move.l  0(a0,d0.l),d7            ; Datei-Nummer
    ls5:    move.l  #{FS_LOCKO},(sp)
            jsr     {FS_UNLOCK}
            addq.l  #4,sp
            move.l  d7,d0
            bmi     lsf
            pea     LH
            move.l  d0,-(sp)
            jsr     {FS_STAT}
            addq.l  #8,sp
            tst.l   d0
            bne     lsf
            pea     LFH
            pea     LH
            jsr     {FS_OPEN}
            addq.l  #8,sp
            tst.l   d0
            ble     lsf
            pea     LFH
            pea     64.w
            pea     {SCR + 0x100}
            jsr     {FS_READ}
            lea     12(sp),sp
            moveq   #64,d1
            cmp.l   d1,d0
            bne     lsc
            jmp     LSTART2
    lsc:    jmp     LFAILC
    lsf:    jmp     LFAILD
    ;@SEG
    LSTART2: lea    {SCR + 0x100},a0
            move.l  8(a0),d1                 ; Rate
            cmpi.l  #4000,d1
            bcs     lsc2
            cmpi.l  #192000,d1
            bhi     lsc2
            moveq   #12,d2
            lsl.l   d2,d1
            move.l  #3000,d2
            divu.l  d2,d1
            move.l  d1,LRF                   ; Rate * 65536 / 48000
            move.l  4(a0),d1                 ; Bytes
            beq     lsc2
            move.l  LH_8,d2
            subi.l  #64,d2
            cmp.l   d2,d1
            bhi     lsc2
            andi.l  #0xfffffffc,d1
            mvz.b   1(a0),d0
            move.l  d0,LSTER
            move.l  d1,LTOT
            clr.l   LDONE
            tst.l   d0
            beq     ls1
            lsr.l   #1,d1                    ; Mono-Bytes
    ls1:    move.l  d1,d2
            lsr.l   #1,d2
            move.l  d2,LFR                   ; Frames
            addi.l  #{CHUNK + 32 + 15 + 256},d1   ; + Uebersicht (128 Spalten min / max)
            andi.l  #0xfffffff0,d1
            move.l  d1,LNEED
            jmp     LALLOC                   ; smp28: Platz in Tabelle und Speicher (erste Luecke), sonst freigeben
    lsc2:   jmp     LFAILC
    ;@SEG
    LFAILC: pea     LFH
            jsr     {FS_CLOSE}
            addq.l  #4,sp
    LFAILD: move.l  LFP,d0                   ; Kennung (d6) in den Fehl-Ring
            addq.l  #1,d0
            moveq   #{NFAIL - 1},d1
            and.l   d1,d0
            move.l  d0,LFP
            lsl.l   #2,d0
            lea     LFAIL,a0
            move.l  d6,0(a0,d0.l)
            rts
    ''', [M_LS, M_LS2, M_LF])


def b_lc(S):
    """LCHUNK: naechste 64 KB lesen (Stereo auf der Stelle zu Mono); LCFIN: schliessen, Nullen anhaengen, eintragen."""
    return multi(S, f'''
    LCHUNK: move.l  LTOT,d2
            sub.l   LDONE,d2
            cmpi.l  #{CHUNK},d2
            bls     lc1
            move.l  #{CHUNK},d2
    lc1:    move.l  LDONE,d0
            tst.l   LSTER
            beq     lc2
            lsr.l   #1,d0
    lc2:    movea.l LPTR,a2
            adda.l  d0,a2                    ; Ziel
            pea     LFH
            move.l  d2,-(sp)
            move.l  a2,-(sp)
            jsr     {FS_READ}
            lea     12(sp),sp
            cmp.l   d2,d0
            bne     lerr
            tst.l   LSTER
            beq     lc4
            movea.l a2,a0                    ; Stereo -> Mono (L + R) / 2
            movea.l a2,a1
            move.l  d2,d3
            lsr.l   #2,d3
            beq     lc4
    lc3:    mvs.w   (a0)+,d0
            mvs.w   (a0)+,d1
            add.l   d1,d0
            asr.l   #1,d0
            move.w  d0,(a1)+
            subq.l  #1,d3
            bne     lc3
    lc4:    jsr     LOV                      ; Uebersicht weiter (a2 = Mono-Frames dieses Stuecks)
            add.l   d2,LDONE
            move.l  LDONE,d0
            cmp.l   LTOT,d0
            bcs     lcx
            jmp     LCFIN
    lcx:    rts
    lerr:   pea     LFH
            jsr     {FS_CLOSE}
            addq.l  #4,sp
            clr.l   LST
            move.l  LID,d6
            jmp     LFAILD
    ;@SEG
    LCFIN:  pea     LFH
            jsr     {FS_CLOSE}
            addq.l  #4,sp
            movea.l LPTR,a0
            move.l  LFR,d0
            add.l   d0,d0
            adda.l  d0,a0
            moveq   #7,d0
    lc5:    clr.l   (a0)+
            subq.l  #1,d0
            bpl     lc5
            move.l  a0,d0
            addi.l  #15,d0
            andi.l  #0xfffffff0,d0
            movea.l d0,a1                    ; Uebersicht hinter das Sample (die Anzeige findet sie ueber Daten + Frames)
            lea     OVB,a0
            moveq   #63,d1
    lc6:    move.l  (a0)+,(a1)+
            subq.l  #1,d1
            bpl     lc6
            move.l  a1,POOLT
            movea.l LSLOT,a0
            move.l  LPTR,d0
            move.l  d0,4(a0)
            move.l  LFR,d0
            move.l  d0,8(a0)
            move.l  LRF,d0
            move.l  d0,12(a0)
            move.l  LID,d0
            move.l  d0,(a0)                  ; zuletzt: ab jetzt sichtbar fuer die Stimmen
            clr.l   LST
            rts
    ;@SEG
    ; Uebersicht (smp4): 128 Spalten (min, max) als Bytes (Sample >> 8), Spalte c endet bei Frame ((c + 1) * Frames) >> 7;
    ; beim Laden Stueck fuer Stueck in OVB (die Stereo-Stuecke landen roh hinter den Mono-Daten), LCFIN kopiert sie
    LOVI:   clr.l   LOVC
            clr.l   LOVF
            move.l  LFR,d0
            lsr.l   #7,d0
            move.l  d0,LOVB
            move.l  #32767,d0
            move.l  d0,LOVMN
            not.l   d0
            move.l  d0,LOVMX
            rts
    LOV:    lea     -32(sp),sp               ; a2 = Mono-Frames, d2 = gelesene Bytes (Stereo: / 4, Mono: / 2)
            movem.l d2-d7/a2-a3,(sp)
            move.l  d2,d7
            lsr.l   #1,d7
            tst.l   LSTER
            beq     lv0
            lsr.l   #1,d7
    lv0:    move.l  LOVC,d2
            cmpi.l  #128,d2
            bcc     lv9
            tst.l   d7
            beq     lv9
            movea.l a2,a0
            move.l  LOVF,d3
            move.l  LOVB,d4
            move.l  LOVMN,d5
            move.l  LOVMX,d6
            lea     OVB,a2
            lea     LFR,a3
            jmp     LOVL
    lv9:    movem.l (sp),d2-d7/a2-a3
            lea     32(sp),sp
            rts
    ;@SEG
    LOVL:
    lv1:    mvs.w   (a0)+,d0
            cmp.l   d5,d0
            bge     lv2
            move.l  d0,d5
    lv2:    cmp.l   d6,d0
            ble     lv3
            move.l  d0,d6
    lv3:    addq.l  #1,d3
    lv4:    cmp.l   d4,d3
            bcs     lv6
            move.l  d5,d1                    ; Spalte fertig
            asr.l   #8,d1
            move.b  d1,0(a2,d2.l*2)
            move.l  d6,d1
            asr.l   #8,d1
            move.b  d1,1(a2,d2.l*2)
            move.l  d0,d5
            move.l  d0,d6
            addq.l  #1,d2
            cmpi.l  #128,d2
            bcc     lv8
            move.l  d2,d1
            addq.l  #1,d1
            mulu.l  (a3),d1
            lsr.l   #7,d1
            move.l  d1,d4
            bra     lv4
    lv6:    subq.l  #1,d7
            bne     lv1
    lv8:    move.l  d2,LOVC
            move.l  d3,LOVF
            move.l  d4,LOVB
            move.l  d5,LOVMN
            move.l  d6,LOVMX
            movem.l (sp),d2-d7/a2-a3
            lea     32(sp),sp
            rts
    ''', [M_LC, M_LC2, M_LOV, M_LOV2])


def b_br(S):
    """SPARSE (jsr von 0x400a6602 statt des Preset-Lesers 0x400a3052; a0 = &Ergebnis, 4(sp) = &Handle {Datei, Kennung,
    Groesse, x}): auf einer Sampl-Spur wird eine Datei, die kein Preset ist (48..160 B), zum Sound der Spur mit ihrer
    Kennung und dem Dateinamen (SPNAME), als echter shared_ptr (Sound + Kontrollblock wie die Firmware). Sonst die Firmware."""
    return multi(S, f'''
    SPARSE: lea     -28(sp),sp
            movem.l d2-d4/a2-a5,(sp)
            movea.l a0,a5                    ; &Ergebnis
            movea.l 32(sp),a4                ; Handle
            move.l  {ACT_TRACK},d0
            moveq   #5,d1
            cmp.l   d1,d0
            bhi     orig
            move.l  {KITP},d1
            beq     orig
            muls.w  #100,d0
            add.l   d1,d0
            addi.l  #28,d0
            movea.l d0,a3                    ; Sound der Spur
            mvz.b   38(a3),d0
            moveq   #{MACH},d1
            cmp.l   d1,d0
            bne     orig
            move.l  8(a4),d0
            move.l  d0,d1
            subi.l  #48,d0
            cmpi.l  #112,d0
            bls     orig                     ; Preset (48..160 B): wie immer
            moveq   #66,d0
            cmp.l   d0,d1
            bcs     none                     ; zu klein fuer Kopf + 1 Frame
            pea     100.w
            jsr     {NEW}
            movea.l d0,a2                    ; Sound
            pea     16.w
            jsr     {NEW}
            addq.l  #8,sp
            movea.l d0,a1                    ; Kontrollblock
            move.l  #{SPVT},(a1)
            moveq   #1,d0
            move.l  d0,4(a1)
            move.l  d0,8(a1)
            move.l  a2,12(a1)
            move.l  a2,(a5)
            move.l  a1,4(a5)
            jmp     SPNAME
    none:   clr.l   (a5)
            clr.l   4(a5)
    SPOUT:  move.l  a5,d0
            movea.l a5,a0
            movem.l (sp),d2-d4/a2-a5
            lea     28(sp),sp
            rts
    orig:   movea.l a5,a0
            movem.l (sp),d2-d4/a2-a5
            lea     28(sp),sp
            jmp     {PARSE}
    ;@SEG
    SPNAME: movea.l a3,a0                    ; Sound der Spur kopieren
            movea.l a2,a1
            moveq   #25,d0
    cp:     move.l  (a0)+,(a1)+
            subq.l  #1,d0
            bne     cp
            move.l  4(a4),d0
            move.l  d0,{O_ID}(a2)            ; Kennung
            move.l  {FS_LOCKO},d0            ; Browser schon im Dateisystem: Name der Spur lassen
            cmp.l   {RUNNING},d0
            beq     nm
            pea     {SCR}                    ; Name = letzter Teil des Pfads
            clr.l   -(sp)
            move.l  (a4),-(sp)
            jsr     {FS_PATH}
            lea     12(sp),sp
            lea     4(a2),a1
            moveq   #3,d1
    cz:     clr.l   (a1)+
            subq.l  #1,d1
            bpl     cz
            tst.l   d0
            beq     nm
            movea.l d0,a0
            movea.l d0,a1
    ns:     move.b  (a0)+,d1
            beq     ne
            moveq   #0x2f,d2
            cmp.b   d2,d1
            bne     ns
            movea.l a0,a1
            bra     ns
    ne:     lea     4(a2),a0
            moveq   #14,d2
    nc:     move.b  (a1)+,d1
            beq     nm
            move.b  d1,(a0)+
            subq.l  #1,d2
            bpl     nc
    nm:     move.l  4(a4),d0
            move.l  d0,LREQ                  ; sofort laden
            lea     LFAIL,a0                 ; neuer Versuch erlaubt
            moveq   #{NFAIL - 1},d1
    nf:     cmp.l   (a0),d0
            bne     nf1
            clr.l   (a0)
    nf1:    addq.l  #4,a0
            subq.l  #1,d1
            bpl     nf
            jmp     SPOUT
    ''', [M_BR, M_BR2])


def b_kd(S):
    """KDRAW (Vtable 0x4010053c statt 0x4001e40a, Zeichnen der Parameter-Ansicht mit Knopf-Popup; 4(sp) Ansicht, 8(sp) Bild):
    beim Drehen von COLOR (Start) / SHAPE (Length) einer Sampl-Spur mit geladenem Sample die Wellenform statt des Popups.
    Sonst (anderer Parameter, kein Popup, Trig gehalten = p-lock, kein Sample) die Firmware."""
    return multi(S, f'''
    KDRAW:  lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            movea.l 48(sp),a2                ; Ansicht
            move.l  0x230(a2),d4             ; Deskriptor des Popups
            moveq   #{D_START},d0
            sub.l   d0,d4                    ; 0 = Start, 1 = Length
            moveq   #1,d0
            cmp.l   d0,d4
            bhi     kdo
            move.l  {ACT_TRACK},d0
            moveq   #5,d1
            cmp.l   d1,d0
            bhi     kdo
            move.l  {KITP},d1
            beq     kdo
            muls.w  #100,d0
            add.l   d1,d0
            addi.l  #28,d0
            movea.l d0,a3                    ; Sound der Spur
            mvz.b   38(a3),d0
            moveq   #{MACH},d1
            cmp.l   d1,d0
            bne     kdo
            jsr     {UIGET}
            movea.l d0,a0
            tst.l   0x58(a0)                 ; Popup sichtbar
            beq     kdo
            tst.b   0x164(a0)                ; Trig gehalten (p-lock): wie die Firmware
            bne     kdo
            move.l  {O_ID}(a3),d0
            beq     kdo
            lea     TAB,a4
            moveq   #{NTAB - 1},d1
    kd1:    cmp.l   (a4),d0
            beq     kd2
            lea     16(a4),a4
            subq.l  #1,d1
            bpl     kd1
    kdo:    movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            jmp     {KDRAW_ORIG}
    kd2:    move.l  52(sp),d3                ; Bild
            jmp     KDRAW2
    ;@SEG
    ; Wellenform: Bereich y 0..52 (Mitte 26), Spalten Start..Ende voll, davor / dahinter jede zweite (gedimmt)
    KDRAW2: clr.l   -(sp)
            pea     63.w
            pea     127.w
            clr.l   -(sp)
            clr.l   -(sp)
            move.l  d3,-(sp)
            jsr     {FILL_F}
            lea     24(sp),sp
            movea.l 4(a4),a5                 ; Uebersicht = (Daten + 2 * Frames + 32 + 15) & ~15 (wie LCFIN)
            move.l  8(a4),d0
            add.l   d0,d0
            adda.l  d0,a5
            lea     47(a5),a5
            move.l  a5,d0
            andi.l  #0xfffffff0,d0
            movea.l d0,a5
            mvz.b   42(a3),d6                ; Start 0..127 = Spalte
            mvz.b   44(a3),d7                ; Ende 0..127 (wie STRIG2, smp12)
    kd3:    moveq   #0,d5
    kd4:    cmp.l   d6,d5
            bcs     kd5
            cmp.l   d7,d5
            bls     kd6
    kd5:    btst    #0,d5
            bne     kd7
    kd6:    pea     1.w
            move.b  1(a5,d5.l*2),d0          ; max
            extb.l  d0
            muls.w  #26,d0
            asr.l   #7,d0
            moveq   #26,d1
            add.l   d1,d0
            move.l  d0,-(sp)
            move.l  d5,-(sp)
            move.b  0(a5,d5.l*2),d0          ; min
            extb.l  d0
            muls.w  #26,d0
            asr.l   #7,d0
            moveq   #26,d1
            add.l   d1,d0
            move.l  d0,-(sp)
            move.l  d5,-(sp)
            move.l  d3,-(sp)
            jsr     {FILL_F}
            lea     24(sp),sp
    kd7:    addq.l  #1,d5
            cmpi.l  #128,d5
            bcs     kd4
            jmp     KDRAW3
    ;@SEG
    ; Linien bei Start und Ende (umgekehrt, sichtbar auch in der Wellenform), oben Parameter und Wert
    KDRAW3: pea     -1.w
            pea     52.w
            move.l  d6,-(sp)
            clr.l   -(sp)
            move.l  d6,-(sp)
            move.l  d3,-(sp)
            jsr     {FILL_F}
            lea     24(sp),sp
            cmp.l   d6,d7
            beq     kd8
            pea     -1.w
            pea     52.w
            move.l  d7,-(sp)
            clr.l   -(sp)
            move.l  d7,-(sp)
            move.l  d3,-(sp)
            jsr     {FILL_F}
            lea     24(sp),sp
    kd8:    lea     KDN,a0                   ; oben links der Parameter, rechts der Wert
            move.l  0(a0,d4.l*4),-(sp)
            pea     {FMT_S}
            clr.l   -(sp)
            pea     55.w
            clr.l   -(sp)
            pea     {F_NAME}
            move.l  d3,-(sp)
            jsr     {TXT_F}
            lea     28(sp),sp
            mvz.b   42(a3,d4.l*2),d0
            move.l  d0,-(sp)
            pea     {FMT_D}
            pea     4.w
            pea     55.w
            pea     128.w
            pea     {F_NAME}
            move.l  d3,-(sp)
            jsr     {TXT_F}
            lea     28(sp),sp
            movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            rts
    ''', [M_KD, M_KD2, M_KD3])


def b_sl(S):
    """smp5: Sample-Lock nur fuer das Sample. SLK (jsr von 0x400590ce statt 'move.l d2,d0 ; addi.l #$93,d0', Uebernahme
    eines Trig-Ereignisses in die Klangerzeugung; a1 = Kit, a2 = Ereignis, a5 = Sound fuer den Trig, d2 = Spur): ist a5 der
    Sound-Lock des Trigs (Ereignis +0x2c; smp7: smp5 pruefte +0x30 = Vorhoeren, Pip: Sample-Lock ging nicht) und sind Spur und Lock Sampl, merkt OVR[t] die Kennung des Locks und a5 wird der
    Sound der Spur - alle anderen Parameter kommen aus der Spur, echte p-locks bleiben (die Firmware legt sie danach an).
    KSO (aus STICK): Samples der Locks laden. Browser (Vorschau): KCUR (Vtable des Preset-Browsers +0x4c statt 0x400a64be,
    Cursor bewegt; smp8: Cursor = Liste +0x10, smp7 las +0x24): die markierte Datei wird auf einer Sampl-Spur sofort das
    Sample der Spur."""
    return multi(S, f'''
    SLK:    move.l  d2,d0
            moveq   #100,d1
            muls.l  d1,d0
            lea     28(a1,d0.l),a0           ; Sound der Spur im Kit
            lea     OVR,a1
            clr.l   0(a1,d2.l*4)
            cmpa.l  a0,a5
            beq     sl9
            cmpa.l  0x2c(a2),a5              ; Sound-Lock des Sequencers (+0x2c; +0x30 = Vorhoeren im Browser)?
            bne     sl9
            mvz.b   38(a0),d0
            moveq   #{MACH},d1
            cmp.l   d1,d0
            bne     sl9
            mvz.b   38(a5),d0
            cmp.l   d1,d0
            bne     sl9
            move.l  {O_ID}(a5),d0
            beq     sl9
            move.l  d0,0(a1,d2.l*4)
            movea.l a0,a5                    ; Parameter aus der Spur
    sl9:    move.l  d2,d0
            addi.l  #0x93,d0
            rts
    KSO:    lea     OVR,a3                   ; Samples der Locks (STICK, nach den Spuren)
            moveq   #5,d7
    ko1:    move.l  (a3)+,d0
            btst    #0,d0
            beq     ko2
            jsr     LKNOWN
            tst.l   d1
            bne     ko2
            jmp     LSTART
    ko2:    subq.l  #1,d7
            bpl     ko1
            jmp     KSO2                     ; smp28: dann alle Locks des Patterns vorladen
    ;@SEG
    KCUR:   move.l  8(sp),-(sp)              ; Cursor bewegt (Vtable +0x4c): erst die Firmware (Vorhoeren der Presets)
            move.l  8(sp),-(sp)
            jsr     {BR_CUR}
            addq.l  #8,sp
            lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            movea.l 48(sp),a2                ; Browser
            move.l  0x10(a2),d3              ; Cursor (Liste +0x10, von der Firmware normalisiert; vt+0x4c bekommt ihn als Argument)
            jsr     BRPREV
            movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            rts
    BRPREV: move.l  {ACT_TRACK},d0
            moveq   #5,d1
            cmp.l   d1,d0
            bhi     bp9
            move.l  {KITP},d1
            beq     bp9
            muls.w  #100,d0
            add.l   d1,d0
            addi.l  #28,d0
            movea.l d0,a3                    ; Sound der Spur
            mvz.b   38(a3),d0
            moveq   #{MACH},d1
            cmp.l   d1,d0
            bne     bp9
            jmp     BRP2
    bp9:    rts
    ;@SEG
    BRP2:   jsr     {UIGET}
            movea.l d0,a0
            tst.b   0x164(a0)                ; Trig gehalten: Lock wie immer erst mit YES
            bne     bq9
            move.l  0x278(a2),d0             ; Dateiliste aktiv
            beq     bq9
            cmp.l   0x280(a2),d0
            bne     bq9
            movea.l d0,a4
            move.l  d3,-(sp)
            move.l  a4,-(sp)
            movea.l (a4),a0
            movea.l 0x20(a0),a0
            jsr     (a0)                     ; Datei (kein Ordner)?
            addq.l  #8,sp
            tst.b   d0
            beq     bq9
            jmp     BRPV2
    bq9:    rts
    ;@SEG
    BRPV2:  lea     {HBUF},a0                ; Kopf der Datei: Nummer, Kennung, Groesse
            move.l  d3,-(sp)
            move.l  a4,-(sp)
            jsr     {FL_ENTRY}
            addq.l  #8,sp
            lea     {HBUF},a4
            moveq   #-1,d0
            cmp.l   (a4),d0
            beq     bn9
            move.l  8(a4),d0
            move.l  d0,d1
            subi.l  #48,d0
            cmpi.l  #112,d0
            bls     bn9                      ; Preset
            moveq   #66,d0
            cmp.l   d0,d1
            bcs     bn9
            move.l  4(a4),d0
            btst    #0,d0
            beq     bn9
            cmp.l   {O_ID}(a3),d0
            beq     bn9
            move.l  d0,{O_ID}(a3)            ; Kennung in den Sound der Spur
            move.l  {FS_LOCKO},d0            ; Name = Dateiname (nicht innerhalb des Dateisystems)
            cmp.l   {RUNNING},d0
            beq     bn5
            pea     {SCR}
            clr.l   -(sp)
            move.l  (a4),-(sp)
            jsr     {FS_PATH}
            lea     12(sp),sp
            tst.l   d0
            beq     bn5
            lea     4(a3),a1
            moveq   #3,d1
    bz:     clr.l   (a1)+
            subq.l  #1,d1
            bpl     bz
            movea.l d0,a0
            movea.l d0,a1
    bs:     move.b  (a0)+,d1
            beq     be
            moveq   #0x2f,d2
            cmp.b   d2,d1
            bne     bs
            movea.l a0,a1
            bra     bs
    be:     jmp     BRNC
    bn5:    jmp     BRLQ
    bn9:    rts
    ;@SEG
    BRNC:   lea     4(a3),a0                 ; bis 15 Zeichen
            moveq   #14,d2
    bc:     move.b  (a1)+,d1
            beq     BRLQ
            move.b  d1,(a0)+
            subq.l  #1,d2
            bpl     bc
    BRLQ:   move.l  4(a4),d0
            move.l  d0,LREQ                  ; sofort laden
            lea     LFAIL,a0
            moveq   #{NFAIL - 1},d1
    bf:     cmp.l   (a0),d0
            bne     bf1
            clr.l   (a0)
    bf1:    addq.l  #4,a0
            subq.l  #1,d1
            bpl     bf
            rts
    ''', [M_SLK, M_BRT, M_BRP, M_BRN, M_BRL])


def px_text():
    """smp28 (Nutzlast, PX_ORG): Pip 09.11.: mehr als 3 Sample-Locks -> Trigs teils stumm, Locks ohne Wirkung. Ursache: ein
    Lock-Sample wurde erst beim ersten Trig geladen (der Trig selbst stumm), geschuetzt war nur der Lock des letzten Trigs
    (OVR), und bei voller Tabelle gab LEVICT immer den niedrigsten freien Platz frei = das zuletzt geladene Lock-Sample: die
    Locks warfen sich gegenseitig hinaus (jeder Neuladen-Trig stumm); freigegebener Speicher kam nur oben zurueck (POOLT), bis
    alles voll war und jedes neue Sample in den Fehl-Ring ging. Jetzt:
    PLF(d0 = Kennung | 0): Sound-Locks des laufenden Patterns (Grit-Spur, Grit-Lock). d0 != 0 -> d1 = d0, falls ein Lock es
    benutzt; d0 = 0 -> d1 = erste Lock-Kennung, die weder geladen noch fehlgeschlagen ist (0 = keine).
    KSO2 (aus KSO, nach Spuren und OVR): diese Kennung laden -> alle Locks des Patterns liegen bereit, bevor sie spielen.
    NEED(d0) -> d1 != 0: Spur des Kits, OVR oder Lock des Patterns.
    LALLOC (aus LSTART2, LNEED = Bytes): freier Platz in der Tabelle und erste passende Luecke im Speicher (LFIT); sonst
    LEVICT: ein Sample frei, das nichts braucht (NEED) und keine Stimme spielt; nichts frei -> Fehl-Ring."""
    return f'''
    LALLOC: lea     TAB,a0                   ; d6 = Kennung (Datei offen)
            moveq   #{NTAB - 1},d1
    la1:    tst.l   (a0)
            beq     la2
            lea     16(a0),a0
            subq.l  #1,d1
            bpl     la1
            bra     la5                      ; Tabelle voll
    la2:    move.l  a0,LSLOT
            jsr     LFIT
            tst.l   d0
            beq     la5                      ; Speicher voll
            move.l  d0,LPTR
            move.l  d6,LID
            jsr     LOVI
            moveq   #1,d0
            move.l  d0,LST
            rts
    la5:    jsr     LEVICT
            tst.l   d0
            bne     LALLOC
            jmp     LFAILC
    LFIT:   lea     -24(sp),sp               ; -> d0 = niedrigster Anfang einer Luecke mit LNEED Bytes (0 = keine)
            movem.l d2-d6/a2,(sp)
            moveq   #0,d0
            move.l  #{POOL0},d2              ; Kandidat: Anfang des Speichers, dann das Ende jedes Samples
            lea     TAB,a2
            moveq   #{NTAB},d6
    lf1:    move.l  d2,d3
            add.l   LNEED,d3
            cmpi.l  #{POOL_END},d3
            bhi     lf5
            lea     TAB,a0
            moveq   #{NTAB - 1},d4
    lf2:    tst.l   (a0)
            beq     lf3
            cmp.l   4(a0),d3                 ; Kandidat endet vor dem Sample
            bls     lf3
            jsr     LEND
            cmp.l   d2,d1                    ; Sample endet hinter dem Kandidaten -> ueberlappt
            bhi     lf5
    lf3:    lea     16(a0),a0
            subq.l  #1,d4
            bpl     lf2
            tst.l   d0                       ; passt: den niedrigsten merken
            beq     lf4
            cmp.l   d0,d2
            bcc     lf5
    lf4:    move.l  d2,d0
    lf5:    subq.l  #1,d6
            bmi     lf9
            movea.l a2,a0
            lea     16(a2),a2
            tst.l   (a0)
            beq     lf5
            jsr     LEND
            move.l  d1,d2
            bra     lf1
    lf9:    movem.l (sp),d2-d6/a2
            lea     24(sp),sp
            rts
    LEND:   move.l  8(a0),d1                 ; a0 = Eintrag -> d1 = Ende samt Uebersicht (wie LCFIN)
            add.l   d1,d1
            add.l   4(a0),d1
            addi.l  #47,d1
            andi.l  #0xfffffff0,d1
            addi.l  #256,d1
            rts
    LEVICT: lea     -16(sp),sp               ; -> d0 = 1: ein Platz frei
            movem.l d2-d3/d5/a2,(sp)
            lea     TAB,a2
            moveq   #{NTAB - 1},d5
    le1:    move.l  (a2),d2
            beq     le8
            move.l  d2,d0
            jsr     NEED
            tst.l   d1
            bne     le8
            clr.l   (a2)                     ; zuerst austragen: keine neue Stimme greift mehr zu
            move.l  4(a2),d3
            lea     {VOICE0 + V['PTR']},a0
            moveq   #5,d1
    le5:    cmp.l   (a0),d3
            beq     le7
            lea     {VSTRIDE}(a0),a0
            subq.l  #1,d1
            bpl     le5
            moveq   #1,d0
            bra     le9
    le7:    move.l  d2,(a2)                  ; eine Stimme spielt es noch
    le8:    lea     16(a2),a2
            subq.l  #1,d5
            bpl     le1
            moveq   #0,d0
    le9:    movem.l (sp),d2-d3/d5/a2
            lea     16(sp),sp
            rts
    NEED:   move.l  {KITP},d1                ; d0 = Kennung -> d1 != 0: gebraucht (d0 bleibt)
            beq     nd2
            movea.l d1,a0
            lea     28(a0),a0
            moveq   #5,d1
    nd1:    cmp.l   {O_ID}(a0),d0
            beq     ndy
            lea     100(a0),a0
            subq.l  #1,d1
            bpl     nd1
    nd2:    lea     OVR,a0
            moveq   #5,d1
    nd3:    cmp.l   (a0)+,d0
            beq     ndy
            subq.l  #1,d1
            bpl     nd3
            jmp     PLF
    ndy:    moveq   #1,d1
            rts
    KSO2:   moveq   #0,d0
            jsr     PLF
            move.l  d1,d0
            beq     ks9
            jmp     LSTART
    ks9:    rts
    PLF:    lea     -36(sp),sp
            movem.l d2-d7/a2-a4,(sp)
            move.l  d0,d6                    ; gesuchte Kennung (0 = erste ungeladene)
            moveq   #0,d5
            move.l  {C.CUR_PAT},d0
            beq     pf9
            movea.l d0,a2                    ; Spur im Pattern
            move.l  {KITP},d0
            beq     pf9
            movea.l d0,a3                    ; Kit
            lea     28(a3),a4                ; Sound der Spur
            moveq   #5,d7
    pf1:    mvz.b   38(a4),d0
            moveq   #{MACH},d1
            cmp.l   d1,d0
            bne     pf6
            lea     {T_LOCK}(a2),a1
            moveq   #63,d4
    pf2:    mvs.b   0(a1,d4.l),d0            ; Lock-Index des Steps
            tst.l   d0
            bmi     pf5
            moveq   #{NPOOL - 1},d1
            cmp.l   d1,d0
            bhi     pf5
            muls.w  #100,d0
            movea.l a3,a0
            adda.l  d0,a0
            lea     {K_POOL}(a0),a0          ; Lock-Sound
            tst.b   4(a0)
            beq     pf5
            mvz.b   38(a0),d0
            moveq   #{MACH},d1
            cmp.l   d1,d0
            bne     pf5
            move.l  {O_ID}(a0),d0
            btst    #0,d0                    ; Kennungen von Dateien sind ungerade
            beq     pf5
            tst.l   d6
            beq     pf3
            cmp.l   d6,d0
            beq     pf8
            bra     pf5
    pf3:    move.l  d0,d2
            jsr     LKNOWN
            move.l  d2,d0
            tst.l   d1
            beq     pf8
    pf5:    subq.l  #1,d4
            bpl     pf2
    pf6:    lea     {T_STRIDE}(a2),a2
            lea     100(a4),a4
            subq.l  #1,d7
            bpl     pf1
            bra     pf9
    pf8:    move.l  d0,d5
    pf9:    move.l  d5,d1
            movem.l (sp),d2-d7/a2-a4
            lea     36(sp),sp
            rts
    ; DCK (smp41; a0 = Block 32 x Q31 nach VCA / Attack, a2 = Stimme; Grit AMPT, Vlvt SRND8): beim Trig springt der Ausgang
    ; sonst vom letzten Wert des alten Tons auf den neuen (Knacken). Versatz LAST - out[0] wird zum Block addiert und faellt
    ; linear in NDK Samples auf 0 (Rechnung in Q29, gesaettigt). LAST = letztes Sample jedes Blocks. Erhaelt d2-d7 / a2-a6.
    DCK:    move.l  a2,d0
            subi.l  #{VOICE0},d0
            bmi     dk9
            move.l  #{VSTRIDE},d1
            divu.l  d1,d0
            moveq   #5,d1
            cmp.l   d1,d0
            bhi     dk9
            lsl.l   #4,d0
            lea     {DCKS_A:#x},a1
            adda.l  d0,a1                    ; +0 LAST, +4 ACC (Q29), +8 STEP, +12 REM
            lea     -16(sp),sp
            movem.l d2-d4/a3,(sp)
            tst.l   0x38(a2)
            beq     dk1
            move.l  (a1),d0
            asr.l   #2,d0
            move.l  (a0),d1
            asr.l   #2,d1
            sub.l   d1,d0                    ; Versatz (Q29)
            move.l  d0,4(a1)
            moveq   #{NDK},d1
            divs.l  d1,d0
            move.l  d0,8(a1)
            move.l  d1,12(a1)
    dk1:    move.l  12(a1),d4                ; REM
            beq     dk8
            move.l  4(a1),d2                 ; ACC
            move.l  8(a1),d3                 ; STEP
            movea.l a0,a3
            moveq   #31,d1
    dkl:    move.l  (a3),d0
            asr.l   #2,d0
            add.l   d2,d0
            cmpi.l  #0x1fffffff,d0
            ble     dk2
            move.l  #0x7fffffff,d0
            bra     dk4
    dk2:    cmpi.l  #-0x20000000,d0
            bge     dk3
            move.l  #0x80000000,d0
            bra     dk4
    dk3:    asl.l   #2,d0
    dk4:    move.l  d0,(a3)+
            sub.l   d3,d2
            subq.l  #1,d4
            beq     dk5
            subq.l  #1,d1
            bpl     dkl
    dk5:    tst.l   d4
            bne     dk6
            moveq   #0,d2
    dk6:    move.l  d2,4(a1)
            move.l  d4,12(a1)
    dk8:    move.l  124(a0),(a1)             ; LAST
            movem.l (sp),d2-d4/a3
            lea     16(sp),sp
    dk9:    rts
    '''


def b_flt(S):
    """SWEEP = Filter wie beim Model:Samples (Pip): Mitte aus, links Tiefpass, rechts Hochpass, ohne Resonanz (Q 0.707)
    und ohne Saettigung - ein reiner Bearbeitungsfilter. Zustandsvariablen-Filter wie der Spur-Filter (Zavalishin,
    trapezoidal); a1 = 1 / (1 + g (g + k)), a2 = g a1, a3 = g a2 (g = tan(pi f / 48 kHz) aus FG, 62 Stufen 20 Hz .. 16 kHz).
    smp8 (Pip: "knackt leise ueber 0", "ganz am Anfang, damit die Emulationen das gefilterte Signal faerben"):
      * Lage: Modelle filtern am Anfang der Kette, im Takt des Wandlers auf dem gelesenen Wert (SRK2 -> SFTK), vor
        Pegel / Clip / Bits / mu-law / Halten / Rekonstruktion. Die Stufe wird um den Takt verschoben (SHIFT: log2 aus
        TINC), die Grenzfrequenz bleibt in Hz (oben hoechstens Takt / 3). Clean: auf dem fertigen Block (linear, gleich).
      * Uebergaenge: Ein- und Ausschalten und der Seitenwechsel blenden ueber einen Block (32 Samples) zwischen trocken
        und gefiltert; Seitenwechsel = erst ausblenden, dann einblenden. Neue Stufe auf derselben Seite: neue Koeffizienten.
    V_FI: Byte 0 = Blende (0 keine, 1 ein, 2 aus), Byte 1 = Seite (0 aus, 1 Hochpass, 2 Tiefpass), Wort = Stufe.
    SFLT (aus AMPT, nach dem Block) entscheidet fuer den naechsten gefilterten Block (Clean: diesen Block, gleich danach)."""
    return multi(S, f'''
    SFLT:   move.l  V_FW(a2),d0              ; SWEEP (8.8), Mitte 64 = aus
            addi.l  #0x80,d0
            lsr.l   #8,d0
            moveq   #64,d1
            sub.l   d1,d0
            moveq   #0,d2
            tst.l   d0
            beq     ft
            bmi     fl2
            moveq   #1,d2                    ; Hochpass: Stufe d - 1 (tief -> hoch)
            subq.l  #1,d0
            bra     fl3
    fl2:    moveq   #2,d2                    ; Tiefpass: 62 - |d| (offen -> zu)
            add.l   d0,d1
            subq.l  #2,d1
            move.l  d1,d0
            bpl     fl3
            moveq   #0,d0
    fl3:    tst.l   V_VIN(a2)
            beq     fl4
            jsr     SHIFT                    ; Modell: Stufe + log(48 kHz / Takt)
    fl4:    moveq   #{NFG - 1},d1
            cmp.l   d1,d0
            ble     ft
            move.l  d1,d0
    ft:     swap    d2
            or.l    d0,d2                    ; Ziel: Seite << 16 | Stufe
            move.l  V_FI(a2),d1
            move.l  d1,d3
            andi.l  #0xffffff,d1             ; jetzt (ohne Blende)
            moveq   #24,d4
            lsr.l   d4,d3                    ; Blende
            moveq   #2,d4
            cmp.l   d4,d3
            bne     fc1
            moveq   #0,d1                    ; ausgeblendet: jetzt aus
            clr.l   V_IC1(a2)
            clr.l   V_IC2(a2)
    fc1:    jmp     SFC3
    ;@SEG
    SFC3:   cmp.l   d1,d2
            beq     fsm
            move.l  d1,d3
            swap    d3
            tst.w   d3
            bne     fon
            clr.l   V_IC1(a2)                ; aus -> an: Zustand leer, einblenden
            clr.l   V_IC2(a2)
            ori.l   #0x1000000,d2
            move.l  d2,V_FI(a2)
            move.l  d2,d0
            andi.l  #0xffff,d0
            jmp     SFCO
    fon:    move.l  d2,d4
            swap    d4
            cmp.w   d3,d4
            bne     fou
            move.l  d2,V_FI(a2)              ; gleiche Seite, neue Stufe
            move.l  d2,d0
            andi.l  #0xffff,d0
            jmp     SFCO
    fou:    ori.l   #0x2000000,d1            ; Seite wechselt / aus: erst ausblenden (alte Koeffizienten)
            move.l  d1,V_FI(a2)
            jmp     SFGO
    fsm:    move.l  d1,V_FI(a2)
            tst.l   d1
            bne     fs1
            rts
    fs1:    jmp     SFGO
    ;@SEG
    SFCO:   lea     FG,a0                    ; d0 = Stufe: g (Q15) -> a1, a2, a3 (Q31)
            mvz.w   0(a0,d0.l*2),d3
            move.l  d3,d4
            lsr.l   #1,d4                    ; g Q14
            move.l  d4,d1
            addi.l  #23170,d1                ; + k (sqrt 2, Q14)
            mulu.l  d4,d1
            moveq   #14,d2
            lsr.l   d2,d1
            addi.l  #16384,d1                ; 1 + g (g + k), Q14
            move.l  #0x40000000,d2
            divu.l  d1,d2                    ; a1 Q16
            moveq   #15,d1
            lsl.l   d1,d2
            bpl     co1
            move.l  #0x7fffffff,d2
    co1:    move.l  d2,V_FA1(a2)
            lsl.l   d1,d3                    ; g Q30
            movclr  acc0,d0
            mac     d3,d2,acc0
            mac     d3,d2,acc0                 ; statt '<<' (smp13)
            movclr  acc0,d2                  ; a2 = g a1
            move.l  d2,V_FA2(a2)
            mac     d3,d2,acc0
            mac     d3,d2,acc0                 ; statt '<<' (smp13)
            movclr  acc0,d2                  ; a3 = g a2
            move.l  d2,V_FA3(a2)
            jmp     SFGO
    ;@SEG
    SFGO:   tst.l   V_VIN(a2)
            beq     go1
            rts                              ; Modelle: im naechsten Block am Wandler
    go1:    lea     -128(a6),a1              ; Clean: dieser Block
            moveq   #0,d7
    go2:    move.l  (a1),d0
            move.l  d7,d1
            jsr     SFX
            move.l  d0,(a1)+
            addq.l  #1,d7
            cmpa.l  a6,a1
            bne     go2
            rts
    ;@SEG
    ; SFX: ein Sample d0 (Q31), d1 = Index im Block (Blende) -> d0. Haelt d6 / d7 / a0..a6; d1..d5, acc0 / acc1 frei.
    ; halbe Skala hinein, v3 = x - ic2, v1 = a1 ic1 + a2 v3, v2 = ic2 + a2 ic1 + a3 v3, ic = 2 v - ic
    SFX:    move.l  d6,-(sp)
            move.l  d1,d6
            move.l  d0,-(sp)                 ; trocken
            asr.l   #1,d0
            move.l  V_FA2(a2),d5
            move.l  V_IC1(a2),d2
            move.l  V_IC2(a2),d3
            move.l  d0,d1
            sub.l   d3,d1                    ; v3
            movclr  acc0,d4
            move.l  V_FA1(a2),d4
            mac     d4,d2,acc0
            mac     d5,d1,acc0               ; v1
            move.l  d3,acc1
            mac     d5,d2,acc1
            move.l  V_FA3(a2),d4
            mac     d4,d1,acc1               ; v2 = Tiefpass
            movclr  acc0,d1
            move.l  d1,d4
            add.l   d4,d4
            sub.l   d2,d4
            move.l  d4,V_IC1(a2)
            movclr  acc1,d4
            move.l  d4,d2
            add.l   d2,d2
            sub.l   d3,d2
            move.l  d2,V_IC2(a2)
            btst    #0,V_FI+1(a2)            ; Seite 1 = Hochpass = x - k v1 - v2
            beq     sx1
            move.l  d0,acc0
            move.l  #{K30},d2
            msac    d2,d1,acc0
            msac    d2,d1,acc0                 ; statt '<<' (smp13)
            movclr  acc0,d0
            sub.l   d4,d0
            move.l  d0,d4
    sx1:    jmp     SFX2
    ;@SEG
    SFX2:   move.l  (sp)+,d1                 ; d4 = y / 2, d1 = trocken
            mvz.b   V_FI(a2),d2
            tst.l   d2
            bne     sx3
            move.l  d4,d0                    ; ohne Blende: verdoppeln (gesaettigt)
            add.l   d0,d0
            bvc     sx9
            move.l  #0x7fffffff,d0
            tst.l   d4
            bpl     sx9
            addq.l  #1,d0
            bra     sx9
    sx3:    asr.l   #1,d1                    ; Blende: y / 2 = d / 2 + (y - d) / 2 * w / 32
            move.l  d4,d0
            sub.l   d1,d0
            asr.l   #5,d0
            moveq   #1,d3
            add.l   d6,d3                    ; ein: w = i + 1
            moveq   #1,d5
            cmp.l   d5,d2
            beq     sx4
            moveq   #31,d3
            sub.l   d6,d3                    ; aus: w = 31 - i
    sx4:    muls.l  d3,d0
            add.l   d1,d0
            add.l   d0,d0
    sx9:    move.l  (sp)+,d6
            rts
    ;@SEG
    ; SFTK: am Wandler (SRK2), d0 = Wert (16 Bit) -> gefiltert (16 Bit); haelt d6 / d7 / a0..a6
    SFTK:   swap    d0
            clr.w   d0
            move.l  a1,d1
            sub.l   a6,d1
            addi.l  #128,d1
            asr.l   #2,d1                    ; Index im Block
            jsr     SFX
            addi.l  #0x8000,d0
            bvc     tk1
            move.l  #0x7fffffff,d0
    tk1:    swap    d0
            ext.l   d0
    SFTKR:  rts
    ;@SEG
    ; SHIFT: d0 += round(log(2^32 / TINC) / log(r)), r = 800^(1/61); d1 / d3..d5 frei
    SHIFT:  move.l  V_TINC(a2),d1
            beq     sh9
            moveq   #0,d3
    sh1:    tst.l   d1
            bmi     sh2
            add.l   d1,d1
            addq.l  #1,d3
            bra     sh1
    sh2:    lsr.l   #8,d1
            lsr.l   #7,d1
            andi.l  #0xffff,d1               ; m (Q16)
            move.l  #0x10000,d4              ; log2(1 + m) ~ m + 0.343 m (1 - m)
            sub.l   d1,d4
            mulu.l  d1,d4
            swap    d4
            andi.l  #0xffff,d4
            move.l  #22479,d5
            mulu.l  d5,d4
            swap    d4
            andi.l  #0xffff,d4
            add.l   d4,d1
            addq.l  #1,d3
            swap    d3
            clr.w   d3
            sub.l   d1,d3                    ; log2(2^32 / TINC), Q16
            move.l  #{SHK},d1
            mulu.l  d1,d3
            addi.l  #0x200000,d3
            moveq   #22,d1
            lsr.l   d1,d3
            add.l   d3,d0
    sh9:    rts
    ''', [M_FL, M_FL2, M_FL3, M_FL7, M_FL4, M_FL5, M_FL6, M_FL8], **VK)


def b_bsh(S):
    """smp12 (Pip: "Blockverschiebung als Zusatzgeste"): FUNC + SAMPLE START (COLOR) auf einer Sampl-Spur verschiebt Start und
    Ende gemeinsam (Core-Encoder-Slot 'sampler'). Die Drehung wird so begrenzt, dass das Fenster seine Breite behaelt; dann
    baut der Handler fuer den Knopf SHAPE (Ende) dasselbe Ereignis wie die Firmware am Haken 0x400081b8 (0x4006f698 bauen,
    0x40006158 senden, 0x400cf76a aufraeumen; d2 / d4 der Firmware) und laesst das Ereignis fuer COLOR weiterlaufen (d0 = 0).
    Mit gehaltenem Trig (p-locks) wie die Firmware."""
    return multi(S, f'''
    BSH:    move.l  4(a2),d0                 ; Encoder 4 = COLOR (Start)
            moveq   #4,d1
            cmp.l   d1,d0
            bne     bn
            pea     1.w
            jsr     {C.HELD}
            addq.l  #4,sp
            tst.l   d0
            beq     bn
            jsr     {UIGET}
            movea.l d0,a0
            tst.b   0x164(a0)                ; Trig gehalten: p-lock wie die Firmware
            bne     bn
            move.l  {ACT_TRACK},d0
            moveq   #5,d1
            cmp.l   d1,d0
            bhi     bn
            move.l  {KITP},d1
            beq     bn
            muls.w  #100,d0
            add.l   d1,d0
            addi.l  #28,d0
            movea.l d0,a0                    ; Sound der Spur
            mvz.b   38(a0),d0
            moveq   #{MACH},d1
            cmp.l   d1,d0
            bne     bn
            jmp     BSH2
    bn:     moveq   #0,d0
            rts
    ;@SEG
    BSH2:   lea     -16(sp),sp
            movem.l d2-d5,(sp)
            mvz.b   42(a0),d2                ; Start
            mvz.b   44(a0),d3                ; Ende
            cmp.l   d3,d2
            bls     bs1
            move.l  d2,d0                    ; d2 = kleiner, d3 = groesser
            move.l  d3,d2
            move.l  d0,d3
    bs1:    mvs.b   8(a2),d1
            bpl     bs2
            neg.l   d2
            cmp.l   d2,d1
            bge     bs3
            move.l  d2,d1
            bra     bs3
    bs2:    moveq   #127,d0
            sub.l   d3,d0
            cmp.l   d0,d1
            ble     bs3
            move.l  d0,d1
    bs3:    move.b  d1,8(a2)                 ; begrenzte Drehung fuer beide
            jmp     BSH3
    ;@SEG
    BSH3:   move.l  20(sp),d3                ; d2 der Firmware (Ereignis-Puffer)
            move.l  36(sp),-(sp)             ; FUNC
            move.l  36(sp),-(sp)             ; d5 der Firmware
            move.l  d1,-(sp)
            pea     5.w                      ; Knopf SHAPE (Ende)
            move.l  d3,-(sp)
            jsr     0x4006F698
            move.l  d3,-(sp)
            move.l  d4,-(sp)
            jsr     0x40006158
            move.l  d3,-(sp)
            jsr     0x400CF76A
            lea     32(sp),sp
            movem.l (sp),d2-d5
            lea     16(sp),sp
            moveq   #0,d0
            rts
    ''', [M_BSH, M_BSH2, M_BSH3])


# ---------------- Daten-Masken (feste Lagen)
def data_parts():
    lab, parts = {}, {}
    # Tabelle der geladenen Samples (RAM)
    lab['TAB'] = TAB_A                               # smp28: in der Nutzlast (32 Plaetze)
    lab['LFAIL'] = LFAIL_A; lab['LNEED'] = LNEED_A
    # Zeilen: 7 x 32 B (Zeile 6: Decay = 24; den Rest schreibt der Konstruktor), danach VEC7
    rows = bytearray(7 * 32); struct.pack_into('>I', rows, 6 * 32, D_DEC)
    lab['ROWS7'] = M_ROWS; lab['VEC7'] = M_ROWS + len(rows)
    parts[M_ROWS] = bytes(rows) + struct.pack('>7I', *range(1, 8))
    parts[M_CT] = model_rows(); lab['MODT'] = M_CT
    parts[M_FG] = struct.pack('>%dH' % NFG, *fg_values()); lab['FG'] = M_FG
    # M_VT: mu-law-Exponenten (257 B), Namen der Modelle (Zeiger, Texte) fuer den Formatierer
    v = bytearray(segt()); lab['SEGT'] = M_VT
    v += bytes(-len(v) % 4); lab['MNAMES'] = M_VT + len(v); at = len(v); v += bytes(4 * NMOD)
    for i, m in enumerate(MODELS):
        struct.pack_into('>I', v, at + 4 * i, M_VT + len(v)); v += MSHORT[i].encode() + b'\0'
    lab['OVB'] = SCR + 0x200                         # Uebersicht beim Laden (256 B im Arbeitsbereich)
    # M_DAT: FH, P12, UPD7, RND7, Lade-Zustand
    d = bytearray()
    lab['P12'] = M_DAT + len(d); d += struct.pack('>13I', *p12_values())
    lab['UPD7'] = M_DAT + len(d); d += bytes(28)
    lab['RND7'] = M_DAT + len(d); d += bytes(28)
    for nm, n in (('LST', 4), ('LREQ', 4), ('LID', 4), ('LPTR', 4), ('LTOT', 4), ('LDONE', 4), ('LFR', 4), ('LRF', 4),
                  ('LSTER', 4), ('LSLOT', 4), ('POOLT', 4), ('LFP', 4), ('LH', 16), ('LFH', 16), ('BUSY', 4),
                  ('LOVC', 4), ('LOVF', 4), ('LOVB', 4), ('LOVMN', 4), ('LOVMX', 4)):
        lab[nm] = M_DAT + len(d); d += bytes(n)
    lab['LH_8'] = lab['LH'] + 8
    d += bytes(-len(d) % 2)
    lab['FH'] = M_DAT + len(d)
    a = A(lab['FH'])
    asm(a, f'''
    FH:     tst.l   d1
            bne     fs
            move.l  76(a0),{O_ID}(a1)
            rts
    fs:     move.l  {O_ID}(a1),76(a0)
            rts
    ''')
    d += adone(a)
    parts[M_DAT] = bytes(d)
    # M_STR: REC8-Daten (RAM), Namen der Maschinen, Texte der Deskriptoren
    s = bytearray()
    lab['R8'] = M_STR; s += bytes(76); lab['R8_4'] = M_STR + 4; lab['R8_8'] = M_STR + 8
    lab['R8OK'] = M_STR + len(s); s += bytes(4)
    lab['R8MAP'] = M_STR + len(s); s += bytes([D_START, D_LEN, D_SWP, D_VIN, D_DEC]) + bytes(3)
    lab['NAMES7'] = M_STR + len(s); names_at = len(s); s += bytes(28)
    strs = {}
    for t in [MNAME] + [k[4] for k in KNOBS] + [k[5] for k in KNOBS]:
        strs[t] = M_STR + len(s); s += t.encode() + b'\0'
    struct.pack_into('>7I', s, names_at, *NAMES_ORIG, strs[MNAME])
    parts[M_STR] = bytes(s)
    v += bytes(-len(v) % 4); lab['KDN'] = M_VT + len(v); at = len(v); v += bytes(8)
    for i, t in enumerate(KDLAB):
        struct.pack_into('>I', v, at + 4 * i, M_VT + len(v)); v += t.encode() + b'\0'
    for nm, n in (('OVR', 24), ('BRP', 4), ('BRT', 4), ('BRC', 4)):
        lab[nm] = M_VT + len(v); v += bytes(n)
    parts[M_VT] = bytes(v)
    return parts, lab, strs


CODE = (b_reg, b_rec, b_vox, b_trg, b_blk, b_rnd, b_ld, b_ls, b_lc, b_br, b_kd, b_sl, b_flt, b_bsh)
CODE_MASKS = (M_REG, M_REC, M_VOX, M_TRG, M_TRG2, M_BLK, M_BLK2, M_BLK3, M_RND, M_CLN, M_RAS, M_RAS2, M_RAS3, M_RAS4, M_BQ, M_RAS5,
              M_BQ2, M_LOV, M_LOV2, M_SLK, M_BRT, M_BRP, M_BRN, M_BRL, M_FL, M_FL2, M_FL3, M_FL4, M_FL5, M_FL6, M_FL7, M_FL8, M_BSH, M_BSH2, M_BSH3, M_KD, M_KD2, M_KD3, M_LD, M_LK, M_LS, M_LS2, M_LF, M_LC,
              M_LC2, M_BR, M_BR2)


def build():
    parts, lab, strs = data_parts()
    S = collections.defaultdict(int, lab)
    for _ in range(2):                                   # 1. Durchgang: Lagen der Labels; 2.: mit allen Adressen
        E.LOG[:] = [x for x in E.LOG if not any(va <= x[0] < va + SIZE[va] for va in CODE_MASKS)]
        E.LOG[:] = [x for x in E.LOG if not PX_ORG <= x[0] < PX_END]
        found = {}
        for fn in CODE:
            pieces, l = fn(S)
            for va, code in pieces:
                parts[va] = code
            found.update(l)
        a = A(PX_ORG); asm(a, px_text(), S); found.update(a.lab)          # smp28: Lade-Verwaltung in der Nutzlast
        px = adone(a, S); assert PX_ORG + len(px) <= DCKS_A, (len(px), DCKS_A - PX_ORG)   # smp41: DCKS dahinter
        S = dict(lab, **found)
    parts['PX'] = px
    # update / render mit 7 Eintraegen
    upd = struct.pack('>7I', *UPD_ORIG, S['SUPD']); rnd = struct.pack('>7I', *RND_ORIG, S['SRND'])
    d = bytearray(parts[M_DAT])
    d[S['UPD7'] - M_DAT:S['UPD7'] - M_DAT + 28] = upd
    d[S['RND7'] - M_DAT:S['RND7'] - M_DAT + 28] = rnd
    parts[M_DAT] = bytes(d)
    _, pl = b_pay()
    S.update({k: pl[k] for k in ('MIMG', 'MIMGF', 'GBM', 'GICON') + XSYMS})
    return parts, S, strs


def desc_rows(strs):
    out = []
    for k, slot, dflt, key, lng, sht in KNOBS:
        top = (NMOD - 1) << 8 if k == D_VIN else 0x7F00
        out.append((DESC0 + DSTRIDE * k, struct.pack('>14I', MACH, slot, 0, top, dflt, 0, 0xFFFFFFFF, 0xFFFFFFFF, 0,
                                                     0x600, key, strs[lng], SNARE_GROUP, strs[sht])))
    return out


def tweak(img):
    base = apply(img, core.tweak(img))
    parts, S, strs = build()
    W = Writes(base)
    px = parts.pop('PX')
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    for va, ck, new in BOUNDS:
        W.hook(va, (2, ck), struct.pack('>H', new))
    W.hook(MAP6, MAP_CK, bytes([MACH]))
    W.hook(ALG_MAX, struct.pack('>I', (MACH - 1) << 8), struct.pack('>I', MACH << 8))
    for va in ROW_REFS:
        W.hook(va, struct.pack('>I', ROWS), struct.pack('>I', S['ROWS7']))
    W.hook(NAMES_REF, struct.pack('>I', NAMES), struct.pack('>I', S['NAMES7']))
    W.hook(UPD_REF, struct.pack('>I', UPD_TAB), struct.pack('>I', S['UPD7']))
    W.hook(RND_REF, struct.pack('>I', RND_TAB), struct.pack('>I', S['RND7']))
    blob, pl = b_pay()
    assert len(base) == C.IMG_END - BASE + C.PAYSZ
    W.put(C.IMG_END + PAY_OFF, blob)                                   # smp17: Platz 'sampler' der Nutzlast
    assert PAY_ORG + len(blob) <= PX_ORG, (len(blob), PX_ORG - PAY_ORG)
    W.put(C.IMG_END + (PX_ORG - C.PAY), px)                            # smp28: Lade-Verwaltung
    W.hook(IMG_HOOK, IMG_CK, jmp(S['MIMG']))
    W.hook(X_ID, X_ID_CK, jmp(S['XID']))                               # smp20: Transfer-Kennung CYC / SMP
    W.hook(X_PR, X_PR_CK, jmp(S['XPR']))
    W.hook(X_RT, jsr(X_RTFN), jsr(S['XRT']))
    W.hook(X_OT, X_OT_CK, jmp(S['XOT']) + bytes.fromhex('4e71'))
    W.hook(X_CFG, X_CFG_CK, jmp(S['XCFG']))
    W.hook(RAT_HOOK, RAT_CK, jmp(S['RAT']))
    W.hook(ROF_HOOK, ROF_CK, jmp(S['ROF']))
    W.hook(KV_HOOK, KV_CK, jsr(S['KV']) + bytes.fromhex('4e71'))
    W.hook(BR_HOOK, jsr(PARSE), jsr(S['SPARSE']))
    W.hook(TK_HOOK, jsr(VCRENDER), jsr(S['STICK']))
    W.hook(VT_KDRAW, struct.pack('>I', KDRAW_ORIG), struct.pack('>I', S['KDRAW']))
    W.hook(SL_HOOK, SL_CK, jsr(S['SLK']) + bytes.fromhex('4e71'))
    # smp15 (Pip 03.11.): wie beim Model:Samples erst das Anklicken (YES) legt das Sample auf Spur / Trig; der Cursor allein
    # setzt nichts mehr (KCUR bleibt im Code, die Vtable 0x40118438 bleibt bei der Firmware)
    for va, row in desc_rows(strs):
        assert struct.unpack_from('>i', base, va - BASE)[0] == -1, f"Deskriptor {(va - DESC0) // DSTRIDE} nicht frei"
        W.put(va, row)
    core.sslot_write(W, 'sampler', S['FH'])
    core.slot_write(W, 'sampler', S['BSH'])
    hooks = [x[0] for x in BOUNDS] + [MAP6, ALG_MAX] + list(ROW_REFS) + [NAMES_REF, UPD_REF, RND_REF, IMG_HOOK, RAT_HOOK,
                                                                         ROF_HOOK, KV_HOOK, BR_HOOK, TK_HOOK, VT_KDRAW, SL_HOOK,
                                                                         X_ID, X_PR, X_RT, X_OT, X_CFG]
    return patch('sampler', 16, 'Grit (sampler machine)',
                 ["7th machine 'Grit': plays samples from the +Drive (Elektron format), chosen in the preset browser.",
                  "PITCH, DECAY, COLOR = sample start, SHAPE = sample length, CONTOUR = model; PUNCH = loop, GATE = reverse.",
                  "Models: CLEAN, SP (26 kHz fixed clock, drop-sample, 12 bit, 4-pole 12 kHz), LM (28 kHz clock with pitch,"
                  " 8-bit mu-law, 2-pole 11 kHz). Turning COLOR / SHAPE shows the waveform with start and end lines.",
                  "Sample locks lock only the sample; clicking a file in the browser (YES) puts it on the track / trig, like on the Model:Samples.",
                  "All sample locks of the playing pattern are preloaded and kept in memory (up to 32 samples); freed memory is reused.",
                  "FUNC + PITCH = Voices 1..3: up to 3 notes ring at once (each with its own sample, pitch, start / end); a trig cuts",
                  " its own previous note (e.g. a fast 808), the oldest note fades out. Default 1 = as before.",
                  "Device Config > Transfer: CYC (stock) / SMP (answers Elektron Transfer as a Model:Samples, for uploading samples; method from",
                  " Model-TG by TinyGregAudio, MIT; own code). Every boot starts at CYC; reconnect Transfer after switching; never accept an OS in SMP.",
                  "Erzeugt von v2/g2_sampler.py."], W,
                 requires=['core'], hooks=[f"{x:#x}" for x in hooks],
                 memory=[{"va": f"{TAB_A:#x}", "size": 16 * NTAB, "ram": True, "use": "loaded samples (payload)"},
                         {"va": f"{M_ROWS:#x}", "size": 7 * 32, "ram": True, "use": "machine rows (7)"},
                         {"va": f"{POOL0:#x}", "size": POOL_END - SCR, "ram": True, "use": "sample memory (outside the image)"}],
                 symbols={k: f"{S[k]:#x}" for k in ('SUPD', 'SRND', 'STRIG', 'SBLK', 'STICK', 'LSTART', 'LCHUNK', 'LKNOWN',
                                                     'SPARSE', 'FH', 'REC8', 'RAT', 'ROF', 'KV', 'MIMG', 'MIMGF', 'GBM', 'GICON', 'TAB', 'ROWS7', 'VEC7',
                                                     'NAMES7', 'UPD7', 'RND7', 'LST', 'LREQ', 'POOLT', 'LFAIL', 'R8', 'R8OK', 'BUSY',
                                                     'MODT', 'SEGT', 'MNAMES', 'MFMT', 'SBQ', 'P12', 'KDRAW', 'LOV', 'LOVI',
                                                     'LOVC', 'OVB', 'SLK', 'KSO', 'KSO2', 'PLF', 'NEED', 'LEVICT', 'LALLOC', 'LFIT', 'LNEED', 'DCK', 'KCUR', 'BRPREV', 'OVR', 'BRP', 'BRC', 'SFTK', 'SFTKR', 'SFLT', 'SFX', 'BSH') + XSYMS},
                 params={"machine": MACH, "k_id": K_ID, "pool": [f"{POOL0:#x}", f"{POOL_END:#x}"], "ntab": NTAB,
                         "voice": {k: f"{x:#x}" for k, x in V.items()}})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, S, _ = build()
    print({f"{va:#x}" if va != "PX" else va: (len(b), SIZE.get(va, PX_END - PX_ORG)) for va, b in parts.items()})

# level-pan-values (v2, Patch 19): Portierung aus Modded-Cycles. Prueft mit dem Test von Modded-Cycles
# (tools/emu/test_level_pan.py, 18nelli18, MIT): echter UI-Takt, Schrittweite, Encoder- und Zeichen-Haken des Hauptbild-
# schirms, Pixel aller Werte gegen das Modell der Schrift, Anzeigedauer. Basis = v2-Image ohne Patch 19, Image = mit.
# Dazu: Variablen im Image auf null, keine Schreibstelle eines anderen v2-Patches auf denselben Bytes (gen_all prueft das).
# Aufruf: test_levelpan.py [--alone]
import sys, struct, importlib.util
from rig import *
ALONE = '--alone' in sys.argv
sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools' / 'emu')); sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools'))
spec = importlib.util.spec_from_file_location('lptest', ROOT / 'Modded-Cycles' / 'tools' / 'emu' / 'test_level_pan.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
# Der v2-Takthaken sitzt am Anfang des Timer-Dienstes (0x40090f48, hold-mute belegt 0x400081f2). Der Rig des Upstream-Tests
# ersetzt 0x40090f48 komplett; hier wird stattdessen hinter den zwei Eingangsbefehlen (0x40090f50) abgefangen.
TIMERS_CONT = 0x40090F50
M.TIMERS = 0x9F800000                                           # Upstream-Stub auf eine nie erreichte Adresse
_init = M.Rig.__init__
def _rig_init(r, im, var):
    _init(r, im, var)
    def hook(uc, a, size, _):
        sp = uc.reg_read(M.mk.UC_M68K_REG_A7)
        regs = [uc.reg_read(x) for x in (M.mk.UC_M68K_REG_D2, M.mk.UC_M68K_REG_A2, M.mk.UC_M68K_REG_A3, M.mk.UC_M68K_REG_A4)]
        r.seen.setdefault('timers', []).append((r.r32(sp + 28), list(struct.unpack('>4I', uc.mem_read(sp, 16))) == regs))
        uc.reg_write(M.mk.UC_M68K_REG_PC, r.r32(sp + 24)); uc.reg_write(M.mk.UC_M68K_REG_A7, sp + 28)
    r.uc.hook_add(M.UC_HOOK_CODE, hook, begin=TIMERS_CONT, end=TIMERS_CONT)
M.Rig.__init__ = _rig_init
def own_tick(base, img, var):
    out = {}
    for name, im in (('Basis', base), ('Image', img)):
        r = M.Rig(im, var)
        r.w32(var[0], 0xfffffffe)
        out[name] = [r.tick() for _ in range(3)]
        out[name + 'cnt'] = r.r32(var[0])
    chk('Takt: Timer-Dienst mit gleichem Argument, gleichem Rahmen (d2/a2-a4), Pile ausgeglichen', 
        out['Basis'] == out['Image'] == [([(0x5a5a0005, True)], True)] * 3)
    chk('Takt: Zaehler +1 pro Takt im Image (%d), Basis unveraendert' % out['Imagecnt'], out['Imagecnt'] == 1)
ids = ['level-pan-values'] if ALONE else V2_IDS
img = v2_image(ids, latch=not ALONE)
base = v2_image([i for i in ids if i != 'level-pan-values'], latch=not ALONE)
LS = V2SYM['level-pan-values']
var = (LS['LP_CNT'], LS['LP_PAN'], LS['LP_LVL'])
chk('Zaehler und Ablaufzeiten im Image auf null', img[var[0] - BASE:var[0] - BASE + 68] == bytes(68))
print('Modded-Cycles-Test:')
own_tick(base, img, var); M.step((base, var), (img, var), None); M.encoder(img, var); M.draw(img, var)
M.pixels(img, None, var); M.duration(img, None, var)
chk('Modded-Cycles-Test (Takt, Schrittweite, Encoder, Zeichnen, Pixel aller Werte, Dauer): %d Fehler %s' % (len(M.FAIL), M.FAIL[:3]),
    not M.FAIL)
done()

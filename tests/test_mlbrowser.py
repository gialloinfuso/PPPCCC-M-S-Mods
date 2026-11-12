# multiline-browser (v2, Patch 17): Portierung aus Modded-Cycles. Prueft mit dem Test von Modded-Cycles
# (tools/emu/test_multiline_browser.py, 18nelli18, MIT): echter Zeichenlauf des Browsers 0x400a539c, echte Liste, echte
# Schriften. Basis = v2-Image ohne Patch 17, Image = mit (alle anderen Patches, auch sampler und browser-scroll, dabei).
# Dazu: Schreibstellen nur in den eigenen Masken / an den Haken, keine auf der Laufschrift-Stelle 0x400a55a1..a3.
# Aufruf: test_mlbrowser.py [--alone]   (--alone: nur dieser Patch)
import sys, importlib.util
from rig import *
import g2_mlbrowser as ML
ALONE = '--alone' in sys.argv
spec = importlib.util.spec_from_file_location('mltest', ROOT / 'Modded-Cycles' / 'tools' / 'emu' / 'test_multiline_browser.py')
sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools' / 'emu')); sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools'))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
ids = ['multiline-browser'] if ALONE else V2_IDS
img = v2_image(ids, latch=not ALONE)
base = v2_image([i for i in ids if i != 'multiline-browser'], latch=not ALONE)
t = V2P['multiline-browser']
mine = [(w['off'] + BASE, len(w['new']) // 2) for w in t['writes']]
chk('keine Schreibstelle auf der Laufschrift-Stelle 0x400a55a1..0x400a55a3 (browser-scroll)',
    all(a + n <= M.SCROLL_HOOK or a >= M.SCROLL_HOOK + 3 for a, n in mine))
has_scroll = base[M.SCROLL_HOOK - BASE:M.SCROLL_HOOK - BASE + 3] != STOCK[M.SCROLL_HOOK - BASE:M.SCROLL_HOOK - BASE + 3]
print('Modded-Cycles-Test:')
M.screen(base, img); M.moves(base, img); M.small(base, img); M.subfolder(base, img); M.marks(img); M.empty(img)
M.scroll(img, has_scroll)
chk('Modded-Cycles-Test (Bildschirm, Cursor, kleine Ordner, Unterordner, geladener Sound, Zeichen, leer, Laufschrift): '
    '%d Fehler %s' % (len(M.FAIL), M.FAIL[:3]), not M.FAIL)
done()

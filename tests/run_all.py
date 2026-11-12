#!/usr/bin/env python3
"""Run every emulator test against your own firmware.

usage: python3 tests/run_all.py <section_3_MAIN_OS.bin of the official Model:Cycles OS 1.13> [test name ...] [-j N]

Needs: unicorn, capstone, numpy and Pillow (pip install unicorn capstone numpy pillow), and a checkout of
https://github.com/18nelli18/Modded-Cycles (folder "Modded-Cycles": tools/sprites.py and the emulator rigs in
tools/emu) in the repository root. With a checkout of https://github.com/drumkilla/elektron-model-tweaks there as well,
test_latch.py and test_browserscroll.py also compare the latching mute and the scrolling names with drumkilla's tweaks.

The tests were written against a development layout. This script builds it in build/testenv (git-ignored) with
src/regen.py: it regenerates every patch, and also the v1.0.0 patches, which some tests use as the reference (the
v2 sound code must be bit-identical to v1). Then it runs each test there, two at a time (-j to change). The tests
run the original firmware code in Unicorn, print their checks (in German) and end with an overall result ("GESAMT ok").
Each test takes from a few seconds to several minutes.
"""
import json
import pathlib
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import regen  # noqa: E402

ENV = ROOT / 'build' / 'testenv'
ROOT_FILES = ('ramalias.py',)                       # lives in the env root (the tests import it from there)
# 02 and 03 are byte-identical to v1.0.0 (development names of v1)
SAME_AS_V1 = [('02-hold-mute', '64-hold-mute-v3'), ('03-delay-notes', '65-delay-notes')]
# tests that also run on an image with only the core and that patch
ALONE = ('test_control', 'test_directjump', 'test_fill2', 'test_filterleds', 'test_levelpan', 'test_lfoamount',
         'test_mlbrowser', 'test_sampler', 'test_trackfilter', 'test_trigselect')


def run(work, name, args):
    r = subprocess.run([sys.executable, f'{name}.py'] + args, cwd=work / 'v2' / 'tests', capture_output=True, text=True,
                       errors='replace')
    out = r.stdout + r.stderr
    bad = r.returncode != 0 or 'GESAMT ok' not in out
    return name + (' ' + ' '.join(args) if args else ''), bad, '\n'.join(out.strip().splitlines()[-3:])


def main():
    argv = sys.argv[1:]
    jobs = 2
    if '-j' in argv:
        i = argv.index('-j'); jobs = int(argv[i + 1]); del argv[i:i + 2]
    if not argv:
        sys.exit(__doc__)
    only = set(argv[1:])
    work = regen.make_env(argv[0], ENV, v1=True)
    (work / 'v2' / 'tests').mkdir()
    for f in (ROOT / 'tests').glob('*.py'):
        if f.name in ROOT_FILES:
            shutil.copy(f, work / f.name)
        elif f.name != 'run_all.py':
            shutil.copy(f, work / 'v2' / 'tests' / f.name)
    failed = []
    for v2, v1 in SAME_AS_V1:
        a = json.loads((work / 'v2' / 'out' / f'{v2}.json').read_text())['writes']
        b = json.loads((work / 'solo' / f'{v1}.json').read_text())['writes']
        if [(w['off'], w['old'], w['new']) for w in a] != [(w['off'], w['old'], w['new']) for w in b]:
            failed.append(f'{v2} differs from v1')
    print('02, 03 identical to v1.0.0' if not failed else '!! ' + ', '.join(failed))
    names = sorted(f.stem for f in (ROOT / 'tests').glob('test_*.py'))
    todo = [(n, []) for n in names] + [(n, ['--alone']) for n in ALONE if n in names]
    if only:
        todo = [(n, a) for n, a in todo if n in only or n[5:] in only]
    with ThreadPoolExecutor(jobs) as ex:
        for label, bad, tail in ex.map(lambda x: run(work, *x), todo):
            print(f"\n===== {label}: {'FAILED' if bad else 'ok'}\n{tail}", flush=True)
            if bad:
                failed.append(label)
    print('\nall tests ok' if not failed else f"\nFAILED: {', '.join(failed)}")
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()

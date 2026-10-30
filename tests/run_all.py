#!/usr/bin/env python3
"""Run every emulator test against your own firmware.

usage: python3 tests/run_all.py <section_3_MAIN_OS.bin of the official Model:Cycles OS 1.13> [test name ...]

Needs: unicorn and capstone (pip install unicorn capstone), Pillow (optional), and checkouts of
https://github.com/18nelli18/Modded-Cycles (folder "Modded-Cycles": tools/sprites.py and the seqrig / mcengine
emulator rigs) and https://github.com/drumkilla/elektron-model-tweaks (folder "elektron-model-tweaks", for
01-latching-mute.json) in the repository root.

The tests were written against a development layout. This script builds it in build/testenv (git-ignored) with
src/regen.py: it regenerates every v2 patch, and also the v1.0.0 patches, which some tests use as the reference
(the v2 sound code must be bit-identical to v1; patches 01-04 are unchanged and keep their v1 tests). Then it runs
each test there. The tests print their checks (in German) and end with an overall result.
"""
import json
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import regen  # noqa: E402

ENV = ROOT / 'build' / 'testenv'
ROOT_TESTS = ('test_settings_key_113.py', 'test_solo.py', 'test_livemute.py', 'test_holdmute_113.py', 'test_delaynotes.py',
              'ramalias.py')
# 01-04 are byte-identical to v1.0.0; their tests use the development names of v1
SAME_AS_V1 = [('01-mute-solo', '62-mute-solo'), ('02-live-mute', '63-live-mute'), ('03-hold-mute', '64-hold-mute-v3'),
              ('04-delay-notes', '65-delay-notes')]
# (label, file, arguments); tests in ROOT_TESTS run in the env root, the others in v2/tests
TESTS = [('solo', 'test_solo', []), ('livemute', 'test_livemute', []), ('holdmute_113', 'test_holdmute_113', []),
         ('delaynotes', 'test_delaynotes', ['smp/delaynotes.bin']),
         ('core', 'test_core', []), ('popup', 'test_popup', []), ('modular', 'test_modular', []),
         ('fx_diff', 'test_fx_diff', []), ('mods_diff', 'test_mods_diff', []), ('groove_seq', 'test_groove_seq', []),
         ('control', 'test_control', []), ('control --alone', 'test_control', ['--alone']),
         ('trigselect', 'test_trigselect', []), ('trigselect --alone', 'test_trigselect', ['--alone']),
         ('fill2', 'test_fill2', []), ('fill2 --alone', 'test_fill2', ['--alone']),
         ('trackfilter', 'test_trackfilter', []), ('trackfilter --alone', 'test_trackfilter', ['--alone']),
         ('filterleds', 'test_filterleds', []), ('filterleds --alone', 'test_filterleds', ['--alone']),
         ('lfoamount', 'test_lfoamount', []), ('lfoamount --alone', 'test_lfoamount', ['--alone']),
         ('directjump', 'test_directjump', []), ('directjump --alone', 'test_directjump', ['--alone']),
         ('settings_key_113', 'test_settings_key_113', ['v2/out/full_section3.bin'])]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    only = set(sys.argv[2:])
    work = regen.make_env(sys.argv[1], ENV, v1=True)
    (work / 'v2' / 'tests').mkdir()
    for f in (ROOT / 'tests').glob('*.py'):
        if f.name in ROOT_TESTS:
            shutil.copy(f, work / f.name)
        elif f.name != 'run_all.py':
            shutil.copy(f, work / 'v2' / 'tests' / f.name)
    failed = []
    for v2, v1 in SAME_AS_V1:
        a = json.loads((work / 'v2' / 'out' / f'{v2}.json').read_text())['writes']
        b = json.loads((work / 'solo' / f'{v1}.json').read_text())['writes']
        if [(w['off'], w['old'], w['new']) for w in a] != [(w['off'], w['old'], w['new']) for w in b]:
            failed.append(f'{v2} differs from v1')
    print('01-04 identical to v1.0.0' if not failed else '!! ' + ', '.join(failed))
    img = bytearray((work / 'out' / 'section_3_MAIN_OS.bin').read_bytes())
    for w in json.loads((work / 'v2' / 'out' / '04-delay-notes.json').read_text())['writes']:
        n = bytes.fromhex(w['new'])
        img[w['off']:w['off'] + len(n)] = n
    (work / 'smp').mkdir()
    (work / 'smp' / 'delaynotes.bin').write_bytes(img)
    for label, name, args in TESTS:
        if only and name not in only and label not in only:
            continue
        cwd = work if f'{name}.py' in ROOT_TESTS else work / 'v2' / 'tests'
        print(f"\n===== {label}", flush=True)
        r = subprocess.run([sys.executable, f'{name}.py'] + args, cwd=cwd, capture_output=True, text=True,
                           errors='replace')
        out = r.stdout + r.stderr
        print('\n'.join(out.strip().splitlines()[-4:]))
        if r.returncode != 0 or 'FAIL' in out or 'FEHLER' in out:
            failed.append(label)
    print('\nall tests ok' if not failed else f"\nFAILED: {', '.join(failed)}")
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()

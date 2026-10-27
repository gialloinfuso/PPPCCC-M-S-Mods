#!/usr/bin/env python3
"""Regenerate every patch from the generators and compare it with patches/.

usage: python3 src/regen.py <section_3_MAIN_OS.bin of the official Model:Cycles OS 1.13> [<work dir>]

Needs checkouts of https://github.com/18nelli18/Modded-Cycles (folder "Modded-Cycles", for tools/sprites.py) and
https://github.com/drumkilla/elektron-model-tweaks (folder "elektron-model-tweaks", for 01-latching-mute.json, which
the overlap check applies first) in the repository root, and capstone (pip install capstone).

The generators were written against a development layout. This script builds it in the work dir (default:
build/regen, git-ignored):

  out/section_3_MAIN_OS.bin   your base image
  solo/                       src/*.py   (shared code: assembler, effect cores, popup fonts, groove tables)
  v2/                         src/v2/*.py (one generator per patch, gen_all.py runs them all)
  grooves/, Modded-Cycles, elektron-model-tweaks

gen_all.py writes the development format to v2/out/: with the original bytes in "old", and in "orig" the places
where a patch's code holds original firmware bytes (instructions a hook moves; the generators copy them from your
image). That stays on your machine. This script reduces every write the same way as the published patches
(tools/apply_patches.py to_public: len + SHA-256, "orig" -> zeros + "from_original") and checks that the result is
identical to patches/*.json.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_patches  # noqa: E402  (to_public: the same reduction as the published patches)
CHECKOUTS = ('Modded-Cycles', 'elektron-model-tweaks')
# v1.0.0 generators (development names), used by the tests as the reference for the v2 sound and gesture code
V1GEN = [('gen_solo.py', '62-mute-solo'), ('gen_livemute.py', '63-live-mute'), ('gen_holdmute_113.py', '64-hold-mute-v3'),
         ('gen_delaynotes_113.py', '65-delay-notes'), ('gen_chorus_113.py', '66-chorus'), ('gen_phaser_113.py', '67-phaser'),
         ('gen_digidelay_113.py', '68-digi-delay'), ('gen_razer_113.py', '69-razer'), ('gen_moddelay_113.py', '70-mod-delays'),
         ('gen_strum_113.py', '71-strum'), ('gen_loadmeter_113.py', '72-load-meter'), ('gen_groove_113.py', '73-groove')]


def make_env(base, work, v1=False):
    """Build the development layout in work and run all v2 generators (and the v1 ones if v1)."""
    base, work = pathlib.Path(base).resolve(), pathlib.Path(work)
    for need in CHECKOUTS:
        if not (ROOT / need).is_dir():
            sys.exit(f"!! missing checkout: {ROOT / need}")
    if work.exists():
        shutil.rmtree(work)
    (work / 'out').mkdir(parents=True)
    shutil.copy(base, work / 'out' / 'section_3_MAIN_OS.bin')
    shutil.copytree(ROOT / 'src', work / 'solo', ignore=shutil.ignore_patterns('v2', '__pycache__', 'regen.py'))
    shutil.copytree(ROOT / 'src' / 'v2', work / 'v2', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT / 'grooves', work / 'grooves')
    for need in CHECKOUTS:
        os.symlink(ROOT / need, work / need)
    subprocess.run([sys.executable, 'v2/gen_all.py'], cwd=work, check=True, stdout=subprocess.DEVNULL)
    if v1:
        for gen, name in V1GEN:
            subprocess.run([sys.executable, str(work / 'solo' / gen), str(work / 'out' / 'section_3_MAIN_OS.bin'),
                            str(work / 'solo' / f'{name}.json')], cwd=work / 'solo', check=True, stdout=subprocess.DEVNULL)
    return work


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    work = make_env(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ROOT / 'build' / 'regen')
    names = json.loads((ROOT / 'patches' / 'manifest.json').read_text())['patches']
    bad = 0
    for name in names:
        dev = json.loads((work / 'v2' / 'out' / name).read_text())
        pub = json.loads((ROOT / 'patches' / name).read_text())
        same = ([apply_patches.to_public(w) for w in dev['writes']] == pub['writes']
                and dev['id'] == pub['id'] and dev['order'] == pub['order'])
        bad += not same
        print(f"{'ok ' if same else 'DIFF'} {name[:-5]}")
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()

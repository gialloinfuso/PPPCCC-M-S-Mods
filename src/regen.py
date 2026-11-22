#!/usr/bin/env python3
"""Regenerate every patch from the generators and compare it with patches/.

usage: python3 src/regen.py <official model-cycles_OS1.13.syx, or its section_3_MAIN_OS.bin> [<work dir>]
       python3 src/regen.py <official .syx or .bin> --write [--samples <Cycles OS for Model:Samples .syx or .bin>]

Without --write it only compares. With --write it rewrites patches/*.json from the generators (name, description and
the other hand-written fields of each published file stay as they are; requires, hooks, memory, symbols ... and the writes
come from the generator) and patches/manifest.json (full set and result checksums). --samples also renews the checksums
of the Model:Samples base in the manifest; without it that entry is kept and flagged as possibly stale.

Needs a checkout of https://github.com/18nelli18/Modded-Cycles (folder "Modded-Cycles", for tools/sprites.py, the list
of free sprite masks) in the repository root, plus capstone and Pillow (pip install capstone pillow).

The generators were written against a development layout. This script builds it in the work dir (default:
build/regen, git-ignored):

  out/section_3_MAIN_OS.bin   your base image
  solo/                       src/*.py   (shared code: effect cores, popup fonts, groove tables)
  v2/                         src/v2/*.py (one generator per patch, gen_all.py runs them all)
  grooves/, Modded-Cycles

gen_all.py writes the development format to v2/out/: with the original bytes in "old", and in "orig" the places
where a patch's code holds original firmware bytes (instructions a hook moves; the generators copy them from your
image). That stays on your machine. This script reduces every write the same way as the published patches
(tools/apply_patches.py to_public: len + SHA-256, "orig" -> zeros + "from_original") and checks that the result is identical to patches/*.json.
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_patches  # noqa: E402  (to_public: the same reduction as the published patches)
CHECKOUTS = ('Modded-Cycles',)
# v1.0.0 generators (development names), used by the tests as the reference for the v2 sound and gesture code
V1GEN = [('gen_solo.py', '62-mute-solo'), ('gen_livemute.py', '63-live-mute'), ('gen_holdmute_113.py', '64-hold-mute-v3'),
         ('gen_delaynotes_113.py', '65-delay-notes'), ('gen_chorus_113.py', '66-chorus'), ('gen_phaser_113.py', '67-phaser'),
         ('gen_digidelay_113.py', '68-digi-delay'), ('gen_razer_113.py', '69-razer'), ('gen_moddelay_113.py', '70-mod-delays'),
         ('gen_strum_113.py', '71-strum'), ('gen_loadmeter_113.py', '72-load-meter'), ('gen_groove_113.py', '73-groove')]


KEEP = ('requires', 'conflicts', 'hooks', 'memory', 'settings', 'pattern', 'symbols', 'params')
TR = {'S1 + SC': 'press hook + UI tick', 'S2 + Zustand': 'release hook + state', 'Anzeige + Tabelle': 'display + table',
      'DSP-Triolen': 'DSP triplets'}
GERMAN = r'[äöüß]|Erzeugt|Zustand|Anzeige|Spur|Knopf|Taste|Muster'    # published patch files are English


def tr(x):
    if isinstance(x, str): return TR.get(x, x)
    if isinstance(x, list): return [tr(v) for v in x]
    if isinstance(x, dict): return {k: tr(v) for k, v in x.items()}
    return x


def section3(path):
    """section 3 (MAIN OS) from a .syx (unpacked with tools/vendor) or a .bin"""
    path = pathlib.Path(path)
    if path.suffix.lower() != '.syx':
        return path.read_bytes()
    sys.path.insert(0, str(ROOT / 'tools' / 'vendor'))
    import tweak
    return bytes(tweak.read_firmware(str(path))['main_os'])


def write(work, base_img, samples_img=None):
    """patches/*.json and manifest.json from the generator output in work/v2/out"""
    import re
    mpath = ROOT / 'patches' / 'manifest.json'
    man = json.loads(mpath.read_text())
    names = man['patches']
    for name in names:
        dev = json.loads((work / 'v2' / 'out' / name).read_text())
        pub = json.loads((ROOT / 'patches' / name).read_text())
        assert dev['id'] == pub['id'] and dev['order'] == pub['order'], name
        new = {k: v for k, v in pub.items() if k not in KEEP and k != 'writes'}
        for k in KEEP:
            if k in dev: new[k] = tr(dev[k])
        new['writes'] = [apply_patches.to_public(w) for w in dev['writes']]
        txt = json.dumps(new)
        m = re.search(GERMAN, txt)
        if m:
            sys.exit(f"!! {name}: German text in a published field near: {txt[max(0, m.start() - 80):m.end() + 40]}")
        (ROOT / 'patches' / name).write_text(json.dumps(new, indent=1) + '\n')
        print(f"{'same' if new == pub else 'NEW '} {name[:-5]}")
    ps = [json.loads((ROOT / 'patches' / n).read_text()) for n in names]
    full = (work / 'v2' / 'out' / 'full_section3.bin').read_bytes()
    man['full_set'] = [t['id'] for t in ps]
    for b in man['bases']:
        img = base_img if b['target'] == 'cycles' else samples_img
        if img is None:
            print(f"   manifest: '{b['target']}' base kept (pass --samples to renew it)")
            continue
        res = apply_patches.apply(img, ps)
        if b['target'] == 'cycles':
            assert res == full, 'published patches do not reproduce the generator image'
        b.update(section3_sha256=hashlib.sha256(img).hexdigest(), full_set_result_sha256=hashlib.sha256(res).hexdigest(),
                 result_size=len(res))
    mpath.write_text(json.dumps(man, indent=1) + '\n')
    print('   manifest.json written')


def make_env(base, work, v1=False):
    """Build the development layout in work and run all v2 generators (and the v1 ones if v1)."""
    work = pathlib.Path(work)
    for need in CHECKOUTS:
        if not (ROOT / need).is_dir():
            sys.exit(f"!! missing checkout: {ROOT / need}")
    if work.exists():
        shutil.rmtree(work)
    (work / 'out').mkdir(parents=True)
    (work / 'out' / 'section_3_MAIN_OS.bin').write_bytes(base if isinstance(base, bytes) else section3(base))
    shutil.copytree(ROOT / 'src', work / 'solo', ignore=shutil.ignore_patterns('v2', '__pycache__', 'regen.py'))
    shutil.copytree(ROOT / 'src' / 'v2', work / 'v2', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT / 'grooves', work / 'grooves')
    for need in CHECKOUTS:
        os.symlink(ROOT / need, work / need)
    if (ROOT / 'elektron-model-tweaks').is_dir():                # optional: tests compare with drumkilla's tweaks
        os.symlink(ROOT / 'elektron-model-tweaks', work / 'elektron-model-tweaks')
    subprocess.run([sys.executable, 'v2/gen_all.py'], cwd=work, check=True, stdout=subprocess.DEVNULL)
    if v1:
        for gen, name in V1GEN:
            subprocess.run([sys.executable, str(work / 'solo' / gen), str(work / 'out' / 'section_3_MAIN_OS.bin'),
                            str(work / 'solo' / f'{name}.json')], cwd=work / 'solo', check=True, stdout=subprocess.DEVNULL)
    return work


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.exit(__doc__)
    do_write = '--write' in argv
    if do_write: argv.remove('--write')
    samples = None
    if '--samples' in argv:
        i = argv.index('--samples'); samples = section3(argv[i + 1]); del argv[i:i + 2]
    base = section3(argv[0])
    work = make_env(base, argv[1] if len(argv) > 1 else ROOT / 'build' / 'regen')
    if do_write:
        write(work, base, samples)
        return
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

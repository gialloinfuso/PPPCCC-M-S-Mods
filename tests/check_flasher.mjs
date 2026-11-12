// The flasher's core (flasher/lib.js) against tools/build.py: same output files, byte for byte.
// usage: node tests/check_flasher.mjs <model-cycles_OS1.13.syx> [<Cycles OS for Model:Samples .syx>] [<model-samples_OS1.13.syx>]
// Builds the full set and a few subsets with both and compares; with the official Samples file also the cross-flash.
import { readFileSync, mkdtempSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import * as L from "../flasher/lib.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const [cycFile, smpBase, smpOfficial] = process.argv.slice(2);
if (!cycFile) { console.log("usage: node tests/check_flasher.mjs <model-cycles_OS1.13.syx> [<Cycles OS for Samples .syx>] [<model-samples_OS1.13.syx>]"); process.exit(2); }
const manifest = JSON.parse(readFileSync(join(ROOT, "patches/manifest.json")));
const all = manifest.patches.map((f) => JSON.parse(readFileSync(join(ROOT, "patches", f))));
const tmp = mkdtempSync(join(tmpdir(), "flash-"));
let ok = true;
const chk = (name, c) => { ok &&= !!c; console.log((c ? "ok   " : "FAIL ") + name); };
const same = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);

function py(input, ids, smp) {
  const out = join(tmp, "py" + Math.random().toString(36).slice(2));
  execFileSync("python3", [join(ROOT, "tools/build.py"), "--in", input, "--out", out, ...(smp ? ["--smp"] : []), ...ids], { stdio: "pipe" });
  const r = { cyc: readFileSync(out + "_cyc-os.syx") };
  if (smp) r.smp = readFileSync(out + "_smp-os.syx");
  return r;
}
async function caseOf(label, input, ids, smp) {
  const t0 = Date.now();
  const res = await L.build(readFileSync(input), ids.length ? L.resolve(ids, all) : all, manifest);
  const ms = Date.now() - t0;
  const ref = py(input, ids, smp);
  chk(`${label}: _cyc-os.syx identical to build.py (${(ms / 1000).toFixed(1)} s)`, same(res.outs.cyc, ref.cyc));
  if (smp) chk(`${label}: _smp-os.syx identical to build.py`, same(res.outs.smp, ref.smp));
}
await caseOf("Cycles, all patches", cycFile, [], false);
await caseOf("Cycles, mute-solo + reverb-fx + track-filter", cycFile, ["mute-solo", "reverb-fx", "track-filter"], false);
await caseOf("Cycles, mono (+ sampler, strings, core)", cycFile, ["mono"], false);
await caseOf("Cycles, hold-mute only (no core)", cycFile, ["hold-mute"], false);
if (smpBase) {
  await caseOf("Samples base, all patches", smpBase, [], true);
  await caseOf("Samples base, pad-mode + groove", smpBase, ["pad-mode", "groove"], true);
}
if (smpBase) {
  // the cross-flash steps against an existing Cycles-for-Samples file: same key derivation, MAIN OS, section 3, container
  const out = await L.crossParts(await L.firmwareWithKey(readFileSync(cycFile)), await L.firmwareWithKey(readFileSync(smpBase)));
  chk("cross-flash steps reproduce the Cycles-for-Samples file byte for byte", same(out, readFileSync(smpBase)));
}
if (smpOfficial) {
  const base = await L.cyclesForSamples(readFileSync(cycFile), readFileSync(smpOfficial));
  const out = join(tmp, "cross.syx");
  execFileSync("python3", [join(ROOT, "tools/vendor/crossflash.py"), "--cycles", cycFile, "--samples", smpOfficial, "--to", "samples", "-o", out], { stdio: "pipe" });
  chk("cross-flash (--to samples) identical to crossflash.py", same(base, readFileSync(out)));
}
let bad = false;
try { await L.build(readFileSync(cycFile).subarray(0, 50000), all, manifest); } catch (e) { bad = true; }
chk("a damaged file is refused", bad);
console.log(ok ? "all ok" : "FAILED");
process.exit(ok ? 0 : 1);

// PPPCCC M:C Mods – flasher page. The building is in lib.js; this file is the page around it.
import * as L from "./lib.js";

const $ = (id) => document.getElementById(id);
const VERSION_NAME = "pppccc-mods-2.3.0";
const MACHINES = ["sampler", "strings", "mono"];
const st = { dev: null, mode: "first", files: {}, manifest: null, all: [], sel: new Set(), result: null, sending: false, stop: false };

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const num = (t) => String(t.order).padStart(2, "0");
function short(t) {                                       // first sentence of the description
  const s = t.description.join(" ");
  const m = s.match(/^.*?[.!](?=\s+[A-Z(]|$)/);
  return m ? m[0] : s;
}
const paint = () => new Promise((r) => setTimeout(r, 30));
function setStatus(id, text, kind = "") { const e = $(id); e.textContent = text; e.className = "status-line " + kind; }
function lock(id, locked) { if (locked) $(id).setAttribute("data-locked", ""); else $(id).removeAttribute("data-locked"); }

// ------------------------------------------------------------------ data
async function loadPatches() {
  const m = await (await fetch("../patches/manifest.json", { cache: "no-cache" })).json();
  st.manifest = m;
  st.all = await Promise.all(m.patches.map(async (f) => (await fetch("../patches/" + f, { cache: "no-cache" })).json()));
  $("version").textContent = m.version;
  for (const t of st.all) if (t.id !== "core") st.sel.add(t.id);
  renderList();
}
const byId = (id) => st.all.find((t) => t.id === id);
const requiresOf = (id) => (byId(id).requires || []);
function needsClosure(id, acc = new Set()) {
  for (const r of requiresOf(id)) if (!acc.has(r)) { acc.add(r); needsClosure(r, acc); }
  return acc;
}
function dependents(id) { return st.all.filter((t) => needsClosure(t.id).has(id)).map((t) => t.id); }

// ------------------------------------------------------------------ step 1
function chooseDevice(dev) {
  st.dev = dev;
  for (const b of document.querySelectorAll("#devices .choice")) b.classList.toggle("on", b.dataset.dev === dev);
  $("smp-mode").hidden = dev !== "samples";
  $("need-cycles").hidden = dev !== "cycles";
  $("need-samples").hidden = dev !== "samples";
  lock("s2", false);
  st.result = null; $("result").hidden = true; setStatus("build-status", "");
  renderFiles();
}

// ------------------------------------------------------------------ step 2
async function takeFiles(list) {
  for (const f of list) {
    const raw = new Uint8Array(await f.arrayBuffer());
    const sha = await L.sha256hex(raw);
    let kind = null, msg = "";
    if (sha === L.OFFICIAL.cycles.syx) kind = "cycles";
    else if (sha === L.OFFICIAL.samples.syx) kind = "samples";
    else {
      try {
        const fw = L.readFirmware(raw);
        const ms = await L.sha256hex(fw.main);
        const b = st.manifest.bases.find((x) => x.section3_sha256 === ms);
        if (b && b.target === "samples") kind = "cross";
        else if (b && b.target === "cycles") kind = "cycles";
        else msg = "an Elektron OS file, but not the official OS 1.13 (perhaps already modified?)";
      } catch (e) { msg = "not an Elektron OS file (" + e.message + ")"; }
    }
    if (kind) st.files[kind] = { raw, name: f.name };
    else st.files["bad:" + f.name] = { name: f.name, msg };
  }
  renderFiles();
}
const LABEL = { cycles: "official Model:Cycles OS 1.13", samples: "official Model:Samples OS 1.13",
                cross: "Cycles OS for Model:Samples (cross-flash)" };
function haveBase() {
  if (st.dev === "cycles") return !!st.files.cycles;
  if (st.dev === "samples") return !!(st.files.cross || (st.files.cycles && st.files.samples));
  return false;
}
function renderFiles() {
  const ul = $("files");
  ul.innerHTML = "";
  for (const [k, f] of Object.entries(st.files)) {
    const li = document.createElement("li");
    li.innerHTML = k.startsWith("bad:") ? `<span class="bad">✗</span> <span>${esc(f.name)} – ${esc(f.msg)}</span>`
                                        : `<span class="ok">✓</span> <span>${esc(f.name)} – ${LABEL[k]}</span>`;
    ul.appendChild(li);
  }
  if (st.dev === "samples" && !haveBase()) {
    const miss = !st.files.cycles ? "model-cycles_OS1.13.syx" : "model-samples_OS1.13.syx";
    const li = document.createElement("li");
    li.innerHTML = `<span class="note">still needed: <code>${miss}</code></span>`;
    ul.appendChild(li);
  }
  lock("s3", !haveBase()); lock("s4", !haveBase());
  updateBuild();
}

// ------------------------------------------------------------------ step 3
function row(t, opts = {}) {
  const d = document.createElement("label");
  d.className = "patch";
  const needs = requiresOf(t.id).filter((r) => r !== "core").map((r) => num(byId(r))).join(", ");
  d.innerHTML = `<input type="checkbox" ${opts.disabled ? "disabled" : ""}><span class="num">${num(t)}</span>` +
    `<span class="name">${esc(t.name)}</span><span class="needs">${(t.requires || []).includes("core") ? "core" : ""}` +
    `${needs ? " + " + needs : ""}</span><span class="desc">${esc(short(t))} ` +
    `<a href="../docs/patches/${num(t)}-${t.id}.md" target="_blank" rel="noopener">Details</a></span><span class="why"></span>`;
  d.querySelector("a").href = `https://github.com/gialloinfuso/PPPCCC-M-S-Mods/blob/main/docs/patches/${num(t)}-${t.id}.md`;
  const cb = d.querySelector("input");
  cb.dataset.id = t.id;
  if (!opts.disabled) cb.addEventListener("change", () => toggle(t.id, cb.checked));
  return d;
}
function renderList() {
  const list = $("list");
  list.innerHTML = "";
  const core = byId("core");
  $("core-row").replaceWith(Object.assign(row(core, { disabled: true }), { id: "core-row" }));
  $("core-row").classList.add("core");
  let group = null;
  for (const t of st.all) {
    if (t.id === "core") continue;
    if (MACHINES.includes(t.id)) {
      if (!group) {
        group = document.createElement("div"); group.className = "group";
        group.innerHTML = '<div class="gnote">Grit, Vlvt and Monom only work together: Vlvt needs Grit, Monom needs Grit and Vlvt. ' +
                          "Ticking one ticks what it needs.</div>";
        list.appendChild(group);
      }
      group.appendChild(row(t));
    } else list.appendChild(row(t));
  }
  refreshChecks();
}
function toggle(id, on) {
  if (on) { st.sel.add(id); for (const r of needsClosure(id)) if (r !== "core") st.sel.add(r); }
  else { st.sel.delete(id); for (const d of dependents(id)) st.sel.delete(d); }
  refreshChecks();
}
function chosen() { return L.resolve([...st.sel], st.all); }      // + core and every other requirement
function refreshChecks() {
  const ids = new Set(chosen().map((t) => t.id));
  for (const cb of document.querySelectorAll(".patch input")) {
    const id = cb.dataset.id, row_ = cb.closest(".patch"), why = row_.querySelector(".why");
    cb.checked = ids.has(id);
    const auto = ids.has(id) && !st.sel.has(id);
    row_.classList.toggle("auto", auto);
    if (id === "core") why.textContent = ids.has("core") ? "added automatically (needed by " +
      st.all.filter((t) => ids.has(t.id) && (t.requires || []).includes("core")).length + " of the chosen patches)" : "not needed by the chosen patches";
    else why.textContent = auto ? "added: needed by another chosen patch" : "";
  }
  const n = [...ids].filter((i) => i !== "core").length;
  $("count").textContent = `${n} of ${st.all.length - 1} patches` + (ids.has("core") ? " + core" : "");
  st.result = null; $("result").hidden = true;
  updateBuild();
}
function updateBuild() { $("build").disabled = !haveBase() || !st.sel.size; }

// ------------------------------------------------------------------ step 4
async function build() {
  $("build").disabled = true; $("result").hidden = true;
  try {
    let base;
    if (st.dev === "cycles") base = st.files.cycles.raw;
    else if (st.files.cross) base = st.files.cross.raw;
    else {
      setStatus("build-status", "Putting the Cycles OS into the Model:Samples container…"); await paint();
      base = await L.cyclesForSamples(st.files.cycles.raw, st.files.samples.raw);
    }
    const ps = chosen();
    const t0 = performance.now();
    const res = await L.build(base, ps, st.manifest, async (m) => { setStatus("build-status", m[0].toUpperCase() + m.slice(1) + "…"); });
    st.result = res;
    const files = [];
    if (st.dev === "cycles") files.push(["cyc", "_cyc-os.syx", "for your Model:Cycles"]);
    else if (st.mode === "first") files.push(["smp", "_smp-os.syx", "first flash (from the Samples OS)"], ["cyc", "_cyc-os.syx", "later updates"]);
    else files.push(["cyc", "_cyc-os.syx", "update (a Cycles OS already runs)"], ["smp", "_smp-os.syx", "first flash, from the Samples OS"]);
    st.primary = res.outs[files[0][0]];
    const dl = $("downloads"); dl.innerHTML = "";
    files.forEach(([k, suf, what], i) => {
      const b = document.createElement("button");
      b.className = "btn" + (i ? "" : " primary");
      b.textContent = "⬇ " + VERSION_NAME + suf;
      b.title = what;
      b.addEventListener("click", () => download(res.outs[k], VERSION_NAME + suf));
      dl.appendChild(b);
      const s = document.createElement("span"); s.className = "note"; s.textContent = what; dl.appendChild(s);
    });
    const fsha = await L.sha256hex(st.primary);
    $("result-text").innerHTML = `<b>Built and checked</b> in ${((performance.now() - t0) / 1000).toFixed(1)} s: ` +
      `${ps.length} patches (${ps.map(num).join(", ")}).<br>Every write was checked against your file; the output was unpacked ` +
      `again and its checksums, signature and MAIN OS verified.` +
      (res.fullSet ? "<br>The MAIN OS matches the <b>published SHA-256</b> of the full set." : "") +
      `<br>MAIN OS <code>${res.mainSha}</code><br>File <code>${fsha}</code>`;
    $("howto").innerHTML = howto();
    $("result").hidden = false;
    setStatus("build-status", "Done.", "ok");
  } catch (e) {
    setStatus("build-status", "Stopped: " + e.message, "bad");
  }
  $("build").disabled = false;
}
function howto() {
  const file = st.dev === "samples" && st.mode === "first" ? "_smp-os" : "_cyc-os";
  const start = st.dev === "samples" && st.mode === "first"
    ? "On the Model:Samples: open the start-up menu (hold <b>FUNC</b> while switching on) and choose <b>OS UPGRADE</b>, or simply stay in the running Samples OS."
    : "On the device: open the start-up menu (hold <b>FUNC</b> while switching on) and choose <b>OS UPGRADE</b>, or simply stay in the running OS.";
  return `<li>Connect the device to this computer over <b>USB</b>; close Elektron Transfer and other MIDI programs.</li>` +
         `<li>${start}</li><li>Tick the box, press <b>Find MIDI devices</b>, choose the device and press <b>Send</b> ` +
         `(the <code>${file}</code> file, about 5 minutes).</li><li>Wait until the device has written the OS and restarts. Do not switch it off.</li>`;
}
function download(bytes, name) {
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

// ------------------------------------------------------------------ Web MIDI
const DIN_BYTES_PER_SEC = 31250 / 10;
let midi = null;
async function connectMidi() {
  if (!navigator.requestMIDIAccess) { setStatus("send-status", "This browser has no Web MIDI. Use Chrome or Edge, or download the file.", "bad"); return; }
  try { midi = await navigator.requestMIDIAccess({ sysex: true }); }
  catch (e) { setStatus("send-status", "MIDI access was refused: " + e.message, "bad"); return; }
  const sel = $("midi-port"); sel.innerHTML = "";
  for (const out of midi.outputs.values()) {
    const o = document.createElement("option"); o.value = out.id; o.textContent = out.name;
    if (/model|elektron/i.test(out.name)) o.selected = true;
    sel.appendChild(o);
  }
  sel.hidden = !sel.options.length;
  setStatus("send-status", sel.options.length ? "" : "No MIDI outputs found. Is the device connected over USB?", sel.options.length ? "" : "bad");
  updateSend();
}
function updateSend() { $("send").disabled = !(midi && $("midi-port").options.length && $("backed-up").checked && st.primary && !st.sending); }
async function send() {
  const out = midi && midi.outputs.get($("midi-port").value);
  if (!out || !st.primary) return;
  if (!confirm("Send the new OS to " + out.name + " now? Do not switch the device off while it is updating.")) return;
  const pace = Math.max(1, parseFloat($("pace").value) || 1.4);
  const msgs = L.splitMessages(st.primary);
  st.sending = true; st.stop = false; updateSend();
  $("stop").hidden = false; $("progress").hidden = false; $("progress").max = msgs.length;
  const minutes = Math.ceil(st.primary.length / DIN_BYTES_PER_SEC * pace / 60);
  setStatus("send-status", `Sending ${msgs.length} messages, about ${minutes} min…`);
  let n = 0;
  for (; n < msgs.length && !st.stop; n++) {
    out.send(msgs[n]);
    await new Promise((r) => setTimeout(r, pace * msgs[n].length / DIN_BYTES_PER_SEC * 1000));
    if (n % 20 === 0) $("progress").value = n;
  }
  $("progress").value = n;
  st.sending = false; $("stop").hidden = true; updateSend();
  if (n < msgs.length) setStatus("send-status", `Stopped after ${n} of ${msgs.length} messages. Start again from the start-up menu.`, "bad");
  else setStatus("send-status", "Sent. Follow the device's screen until it restarts.", "ok");
}

// ------------------------------------------------------------------ wiring
for (const b of document.querySelectorAll("#devices .choice")) b.addEventListener("click", () => chooseDevice(b.dataset.dev));
for (const r of document.querySelectorAll('input[name="smpmode"]')) r.addEventListener("change", () => { st.mode = r.value; st.result = null; $("result").hidden = true; });
$("file").addEventListener("change", (e) => takeFiles(e.target.files));
const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); takeFiles(e.dataTransfer.files); });
$("all").addEventListener("click", () => { for (const t of st.all) if (t.id !== "core") st.sel.add(t.id); refreshChecks(); });
$("none").addEventListener("click", () => { st.sel.clear(); refreshChecks(); });
$("build").addEventListener("click", build);
$("midi-connect").addEventListener("click", connectMidi);
$("midi-port").addEventListener("change", updateSend);
$("backed-up").addEventListener("change", updateSend);
$("send").addEventListener("click", send);
$("stop").addEventListener("click", () => { st.stop = true; });
window.addEventListener("beforeunload", (e) => { if (st.sending) e.preventDefault(); });
loadPatches().catch((e) => setStatus("build-status", "Could not load the patch list: " + e.message, "bad"));

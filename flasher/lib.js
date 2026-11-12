// PPPCCC M:C Mods – flasher core. Runs in the browser and in Node (tests): no network, no server, nothing is uploaded.
//
// A JavaScript port that produces byte-for-byte the same files as tools/build.py:
//   - SysEx transport, ELE3 container, aPLib codec: drumkilla's mtlib (tools/vendor/mtlib, MIT; based on
//     elektron-firmware-tool by Marcel Bierling, MIT)
//   - compression of the longer MAIN OS: Modded-Cycles' aplib_grow.py (tools/vendor, MIT)
//   - the Cycles OS for a Model:Samples: Modded-Cycles' crossflash.py --to samples (tools/vendor, MIT)
//   - applying the patches: this repository's tools/apply_patches.py
// tests/check_flasher.mjs builds every case in Node and compares the files with tools/build.py.

const subtle = globalThis.crypto.subtle;
export const hex = (b) => Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
export async function sha256(b) { return new Uint8Array(await subtle.digest("SHA-256", b)); }
export async function sha256hex(b) { return hex(await sha256(b)); }
async function hmacSha256(key, msg) {
  const k = await subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await subtle.sign("HMAC", k, msg));
}
function same(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}
function indexOf(buf, pat, from = 0) {
  outer: for (let i = from; i <= buf.length - pat.length; i++) {
    for (let k = 0; k < pat.length; k++) if (buf[i + k] !== pat[k]) continue outer;
    return i;
  }
  return -1;
}
const be32 = (b, o) => ((b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]) >>> 0;
function put32(b, o, v) { b[o] = v >>> 24; b[o + 1] = (v >>> 16) & 255; b[o + 2] = (v >>> 8) & 255; b[o + 3] = v & 255; }

class Bytes {                                   // growable byte buffer
  constructor(n = 1 << 16) { this.a = new Uint8Array(n); this.n = 0; }
  grow(k) { if (this.n + k > this.a.length) { const b = new Uint8Array(Math.max(this.a.length * 2, this.n + k)); b.set(this.a.subarray(0, this.n)); this.a = b; } }
  push(v) { this.grow(1); this.a[this.n++] = v; }
  add(arr) { this.grow(arr.length); this.a.set(arr, this.n); this.n += arr.length; }
  get bytes() { return this.a.subarray(0, this.n); }
}

// ------------------------------------------------------------------ SysEx transport (mtlib/syx.py)
const MSG_LEN = 128, PAYLOAD_OFF = 10, PAYLOAD_END = 126, CS_OFF = 126;
export const BYTES_PER_MSG = 101, CYCLES = 0x11, SAMPLES = 0x0f;
const PRODUCTS = { 0x11: ["Model:Cycles", 0x0c, 0x3a, 0x22], 0x0f: ["Model:Samples", 0x0a, 0x3c, 0x1e] };

function checksum(m, V, C0) {
  let s = 0;
  for (let i = 8; i < 126; i++) s += m[i] ^ ((V - i) & 0x3f);
  return (C0 - s) & 0x7f;
}
export function splitMessages(raw) {
  const msgs = [];
  let i = 0;
  for (;;) {
    const a = raw.indexOf(0xf0, i);
    if (a < 0) break;
    const b = raw.indexOf(0xf7, a);
    if (b < 0) break;
    msgs.push(raw.subarray(a, b + 1));
    i = b + 1;
  }
  return msgs;
}
const u21 = (b, o) => (b[o] << 14) | (b[o + 1] << 7) | b[o + 2];
const p21 = (v) => [(v >> 14) & 0x7f, (v >> 7) & 0x7f, v & 0x7f];

export function unwrap(raw) {
  const msgs = splitMessages(raw);
  if (msgs.length < 3) throw new Error("not an Elektron SysEx file: too few messages");
  const head = msgs[0], tail = msgs[msgs.length - 1], data = msgs.slice(1, -1);
  const isE = (m) => m[1] === 0x00 && m[2] === 0x20 && m[3] === 0x3c;
  if (!isE(head) || !isE(tail)) throw new Error("not an Elektron SysEx file");
  const prod = head[4];
  if (!PRODUCTS[prod]) throw new Error("unknown product id 0x" + prod.toString(16));
  const [name, , V, C0] = PRODUCTS[prod];
  if (head[6] !== 0x7f || head[7] !== 0x01 || tail[6] !== 0x7f || tail[7] !== 0x02) throw new Error("start/end markers missing");
  const start = u21(head, 9), count = u21(head, 12);
  if (count !== data.length) throw new Error(`marker declares ${count} messages, found ${data.length}`);
  const body = new Uint8Array(count * BYTES_PER_MSG);
  let o = 0;
  data.forEach((m, n) => {
    if (m.length !== MSG_LEN) throw new Error(`message ${n}: length ${m.length}`);
    if (m[CS_OFF] !== checksum(m, V, C0)) throw new Error(`message ${n}: checksum mismatch`);
    for (let i = PAYLOAD_OFF; i < PAYLOAD_END; i += 8) {
      const hi = m[i];
      for (let k = 0; k < 7 && i + 1 + k < PAYLOAD_END; k++) body[o++] = ((hi << (k + 1)) & 0x80) | m[i + 1 + k];
    }
  });
  return [body.subarray(0, o), { product: prod, name, start_seq: start, count }];
}

export function wrap(body, product, startSeq) {
  const [, dev, V, C0] = PRODUCTS[product];
  if (body.length % BYTES_PER_MSG) throw new Error("body length must be a multiple of 101");
  const count = body.length / BYTES_PER_MSG;
  const pre = [0xf0, 0x00, 0x20, 0x3c, product, 0x00];
  const out = new Bytes(count * 130 + 64);
  out.add([...pre, 0x7f, 0x01, dev, ...p21(startSeq), ...p21(count), 0xf7]);
  const m = new Uint8Array(MSG_LEN);
  for (let n = 0; n < count; n++) {
    const seq = startSeq + n;
    m.set(pre, 0); m[6] = 0x7e; m[7] = 0x00; m[8] = seq >> 7; m[9] = seq & 0x7f;
    let o = 10;
    const chunk = body.subarray(n * BYTES_PER_MSG, (n + 1) * BYTES_PER_MSG);
    for (let i = 0; i < chunk.length; i += 7) {
      let hi = 0;
      const c = chunk.subarray(i, i + 7);
      c.forEach((v, k) => { hi |= (v >> 7) << (6 - k); });
      m[o++] = hi;
      for (const v of c) m[o++] = v & 0x7f;
    }
    m[126] = 0; m[127] = 0xf7;
    m[CS_OFF] = checksum(m, V, C0);
    out.add(m);
  }
  out.add([...pre, 0x7f, 0x02, dev, ...p21(startSeq), ...p21(count), 0xf7]);
  return out.bytes.slice();
}

// ------------------------------------------------------------------ ELE3 container (mtlib/container.py)
const PREAMBLE = 8, TABLE_OFF = 0x20, ENTRY_SZ = 16, ALIGN = 16, DIGEST_LEN = 32, KEY_STR_MAX = 64;
const KEY_ANCHOR = [0xbe, 0xf9, 0xa3, 0xf7, 0xc6, 0x71, 0x78, 0xf2];   // tail of the SHA-256 round constants

export function contentChecksum(c) {
  let acc = 0;
  for (let k = 0; k < (c.length >> 2); k++) acc = (acc + (((k + 1) ^ be32(c, 4 * k)) >>> 0)) >>> 0;
  return acc;
}
export function parse(stream) {
  if (stream.length < PREAMBLE + TABLE_OFF) throw new Error("stream too short");
  const declared = be32(stream, 0);
  const blob = stream.subarray(PREAMBLE, PREAMBLE + declared);
  if (!(blob[0] === 0x45 && blob[1] === 0x4c && blob[2] === 0x45 && blob[3] === 0x33)) throw new Error("no ELE3 magic - not this firmware format");
  const n = be32(blob, 0x1c);
  if (n < 1 || n > 16) throw new Error("implausible section count: " + n);
  const sections = [];
  for (let s = 0; s < n; s++) {
    const e = TABLE_OFF + s * ENTRY_SZ;
    sections.push({ index: s, id: be32(blob, e), off: be32(blob, e + 4), size: be32(blob, e + 8), attr: be32(blob, e + 12) });
  }
  return { declared, blob, sections };
}
const sec = (c, id) => c.sections.find((s) => s.id === id);
const body = (c, s) => c.blob.subarray(s.off, s.off + s.size);

export async function findKey(buffers, message, expect) {
  for (const buf of buffers) {
    let i = indexOf(buf, KEY_ANCHOR);
    while (i >= 0) {
      const s = i + KEY_ANCHOR.length;
      let p = s;
      while (p < buf.length && buf[p] >= 0x20 && buf[p] < 0x7f && p - s < KEY_STR_MAX) p++;
      if (p > s && p < buf.length && buf[p] === 0 && p + 1 + 32 <= buf.length) {
        const text = buf.slice(s, p);
        const h = await sha256(text), hr = await sha256(text.slice().reverse());
        const key = new Uint8Array(32).map((_, k) => h[k] ^ hr[k] ^ buf[p + 1 + k]);
        if (same(await hmacSha256(key, message), expect)) return key;
      }
      i = indexOf(buf, KEY_ANCHOR, i + 1);
    }
  }
  return null;
}
export async function rebuild(c, replacements, key) {
  const { blob, sections } = c;
  const first = Math.min(...sections.map((s) => s.off));
  const out = new Bytes(blob.length + (1 << 20));
  out.add(blob.subarray(0, first));
  const order = sections.map((_, i) => i).sort((a, b) => sections[a].off - sections[b].off);
  let pos = first;
  for (const i of order) {
    const s = sections[i];
    const data = replacements[s.id] || body(c, s);
    pos = (pos + ALIGN - 1) & ~(ALIGN - 1);
    while (out.n < pos) out.push(0);
    out.n = pos; out.add(data);
    const e = TABLE_OFF + s.index * ENTRY_SZ;
    put32(out.a, e + 4, pos); put32(out.a, e + 8, data.length);
    pos += data.length;
  }
  const hoff = (pos + 4 + ALIGN - 1) & ~(ALIGN - 1);
  while (out.n < hoff) out.push(0);
  out.n = hoff;
  out.add(await hmacSha256(key, out.bytes.slice(0, hoff)));
  return out.bytes.slice(0, hoff + DIGEST_LEN);
}
export function buildStream(blob, padTo) {
  let n = PREAMBLE + blob.length;
  if (n % padTo) n += padTo - (n % padTo);
  const s = new Uint8Array(n);
  put32(s, 0, blob.length); put32(s, 4, contentChecksum(blob)); s.set(blob, PREAMBLE);
  return s;
}

// ------------------------------------------------------------------ aPLib variant (mtlib/aplib.py, aplib_grow.py)
const SECT_HDR = 8, OFFSET_BIAS = 767, REUSE_GAMMA = 2, FAR_THRESHOLD = 3328, END_GAMMA = 0x1000002;
const LITERAL = 1, MATCH = 0;

export function depack(stream) {
  if (stream.length < SECT_HDR) throw new Error("section shorter than its header");
  let ip = SECT_HDR, tag = 0;
  const byte = () => { if (ip >= stream.length) throw new Error("corrupt stream: past the end"); return stream[ip++]; };
  const bit = () => {
    tag <<= 1;
    if ((tag & 0xff) === 0) { const by = byte(); tag = (by << 1) | 1; return (by >> 7) & 1; }
    return (tag >> 8) & 1;
  };
  const gamma = () => {
    let v = 1;
    for (;;) {
      v = v * 2 + bit();
      if (bit()) return v;
      if (v > 0x02000000) throw new Error("corrupt stream: gamma overflowed");
    }
  };
  const out = new Bytes(1 << 21);
  let ops = new Int32Array(1 << 20), nops = 0;
  const op = (k, p, o, n) => {
    if (nops + 4 > ops.length) { const b = new Int32Array(ops.length * 2); b.set(ops); ops = b; }
    ops[nops++] = k; ops[nops++] = p; ops[nops++] = o; ops[nops++] = n;
  };
  let lastOff = 1;
  for (;;) {
    if (bit()) { op(LITERAL, out.n, 0, 1); out.push(byte()); continue; }
    const g = gamma();
    let off;
    if (g === REUSE_GAMMA) off = lastOff;
    else {
      off = (g * 256 + byte()) % 4294967296;
      if (off === OFFSET_BIAS) break;
      off -= OFFSET_BIAS;
      lastOff = off;
    }
    const sl = 2 * bit() + bit();
    let L = sl ? sl : gamma() + 2;
    if (off > FAR_THRESHOLD) L += 1;
    const n = L + 1;
    if (off === 0 || off > out.n) throw new Error("corrupt stream: offset past the output");
    op(MATCH, out.n, off, n);
    out.grow(n);
    const src = out.n - off, a = out.a;
    for (let k = 0; k < n; k++) a[out.n + k] = a[src + k];
    out.n += n;
  }
  return [out.bytes.slice(), ops.subarray(0, nops)];
}

class Writer {
  constructor() { this.o = new Bytes(1 << 21); this.o.add(new Uint8Array(SECT_HDR)); this.tagpos = -1; this.tagbits = 0; }
  bit(v) {
    if (this.tagbits === 0) { this.tagpos = this.o.n; this.o.push(0); this.tagbits = 8; }
    if (v) this.o.a[this.tagpos] |= 1 << (this.tagbits - 1);
    this.tagbits--;
  }
  gamma(v) {
    for (let i = 32 - Math.clz32(v) - 2; i >= 0; i--) { this.bit((v >>> i) & 1); this.bit(i === 0 ? 1 : 0); }
  }
  literal(b) { this.bit(1); this.o.push(b); }
  match(off, n, lastOff) {
    this.bit(0);
    if (off === lastOff) this.gamma(REUSE_GAMMA);
    else { const raw = off + OFFSET_BIAS; this.gamma(raw >>> 8); this.o.push(raw & 0xff); }
    const base = n - 1 - (off > FAR_THRESHOLD ? 1 : 0);
    if (base <= 3) { this.bit(base >> 1); this.bit(base & 1); }
    else { this.bit(0); this.bit(0); this.gamma(base - 2); }
  }
  end() { this.bit(0); this.gamma(END_GAMMA); this.o.push(0xff); }
}

const MIN_MATCH = 4, MAX_MATCH = 0xffff, WINDOW = 1 << 20;
function tail(w, data, start, lastOff) {           // aplib_grow._tail: greedy compression of the appended part
  const n = data.length, table = new Map();
  const key = (i) => ((data[i] << 24) | (data[i + 1] << 16) | (data[i + 2] << 8) | data[i + 3]) >>> 0;
  let i = start;
  while (i < n) {
    let bestLen = 0, bestOff = 0;
    if (i + MIN_MATCH <= n) {
      const k = key(i), cand = table.get(k);
      if (cand !== undefined && i - cand <= WINDOW) {
        let length = MIN_MATCH;
        const limit = Math.min(n - i, MAX_MATCH);
        while (length < limit && data[cand + length] === data[i + length]) length++;
        bestLen = length; bestOff = i - cand;
      }
      table.set(k, i);
    }
    if (bestLen >= MIN_MATCH) {
      w.match(bestOff, bestLen, lastOff);
      lastOff = bestOff;
      const stop = Math.min(i + bestLen, n - MIN_MATCH + 1);
      for (let k = i + 1; k < stop; k++) table.set(key(k), k);
      i += bestLen;
    } else { w.literal(data[i]); i++; }
  }
}

// repack (origLen = data.length) and repack_grow (data longer than the original): re-emit the original ops, ops that
// touch a changed byte become literals, the appended part is compressed by tail().
export function repack(data, ops, dirty, origLen = data.length) {
  const pre = new Int32Array(dirty.length + 1);
  for (let i = 0; i < dirty.length; i++) pre[i + 1] = pre[i] + dirty[i];
  const anyOrig = pre[origLen] > 0;
  const has = (a, b) => pre[Math.min(b, dirty.length)] - pre[Math.max(a, 0)] > 0;
  const w = new Writer();
  let lastOff = 1;
  for (let j = 0; j < ops.length; j += 4) {
    const kind = ops[j], pos = ops[j + 1], off = ops[j + 2], n = ops[j + 3];
    if (kind === LITERAL) { w.literal(data[pos]); continue; }
    const end = pos + n, src = pos - off;
    if (anyOrig && (has(pos, end) || has(src, src + n))) for (let k = pos; k < end; k++) w.literal(data[k]);
    else { w.match(off, n, lastOff); lastOff = off; }
  }
  if (data.length > origLen) tail(w, data, origLen, lastOff);
  w.end();
  const b = w.o.bytes.slice();
  put32(b, 0, b.length - SECT_HDR);
  let s = 0;
  for (let i = SECT_HDR; i < b.length; i++) s = (s + b[i]) >>> 0;
  put32(b, 4, s);
  return b;
}

// ------------------------------------------------------------------ firmware files (tweak.py read_firmware / verify)
export const OFFICIAL = {
  cycles: { product: 0x11, name: "Model:Cycles", syx: "44fe586269631a0ca7da25a3383fc6733c314809505fc3cc52f1e0ed9800640c",
            main: "cc99d4f0175d34d1e91d046e6ec85a5e8ab58ab9edbb3c24406acd48cb99ee98" },
  samples: { product: 0x0f, name: "Model:Samples", syx: "e11859b68deb7e5e3fe86ab32581212093849c4be5d3950add011eac398a2ce8",
             main: "a351392c62ec1c6c3324a807baf46934690d54edfc76029a4b4882541cad1ab2" },
};

function plainSections(c) {
  return c.sections.map((s) => { const b = body(c, s); try { return depack(b)[0]; } catch (e) { return b; } });
}
export function readFirmware(raw) {
  const [stream, info] = unwrap(raw);
  const c = parse(stream);
  const s3 = sec(c, 3);
  if (!s3) throw new Error("the container has no section 3 (MAIN OS)");
  const [main, ops] = depack(body(c, s3));
  return { raw, stream, info, cont: c, main, ops, plain: plainSections(c) };
}
async function containerKey(c, plain) {
  const n = c.blob.length;
  return findKey(plain, c.blob.subarray(0, n - DIGEST_LEN), c.blob.subarray(n - DIGEST_LEN));
}
export async function verify(raw) {
  const [stream] = unwrap(raw);                      // every packet checksum
  const c = parse(stream);
  if (contentChecksum(c.blob) !== be32(stream, 4) || be32(stream, 0) !== c.blob.length) return false;
  for (const s of c.sections) {
    const b = body(c, s);
    if (b.length >= 8) {
      const slen = be32(b, 0), ssum = be32(b, 4);
      if (slen > 0 && slen <= b.length - 8) {
        let acc = 0;
        for (let i = 8; i < 8 + slen; i++) acc = (acc + b[i]) >>> 0;
        if (acc !== ssum) return false;
      }
    }
  }
  return (await containerKey(c, plainSections(c))) !== null;
}

// ------------------------------------------------------------------ Cycles OS for a Model:Samples (crossflash.py --to samples)
const MAIN_BASE = 0x40000400, CYC_KEY_STR_VA = 0x40129650, CYC_KEY_CONST_VA = 0x401296b2;
const CYC_KEY_CODE = [[0x4005275c, "487940129650"], [0x400527c0, "43f9401296b2"]];   // pea "REVERB SEND" ; lea C (addresses only)

async function loadOfficial(raw, which) {
  const ref = OFFICIAL[which];
  if ((await sha256hex(raw)) !== ref.syx) throw new Error(`this is not the official ${ref.name} OS 1.13 file`);
  const fw = readFirmware(raw);
  if (fw.info.product !== ref.product) throw new Error(`${ref.name}: unexpected product id`);
  if ((await sha256hex(fw.main)) !== ref.main) throw new Error(`${ref.name}: unexpected MAIN OS`);
  fw.key = await containerKey(fw.cont, fw.plain);
  if (!fw.key) throw new Error(`${ref.name}: container key not found`);
  return fw;
}
export async function checkOfficial(raw, which) { await loadOfficial(raw, which); return true; }

export async function cyclesForSamples(cycRaw, smpRaw) {
  return crossParts(await loadOfficial(cycRaw, "cycles"), await loadOfficial(smpRaw, "samples"));
}
// cyc: the official Cycles file (readFirmware + key); smp: a file in the Model:Samples container (its sections 2, 4, 5
// and its key are used). Also used by the test with an existing Cycles-for-Samples file as smp.
export async function firmwareWithKey(raw) {
  const fw = readFirmware(raw);
  fw.key = await containerKey(fw.cont, fw.plain);
  if (!fw.key) throw new Error("container key not found");
  return fw;
}
export async function crossParts(cyc, smp) {
  const main = cyc.main;
  for (const [va, want] of CYC_KEY_CODE) if (hex(main.subarray(va - MAIN_BASE, va - MAIN_BASE + 6)) !== want) throw new Error("unexpected key check code");
  const so = CYC_KEY_STR_VA - MAIN_BASE;
  const text = main.slice(so, so + 12);
  if (new TextDecoder().decode(text) !== "REVERB SEND\0") throw new Error("unexpected key derivation string");
  const t = text.slice(0, 11);
  const h = await sha256(t), hr = await sha256(t.slice().reverse());
  const co = CYC_KEY_CONST_VA - MAIN_BASE;
  const old = main.subarray(co, co + 32);
  for (let k = 0; k < 32; k++) if ((h[k] ^ hr[k] ^ old[k]) !== cyc.key[k]) throw new Error("Cycles key differs from the bootstrap key");
  const patched = main.slice();
  for (let k = 0; k < 32; k++) patched[co + k] = h[k] ^ hr[k] ^ smp.key[k];
  const dirty = new Uint8Array(main.length);
  dirty.fill(1, co, co + 32);
  const s3 = repack(patched, cyc.ops, dirty);
  if (!same(depack(s3)[0], patched)) throw new Error("recompression of the MAIN OS failed");
  const blob = await rebuild(smp.cont, { 3: s3 }, smp.key);
  return wrap(buildStream(blob, BYTES_PER_MSG), smp.info.product, smp.info.start_seq);
}

// ------------------------------------------------------------------ patches (tools/apply_patches.py)
const KEY_OFF = 0x401296b2 - MAIN_BASE;
const unhex = (s) => { const b = new Uint8Array(s.length >> 1); for (let i = 0; i < b.length; i++) b[i] = parseInt(s.substr(2 * i, 2), 16); return b; };

export function resolve(ids, all) {
  const byId = Object.fromEntries(all.map((t) => [t.id, t]));
  const have = new Set(ids), todo = [...ids];
  while (todo.length) for (const r of byId[todo.pop()].requires || []) if (!have.has(r) && byId[r]) { have.add(r); todo.push(r); }
  return all.filter((t) => have.has(t.id)).sort((a, b) => a.order - b.order);
}

export async function applyPatches(img, patches) {
  const src = img;
  let out = new Bytes(img.length + (1 << 17));
  out.add(img);
  const have = new Set(), used = [];
  for (const t of [...patches].sort((a, b) => a.order - b.order)) {
    const missing = (t.requires || []).filter((r) => !have.has(r));
    if (missing.length) throw new Error(`${t.id}: requires ${missing.join(", ")}`);
    const bad = (t.conflicts || []).filter((c) => have.has(c));
    if (bad.length) throw new Error(`${t.id}: conflicts with ${bad.join(", ")}`);
    for (const w of t.writes) {
      const off = w.off, nw = unhex(w.new);
      for (const f of w.from_original || []) {
        const b = src.subarray(f.off, f.off + f.len);
        if ((await sha256hex(b)) !== f.sha256) throw new Error(`${t.id}: unexpected original bytes - wrong base OS`);
        nw.set(b, f.at);
      }
      let n, ok;
      if (w.len === 0) { ok = off === out.n && w.old_sha256 === "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"; n = nw.length; }
      else { n = w.len; ok = (await sha256hex(out.a.subarray(off, off + n))) === w.old_sha256 && nw.length === n; }
      if (!ok) throw new Error(`${t.id}: unexpected bytes at 0x${(off + MAIN_BASE).toString(16)} - wrong base OS or already patched`);
      const end = off + n;
      if (off < KEY_OFF + 32 && end > KEY_OFF) throw new Error(`${t.id}: would touch the update key`);
      for (const [a, b, who] of used) if (!(end <= a || off >= b || who === t.id || (t.requires || []).includes(who))) throw new Error(`${t.id}: collides with ${who}`);
      if (off + nw.length > out.n) { out.grow(off + nw.length - out.n); out.n = off + nw.length; }
      out.a.set(nw, off);
      used.push([off, end, t.id]);
    }
    have.add(t.id);
  }
  return out.bytes.slice();
}

// ------------------------------------------------------------------ the whole build (tools/build.py)
// base: the official Model:Cycles file, or the Cycles OS for a Model:Samples (cyclesForSamples). Returns the output files.
export async function build(baseRaw, patches, manifest, progress = () => {}) {
  progress("reading the firmware");
  const fw = readFirmware(baseRaw);
  const baseSha = await sha256hex(fw.main);
  const b = manifest.bases.find((x) => x.section3_sha256 === baseSha);
  if (!b) throw new Error("this MAIN OS is neither the official Model:Cycles OS 1.13 nor its Model:Samples cross-flash");
  progress("applying " + patches.length + " patches");
  const img = await applyPatches(fw.main, patches);
  const res = await sha256hex(img);
  const full = [...patches.map((t) => t.id)].sort().join() === [...manifest.full_set].sort().join();
  if (full && res !== b.full_set_result_sha256) throw new Error("the result differs from the published SHA-256");
  progress("compressing");
  const n0 = fw.main.length, dirty = new Uint8Array(img.length);
  for (let i = 0; i < n0; i++) if (fw.main[i] !== img[i]) dirty[i] = 1;
  dirty.fill(1, n0);
  const s3 = repack(img, fw.ops, dirty, n0);
  progress("signing");
  const key = await containerKey(fw.cont, fw.plain);
  if (!key) throw new Error("could not recover the container key from this firmware");
  const blob = await rebuild(fw.cont, { 3: s3 }, key);
  const smp = wrap(buildStream(blob, BYTES_PER_MSG), fw.info.product, fw.info.start_seq);
  const outs = {};
  if (b.target === "cycles") outs.cyc = smp;
  else { outs.smp = smp; outs.cyc = wrap(unwrap(smp)[0], CYCLES, fw.info.start_seq); }
  progress("checking the result");
  for (const raw of Object.values(outs)) {
    if (!(await verify(raw))) throw new Error("the output file failed its check");
    if (!same(readFirmware(raw).main, img)) throw new Error("the output MAIN OS differs from the patched image");
  }
  return { outs, target: b.target, mainSha: res, fullSet: full };
}

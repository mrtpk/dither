// 07-audio-reactive/main.js
// Audio-reactive two-tone Bayer dither. A still image (../data/samples/03a.png)
// is dithered in real time by a WebGL fragment shader, and the dither uniforms
// are driven live by WebAudio analysis of one of three sources:
//   - microphone (getUserMedia audio)
//   - a user-chosen audio file (<audio> -> MediaElementSource)
//   - ?src=tone : internal oscillators + LFO (deterministic, headless-friendly)
//
// The Bayer dither runs in GLSL (GPU) because ordered dithering is stateless
// per pixel and maps perfectly onto a parallel fragment shader. The Bayer math
// is re-implemented here (mirroring shared/dither.js) rather than importing the
// CPU/Canvas engine. Only the *uniforms* are new: they come from smoothed audio
// features (loudness -> coarseness, bass -> contrast/threshold, treble -> hue).

// ---- DOM ---------------------------------------------------------------------
const glcanvas = document.getElementById('glcanvas');
const meterCanvas = document.getElementById('meter');
const sampleImg = document.getElementById('sampleImg');
const audioEl = document.getElementById('audioEl');
const statusEl = document.getElementById('status');
const levelOutEl = document.getElementById('levelOut');
const fpsEl = document.getElementById('fps');
const srcOutEl = document.getElementById('srcOut');
const startBtn = document.getElementById('startBtn');
const micBtn = document.getElementById('micBtn');
const fileInput = document.getElementById('fileInput');
const sensitivityEl = document.getElementById('sensitivity');
const sensitivityOut = document.getElementById('sensitivityOut');

const SAMPLE_SRC = '../data/samples/03a.png';
const MAX_SIDE = 960; // cap the larger canvas dimension for perf

// ---- Utility -----------------------------------------------------------------

// hex -> normalized [r,g,b] in 0..1 (mirrors shared/palettes.js hexToRgb, then /255)
function hexToRgb01(hex) {
  const h = hex.replace('#', '');
  const s = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const n = parseInt(s, 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

function setStatus(text, isError) {
  statusEl.textContent = text;
  statusEl.classList.toggle('error', !!isError);
}

function clamp(x, lo, hi) { return Math.min(hi, Math.max(lo, x)); }
function mix(a, b, t) { return a + (b - a) * t; }

// HSL (h in degrees, s/l in 0..1) -> [r,g,b] in 0..1.
function hslToRgb01(h, s, l) {
  h = ((h % 360) + 360) % 360;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  let r = 0, g = 0, b = 0;
  if (h < 60) { r = c; g = x; b = 0; }
  else if (h < 120) { r = x; g = c; b = 0; }
  else if (h < 180) { r = 0; g = c; b = x; }
  else if (h < 240) { r = 0; g = x; b = c; }
  else if (h < 300) { r = x; g = 0; b = c; }
  else { r = c; g = 0; b = x; }
  return [r + m, g + m, b + m];
}

// ---- Bayer matrix (mirror of shared/dither.js) -------------------------------
// Recursive 2^k x 2^k Bayer index matrix.
function bayerMatrix(n) {
  if (n === 2) return [[0, 2], [3, 1]];
  const prev = bayerMatrix(n / 2);
  const half = n / 2;
  const m = Array.from({ length: n }, () => new Array(n).fill(0));
  for (let y = 0; y < half; y++) {
    for (let x = 0; x < half; x++) {
      const base = 4 * prev[y][x];
      m[y][x] = base + 0;
      m[y][x + half] = base + 2;
      m[y + half][x] = base + 3;
      m[y + half][x + half] = base + 1;
    }
  }
  return m;
}

// Normalized thresholds in [0,1): (index + 0.5) / (n*n).
function normalizedBayer(n) {
  const m = bayerMatrix(n);
  const denom = n * n;
  return m.map((row) => row.map((v) => (v + 0.5) / denom));
}

// Build an n*n*4 RGBA8 buffer holding round(threshold*255) in the R channel.
function bayerLutBytes(n) {
  const norm = normalizedBayer(n);
  const bytes = new Uint8Array(n * n * 4);
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const i = (y * n + x) * 4;
      bytes[i] = Math.round(norm[y][x] * 255); // R = threshold
      bytes[i + 1] = 0;
      bytes[i + 2] = 0;
      bytes[i + 3] = 255;
    }
  }
  return bytes;
}

// ---- GLSL --------------------------------------------------------------------
const VERT_SRC = `
attribute vec2 aPos;   // clip-space -1..1 fullscreen quad
void main() {
  gl_Position = vec4(aPos, 0.0, 1.0);
}
`;

const FRAG_SRC = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif

uniform sampler2D uVideo;
uniform sampler2D uBayer;
uniform float uBayerSize;
uniform float uContrast;
uniform float uPixelScale;
uniform float uThresholdShift;   // NEW vs 03: audio (bass) shifts the threshold
uniform vec2  uResolution;
uniform vec3  uInk;
uniform vec3  uGround;

void main() {
  // Block / pixel-scale coordinate (chunky pixels align to the dither grid).
  vec2 px = floor(gl_FragCoord.xy / uPixelScale);
  vec2 uv = (px * uPixelScale + 0.5 * uPixelScale) / uResolution;

  // Sample + luminance (matches shared/dither.js luminance weights).
  vec3 c = texture2D(uVideo, uv).rgb;
  float l = dot(c, vec3(0.299, 0.587, 0.114));

  // Contrast: midpoint stretch around 0.5 (mirror of applyContrast in 0..1 space).
  l = clamp((l - 0.5) * uContrast + 0.5, 0.0, 1.0);

  // Bayer threshold for this cell, tiled per output block, plus audio shift.
  vec2 cell = mod(px, uBayerSize);
  float t = clamp(texture2D(uBayer, (cell + 0.5) / uBayerSize).r + uThresholdShift, 0.0, 1.0);

  // Two-tone ordered-dither decision: brighter than threshold -> ground.
  float on = step(t, l);
  vec3 outc = mix(uInk, uGround, on);
  gl_FragColor = vec4(outc, 1.0);
}
`;

// ---- State -------------------------------------------------------------------
const BASE_GROUND_HUE = 68;  // acid-green-ish ground (Loudest Night)
const INK = hexToRgb01('#0a0a0a');

const state = {
  sensitivity: parseFloat(sensitivityEl.value) || 1.0,
  // smoothed audio features
  rms: 0,
  bass: 0,
  mid: 0,
  treble: 0,
  // mapped dither params
  bayerSize: 4,
  pixelScale: 1,
  contrast: 1.4,
  thresholdShift: 0,
  ground: hslToRgb01(BASE_GROUND_HUE, 1.0, 0.5),
};

// ---- WebGL setup -------------------------------------------------------------
let gl = null;
let program = null;
const loc = {};
let videoTex = null;
let bayerTex = null;
let uploadedBayerSize = 0;
let imageUploaded = false;
let sized = false;
let imageReady = false;

function getGL() {
  const opts = { preserveDrawingBuffer: true, antialias: false, alpha: false };
  return glcanvas.getContext('webgl', opts) ||
         glcanvas.getContext('experimental-webgl', opts);
}

function compileShader(type, src) {
  const sh = gl.createShader(type);
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(sh);
    gl.deleteShader(sh);
    throw new Error('shader compile failed: ' + log);
  }
  return sh;
}

function buildProgram() {
  const vs = compileShader(gl.VERTEX_SHADER, VERT_SRC);
  const fs = compileShader(gl.FRAGMENT_SHADER, FRAG_SRC);
  const prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(prog);
    gl.deleteProgram(prog);
    throw new Error('program link failed: ' + log);
  }
  return prog;
}

function setupQuad() {
  const verts = new Float32Array([
    -1, -1,
     1, -1,
    -1,  1,
     1,  1,
  ]);
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, verts, gl.STATIC_DRAW);
  const aPos = gl.getAttribLocation(program, 'aPos');
  gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);
}

function createVideoTexture() {
  const tex = gl.createTexture();
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE,
    new Uint8Array([0, 0, 0, 255]));
  return tex;
}

function uploadBayerLut(n) {
  gl.activeTexture(gl.TEXTURE1);
  gl.bindTexture(gl.TEXTURE_2D, bayerTex);
  // LUT must NOT be flipped so thresholds match the CPU engine.
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, n, n, 0, gl.RGBA, gl.UNSIGNED_BYTE,
    bayerLutBytes(n));
  uploadedBayerSize = n;
}

function createBayerTexture(n) {
  const tex = gl.createTexture();
  gl.activeTexture(gl.TEXTURE1);
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  bayerTex = tex;
  uploadBayerLut(n);
  return tex;
}

function initGL() {
  gl = getGL();
  if (!gl) throw new Error('WebGL context creation failed');

  program = buildProgram();
  gl.useProgram(program);
  setupQuad();

  loc.uVideo = gl.getUniformLocation(program, 'uVideo');
  loc.uBayer = gl.getUniformLocation(program, 'uBayer');
  loc.uBayerSize = gl.getUniformLocation(program, 'uBayerSize');
  loc.uContrast = gl.getUniformLocation(program, 'uContrast');
  loc.uPixelScale = gl.getUniformLocation(program, 'uPixelScale');
  loc.uThresholdShift = gl.getUniformLocation(program, 'uThresholdShift');
  loc.uResolution = gl.getUniformLocation(program, 'uResolution');
  loc.uInk = gl.getUniformLocation(program, 'uInk');
  loc.uGround = gl.getUniformLocation(program, 'uGround');

  // Sampler bindings: uVideo -> unit 0, uBayer -> unit 1 (set once).
  gl.uniform1i(loc.uVideo, 0);
  gl.uniform1i(loc.uBayer, 1);

  videoTex = createVideoTexture();
  createBayerTexture(state.bayerSize);
}

// ---- Image load --------------------------------------------------------------
function loadSampleImage() {
  return new Promise((resolve) => {
    if (sampleImg.complete && sampleImg.naturalWidth > 0) {
      imageReady = true;
      return resolve();
    }
    sampleImg.onload = () => { imageReady = true; resolve(); };
    sampleImg.onerror = () => resolve();
    sampleImg.src = SAMPLE_SRC;
  });
}

function ensureCanvasSized() {
  if (sized) return;
  const sw = sampleImg.naturalWidth;
  const sh = sampleImg.naturalHeight;
  if (!sw || !sh) return;
  let w = sw, h = sh;
  const larger = Math.max(sw, sh);
  if (larger > MAX_SIDE) {
    const scale = MAX_SIDE / larger;
    w = Math.round(sw * scale);
    h = Math.round(sh * scale);
  }
  glcanvas.width = w;
  glcanvas.height = h;
  gl.viewport(0, 0, w, h);
  sized = true;
}

function bindImageTexture() {
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, videoTex);
  if (!imageUploaded) {
    // Image is static: upload once, flipped upright.
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, sampleImg);
    imageUploaded = true;
  }
}

// ---- WebAudio graph ----------------------------------------------------------
let audioCtx = null;
let analyser = null;
let silentGain = null;
let timeBuf = null;
let freqBuf = null;

// per-source nodes
let currentSourceNode = null;      // node currently feeding the analyser
let toneNodes = null;              // {osc1, osc2, gainA, lfo, lfoGain}
let mediaElSource = null;          // cached MediaElementSource (can only create once)
let micStream = null;

function ensureAudioContext() {
  if (audioCtx) return;
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0.8;
  timeBuf = new Uint8Array(analyser.fftSize);
  freqBuf = new Uint8Array(analyser.frequencyBinCount);

  // Silent sink (REQUIRED): analyser -> silentGain(0) -> destination, wired once
  // for ALL modes so the graph is actively pulled (headless analysers otherwise
  // return all-zeros). gain=0 keeps it inaudible (no sound, no mic feedback).
  silentGain = audioCtx.createGain();
  silentGain.gain.value = 0;
  analyser.connect(silentGain);
  silentGain.connect(audioCtx.destination);
}

function disconnectCurrentSource() {
  if (currentSourceNode) {
    try { currentSourceNode.disconnect(); } catch (e) { /* noop */ }
    currentSourceNode = null;
  }
}

async function resumeAudio() {
  ensureAudioContext();
  try {
    await audioCtx.resume();
  } catch (e) {
    setStatus('audio resume failed: ' + e.message, true);
  }
}

// ---- Sources -----------------------------------------------------------------
function buildTone() {
  ensureAudioContext();
  disconnectCurrentSource();

  const osc1 = audioCtx.createOscillator();
  osc1.type = 'sawtooth';
  osc1.frequency.value = 220;
  const osc2 = audioCtx.createOscillator();
  osc2.type = 'square';
  osc2.frequency.value = 330;

  const gainA = audioCtx.createGain();
  gainA.gain.value = 0.5;

  // LFO wobbles the amplitude (~3 Hz) so analyser output varies frame-to-frame.
  const lfo = audioCtx.createOscillator();
  lfo.type = 'sine';
  lfo.frequency.value = 3;
  const lfoGain = audioCtx.createGain();
  lfoGain.gain.value = 0.4;
  lfo.connect(lfoGain);
  lfoGain.connect(gainA.gain);

  // Optional spectral motion: sweep osc1 frequency slowly with a second LFO tap.
  const lfoFreq = audioCtx.createGain();
  lfoFreq.gain.value = 80;
  lfo.connect(lfoFreq);
  lfoFreq.connect(osc1.frequency);

  osc1.connect(gainA);
  osc2.connect(gainA);
  gainA.connect(analyser);

  osc1.start();
  osc2.start();
  lfo.start();

  toneNodes = { osc1, osc2, gainA, lfo, lfoGain, lfoFreq };
  currentSourceNode = gainA;
  setStatus('tone');
  srcOutEl.textContent = 'source: tone';
}

async function buildMic() {
  ensureAudioContext();
  await resumeAudio();
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    setStatus('mic unavailable: ' + e.message, true);
    return;
  }
  disconnectCurrentSource();
  const src = audioCtx.createMediaStreamSource(micStream);
  // Never route mic audibly to destination (feedback); only the gain=0 sink path.
  src.connect(analyser);
  currentSourceNode = src;
  setStatus('mic');
  srcOutEl.textContent = 'source: mic';
}

async function buildFile(file) {
  ensureAudioContext();
  await resumeAudio();
  disconnectCurrentSource();

  audioEl.src = URL.createObjectURL(file);
  audioEl.loop = true;

  // MediaElementSource can only be created once per element; cache it.
  if (!mediaElSource) {
    mediaElSource = audioCtx.createMediaElementSource(audioEl);
  }
  mediaElSource.connect(analyser);       // analysis tap (-> silentGain -> dest)
  mediaElSource.connect(audioCtx.destination); // audible playback
  currentSourceNode = mediaElSource;

  try {
    await audioEl.play();
  } catch (e) {
    setStatus('file play failed: ' + e.message, true);
  }
  setStatus('file: ' + file.name);
  srcOutEl.textContent = 'source: file';
}

// ---- Feature extraction (§4) -------------------------------------------------
function bandAverage(loHz, hiHz) {
  const nyquist = audioCtx.sampleRate / 2;
  const binWidth = audioCtx.sampleRate / analyser.fftSize;
  const loBin = Math.max(0, Math.floor(loHz / binWidth));
  const hiBin = Math.min(freqBuf.length - 1, Math.ceil(Math.min(hiHz, nyquist) / binWidth));
  let sum = 0, count = 0;
  for (let i = loBin; i <= hiBin; i++) { sum += freqBuf[i]; count++; }
  return count > 0 ? (sum / count) / 255 : 0;
}

function readAudioFeatures() {
  if (!analyser || !audioCtx || audioCtx.state !== 'running') {
    return { rms: 0, bass: 0, mid: 0, treble: 0 };
  }
  analyser.getByteTimeDomainData(timeBuf);
  let acc = 0;
  for (let i = 0; i < timeBuf.length; i++) {
    const s = (timeBuf[i] - 128) / 128;
    acc += s * s;
  }
  const rms = Math.sqrt(acc / timeBuf.length);

  analyser.getByteFrequencyData(freqBuf);
  const bass = bandAverage(20, 250);
  const mid = bandAverage(250, 2000);
  const treble = bandAverage(2000, 8000);
  return { rms, bass, mid, treble };
}

// ---- Smoothing + mapping (§5) ------------------------------------------------
const SMOOTH_K = 0.2;

function smoothAndMap() {
  const raw = readAudioFeatures();
  state.rms = mix(state.rms, raw.rms, SMOOTH_K);
  state.bass = mix(state.bass, raw.bass, SMOOTH_K);
  state.mid = mix(state.mid, raw.mid, SMOOTH_K);
  state.treble = mix(state.treble, raw.treble, SMOOTH_K);

  const sens = state.sensitivity;
  const rmsS = clamp(state.rms * sens, 0, 1);
  const bassS = clamp(state.bass * sens, 0, 1);
  const trebleS = clamp(state.treble * sens, 0, 1);

  // Loudness -> primary coarseness (pixelScale) and discrete Bayer size.
  state.pixelScale = mix(1, 10, rmsS);
  let bsize = 8;
  if (rmsS >= 0.5) bsize = 2;
  else if (rmsS >= 0.2) bsize = 4;
  state.bayerSize = bsize;

  // Bass -> contrast + threshold shift (the "pump" on the kick).
  state.contrast = mix(1.0, 3.0, bassS);
  state.thresholdShift = mix(0.0, 0.25, bassS);

  // Treble -> ground hue rotation.
  state.ground = hslToRgb01(BASE_GROUND_HUE + trebleS * 180, 1.0, 0.5);

  // Test hooks.
  window.__audioLevel = state.rms;
  window.__bands = { bass: state.bass, mid: state.mid, treble: state.treble };
}

function maybeReuploadBayerLut() {
  if (state.bayerSize !== uploadedBayerSize) {
    uploadBayerLut(state.bayerSize);
  }
}

// ---- Uniforms ----------------------------------------------------------------
function updateUniforms() {
  gl.uniform1f(loc.uBayerSize, state.bayerSize);
  gl.uniform1f(loc.uContrast, state.contrast);
  gl.uniform1f(loc.uPixelScale, state.pixelScale);
  gl.uniform1f(loc.uThresholdShift, state.thresholdShift);
  gl.uniform2f(loc.uResolution, glcanvas.width, glcanvas.height);
  gl.uniform3fv(loc.uInk, INK);
  gl.uniform3fv(loc.uGround, state.ground);
}

// ---- Overlay meter (§7) ------------------------------------------------------
const mctx = meterCanvas.getContext('2d');

function drawMeter() {
  const W = meterCanvas.width, H = meterCanvas.height;
  mctx.clearRect(0, 0, W, H);
  mctx.fillStyle = 'rgba(0,0,0,0.3)';
  mctx.fillRect(0, 0, W, H);

  // VU bar (top): length ~ RMS, green->yellow->red.
  const vu = clamp(state.rms * state.sensitivity, 0, 1);
  const vuW = Math.round(vu * (W - 8));
  const grad = mctx.createLinearGradient(4, 0, W - 4, 0);
  grad.addColorStop(0, '#3ad13a');
  grad.addColorStop(0.6, '#e8d13a');
  grad.addColorStop(1, '#e84a3a');
  mctx.fillStyle = grad;
  mctx.fillRect(4, 6, vuW, 12);
  mctx.strokeStyle = 'rgba(255,255,255,0.3)';
  mctx.strokeRect(4, 6, W - 8, 12);

  // Three band bars (bottom): heights ~ band values.
  const bands = [
    { v: state.bass, c: '#4aa3ff' },
    { v: state.mid, c: '#8a7bff' },
    { v: state.treble, c: '#ff6bd6' },
  ];
  const barW = 28;
  const gap = 14;
  const baseY = H - 8;
  const maxH = H - 34;
  const startX = (W - (barW * 3 + gap * 2)) / 2;
  for (let i = 0; i < 3; i++) {
    const h = Math.round(clamp(bands[i].v * state.sensitivity, 0, 1) * maxH);
    const x = startX + i * (barW + gap);
    mctx.fillStyle = bands[i].c;
    mctx.fillRect(x, baseY - h, barW, h);
  }
}

// ---- Render loop -------------------------------------------------------------
let lastFpsTime = performance.now();
let framesSinceFps = 0;

function updateFps() {
  framesSinceFps++;
  const now = performance.now();
  const dt = now - lastFpsTime;
  if (dt >= 500) {
    const fps = (framesSinceFps * 1000) / dt;
    fpsEl.textContent = fps.toFixed(0) + ' fps';
    lastFpsTime = now;
    framesSinceFps = 0;
  }
}

function frame() {
  requestAnimationFrame(frame);
  if (!imageReady) return;
  ensureCanvasSized();
  if (!sized) return;

  smoothAndMap();
  maybeReuploadBayerLut();
  bindImageTexture();
  updateUniforms();
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  drawMeter();

  window.__frames = (window.__frames || 0) + 1;
  levelOutEl.textContent = 'level ' + state.rms.toFixed(3);
  updateFps();
}

// ---- Controls ----------------------------------------------------------------
function wireControls() {
  startBtn.addEventListener('click', async () => {
    await resumeAudio();
    if (!currentSourceNode && new URLSearchParams(location.search).get('src') === 'tone') {
      buildTone();
    }
  });

  micBtn.addEventListener('click', () => { buildMic(); });

  fileInput.addEventListener('change', () => {
    const f = fileInput.files && fileInput.files[0];
    if (f) buildFile(f);
  });

  sensitivityEl.addEventListener('input', () => {
    state.sensitivity = parseFloat(sensitivityEl.value) || 1.0;
    sensitivityOut.textContent = state.sensitivity.toFixed(2);
  });
}

// ---- Source init (§8) --------------------------------------------------------
async function initSource() {
  const params = new URLSearchParams(location.search);
  if (params.get('src') === 'tone') {
    buildTone();
    // Auto-resume for the deterministic headless path.
    await resumeAudio();
    if (audioCtx.state !== 'running') {
      // Fallback: resume on first interaction / visibility change.
      const retry = () => resumeAudio();
      window.addEventListener('pointerdown', retry, { once: true });
      document.addEventListener('visibilitychange', retry, { once: true });
    }
    return;
  }
  setStatus('ready — Start Audio, then Use Mic or Load file');
  srcOutEl.textContent = 'source: none';
}

// ---- Boot --------------------------------------------------------------------
async function main() {
  try {
    initGL();
  } catch (err) {
    setStatus('WebGL error: ' + err.message, true);
    console.error(err);
    return;
  }
  sensitivityOut.textContent = state.sensitivity.toFixed(2);
  wireControls();
  await loadSampleImage();
  await initSource();
  requestAnimationFrame(frame);
}

main();

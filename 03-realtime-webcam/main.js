// 03-realtime-webcam/main.js
// Live, real-time two-tone Bayer-dithered webcam feed rendered by a WebGL
// fragment shader. Pipeline: getUserMedia -> <video> -> per-frame GL texture
// -> shader (luminance -> contrast -> Bayer threshold via LUT texture ->
// two-tone mix) -> <canvas>, driven by requestAnimationFrame.
//
// The dither runs in GLSL (the GPU path) because ordered (Bayer) dithering is
// stateless per pixel and maps perfectly onto a parallel fragment shader. This
// intentionally re-implements the Bayer math from shared/dither.js instead of
// importing that CPU/Canvas engine (which cannot run on the GPU).

// ---- DOM ---------------------------------------------------------------------
const glcanvas = document.getElementById('glcanvas');
const camVideo = document.getElementById('camVideo');
const sampleImg = document.getElementById('sampleImg');
const statusEl = document.getElementById('status');
const fpsEl = document.getElementById('fps');

const bayerSizeEl = document.getElementById('bayerSize');
const contrastEl = document.getElementById('contrast');
const contrastOut = document.getElementById('contrastOut');
const pixelScaleEl = document.getElementById('pixelScale');
const pixelScaleOut = document.getElementById('pixelScaleOut');
const inkColorEl = document.getElementById('inkColor');
const groundColorEl = document.getElementById('groundColor');
const snapshotBtn = document.getElementById('snapshotBtn');
const recordBtn = document.getElementById('recordBtn');

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

  // Bayer threshold for this cell, tiled per output block.
  vec2 cell = mod(px, uBayerSize);
  float t = texture2D(uBayer, (cell + 0.5) / uBayerSize).r;

  // Two-tone ordered-dither decision: brighter than threshold -> ground.
  float on = step(t, l);
  vec3 outc = mix(uInk, uGround, on);
  gl_FragColor = vec4(outc, 1.0);
}
`;

// ---- State -------------------------------------------------------------------
const state = {
  bayerSize: parseInt(bayerSizeEl.value, 10) || 4,
  contrast: parseFloat(contrastEl.value) || 1.4,
  pixelScale: parseInt(pixelScaleEl.value, 10) || 1,
  ink: hexToRgb01(inkColorEl.value),
  ground: hexToRgb01(groundColorEl.value),
};

// ---- WebGL setup -------------------------------------------------------------
let gl = null;
let program = null;
const loc = {}; // uniform locations
let videoTex = null;
let bayerTex = null;
let sizedForSource = false;

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
  // Fullscreen quad as a TRIANGLE_STRIP of 4 clip-space vertices (aPos only).
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
  // NPOT-safe params: CLAMP_TO_EDGE + NEAREST, no mipmaps.
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  // 1x1 placeholder so sampling never returns undefined before first upload.
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE,
    new Uint8Array([0, 0, 0, 255]));
  return tex;
}

function uploadBayerLut(n) {
  gl.activeTexture(gl.TEXTURE1);
  gl.bindTexture(gl.TEXTURE_2D, bayerTex);
  // LUT must NOT be flipped (see plan §3.4) so thresholds match the CPU engine.
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, n, n, 0, gl.RGBA, gl.UNSIGNED_BYTE,
    bayerLutBytes(n));
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

  // Cache uniform locations.
  loc.uVideo = gl.getUniformLocation(program, 'uVideo');
  loc.uBayer = gl.getUniformLocation(program, 'uBayer');
  loc.uBayerSize = gl.getUniformLocation(program, 'uBayerSize');
  loc.uContrast = gl.getUniformLocation(program, 'uContrast');
  loc.uPixelScale = gl.getUniformLocation(program, 'uPixelScale');
  loc.uResolution = gl.getUniformLocation(program, 'uResolution');
  loc.uInk = gl.getUniformLocation(program, 'uInk');
  loc.uGround = gl.getUniformLocation(program, 'uGround');

  // Sampler bindings: uVideo -> unit 0, uBayer -> unit 1 (set once).
  gl.uniform1i(loc.uVideo, 0);
  gl.uniform1i(loc.uBayer, 1);

  videoTex = createVideoTexture();
  createBayerTexture(state.bayerSize);
}

// ---- Source acquisition ------------------------------------------------------
let cameraStream = null;

function getReadySource() {
  if (camVideo.srcObject && camVideo.readyState >= 2 &&
      camVideo.videoWidth > 0 && camVideo.videoHeight > 0) {
    return camVideo;
  }
  if (sampleImg.complete && sampleImg.naturalWidth > 0) {
    return sampleImg;
  }
  return null;
}

function loadSampleImage() {
  return new Promise((resolve) => {
    if (sampleImg.complete && sampleImg.naturalWidth > 0) return resolve();
    sampleImg.onload = () => resolve();
    sampleImg.onerror = () => resolve();
    sampleImg.src = SAMPLE_SRC;
  });
}

async function initSource() {
  const params = new URLSearchParams(location.search);

  if (params.get('src') === 'sample') {
    await loadSampleImage();
    setStatus('sample (image)');
    return;
  }

  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480 },
      audio: false,
    });
    camVideo.srcObject = cameraStream;
    await camVideo.play();
    setStatus('camera');
  } catch (err) {
    await loadSampleImage();
    setStatus('camera unavailable — sample');
  }
}

// ---- Canvas sizing -----------------------------------------------------------
function sourceDims(src) {
  if (src === camVideo) return [camVideo.videoWidth, camVideo.videoHeight];
  return [sampleImg.naturalWidth, sampleImg.naturalHeight];
}

function ensureCanvasSized(src) {
  if (sizedForSource) return;
  const [sw, sh] = sourceDims(src);
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
  sizedForSource = true;
}

// ---- Uniforms ----------------------------------------------------------------
function updateUniforms() {
  gl.uniform1f(loc.uBayerSize, state.bayerSize);
  gl.uniform1f(loc.uContrast, state.contrast);
  gl.uniform1f(loc.uPixelScale, state.pixelScale);
  gl.uniform2f(loc.uResolution, glcanvas.width, glcanvas.height);
  gl.uniform3fv(loc.uInk, state.ink);
  gl.uniform3fv(loc.uGround, state.ground);
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
  const src = getReadySource();
  if (!src) return;
  ensureCanvasSized(src);
  if (!sizedForSource) return;

  // Upload current frame to the video texture (unit 0), flipped upright.
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, videoTex);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true); // scoped to source upload only
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src);

  // uBayer stays bound on unit 1; sampler uniforms set once after link.
  updateUniforms();
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

  window.__ditherFrames = (window.__ditherFrames || 0) + 1;
  updateFps();
}

// ---- Controls ----------------------------------------------------------------
function wireControls() {
  bayerSizeEl.addEventListener('change', () => {
    state.bayerSize = parseInt(bayerSizeEl.value, 10) || 4;
    uploadBayerLut(state.bayerSize); // regenerate + re-upload LUT
  });

  contrastEl.addEventListener('input', () => {
    state.contrast = parseFloat(contrastEl.value);
    contrastOut.textContent = state.contrast.toFixed(2);
  });

  pixelScaleEl.addEventListener('input', () => {
    state.pixelScale = parseInt(pixelScaleEl.value, 10) || 1;
    pixelScaleOut.textContent = String(state.pixelScale);
  });

  inkColorEl.addEventListener('change', () => {
    state.ink = hexToRgb01(inkColorEl.value);
  });

  groundColorEl.addEventListener('change', () => {
    state.ground = hexToRgb01(groundColorEl.value);
  });

  snapshotBtn.addEventListener('click', () => {
    glcanvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `webcam-dither-bayer${state.bayerSize}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }, 'image/png');
  });

  setupRecord();
}

// ---- Record (stretch) --------------------------------------------------------
let mediaRecorder = null;
let recordedChunks = [];

function setupRecord() {
  const canCapture = typeof glcanvas.captureStream === 'function' &&
                     typeof window.MediaRecorder === 'function';
  if (!canCapture) {
    recordBtn.hidden = true;
    return;
  }
  recordBtn.hidden = false;

  recordBtn.addEventListener('click', () => {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop();
      return;
    }
    recordedChunks = [];
    const stream = glcanvas.captureStream(30);
    try {
      mediaRecorder = new MediaRecorder(stream, { mimeType: 'video/webm' });
    } catch (e) {
      mediaRecorder = new MediaRecorder(stream);
    }
    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) recordedChunks.push(e.data);
    };
    mediaRecorder.onstop = () => {
      const blob = new Blob(recordedChunks, { type: 'video/webm' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'webcam-dither.webm';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      recordBtn.innerHTML = '&#9679; Record';
    };
    mediaRecorder.start();
    recordBtn.innerHTML = '&#9632; Stop';
  });
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
  wireControls();
  await initSource();
  requestAnimationFrame(frame);
}

main();

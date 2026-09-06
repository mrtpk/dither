import { twoTone, PALETTES, hexToRgb } from '../shared/palettes.js';

const MAX_EDGE = 800;
const MIN_COVERAGE = 0.01;

const TONE_PRESETS = {
  riso: { ink: '#1e1e78', paper: '#ff4682' },
  loudNeon: { ink: '#0a0a0a', paper: '#d6ff00' },
  inkOnWhite: { ink: '#111111', paper: '#f5f5f5' },
  amber: { ink: '#140c00', paper: '#ffb000' },
  bw: { ink: '#000000', paper: '#ffffff' },
};

const CMYK_ANGLES = { C: 15, M: 75, Y: 0, K: 45 };

const state = {
  mode: 'duotone',
  cellSize: 10,
  dotShape: 'circle',
  screenAngle: 45,
  contrast: 1.2,
  tonePreset: 'riso',
  inkHex: '#1e1e78',
  paperHex: '#ff4682',
};

let sourceImage = null;
let objectUrl = null;
let pendingFrame = null;

const workCanvas = document.getElementById('workCanvas');
const workCtx = workCanvas.getContext('2d', { willReadFrequently: true });
const displayCanvas = document.getElementById('displayCanvas');
const displayCtx = displayCanvas.getContext('2d');

const srcCanvas = document.createElement('canvas');
const srcCtx = srcCanvas.getContext('2d', { willReadFrequently: true });
const plateCanvas = document.createElement('canvas');
const plateCtx = plateCanvas.getContext('2d');

const modeSelect = document.getElementById('mode');
const cellSizeInput = document.getElementById('cellSize');
const cellSizeOut = document.getElementById('cellSizeOut');
const dotShapeSelect = document.getElementById('dotShape');
const screenAngleInput = document.getElementById('screenAngle');
const screenAngleOut = document.getElementById('screenAngleOut');
const contrastInput = document.getElementById('contrast');
const contrastOut = document.getElementById('contrastOut');
const tonePresetSelect = document.getElementById('tonePreset');
const inkColorInput = document.getElementById('inkColor');
const paperColorInput = document.getElementById('paperColor');
const fileInput = document.getElementById('fileInput');
const fileNameEl = document.getElementById('fileName');
const exportBtn = document.getElementById('exportBtn');
const sizeReadout = document.getElementById('sizeReadout');

const screenAngleLabel = document.getElementById('screenAngleLabel');
const tonePresetLabel = document.getElementById('tonePresetLabel');
const inkColorLabel = document.getElementById('inkColorLabel');
const paperColorLabel = document.getElementById('paperColorLabel');

window.__halftoneReady = false;

let cachedSource = null;
let cachedW = 0;
let cachedH = 0;
let cachedImageData = null;
let cachedBufKey = null;
let cachedBuffers = null;

function rgbFill(rgb) {
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

function applyContrast(v, contrast) {
  return Math.min(1, Math.max(0, (v - 0.5) * contrast + 0.5));
}

function workSize(srcW, srcH) {
  const scale = Math.min(1, MAX_EDGE / Math.max(srcW, srcH));
  const W = Math.max(1, Math.round(srcW * scale));
  const H = Math.max(1, Math.round(srcH * scale));
  return { W, H };
}

function getImageData(W, H) {
  if (
    cachedImageData &&
    cachedSource === sourceImage &&
    cachedW === W &&
    cachedH === H
  ) {
    return cachedImageData;
  }
  srcCanvas.width = W;
  srcCanvas.height = H;
  srcCtx.imageSmoothingEnabled = true;
  srcCtx.drawImage(sourceImage, 0, 0, W, H);
  cachedImageData = srcCtx.getImageData(0, 0, W, H);
  cachedSource = sourceImage;
  cachedW = W;
  cachedH = H;
  cachedBufKey = null;
  cachedBuffers = null;
  return cachedImageData;
}

function buildCoverageBuffers(imageData, W, H) {
  const key = `${state.mode}|${state.contrast}|${W}x${H}`;
  if (cachedBuffers && cachedBufKey === key) {
    return cachedBuffers;
  }

  const data = imageData.data;
  const contrast = state.contrast;
  const n = W * H;

  if (state.mode === 'duotone') {
    const buf = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const r = data[i * 4] / 255;
      const g = data[i * 4 + 1] / 255;
      const b = data[i * 4 + 2] / 255;
      const L = 0.299 * r + 0.587 * g + 0.114 * b;
      buf[i] = 1 - applyContrast(L, contrast);
    }
    cachedBuffers = { duotone: buf };
  } else {
    const C = new Float32Array(n);
    const M = new Float32Array(n);
    const Y = new Float32Array(n);
    const K = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const r = applyContrast(data[i * 4] / 255, contrast);
      const g = applyContrast(data[i * 4 + 1] / 255, contrast);
      const b = applyContrast(data[i * 4 + 2] / 255, contrast);
      const c0 = 1 - r;
      const m0 = 1 - g;
      const y0 = 1 - b;
      const k = Math.min(c0, m0, y0);
      C[i] = c0 - k;
      M[i] = m0 - k;
      Y[i] = y0 - k;
      K[i] = k;
    }
    cachedBuffers = { C, M, Y, K };
  }

  cachedBufKey = key;
  return cachedBuffers;
}

function sampleCoverage(buf, W, H, sx, sy, cellSize) {
  const x0 = Math.max(0, Math.floor(sx - cellSize / 2));
  const x1 = Math.min(W, Math.ceil(sx + cellSize / 2));
  const y0 = Math.max(0, Math.floor(sy - cellSize / 2));
  const y1 = Math.min(H, Math.ceil(sy + cellSize / 2));
  if (x1 <= x0 || y1 <= y0) return 0;
  let sum = 0;
  let count = 0;
  for (let y = y0; y < y1; y++) {
    const row = y * W;
    for (let x = x0; x < x1; x++) {
      sum += buf[row + x];
      count++;
    }
  }
  return sum / count;
}

function drawDot(ctx, x, y, c, cellSize, shape) {
  if (shape === 'circle') {
    const r = Math.sqrt(c) * (cellSize * Math.SQRT2 / 2);
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  if (shape === 'square') {
    const side = cellSize * Math.sqrt(c);
    ctx.fillRect(x - side / 2, y - side / 2, side, side);
    return;
  }
  const thickness = cellSize * c;
  ctx.fillRect(x - cellSize / 2, y - thickness / 2, cellSize, thickness);
}

function drawScreen(ctx, buf, W, H, cellSize, angleDeg, shape, fillStyle) {
  const theta = (angleDeg * Math.PI) / 180;
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);

  ctx.save();
  ctx.fillStyle = fillStyle;
  ctx.translate(W / 2, H / 2);
  ctx.rotate(theta);

  const halfDiag = Math.hypot(W, H) / 2;
  const extent = halfDiag + cellSize;
  const n = Math.ceil(extent / cellSize);

  for (let j = -n; j <= n; j++) {
    for (let i = -n; i <= n; i++) {
      const cx = (i + 0.5) * cellSize;
      const cy = (j + 0.5) * cellSize;
      const sx = W / 2 + cx * cos - cy * sin;
      const sy = H / 2 + cx * sin + cy * cos;
      if (
        sx < -cellSize ||
        sx >= W + cellSize ||
        sy < -cellSize ||
        sy >= H + cellSize
      ) {
        continue;
      }
      const c = sampleCoverage(buf, W, H, sx, sy, cellSize);
      if (c < MIN_COVERAGE) continue;
      drawDot(ctx, cx, cy, c, cellSize, shape);
    }
  }

  ctx.restore();
}

function renderDuotone(W, H, buffers) {
  const [inkRgb, paperRgb] = twoTone(state.inkHex, state.paperHex);
  workCanvas.width = W;
  workCanvas.height = H;
  workCtx.globalCompositeOperation = 'source-over';
  workCtx.fillStyle = rgbFill(paperRgb);
  workCtx.fillRect(0, 0, W, H);
  drawScreen(
    workCtx,
    buffers.duotone,
    W,
    H,
    state.cellSize,
    state.screenAngle,
    state.dotShape,
    rgbFill(inkRgb),
  );
}

function renderCmyk(W, H, buffers) {
  workCanvas.width = W;
  workCanvas.height = H;
  workCtx.globalCompositeOperation = 'source-over';
  workCtx.fillStyle = rgbFill(PALETTES.cmyk[4]);
  workCtx.fillRect(0, 0, W, H);

  plateCanvas.width = W;
  plateCanvas.height = H;

  const plates = [
    { buf: buffers.C, angle: CMYK_ANGLES.C, ink: rgbFill(PALETTES.cmyk[1]) },
    { buf: buffers.M, angle: CMYK_ANGLES.M, ink: rgbFill(PALETTES.cmyk[2]) },
    { buf: buffers.Y, angle: CMYK_ANGLES.Y, ink: rgbFill(PALETTES.cmyk[3]) },
    { buf: buffers.K, angle: CMYK_ANGLES.K, ink: rgbFill(PALETTES.cmyk[0]) },
  ];

  for (const plate of plates) {
    plateCtx.globalCompositeOperation = 'source-over';
    plateCtx.fillStyle = '#ffffff';
    plateCtx.fillRect(0, 0, W, H);
    drawScreen(
      plateCtx,
      plate.buf,
      W,
      H,
      state.cellSize,
      plate.angle,
      state.dotShape,
      plate.ink,
    );
    workCtx.globalCompositeOperation = 'multiply';
    workCtx.drawImage(plateCanvas, 0, 0);
  }

  workCtx.globalCompositeOperation = 'source-over';
}

function render() {
  window.__halftoneReady = false;
  if (!sourceImage) return;

  const srcW = sourceImage.naturalWidth;
  const srcH = sourceImage.naturalHeight;
  const { W, H } = workSize(srcW, srcH);
  const imageData = getImageData(W, H);
  const buffers = buildCoverageBuffers(imageData, W, H);

  if (state.mode === 'duotone') {
    renderDuotone(W, H, buffers);
  } else {
    renderCmyk(W, H, buffers);
  }

  displayCanvas.width = W;
  displayCanvas.height = H;
  displayCtx.imageSmoothingEnabled = true;
  displayCtx.drawImage(workCanvas, 0, 0);

  sizeReadout.textContent = `${srcW} × ${srcH} → ${W} × ${H}`;
  window.__halftoneReady = true;
}

function scheduleRender() {
  if (pendingFrame !== null) {
    cancelAnimationFrame(pendingFrame);
  }
  pendingFrame = requestAnimationFrame(() => {
    pendingFrame = null;
    render();
  });
}

function applyTonePreset(presetKey) {
  const preset = TONE_PRESETS[presetKey];
  if (!preset) return;
  state.inkHex = preset.ink;
  state.paperHex = preset.paper;
  inkColorInput.value = preset.ink;
  paperColorInput.value = preset.paper;
}

function updateModeEnabled() {
  const duotone = state.mode === 'duotone';
  screenAngleInput.disabled = !duotone;
  tonePresetSelect.disabled = !duotone;
  inkColorInput.disabled = !duotone;
  paperColorInput.disabled = !duotone;
  screenAngleLabel.classList.toggle('disabled', !duotone);
  tonePresetLabel.classList.toggle('disabled', !duotone);
  inkColorLabel.classList.toggle('disabled', !duotone);
  paperColorLabel.classList.toggle('disabled', !duotone);
}

function loadImageFromUrl(url, name) {
  const img = new Image();
  img.onload = () => {
    if (objectUrl && objectUrl !== url) {
      URL.revokeObjectURL(objectUrl);
    }
    objectUrl = url;
    sourceImage = img;
    fileNameEl.textContent = name;
    scheduleRender();
  };
  img.onerror = () => {
    console.error('Failed to load image:', name);
  };
  img.src = url;
}

async function loadDefaultSample() {
  try {
    const res = await fetch('../data/samples/02a.png');
    if (!res.ok) throw new Error(res.statusText);
    const blob = await res.blob();
    loadImageFromUrl(URL.createObjectURL(blob), '02a.png');
  } catch (err) {
    console.error('Failed to load default sample:', err);
    fileNameEl.textContent = '(sample failed to load)';
  }
}

function handleExport() {
  if (!sourceImage || workCanvas.width === 0) return;
  workCanvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `halftone-${state.mode}-${state.dotShape}.png`;
    a.click();
    URL.revokeObjectURL(url);
  }, 'image/png');
}

function wireControls() {
  modeSelect.addEventListener('change', () => {
    state.mode = modeSelect.value;
    updateModeEnabled();
    scheduleRender();
  });

  cellSizeInput.addEventListener('input', () => {
    state.cellSize = parseInt(cellSizeInput.value, 10);
    cellSizeOut.textContent = String(state.cellSize);
    scheduleRender();
  });

  dotShapeSelect.addEventListener('change', () => {
    state.dotShape = dotShapeSelect.value;
    scheduleRender();
  });

  screenAngleInput.addEventListener('input', () => {
    state.screenAngle = parseInt(screenAngleInput.value, 10);
    screenAngleOut.textContent = String(state.screenAngle);
    scheduleRender();
  });

  contrastInput.addEventListener('input', () => {
    state.contrast = parseFloat(contrastInput.value);
    contrastOut.textContent = state.contrast.toFixed(2);
    scheduleRender();
  });

  tonePresetSelect.addEventListener('change', () => {
    state.tonePreset = tonePresetSelect.value;
    if (state.tonePreset !== 'custom') {
      applyTonePreset(state.tonePreset);
    }
    scheduleRender();
  });

  inkColorInput.addEventListener('change', () => {
    state.inkHex = inkColorInput.value;
    state.tonePreset = 'custom';
    tonePresetSelect.value = 'custom';
    scheduleRender();
  });

  paperColorInput.addEventListener('change', () => {
    state.paperHex = paperColorInput.value;
    state.tonePreset = 'custom';
    tonePresetSelect.value = 'custom';
    scheduleRender();
  });

  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    loadImageFromUrl(URL.createObjectURL(file), file.name);
  });

  exportBtn.addEventListener('click', handleExport);
}

function verifyPaletteSanity() {
  const built = twoTone('#1e1e78', '#ff4682');
  const ref = PALETTES.riso;
  const ok = built.every((c, i) => c.every((v, j) => v === ref[i][j]));
  if (!ok) {
    console.warn('twoTone riso sanity check failed', built, ref);
  }
  hexToRgb('#1e1e78');
}

wireControls();
updateModeEnabled();
verifyPaletteSanity();
loadDefaultSample();

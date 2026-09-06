import { luminance, toGrayscale, BAYER } from '../shared/dither.js';

const MAX_EDGE = 800;
const CHAR_ASPECT = 0.5;

const RAMPS = {
  classic: ' .:-=+*#%@',
  blocks: ' ░▒▓█',
  audio: ' ▁▂▃▄▅▆▇█',
};

const state = {
  columns: 80,
  ramp: 'classic',
  contrast: 1.0,
  brightness: 0,
  invert: false,
  fontSize: 10,
  fgHex: '#d6ff00',
  bgHex: '#0a0a0a',
  viewMode: 'text',
  dither: true,
  ditherStrength: 0.8,
};

let sourceImage = null;
let objectUrl = null;
let pendingFrame = null;

const srcCanvas = document.getElementById('srcCanvas');
const srcCtx = srcCanvas.getContext('2d', { willReadFrequently: true });
const asciiOutput = document.getElementById('asciiOutput');
const exportCanvas = document.getElementById('exportCanvas');
const exportCtx = exportCanvas.getContext('2d');

const columnsInput = document.getElementById('columns');
const columnsOut = document.getElementById('columnsOut');
const rampSelect = document.getElementById('ramp');
const contrastInput = document.getElementById('contrast');
const contrastOut = document.getElementById('contrastOut');
const brightnessInput = document.getElementById('brightness');
const brightnessOut = document.getElementById('brightnessOut');
const invertInput = document.getElementById('invert');
const fontSizeInput = document.getElementById('fontSize');
const fontSizeOut = document.getElementById('fontSizeOut');
const fgColorInput = document.getElementById('fgColor');
const bgColorInput = document.getElementById('bgColor');
const ditherInput = document.getElementById('dither');
const ditherStrengthInput = document.getElementById('ditherStrength');
const ditherStrengthOut = document.getElementById('ditherStrengthOut');
const ditherStrengthLabel = document.getElementById('ditherStrengthLabel');
const viewModeText = document.getElementById('viewModeText');
const viewModeCanvas = document.getElementById('viewModeCanvas');
const copyBtn = document.getElementById('copyBtn');
const downloadBtn = document.getElementById('downloadBtn');
const fileInput = document.getElementById('fileInput');
const fileNameEl = document.getElementById('fileName');
const gridReadout = document.getElementById('gridReadout');

window.__asciiReady = false;

function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}

function capSourceSize(naturalW, naturalH) {
  const scale = Math.min(1, MAX_EDGE / Math.max(naturalW, naturalH));
  return {
    srcW: Math.max(1, Math.round(naturalW * scale)),
    srcH: Math.max(1, Math.round(naturalH * scale)),
  };
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

function revokeObjectUrl() {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }
}

function loadImageFromUrl(url, name) {
  const img = new Image();
  img.onload = () => {
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
    const res = await fetch('../data/samples/01a.png');
    if (!res.ok) throw new Error(res.statusText);
    const blob = await res.blob();
    revokeObjectUrl();
    objectUrl = URL.createObjectURL(blob);
    loadImageFromUrl(objectUrl, '01a.png');
  } catch (err) {
    console.error('Failed to load default sample:', err);
    fileNameEl.textContent = '(sample failed to load)';
  }
}

function boxAverageLuminance(imageData, srcW, cx, cy, cellSrcW, cellSrcH) {
  const srcH = imageData.height;
  const data = imageData.data;

  const x0 = Math.floor(cx * cellSrcW);
  const y0 = Math.floor(cy * cellSrcH);
  const x1 = Math.min(srcW, Math.ceil((cx + 1) * cellSrcW));
  const y1 = Math.min(srcH, Math.ceil((cy + 1) * cellSrcH));

  let sum = 0;
  let count = 0;

  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      const i = (y * srcW + x) * 4;
      sum += luminance(data[i], data[i + 1], data[i + 2]);
      count++;
    }
  }

  return count > 0 ? sum / count : 0;
}

function toneToGlyph(L, cx, cy, ramp) {
  let v = (L - 128) * state.contrast + 128 + state.brightness;
  v = clamp(v, 0, 255);

  if (state.invert) {
    v = 255 - v;
  }

  if (state.dither && state.ditherStrength > 0) {
    const threshold = BAYER[4][cy % 4][cx % 4];
    const t = (threshold - 0.5) * 255 * state.ditherStrength;
    v = clamp(v + t, 0, 255);
  }

  const N = ramp.length;
  const norm = v / 255;
  let idx = (N - 1) - Math.floor(norm * (N - 1));
  idx = clamp(idx, 0, N - 1);
  return ramp[idx];
}

function updateViewMode() {
  const isText = state.viewMode === 'text';
  asciiOutput.hidden = !isText;
  exportCanvas.hidden = isText;
  copyBtn.disabled = !isText;
  downloadBtn.disabled = isText;
}

function updateDitherStrengthEnabled() {
  const enabled = state.dither;
  ditherStrengthInput.disabled = !enabled;
  ditherStrengthLabel.classList.toggle('disabled', !enabled);
}

function renderTextOutput(lines, cols, rows, naturalW, naturalH) {
  asciiOutput.textContent = lines.join('\n');
  asciiOutput.style.fontSize = `${state.fontSize}px`;
  asciiOutput.style.lineHeight = '1';
  asciiOutput.style.color = state.fgHex;
  asciiOutput.style.background = state.bgHex;
  gridReadout.textContent =
    `${naturalW} × ${naturalH} → ${cols} × ${rows} (${cols * rows} chars)`;
}

function renderCanvasOutput(lines, cols, rows) {
  exportCtx.font = `${state.fontSize}px monospace`;
  const charW = exportCtx.measureText('M').width;
  const charH = state.fontSize * 2;

  exportCanvas.width = Math.max(1, Math.ceil(cols * charW));
  exportCanvas.height = Math.max(1, Math.ceil(rows * charH));

  exportCtx.fillStyle = state.bgHex;
  exportCtx.fillRect(0, 0, exportCanvas.width, exportCanvas.height);

  exportCtx.font = `${state.fontSize}px monospace`;
  exportCtx.fillStyle = state.fgHex;
  exportCtx.textBaseline = 'top';

  for (let cy = 0; cy < rows; cy++) {
    const line = lines[cy];
    for (let cx = 0; cx < cols; cx++) {
      exportCtx.fillText(line[cx], cx * charW, cy * charH);
    }
  }
}

function render() {
  window.__asciiReady = false;

  if (!sourceImage) return;

  const naturalW = sourceImage.naturalWidth;
  const naturalH = sourceImage.naturalHeight;
  const { srcW, srcH } = capSourceSize(naturalW, naturalH);

  srcCanvas.width = srcW;
  srcCanvas.height = srcH;
  srcCtx.imageSmoothingEnabled = true;
  srcCtx.drawImage(sourceImage, 0, 0, srcW, srcH);

  const imageData = srcCtx.getImageData(0, 0, srcW, srcH);
  toGrayscale(imageData);

  const cols = clamp(parseInt(columnsInput.value, 10) || state.columns, 20, 300);
  const rows = Math.max(1, Math.round((srcH / srcW) * cols * CHAR_ASPECT));
  const cellSrcW = srcW / cols;
  const cellSrcH = srcH / rows;
  const ramp = RAMPS[state.ramp] || RAMPS.classic;

  const lines = new Array(rows);
  for (let cy = 0; cy < rows; cy++) {
    let row = '';
    for (let cx = 0; cx < cols; cx++) {
      const L = boxAverageLuminance(imageData, srcW, cx, cy, cellSrcW, cellSrcH);
      row += toneToGlyph(L, cx, cy, ramp);
    }
    lines[cy] = row;
  }

  renderTextOutput(lines, cols, rows, naturalW, naturalH);
  renderCanvasOutput(lines, cols, rows);
  updateViewMode();

  window.__asciiReady = true;
}

async function handleCopy() {
  if (state.viewMode !== 'text') return;
  try {
    await navigator.clipboard.writeText(asciiOutput.textContent);
    const prev = copyBtn.textContent;
    copyBtn.textContent = 'Copied!';
    setTimeout(() => {
      copyBtn.textContent = prev;
    }, 1500);
  } catch (err) {
    console.error('Copy failed:', err);
  }
}

function handleDownload() {
  if (state.viewMode !== 'canvas' || exportCanvas.width === 0) return;

  exportCanvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ascii-${state.ramp}-${state.columns}.png`;
    a.click();
    URL.revokeObjectURL(url);
  }, 'image/png');
}

function wireControls() {
  columnsInput.addEventListener('input', () => {
    state.columns = clamp(parseInt(columnsInput.value, 10), 20, 300);
    columnsInput.value = String(state.columns);
    columnsOut.textContent = String(state.columns);
    scheduleRender();
  });

  rampSelect.addEventListener('change', () => {
    state.ramp = rampSelect.value;
    scheduleRender();
  });

  contrastInput.addEventListener('input', () => {
    state.contrast = parseFloat(contrastInput.value);
    contrastOut.textContent = state.contrast.toFixed(2);
    scheduleRender();
  });

  brightnessInput.addEventListener('input', () => {
    state.brightness = parseInt(brightnessInput.value, 10);
    brightnessOut.textContent = String(state.brightness);
    scheduleRender();
  });

  invertInput.addEventListener('change', () => {
    state.invert = invertInput.checked;
    scheduleRender();
  });

  fontSizeInput.addEventListener('input', () => {
    state.fontSize = parseInt(fontSizeInput.value, 10);
    fontSizeOut.textContent = String(state.fontSize);
    scheduleRender();
  });

  fgColorInput.addEventListener('change', () => {
    state.fgHex = fgColorInput.value;
    scheduleRender();
  });

  bgColorInput.addEventListener('change', () => {
    state.bgHex = bgColorInput.value;
    scheduleRender();
  });

  ditherInput.addEventListener('change', () => {
    state.dither = ditherInput.checked;
    updateDitherStrengthEnabled();
    scheduleRender();
  });

  ditherStrengthInput.addEventListener('input', () => {
    state.ditherStrength = parseFloat(ditherStrengthInput.value);
    ditherStrengthOut.textContent = state.ditherStrength.toFixed(2);
    scheduleRender();
  });

  viewModeText.addEventListener('change', () => {
    if (viewModeText.checked) {
      state.viewMode = 'text';
      updateViewMode();
      if (sourceImage) window.__asciiReady = true;
    }
  });

  viewModeCanvas.addEventListener('change', () => {
    if (viewModeCanvas.checked) {
      state.viewMode = 'canvas';
      updateViewMode();
      if (sourceImage) window.__asciiReady = true;
    }
  });

  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    revokeObjectUrl();
    objectUrl = URL.createObjectURL(file);
    loadImageFromUrl(objectUrl, file.name);
  });

  copyBtn.addEventListener('click', handleCopy);
  downloadBtn.addEventListener('click', handleDownload);
}

wireControls();
updateDitherStrengthEnabled();
updateViewMode();
loadDefaultSample();

import { dither, ALGORITHMS, pixelateSource } from '../shared/dither.js';
import { twoTone, PALETTES } from '../shared/palettes.js';

const ALGORITHM_LABELS = {
  'floyd-steinberg': 'Floyd–Steinberg',
  atkinson: 'Atkinson',
  'jarvis-judice-ninke': 'Jarvis–Judice–Ninke',
  bayer2: 'Bayer 2×2',
  bayer4: 'Bayer 4×4',
  bayer8: 'Bayer 8×8',
  threshold: 'Threshold',
};

const BRAND_PRESETS = {
  loudNeon: { ink: '#0a0a0a', ground: '#d6ff00' },
  loudRed: { ink: '#f5f0eb', ground: '#dc1e28' },
  riso: { ink: '#1e1e78', ground: '#ff4682' },
  amber: { ink: '#140c00', ground: '#ffb000' },
};

const BAYER_ALGORITHMS = new Set(['bayer2', 'bayer4', 'bayer8']);

const state = {
  inkHex: '#0a0a0a',
  groundHex: '#d6ff00',
  brandPreset: 'loudNeon',
  algorithm: 'bayer4',
  contrast: 2.25,
  pixelScale: 6,
  strength: 1.0,
  showOverlay: true,
  headlineText: "TWO-TONE BRAND POSTER",
  showMeter: true,
};

let sourceImage = null;
let objectUrl = null;
let pendingFrame = null;

const workCanvas = document.getElementById('workCanvas');
const workCtx = workCanvas.getContext('2d', { willReadFrequently: true });
const posterCanvas = document.getElementById('posterCanvas');
const posterCtx = posterCanvas.getContext('2d');
const displayCanvas = document.getElementById('displayCanvas');
const displayCtx = displayCanvas.getContext('2d');

const brandPresetSelect = document.getElementById('brandPreset');
const inkColorInput = document.getElementById('inkColor');
const groundColorInput = document.getElementById('groundColor');
const algorithmSelect = document.getElementById('algorithm');
const contrastInput = document.getElementById('contrast');
const contrastOut = document.getElementById('contrastOut');
const pixelScaleInput = document.getElementById('pixelScale');
const pixelScaleOut = document.getElementById('pixelScaleOut');
const strengthInput = document.getElementById('strength');
const strengthOut = document.getElementById('strengthOut');
const strengthLabel = document.getElementById('strengthLabel');
const showOverlayInput = document.getElementById('showOverlay');
const headlineTextInput = document.getElementById('headlineText');
const headlineLabel = document.getElementById('headlineLabel');
const showMeterInput = document.getElementById('showMeter');
const meterLabel = document.getElementById('meterLabel');
const fileInput = document.getElementById('fileInput');
const fileNameEl = document.getElementById('fileName');
const exportBtn = document.getElementById('exportBtn');
const sizeReadout = document.getElementById('sizeReadout');

function populateAlgorithmSelect() {
  for (const algo of ALGORITHMS) {
    const opt = document.createElement('option');
    opt.value = algo;
    opt.textContent = ALGORITHM_LABELS[algo] ?? algo;
    algorithmSelect.appendChild(opt);
  }
  algorithmSelect.value = state.algorithm;
}

function updateStrengthEnabled() {
  const enabled = BAYER_ALGORITHMS.has(state.algorithm);
  strengthInput.disabled = !enabled;
  strengthLabel.classList.toggle('disabled', !enabled);
}

function updateOverlayEnabled() {
  const enabled = state.showOverlay;
  headlineTextInput.disabled = !enabled;
  showMeterInput.disabled = !enabled;
  headlineLabel.classList.toggle('disabled', !enabled);
  meterLabel.classList.toggle('disabled', !enabled);
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
    const res = await fetch('../data/samples/02a.png');
    if (!res.ok) throw new Error(res.statusText);
    const blob = await res.blob();
    revokeObjectUrl();
    objectUrl = URL.createObjectURL(blob);
    loadImageFromUrl(objectUrl, '02a.png');
  } catch (err) {
    console.error('Failed to load default sample:', err);
    fileNameEl.textContent = '(sample failed to load)';
  }
}

function applyBrandPreset(presetKey) {
  const preset = BRAND_PRESETS[presetKey];
  if (!preset) return;
  state.inkHex = preset.ink;
  state.groundHex = preset.ground;
  inkColorInput.value = preset.ink;
  groundColorInput.value = preset.ground;
}

function seededHeights(count, seed, minPct, maxPct) {
  let s = seed;
  const heights = [];
  for (let i = 0; i < count; i++) {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    const t = s / 0x7fffffff;
    heights.push(minPct + t * (maxPct - minPct));
  }
  return heights;
}

function composePoster(w, h) {
  posterCanvas.width = w;
  posterCanvas.height = h;
  posterCtx.drawImage(workCanvas, 0, 0);

  if (!state.showOverlay) return;

  const ink = state.inkHex;
  const ground = state.groundHex;

  const headline = state.headlineText.trim();
  if (headline) {
    const bandH = Math.max(1, Math.round(h * 0.12));
    const bandY = h - bandH;
    posterCtx.fillStyle = ground;
    posterCtx.fillRect(0, bandY, w, bandH);

    posterCtx.fillStyle = ink;
    posterCtx.textAlign = 'center';
    posterCtx.textBaseline = 'middle';
    const fontSize = Math.max(8, bandH * 0.55);
    posterCtx.font = `700 ${fontSize}px Impact, Haettenschweiler, "Arial Narrow Bold", system-ui, sans-serif`;
    posterCtx.fillText(headline.toUpperCase(), w / 2, bandY + bandH / 2);
  }

  if (state.showMeter) {
    const stripW = Math.max(1, Math.round(w * 0.08));
    const stripX = w - stripW;
    posterCtx.fillStyle = ground;
    posterCtx.fillRect(stripX, 0, stripW, h);

    const barCount = 7;
    const heights = seededHeights(barCount, w + h, 0.3, 0.95);
    const gap = stripW * 0.08;
    const barW = (stripW - gap * (barCount + 1)) / barCount;

    posterCtx.fillStyle = ink;
    for (let i = 0; i < barCount; i++) {
      const barH = h * heights[i];
      const x = stripX + gap + i * (barW + gap);
      const y = h - barH;
      posterCtx.fillRect(x, y, barW, barH);
    }
  }
}

function render() {
  if (!sourceImage) return;

  const srcW = sourceImage.naturalWidth;
  const srcH = sourceImage.naturalHeight;
  const blockSize = state.pixelScale;

  const { ctx, width: w, height: h } = pixelateSource(
    sourceImage,
    srcW,
    srcH,
    blockSize,
  );

  const imageData = ctx.getImageData(0, 0, w, h);
  const working = new ImageData(
    new Uint8ClampedArray(imageData.data),
    w,
    h,
  );

  const palette = twoTone(state.inkHex, state.groundHex);

  dither(working, {
    algorithm: state.algorithm,
    palette,
    contrast: state.contrast,
    brightness: 0,
    grayscale: true,
    strength: state.strength,
  });

  workCanvas.width = w;
  workCanvas.height = h;
  workCtx.putImageData(working, 0, 0);

  composePoster(w, h);

  const displayPixelSize = blockSize;
  displayCanvas.width = w * displayPixelSize;
  displayCanvas.height = h * displayPixelSize;
  displayCtx.imageSmoothingEnabled = false;
  displayCtx.drawImage(
    posterCanvas,
    0,
    0,
    displayCanvas.width,
    displayCanvas.height,
  );

  sizeReadout.textContent = `${srcW} × ${srcH} → ${w} × ${h}`;
}

function handleExport() {
  if (!sourceImage || posterCanvas.width === 0) return;

  posterCanvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `poster-${state.brandPreset}-${state.algorithm}.png`;
    a.click();
    URL.revokeObjectURL(url);
  }, 'image/png');
}

function wireControls() {
  brandPresetSelect.addEventListener('change', () => {
    state.brandPreset = brandPresetSelect.value;
    if (state.brandPreset !== 'custom') {
      applyBrandPreset(state.brandPreset);
    }
    scheduleRender();
  });

  inkColorInput.addEventListener('input', () => {
    state.inkHex = inkColorInput.value;
    state.brandPreset = 'custom';
    brandPresetSelect.value = 'custom';
    scheduleRender();
  });

  groundColorInput.addEventListener('input', () => {
    state.groundHex = groundColorInput.value;
    state.brandPreset = 'custom';
    brandPresetSelect.value = 'custom';
    scheduleRender();
  });

  algorithmSelect.addEventListener('change', () => {
    state.algorithm = algorithmSelect.value;
    updateStrengthEnabled();
    scheduleRender();
  });

  contrastInput.addEventListener('input', () => {
    state.contrast = parseFloat(contrastInput.value);
    contrastOut.textContent = state.contrast.toFixed(2);
    scheduleRender();
  });

  pixelScaleInput.addEventListener('input', () => {
    state.pixelScale = parseInt(pixelScaleInput.value, 10);
    pixelScaleOut.textContent = String(state.pixelScale);
    scheduleRender();
  });

  strengthInput.addEventListener('input', () => {
    state.strength = parseFloat(strengthInput.value);
    strengthOut.textContent = state.strength.toFixed(2);
    scheduleRender();
  });

  showOverlayInput.addEventListener('change', () => {
    state.showOverlay = showOverlayInput.checked;
    updateOverlayEnabled();
    scheduleRender();
  });

  headlineTextInput.addEventListener('input', () => {
    state.headlineText = headlineTextInput.value;
    scheduleRender();
  });

  showMeterInput.addEventListener('change', () => {
    state.showMeter = showMeterInput.checked;
    scheduleRender();
  });

  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    revokeObjectUrl();
    objectUrl = URL.createObjectURL(file);
    loadImageFromUrl(objectUrl, file.name);
  });

  exportBtn.addEventListener('click', handleExport);
}

function verifyPaletteSanity() {
  const built = twoTone('#0a0a0a', '#d6ff00');
  const ref = PALETTES.loudNeon;
  const ok = built.every((c, i) =>
    c.every((v, j) => v === ref[i][j]),
  );
  if (!ok) {
    console.warn('twoTone loudNeon sanity check failed', built, ref);
  }
}

populateAlgorithmSelect();
wireControls();
updateStrengthEnabled();
updateOverlayEnabled();
verifyPaletteSanity();
loadDefaultSample();

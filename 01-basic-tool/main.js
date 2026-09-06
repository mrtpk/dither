import { dither, ALGORITHMS, pixelateSource } from '../shared/dither.js';
import { PALETTES } from '../shared/palettes.js';

const ALGORITHM_LABELS = {
  'floyd-steinberg': 'Floyd–Steinberg',
  atkinson: 'Atkinson',
  'jarvis-judice-ninke': 'Jarvis–Judice–Ninke',
  bayer2: 'Bayer 2×2',
  bayer4: 'Bayer 4×4',
  bayer8: 'Bayer 8×8',
  threshold: 'Threshold',
};

const PALETTE_LABELS = {
  bw: 'Black & White',
  inkOnWhite: 'Ink on White',
  gameboy: 'Game Boy',
  loudNeon: 'Loud Neon',
  loudRed: 'Loud Red',
  cyanMagenta: 'Cyan / Magenta',
  riso: 'Riso',
  amber: 'Amber',
  cmyk: 'CMYK',
};

const BAYER_ALGORITHMS = new Set(['bayer2', 'bayer4', 'bayer8']);

const state = {
  algorithm: 'floyd-steinberg',
  paletteKey: 'bw',
  contrast: 1,
  brightness: 0,
  pixelScale: 1,
  strength: 1,
  invert: false,
};

let sourceImage = null;
let objectUrl = null;
let pendingFrame = null;

const workCanvas = document.getElementById('workCanvas');
const workCtx = workCanvas.getContext('2d', { willReadFrequently: true });
const displayCanvas = document.getElementById('displayCanvas');
const displayCtx = displayCanvas.getContext('2d');

const algorithmSelect = document.getElementById('algorithm');
const paletteSelect = document.getElementById('palette');
const contrastInput = document.getElementById('contrast');
const contrastOut = document.getElementById('contrastOut');
const brightnessInput = document.getElementById('brightness');
const brightnessOut = document.getElementById('brightnessOut');
const pixelScaleInput = document.getElementById('pixelScale');
const pixelScaleOut = document.getElementById('pixelScaleOut');
const strengthInput = document.getElementById('strength');
const strengthOut = document.getElementById('strengthOut');
const strengthLabel = document.getElementById('strengthLabel');
const invertInput = document.getElementById('invert');
const fileInput = document.getElementById('fileInput');
const fileNameEl = document.getElementById('fileName');
const downloadBtn = document.getElementById('downloadBtn');
const sizeReadout = document.getElementById('sizeReadout');

function populateSelects() {
  for (const algo of ALGORITHMS) {
    const opt = document.createElement('option');
    opt.value = algo;
    opt.textContent = ALGORITHM_LABELS[algo] ?? algo;
    algorithmSelect.appendChild(opt);
  }

  for (const key of Object.keys(PALETTES)) {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = PALETTE_LABELS[key] ?? key;
    paletteSelect.appendChild(opt);
  }
}

function updateStrengthEnabled() {
  const enabled = BAYER_ALGORITHMS.has(state.algorithm);
  strengthInput.disabled = !enabled;
  strengthLabel.classList.toggle('disabled', !enabled);
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

  if (state.invert) {
    const px = working.data;
    for (let i = 0; i < px.length; i += 4) {
      px[i] = 255 - px[i];
      px[i + 1] = 255 - px[i + 1];
      px[i + 2] = 255 - px[i + 2];
    }
  }

  dither(working, {
    algorithm: state.algorithm,
    palette: PALETTES[state.paletteKey],
    contrast: state.contrast,
    brightness: state.brightness,
    grayscale: true,
    strength: state.strength,
  });

  workCanvas.width = w;
  workCanvas.height = h;
  workCtx.putImageData(working, 0, 0);

  const displayPixelSize = blockSize;
  displayCanvas.width = w * displayPixelSize;
  displayCanvas.height = h * displayPixelSize;
  displayCtx.imageSmoothingEnabled = false;
  displayCtx.drawImage(
    workCanvas,
    0,
    0,
    displayCanvas.width,
    displayCanvas.height,
  );

  sizeReadout.textContent = `${srcW} × ${srcH} → ${w} × ${h}`;
}

function handleDownload() {
  if (!sourceImage || workCanvas.width === 0) return;

  workCanvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dither-${state.algorithm}-${state.paletteKey}.png`;
    a.click();
    URL.revokeObjectURL(url);
  }, 'image/png');
}

function wireControls() {
  algorithmSelect.addEventListener('change', () => {
    state.algorithm = algorithmSelect.value;
    updateStrengthEnabled();
    scheduleRender();
  });

  paletteSelect.addEventListener('change', () => {
    state.paletteKey = paletteSelect.value;
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

  invertInput.addEventListener('change', () => {
    state.invert = invertInput.checked;
    scheduleRender();
  });

  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    revokeObjectUrl();
    objectUrl = URL.createObjectURL(file);
    loadImageFromUrl(objectUrl, file.name);
  });

  downloadBtn.addEventListener('click', handleDownload);
}

populateSelects();
wireControls();
updateStrengthEnabled();
loadDefaultSample();

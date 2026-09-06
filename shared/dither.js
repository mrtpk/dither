// shared/dither.js
// Reusable, dependency-free dithering engine for all browser use cases.
// Exposes ordered (Bayer), error-diffusion (Floyd-Steinberg, Atkinson),
// palette snapping, and simple pre-processing (grayscale/contrast/scale).
//
// Usage (ES module):
//   import { dither, ALGORITHMS, toGrayscale, applyContrast } from '../shared/dither.js';
//   dither(imageData, { algorithm: 'floyd-steinberg', palette: [[0,0,0],[255,255,255]] });

// ---- Bayer / ordered matrices (normalized to 0..1 thresholds) ----------------

function bayerMatrix(n) {
  // Recursively build a 2^k x 2^k Bayer matrix.
  if (n === 2) return [[0, 2], [3, 1]];
  const prev = bayerMatrix(n / 2);
  const size = n;
  const half = n / 2;
  const m = Array.from({ length: size }, () => new Array(size).fill(0));
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

function normalizedBayer(n) {
  const m = bayerMatrix(n);
  const denom = n * n;
  return m.map((row) => row.map((v) => (v + 0.5) / denom));
}

export const BAYER = {
  2: normalizedBayer(2),
  4: normalizedBayer(4),
  8: normalizedBayer(8),
};

// ---- Color helpers -----------------------------------------------------------

export function luminance(r, g, b) {
  return r * 0.299 + g * 0.587 + b * 0.114;
}

export function toGrayscale(imageData) {
  const px = imageData.data;
  for (let i = 0; i < px.length; i += 4) {
    const v = luminance(px[i], px[i + 1], px[i + 2]);
    px[i] = px[i + 1] = px[i + 2] = v;
  }
  return imageData;
}

// brightness in [-255,255], contrast as a multiplier (1 = unchanged)
export function applyContrast(imageData, contrast = 1, brightness = 0) {
  const px = imageData.data;
  for (let i = 0; i < px.length; i += 4) {
    for (let c = 0; c < 3; c++) {
      let v = (px[i + c] - 128) * contrast + 128 + brightness;
      px[i + c] = v < 0 ? 0 : v > 255 ? 255 : v;
    }
  }
  return imageData;
}

function nearestColor(palette, r, g, b) {
  let best = palette[0];
  let bestD = Infinity;
  for (let k = 0; k < palette.length; k++) {
    const c = palette[k];
    const dr = r - c[0];
    const dg = g - c[1];
    const db = b - c[2];
    const d = dr * dr + dg * dg + db * db;
    if (d < bestD) { bestD = d; best = c; }
  }
  return best;
}

const BW = [[0, 0, 0], [255, 255, 255]];

// ---- Error-diffusion kernels -------------------------------------------------
// Each entry: [dx, dy, weight]; weights are divided by `divisor`.
const KERNELS = {
  'floyd-steinberg': {
    divisor: 16,
    points: [[1, 0, 7], [-1, 1, 3], [0, 1, 5], [1, 1, 1]],
  },
  atkinson: {
    divisor: 8,
    points: [[1, 0, 1], [2, 0, 1], [-1, 1, 1], [0, 1, 1], [1, 1, 1], [0, 2, 1]],
  },
  'jarvis-judice-ninke': {
    divisor: 48,
    points: [
      [1, 0, 7], [2, 0, 5],
      [-2, 1, 3], [-1, 1, 5], [0, 1, 7], [1, 1, 5], [2, 1, 3],
      [-2, 2, 1], [-1, 2, 3], [0, 2, 5], [1, 2, 3], [2, 2, 1],
    ],
  },
};

function ditherOrdered(imageData, w, h, palette, matrix, strength) {
  const px = imageData.data;
  const n = matrix.length;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      // threshold shifts the value before palette snap; scaled by strength
      const t = (matrix[y % n][x % n] - 0.5) * 255 * strength;
      const c = nearestColor(palette, px[i] + t, px[i + 1] + t, px[i + 2] + t);
      px[i] = c[0]; px[i + 1] = c[1]; px[i + 2] = c[2];
    }
  }
  return imageData;
}

function ditherErrorDiffusion(imageData, w, h, palette, kernel) {
  const px = imageData.data;
  // Work in float per channel to accumulate error.
  const buf = new Float32Array(w * h * 3);
  for (let i = 0, j = 0; i < px.length; i += 4, j += 3) {
    buf[j] = px[i]; buf[j + 1] = px[i + 1]; buf[j + 2] = px[i + 2];
  }
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const bi = (y * w + x) * 3;
      const old = [buf[bi], buf[bi + 1], buf[bi + 2]];
      const c = nearestColor(palette, old[0], old[1], old[2]);
      const err = [old[0] - c[0], old[1] - c[1], old[2] - c[2]];
      buf[bi] = c[0]; buf[bi + 1] = c[1]; buf[bi + 2] = c[2];
      for (const [dx, dy, wgt] of kernel.points) {
        const nx = x + dx;
        const ny = y + dy;
        if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
        const ni = (ny * w + nx) * 3;
        const f = wgt / kernel.divisor;
        buf[ni] += err[0] * f;
        buf[ni + 1] += err[1] * f;
        buf[ni + 2] += err[2] * f;
      }
    }
  }
  for (let i = 0, j = 0; i < px.length; i += 4, j += 3) {
    px[i] = buf[j]; px[i + 1] = buf[j + 1]; px[i + 2] = buf[j + 2];
  }
  return imageData;
}

export const ALGORITHMS = [
  'floyd-steinberg',
  'atkinson',
  'jarvis-judice-ninke',
  'bayer2',
  'bayer4',
  'bayer8',
  'threshold',
];

// Main entry point. Mutates imageData in place and returns it.
// opts: { algorithm, palette, contrast, brightness, grayscale, strength }
export function dither(imageData, opts = {}) {
  const {
    algorithm = 'floyd-steinberg',
    palette = BW,
    contrast = 1,
    brightness = 0,
    grayscale = true,
    strength = 1,
  } = opts;

  const w = imageData.width;
  const h = imageData.height;

  if (contrast !== 1 || brightness !== 0) applyContrast(imageData, contrast, brightness);
  if (grayscale) toGrayscale(imageData);

  if (algorithm.startsWith('bayer')) {
    const n = parseInt(algorithm.slice(5), 10) || 4;
    return ditherOrdered(imageData, w, h, palette, BAYER[n] || BAYER[4], strength);
  }
  if (algorithm === 'threshold') {
    return ditherOrdered(imageData, w, h, palette, [[0.5]], 0);
  }
  const kernel = KERNELS[algorithm] || KERNELS['floyd-steinberg'];
  return ditherErrorDiffusion(imageData, w, h, palette, kernel);
}

// Downscale an ImageBitmap/HTMLImage to a target max dimension using an
// offscreen canvas; returns { canvas, ctx } for chunky-pixel workflows.
export function pixelateSource(source, srcW, srcH, blockSize = 1) {
  const w = Math.max(1, Math.round(srcW / blockSize));
  const h = Math.max(1, Math.round(srcH / blockSize));
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(source, 0, 0, w, h);
  return { canvas: c, ctx, width: w, height: h };
}

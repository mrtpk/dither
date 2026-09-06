// shared/palettes.js
// Named palettes reused across browser use cases. Each palette is an array of
// [r, g, b] triplets. Two-tone palettes are the basis for the "brand" look.

export const PALETTES = {
  bw: [[0, 0, 0], [255, 255, 255]],
  inkOnWhite: [[17, 17, 17], [245, 245, 245]],
  gameboy: [
    [15, 56, 15],
    [48, 98, 48],
    [139, 172, 15],
    [155, 188, 15],
  ],
  // "Loudest Night" style two-tone brand pairs (ink, ground)
  loudNeon: [[10, 10, 10], [214, 255, 0]], // black ink, acid-green ground
  loudRed: [[245, 240, 235], [220, 30, 40]], // paper ink, loud red ground
  cyanMagenta: [[8, 8, 20], [0, 230, 255]],
  riso: [[30, 30, 120], [255, 70, 130]], // riso blue + fluorescent pink
  amber: [[20, 12, 0], [255, 176, 0]],
  cmyk: [
    [0, 0, 0],
    [0, 174, 239],
    [236, 0, 140],
    [255, 242, 0],
    [255, 255, 255],
  ],
};

// Build a two-tone palette from two hex strings, e.g. twoTone('#0a0a0a','#d6ff00')
export function twoTone(inkHex, groundHex) {
  return [hexToRgb(inkHex), hexToRgb(groundHex)];
}

export function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const s = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const n = parseInt(s, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

# How It Works

This tool reproduces **amplitude-modulated (AM) halftone** — the look of newspaper photos, comic-book screens, and risograph duotones. Tone is not chosen per pixel. A regular lattice of ink dots is laid down, and **dot size** carries the gray value. Darker regions get larger spots of a single ink; highlights shrink to pinpoints of paper.

## Dot-area tone reproduction

The eye does not resolve each spot at reading distance. It averages the **ink area** inside a cell against the paper around it. Coverage is the ink fraction of that cell: 0 is empty paper, 1 is a solid patch of ink.

Because perceived darkness tracks **area**, linear sizes must grow with the square root of coverage. A disk whose radius scaled linearly with coverage would have area growing as coverage squared, crushing midtones into a thin band of tiny dots. With radius proportional to the square root of coverage, area stays proportional to coverage, and midtones read honestly.

The largest radius is half the cell diagonal. At full coverage the disk reaches the four corners of its cell and slightly overlaps its orthogonal neighbors, so 100% ink is a continuous field with no paper holes left at the corners. Highlights are the opposite: a few percent coverage becomes a pinpoint on open paper.

Squares follow the same area rule — side length scales with the square root of coverage, and a full cell tiles the lattice. Line screens use a full-width bar whose **thickness** scales linearly with coverage; for a bar that already spans the cell, thickness times cell width is already area.

## Why screens rotate

Two identical (or very similar) grids superimposed at a small angle difference produce **moiré**: a slow beat frequency that looks like stripes or blotches across the page. The beat period is long when the angle gap is small, so the artifact is large and ugly.

Printers rotate each ink’s screen so the strong plates sit about 30° apart. Interference is still there, but its spatial frequency is high. Instead of stripes you get a tight **rosette** — a small flower of overlapping dots that the eye accepts as texture rather than a pattern error. Yellow is the exception: it is the weakest, lightest ink, so it can sit at a less “safe” angle without the moiré being obvious.

A single-ink duotone has no second grid to beat against, so the screen angle is a stylistic choice. 45° is the newspaper default for black: the diagonal is the least noticeable orientation for a regular lattice on a rectangular page.

## CMYK separation

Process color is subtractive. Cyan ink absorbs red, magenta absorbs green, yellow absorbs blue. From a working RGB triple the complementary coverages are therefore one minus each channel: cyan from red, magenta from green, yellow from blue.

Where all three process inks would stack, the result is a muddy brown-black that wastes ink and never quite reaches a clean dark. **Undercolor removal** pulls that common amount out as a dedicated black plate: black is the minimum of the three complementary values, and each of cyan, magenta, and yellow is reduced by that same amount. Shadows then print with opaque black instead of three translucent inks. This tool uses full removal — every shared unit becomes black, with no leftover undercolor in the chromatic plates.

Each plate is a coverage field of its own. The cyan screen samples only cyan, the magenta screen only magenta, and so on. There is no shared gray driving every plate; a red region has high magenta and yellow and almost no cyan or black.

## Subtractive / multiply compositing

On a press, translucent inks **overprint**. Light that survives the first ink is filtered again by the second. Overlaps darken and hue-shift: cyan plus yellow reads green, cyan plus magenta reads blue, magenta plus yellow reads red. All three plus black collapse toward a dark neutral.

On a white digital sheet, **multiply** is the analogue. Each plate is an opaque ink drawing on white; multiplying those plates together darkens where dots overlap, just as overprinting would. Multiplying a transparent plate through alpha would be wrong — the white backing is what makes multiply behave like ink on paper. Because multiply is commutative, the draw order of the four plates does not change the final color; cyan, then magenta, then yellow, then black is only convention.

## Angle choices

The classic process set is yellow at 0°, cyan at 15°, black at 45°, and magenta at 75°.

Black is the strongest, most visible ink, so it sits on the 45° diagonal. Cyan and magenta sit 30° away from black (and 60° from each other), which is the spacing that produces a stable rosette instead of low-frequency moiré. Yellow, least visible, takes the leftover 0° axis — 15° from cyan — where any residual beat is hard to see.

Duotone ignores that set and uses a single user-chosen angle, typically 45°, because there is only one lattice.

## Halftone vs dithering

Both families fake continuous tone with few inks, but they decide different things.

**Dithering** picks **which discrete color** each pixel or cell receives. Ordered Bayer matrices and error-diffusion walks (Floyd–Steinberg, Atkinson) snap to a palette; midtones become a spatial mix of those fixed swatches. The cell never changes size. The algorithm chooses membership.

**AM halftone** keeps **one ink per plate** and varies **dot radius** (or bar thickness) on a rotated regular grid. Coverage becomes area. There is no per-pixel palette snap and no error to diffuse. The newspaper / comic / Riso look comes from that analog growth of spots, not from a threshold matrix deciding ink versus paper at each pixel.

This tool does the latter: Canvas draws disks, squares, or bars whose size follows coverage. It is not a ditherer with a circular brush.

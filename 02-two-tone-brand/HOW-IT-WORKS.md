# How It Works

This tool turns photographs into bold two-ink poster art — the kind of high-contrast, screenprinted look associated with event flyers and risograph prints. Every pixel ends up as either **ink** or **ground**, your two brand colors, while still suggesting shadows, highlights, and texture from the original photo.

## Two-tone quantization

The active palette is always exactly two colors: ink and ground. Before any dithering, each pixel is converted to grayscale and its contrast is pushed (often well above neutral) so midtones separate into distinct light and dark regions. The engine then snaps each pixel to whichever of the two palette entries is nearest in RGB space — measured as squared distance across red, green, and blue.

Because snapping happens on grayscale values, **luminance drives the split**: darker tones tend toward the darker swatch, brighter tones toward the lighter one. In typical presets (acid green on black, amber on deep brown, riso blue on pink) ink is the darker color and ground the brighter, so shadows read as ink and highlights as ground — classic poster logic.

Some presets deliberately invert that relationship. Loud Red uses paper-bright ink on a saturated red ground; the red is actually darker in luminance than the paper tone, so shadow areas snap toward red while highlights snap toward the light ink — a “red field with light type” screenprint read rather than black-on-color.

At equal luminance the choice can be influenced by subtle chromatic differences, but presets are chosen so ink and ground differ enough in brightness for predictable results. To flip dark/light assignment without a dedicated invert control, swap the ink and ground pickers or choose a preset designed with inverted luminance.

## Error diffusion with two colors

When using Floyd–Steinberg, Atkinson, or Jarvis–Judice–Ninke, the engine does not simply threshold each pixel in isolation. After snapping to ink or ground, it computes the **quantization error** — how far the original gray value was from the chosen swatch — and distributes that error to neighboring pixels that have not yet been processed.

Those carried errors push nearby pixels toward the opposite color on the next pass. A 50% gray region cannot exist as a flat mid-gray on a two-color palette; instead it becomes a spatial pattern of ink and ground dots that the eye averages into a smooth tone. With only two inks the patterns are coarse and graphic, which suits poster aesthetics.

## Ordered Bayer and high contrast

Bayer dithering tiles a repeating threshold matrix across the image. Each cell holds a value between 0 and 1; before palette snap, the pixel’s brightness is shifted by a threshold derived from its position in the matrix. The result is a regular grid or dot-screen texture — orderly rather than the organic speckle of error diffusion.

Cranking **contrast** before Bayer pushes values toward extremes: midtones collapse toward black or white in the internal gray representation, so the two-tone snap produces bold, high-contrast cells with little muddy in-between. Combined with Bayer’s regular threshold grid, the output reads as a **screenprint halftone** — chunky, mechanical, and poster-loud. The **strength** control scales how aggressively the Bayer matrix shifts each pixel; it only applies to Bayer algorithms.

## Halftone vs dither (conceptually)

Traditional **halftone** printing simulates continuous tone by varying **dot size or spacing** within a single ink — bigger dots look darker, smaller dots look lighter. **Dithering**, in this tool, means choosing **which discrete color** each cell gets, sometimes spreading rounding error to neighbors. Both approximate full-tone imagery with few inks, but this workflow uses **two fixed inks and spatial color choice**, not variable dot radius. The visual similarity to halftone comes from the regular Bayer grid and high contrast, not from analog dot growth.

## Chunky pixel scale

Before dithering, the source image is downscaled so each block of source pixels becomes one cell on a smaller grid. Dithering then assigns ink or ground per cell. On screen, that grid is upscaled with nearest-neighbor interpolation — no smoothing — so every decision appears as a visible square block. Larger pixel scale means fewer, bigger cells and a more aggressive screenprint / pixel-poster feel.

## Overlay layer

The headline band and audio-meter bars are ordinary Canvas 2D drawing on top of the dithered bitmap. They use the same ink and ground colors for fills and type but are **not** part of the quantization math — they are design garnish for the composed poster. Export includes them; the hidden dither-only layer used for color analysis does not.

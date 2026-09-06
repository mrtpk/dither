# How It Works

This tool turns a photograph into **ASCII art**: each small region of the source image is replaced by a single text character whose **visual weight** (how much ink it puts on the page) approximates the local brightness of that region.

## Luminance

Human eyes do not weigh red, green, and blue equally. Perceived brightness is computed as a weighted sum of the three channels — roughly 30% red, 59% green, and 11% blue. Each character cell averages that value over every source pixel inside its patch, smoothing fine detail into one tone number between black and white.

## Brightness → glyph quantization

Continuous tone must be reduced to a **small discrete set** of characters. The ramp is ordered from light to dark: a space at the light end, punctuation or block elements in the middle, and dense symbols like `@` or full blocks at the dark end.

A normalized brightness value is mapped to an index with a floor operation. Dark tones land on **high indices** (dense glyphs); bright tones land on **low indices** (space or light punctuation). With only a handful of levels, smooth gradients become visible **bands** — stair-steps in tone. That is expected when quantizing to ten or fewer characters.

## Character aspect-ratio correction

Monospace terminal glyphs are roughly **twice as tall as they are wide**. If you divide the image into square source patches — one patch per character — the row count is too high and the result looks **vertically stretched**.

The fix is to use **fewer rows**: multiply the naive row estimate by one-half (equivalently, each character covers a source patch about twice as tall as it is wide). That matches how glyphs actually sit on screen and restores correct proportions in the final ASCII picture.

## Why glyph density works

In a fixed-width font, `@` and `█` occupy the same cell but cover far more ink than `.` or a space. The eye integrates ink over the cell area — the same principle as halftone **dot area**, except the variable is **which character** is chosen rather than how large a dot is drawn. More ink reads as darker; less ink reads as lighter.

## Contrast, brightness, and invert

Before a tone is snapped to a character, it can be stretched around mid-gray (**contrast**), shifted lighter or darker (**brightness**), or flipped (**invert**). Invert swaps which end of the ramp is used — bright becomes dark and vice versa.

## Relationship to dithering

Full **dithering** (error diffusion or ordered thresholds on a palette) snaps pixels to a fixed set of colors and spreads quantization error to neighbors. This tool does not do that for its main path — it picks one character per cell from a brightness ramp.

Optional **ordered Bayer** dithering adds a small spatial threshold offset to each cell's tone **before** the character is chosen. That breaks up flat bands without increasing the number of glyphs. Turning dither off yields clean, gradient-like ASCII bands; turning it on adds texture similar to newspaper screening at the character level.

## Dual output

The same character grid is rendered two ways. A `<pre>` block holds plain text that can be selected and copied. A canvas redraws the identical grid with `fillText` at a chosen font size and colors, suitable for PNG export. Both views show the same rows and columns; only the presentation medium differs.

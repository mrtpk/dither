# How It Works

A video crossfade mixes two pictures in color space: every pixel becomes a blend of both sources, and the file fills with in-between RGB. A printed or 1-bit look cannot do that. This tool animates a **limited-palette wipe** — each pixel is always one source or the other, never a mix — so the motion feels like dots filling a stencil, not a dissolve in a video editor.

## Ordered threshold field

An ordered-dither matrix is a small grid of ranks, each turned into a threshold strictly between zero and one. Tiling that grid over the frame gives every pixel a fixed number: its place in a repeating, space-filling order. That field is computed once and held still for the whole animation. Nothing is re-rolled, and no noise is added. Stability is the effect: the same cells always turn on first.

## The mask is the timeline

Still ordered dither already compares a pixel’s tone to that threshold. Here the comparison drives **which picture is visible**. A single parameter rises from zero to one across the frames. Wherever the threshold is below that parameter, the destination shows; elsewhere the origin remains.

Because every rank sits strictly inside the open unit interval, the endpoints are clean without extra frames or slop. At zero, nothing has crossed the threshold, so the first still is entirely the origin (the first photograph, or paper). At one, every threshold has been passed, so the last still is entirely the destination (the second photograph, or the finished dithered picture). Midway, roughly a fraction of the ranks have lit — Bayer-ordered growth, not a fade.

## Why Bayer, not random

A random threshold at each pixel — even a frozen noise field — grows as unstructured speckle. If the noise is re-rolled each frame, a cell can appear and vanish. Bayer ranks are a **deterministic, space-filling order**: the same lattice cells always light first, then the next rank, then the next. The wipe reads as a retro dithered dissolve, not film grain.

## Two pictures, or one

**Dissolve** places two already-dithered photographs behind the mask. As the parameter rises, B replaces A cell by cell in Bayer order. It is a wipe, not a blend: each pixel is wholly A or wholly B.

**Materialize** uses the same mask on a single image. The origin is a flat sheet of the palette’s lightest color — paper. The destination is the photograph after Bayer dither on that same palette. The picture “grows in” as the lowest ranks reveal ink. This is not a crossfade between two photos; it is ink filling paper in print order.

## Palette before and after

Sources are quantized once, before the loop, so the wipe reveals already-limited dots rather than re-dithering every frame. Each composed frame is snapped to the same tiny RGB set again so encode and resize cannot sneak in intermediate colors. The motion stays 1-bit (or four-color), and the files stay small.

## GIF versus video

GIF is the natural container: a looping palette, two to four colors, and a frame delay of one over the chosen frame rate. A looped GIF jumps from the last still back to the first unless hold frames are added later.

MP4 and WebM need a video codec and even width and height. Dither noise is almost intra-frame grain, so those codecs compress it poorly compared with a two-color GIF. WebM’s VP9 encoder is often missing from a bundled ffmpeg; MP4 or GIF is the practical fallback. GIF remains the right default for this look.

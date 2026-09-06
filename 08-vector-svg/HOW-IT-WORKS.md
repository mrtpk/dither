# How It Works

A raster dither is locked to its pixel grid. Enlarge it and the squares soften or stair-step; send it to a cutter and there is nothing to cut. Screenprint, vinyl, and plotter paths want **geometry** — rectangles and circles that scale to a tee, a poster, or a four-foot banner without a new rasterization. Separating inks into plates is a print-shop workflow, not a Photoshop layer flatten. That is why this tool writes vector marks instead of embedding a picture.

## Why vector for screenprint

A stencil, a film, or a plotter head follows edges. If those edges are pixels, every reprint at a new size is a new resampling, and ink separations become flattened color. Vector output keeps each ink as its own set of shapes on a shared canvas. The shop can scale the sheet, hold registration across plates, and plot or cut without first turning the design back into a bitmap. Resolution independence is the point: the marks stay crisp at merch size because they were never pixels.

## One-bit dither becomes rectangles

Ordered or error-diffusion dither on a coarse grid assigns each cell ink or paper. Each ink cell is a square in the plane. Adjacent ink cells on a row are the same mark as one wider rectangle — same ink on the stencil, fewer primitives in the file. Multi-color palettes do this independently per ink: a cell belongs to at most one color, and unmatched or paper cells emit nothing.

The grid is chosen coarse on purpose. The *look* is chunky cells, the way a low-resolution screenprint reads from across a room, and the file stays plottable. A solid ink row collapses to a single wide rectangle; a Bayer checkerboard still emits many unit squares, which is expected — the texture *is* the pattern.

## Halftone dots as area

Tone can also be ink **area** inside a cell rather than a palette snap. Coverage is the dark fraction of the cell: shadows want more ink, highlights want less. A disk whose area grows with coverage has a radius that grows with the **square root** of coverage. Linear radius would crush midtones; a radius derived from area-over-pi would fail to fill the cell corners at full coverage.

Full coverage uses a radius that reaches the cell corners — half the cell diagonal — so neighboring disks overlap just enough that a solid region reads as a continuous field, not a grid of holes. Highlights shrink to pinpoints on paper. Cells with almost no coverage are skipped so the file does not fill with invisible dots.

## Screen angles

Two regular lattices at a small angle difference beat into a low-frequency moiré. A single-ink merch plate still rotates — classically forty-five degrees — so the lattice is less obvious on a rectangular shirt. The photograph stays upright: coverage is sampled in canvas space. Only the *lattice* rotates, as a layer over that field.

A rotated screen that iterates only the rectangle of the sheet leaves empty wedges at the corners. The sample grid is therefore enlarged (over-scanned) to the circumcircle of the sheet plus a one-cell margin, so the rotated field still covers the whole rectangle. Overflow past the canvas is clipped. Multi-plate process work spaces strong inks about thirty degrees apart so the beat becomes a tight rosette instead of a visible stripe.

## Run-length merging and rounding

Vector files grow with primitive count. Merging consecutive same-ink cells on each row into one rectangle, and rounding coordinates to a modest precision, cuts size without changing the marks at print scale. Sharing a fill on a group, rather than repeating the same color on every child, avoids the same attribute thousands of times. Empty paper cells and near-zero dots are never written. The result of a typical coarse grid should stay in the tens to low hundreds of kilobytes, not megabytes.

## Separations

Each ink is its own stencil. A composite preview stacks every ink on a paper rectangle so the merch design can be judged on screen. A shop wants one file per ink, the same registration (identical canvas for every plate), and typically no filled paper rectangle — a cutter or film should see ink marks only, not a stock-sized box that would also be stroked. Corner registration marks are optional insurance when plates must be aligned by hand. The composite is the proof; the plates are what goes on press.

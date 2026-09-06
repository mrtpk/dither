# How the Audio-Reactive Dither Works

*Canada's Loudest Night* takes a single still image and makes it **pump with
sound**. Nothing about the picture changes — what changes, live, is *how it is
dithered*. This document explains the concepts and the math, from microphone (or
oscillator) to the final two-tone pixels. There is no code here — just the ideas.

## 1. The pipeline

```
audio → AnalyserNode → per-frame features → dither uniforms → GLSL Bayer shader → canvas
```

Sound (from a mic, an audio file, or an internal test tone) is fed into a Web
Audio **analyser**. Every animation frame we read a few numbers out of that
analyser — an overall loudness value and three band-energy values — smooth them,
and use them to set the parameters of an ordered-dithering fragment shader. The
shader then re-renders the same image with those parameters, so the dither
visibly reacts to the audio.

## 2. FFT and frequency bins

The analyser runs a **Fast Fourier Transform (FFT)** over a short sliding window
of the incoming waveform. The window length is `fftSize` (here 2048 samples).
An FFT of `fftSize` real samples produces `fftSize / 2` useful magnitude values,
called **bins** (here 1024 bins). Bin *i* corresponds to a specific frequency:

$$ f(i) = i \cdot \frac{\text{sampleRate}}{\text{fftSize}} $$

At a typical 44.1 kHz sample rate with an FFT size of 2048, each bin is about
21.5 Hz wide. Bin 0 is DC (0 Hz); the last usable bin sits just below the
**Nyquist frequency** (half the sample rate), the highest frequency that can be
represented.

## 3. Byte frequency data

The analyser hands back each bin's magnitude as a byte in the range `0..255`.
These are not raw linear amplitudes: they are converted to **decibels** (a
logarithmic scale that matches how we perceive loudness) and then mapped from a
configured dB range onto `0..255`. Louder energy at a given frequency → a bigger
number for that bin.

The analyser also applies its own **temporal smoothing** controlled by
`smoothingTimeConstant` (0..1). Each frame's bin value is blended with the
previous frame's, so the spectrum glides instead of flickering. Note this
smoothing applies only to the *frequency* data, not to the raw waveform.

## 4. RMS and loudness

To get one honest "how loud is it right now" number we look at the **time-domain
waveform** instead of the spectrum. The analyser gives the waveform as bytes
centered on 128 (128 = silence). We shift each sample to the range `-1..+1`,
square it, average over the window, and take the square root:

$$ \text{RMS} = \sqrt{\frac{1}{N} \sum_{k=1}^{N} \left(\frac{s_k - 128}{128}\right)^2 } $$

This is the **root-mean-square** level. Squaring makes every excursion positive
(so loud negative swings count just as much as positive ones) and weights big
peaks more than small ones, which tracks perceived loudness far better than any
single frequency bin. RMS is our master "loudness" feature.

## 5. Band energy: bass, mid, treble

A single spectrum of 1024 bins is too fine-grained to drive a visual directly, so
we collapse it into three musical bands by averaging the bins that fall inside
each frequency range:

- **Bass** ≈ 20–250 Hz (kick, bass line)
- **Mid** ≈ 250–2000 Hz (vocals, most instruments)
- **Treble** ≈ 2000–8000 Hz (cymbals, air, sparkle)

We find each band's bin range by inverting the bin→frequency formula, then take
the **average** (not the sum) of those bins and divide by 255. Averaging keeps
the three numbers on a comparable `0..1` scale regardless of how many bins a band
happens to contain.

## 6. Mapping audio to dither parameters

The three features drive three dither controls:

| Feature | Dither parameter | Effect |
|---------|------------------|--------|
| Loudness (RMS) | grid coarseness (pixel scale + Bayer size) | louder → chunkier, harsher grid |
| Bass | contrast + threshold shift | the kick "pumps" the whole image |
| Treble | ground (highlight) hue | sparkle rotates the two-tone color |

Raw audio features jitter frame-to-frame. To keep the visual musical rather than
twitchy we apply an **exponential smoothing** (a one-pole low-pass / lerp): each
frame the displayed value moves a fraction *k* of the way toward the new reading,
`smoothed += (raw − smoothed) · k`. Small *k* is calm and heavy; large *k* is
snappy. This is on top of the analyser's own frequency smoothing.

## 7. Why ordered dithering for real-time GPU

Dithering approximates a smooth image with very few colors by scattering pixels
so the eye blends them. There are two broad families:

- **Error diffusion** (Floyd–Steinberg and friends) pushes each pixel's
  quantization error onto its *not-yet-processed neighbors*. That makes it
  inherently **sequential** — a pixel depends on the ones before it — which is a
  poor fit for a GPU that wants to shade thousands of pixels in parallel.
- **Ordered (Bayer) dithering** compares each pixel against a fixed threshold
  read from a small repeating matrix. Every pixel's decision is **independent** —
  it depends only on its own brightness and its position in the tile. This is
  *stateless per pixel*, which is exactly what a parallel fragment shader wants.

Because ordered dithering is stateless, we can recompute the entire frame every
refresh with fresh audio-driven parameters, at real-time frame rates, on the GPU.

## 8. Bayer threshold math

The Bayer matrix is built recursively. Starting from the 2×2 base

$$ \begin{bmatrix} 0 & 2 \\ 3 & 1 \end{bmatrix} $$

each larger `n×n` matrix is assembled from four scaled copies of the previous one
(multiply the previous entries by 4 and add a fixed offset per quadrant). The
integer entries `0 … n²−1` are then **normalized** into thresholds in `[0,1)`:

$$ t = \frac{\text{index} + 0.5}{n^2} $$

We store this matrix as a tiny texture (thresholds packed into one channel). In
the shader, each output block picks its threshold by tiling the matrix across the
image with a modulo of the block coordinate. The dither decision is a single
comparison:

$$ \text{pixel} = \begin{cases} \text{ground} & \text{if } luminance \ge t \\ \text{ink} & \text{otherwise} \end{cases} $$

The **threshold shift** driven by bass simply adds a bias to *t* before the
comparison. Nudging every threshold up or down flips a wave of pixels between ink
and ground at once — that's the visible "pump" on each kick.

## 9. Two-tone mapping

The output uses only two colors: a near-black **ink** and a bright **ground**.
The single threshold comparison above chooses between them, so the image is
rendered as a field of two-tone ordered-dither dots. Treble energy rotates the
**hue** of the ground color (converting an HSL hue back to RGB) while keeping the
ink fixed, so bright, airy passages shift the highlight color while the overall
two-tone, high-contrast poster look stays intact.

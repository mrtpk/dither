# 07 — Audio-Reactive Dither (*Canada's Loudest Night*)

A still image (`../data/samples/03a.png`) is Bayer-dithered in real time by a
WebGL fragment shader, and the dither parameters are driven live by **WebAudio**
analysis. The picture visibly *pumps* with the sound: loudness coarsens the grid,
bass pumps contrast, and treble shifts the highlight color. A small VU/spectrum
overlay shows the analysis.

See [`HOW-IT-WORKS.md`](./HOW-IT-WORKS.md) for the concepts and math.

## Run

Serve from the **repo root** so `../data/samples/03a.png` resolves:

```bash
.venv/bin/python -m http.server 8000
```

Then open one of the three ways to drive it:

- **Microphone** — `http://localhost:8000/07-audio-reactive/`
  Click **▶ Start Audio**, then **🎤 Use Mic** and allow the permission. The
  visual reacts to the room. (The mic is analysed silently — it is never routed
  to the speakers, so there's no feedback.)
- **Audio file** — `http://localhost:8000/07-audio-reactive/`
  Click **▶ Start Audio**, then **📂 Load file** and pick any audio file. The
  track plays through your speakers and drives the dither.
- **Test tone** — `http://localhost:8000/07-audio-reactive/?src=tone`
  Internal oscillators + a low-frequency oscillator (LFO). **No mic or file
  needed** — the audio auto-resumes and is deterministic. This is the path the
  headless smoke test uses.

### Start Audio button / autoplay

Browsers start an `AudioContext` **suspended** until a user gesture. The
**▶ Start Audio** button calls `audioContext.resume()`. In `?src=tone` mode the
context also auto-resumes on load (and retries on first click / tab focus), so
the tone path needs no interaction.

## Controls

| Control | What it does |
|---------|--------------|
| ▶ Start Audio | Resumes the audio context (autoplay policy). |
| 🎤 Use Mic | Uses your microphone as the source. |
| 📂 Load file | Picks an audio file to play and analyse. |
| Sensitivity | Multiplies the mapped feature magnitudes (0.5–3.0). |
| VU / band overlay | Top bar = loudness (RMS); three bars = bass / mid / treble. |

## What reacts to what

| Audio feature | Dither response |
|---------------|-----------------|
| **Loudness (RMS)** | Grid **coarseness** — louder = chunkier pixel blocks and a coarser Bayer grid. |
| **Bass** | **Contrast + threshold shift** — the kick "pumps" the whole image. |
| **Treble** | **Ground hue** — bright/airy content rotates the highlight color. |

> Note: with the `?src=tone` test signal (220/330 Hz), most energy is in bass/mid,
> so loudness and bass responses dominate; treble/hue barely moves — that's
> expected for a low-frequency tone.

Press `Ctrl+C` in the terminal to stop the server.

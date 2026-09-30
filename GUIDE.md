# AI Music Studio – Composition Guide

You compose a song as a JSON object and render it with `render_song` (MCP) or
`python -m studio render song.json` (CLI). Sound comes from **high-quality sampled instruments**
(`sfz:*`: real recorded pianos, drums, DI guitars through real amp captures, a full orchestra),
built-in synths, basic General MIDI sounds, or VST3 plugins. Every song is automatically mixed and
mastered (auto EQ, reverb bus, loudness normalization).

**Always prefer `sfz:` instruments.** Use GM names only for sounds with no `sfz:` equivalent
(vibraphone, organ, choir, music box, sitar...).

## 1. Song format

```json
{
  "title": "Night Drive",
  "bpm": 90,
  "time_signature": [4, 4],
  "swing": 0.15,                  // optional, 0-0.5, delays off-beat 16ths (hip-hop/jazz feel)
  "swing_unit": 0.25,             // 0.25 = 16th swing, 0.5 = 8th swing
  "reverb": {"type": "room"},     // shared reverb bus: room | plate | hall | cathedral (+ "level")
  "loudness": "streaming",        // streaming (-14 LUFS) | loud (-9) | club (-8) | dynamic (-18) | cinematic (-20)
  "tracks": [ ...tracks... ]
}
```

Time is in **beats** (quarter notes). In 4/4 a bar = 4 beats. `bar` numbers start at 0.

### Track

```json
{
  "name": "Keys",                         // unique
  "instrument": "sfz:rhodes",             // sfz:<name>, "synth:<type>", a GM name/number, or "drums" (+ "kit")
  "amp": "rock",                          // amp rig for guitars/basses (see section 3); false = no amp
  "volume": 0.8,                          // linear, ~0.3-1.2
  "pan": -0.3,                            // -1 left .. 1 right
  "transpose": 0,
  "humanize": {"timing_ms": 10, "velocity": 8},   // makes it sound played by a human
  "strum_ms": 12,                         // spreads chord notes low->high like a strummed guitar
  "double_track": false,                  // render twice, hard L/R (huge rock/metal guitar sound)
  "reverb_send": 0.2,                     // amount sent to the song's reverb bus
  "effects": [{"type": "compressor", "threshold_db": -18}],
  "duck": {"source": "Drums", "notes": ["kick"], "depth": 0.7, "release_beats": 0.5},  // sidechain pump
  "sustain": [[0, 3.9], [4, 7.9]],        // sustain pedal down/up (beats) - piano
  "cc": {"1": [[0, 0], [16, 127]]},       // MIDI CC curves (beat, value) for instruments that use them
  "automation": {"volume": [[0, 0.5], [32, 1.0]], "pan": [[0, -1], [16, 1]], "filter": [[0, 400], [32, 12000]]},
  "clips": [ ...clips... ],
  "role": "keys",                         // optional; auto-detected (drums bass guitar keys strings brass...)
  "mute": false, "solo": false
}
```

### Clip (a reusable chunk of music placed at a bar, optionally repeated)

```json
{"bar": 0, "repeat": 4, "length_bars": 1, "notes": [...], "pattern": {...}, "step": 0.25,
 "chords": [...], "every": 4, "oct": 3, "transpose": 0, "vel_scale": 1.0, "beat": 0}
```

- `length_bars` is the loop length for `repeat` (auto = rounded up to whole bars). `beat` offsets the clip.
- A clip can contain any combination of `notes`, `pattern`, `chords`.
- Notes/patterns can also sit directly on the track (treated as a clip at bar 0).

**Notes** – `t` start beat within the clip, `d` duration in beats, `v` velocity 1-127:
```json
{"p": "C4", "t": 0, "d": 1, "v": 90}
{"p": ["E2", "B2", "E3"], "t": 0, "d": 0.5}          // several pitches at once
{"chord": "Am7", "oct": 3, "t": 0, "d": 4, "v": 70}  // chord name, root in octave 3
{"p": "kick", "t": 0}                                 // drum name
```
Pitch: `"C4"` = middle C = 60, `"F#2"`, `"Bb3"`, or MIDI number.
Chords: `C Cm C5 Cdim Caug Csus2 Csus4 C6 Cm6 C7 Cmaj7 Cm7 Cm7b5 Cdim7 C9 Cmaj9 Cm9 Cadd9 C11 C13 C7sus4 C/E`;
optional `"inv": 1` for inversions. `C5` = power chord (root, 5th, octave).
Velocity matters a lot with sampled instruments: soft notes use different recordings than loud ones.

**Expression** (add to any note):
```json
{"p": "B4", "t": 0, "d": 2, "bend": 1, "bend_at": 0.2, "bend_time": 0.15}  // guitar bend up 1 semitone
{"p": "E5", "t": 0, "d": 3, "vib": 0.3, "vib_rate": 5.5}                    // vibrato (semitones)
{"p": "C#1", "t": 0, "d": 1, "slide_to": "C#2", "slide_time": 0.08}         // 808 glide / slide
```
Bends use the track's pitch wheel, so bend single-note lines (leads), not chords. Sample libraries allow
±2 semitones (set `"bend_range"` on the track if the instrument supports more); synths and GM sounds allow ±12.

**Pattern** – step sequencer, one char per step (`step` beats each, default 0.25 = 16th):
`x` hit (vel 100), `X` accent (127), `o` medium (70), `g` ghost (40), `.` or `-` rest. Spaces/`|` ignored.
```json
"pattern": {
  "kick":   "x... ..x. x... ....",
  "snare":  ".... x... .... x..g",
  "hihat":  "x.x. x.x. x.x. x.xo"
}
```
Pattern keys can be drum names or pitches (e.g. `"E2"` for a chugging guitar/bass line).

**Chords shorthand** – one chord every `every` beats; entries can be objects for voicing:
```json
{"bar": 0, "chords": ["Am", {"chord": "F", "oct": 3, "inv": 1}, "C", "G"], "every": 4, "oct": 3, "v": 75}
```

### Drum names
kick kick2 snare snare2 rim clap hihat hihat_pedal hihat_open crash crash2 ride ride_bell china splash
tom_high tom_himid tom_mid tom_low tom_floor tom_floor2 tambourine cowbell shaker cabasa
conga_high conga_low bongo_high bongo_low timbale_high timbale_low claves woodblock triangle sticks

## 2. Instruments

Use `list_instruments` to search (it shows ranges). High-quality `sfz:` instruments:

| Group | Instruments |
|---|---|
| Drums | `sfz:acoustic_drums` (real kit: rock, metal, pop, boom bap), `sfz:acoustic_drums_full` (roomier), `sfz:808_kit`, `sfz:909_kit`, `sfz:trap_kit` |
| Keys | `sfz:grand_piano`, `sfz:rhodes`, `sfz:upright_piano` |
| Guitar (DI → amp) | `sfz:electric_guitar`, `sfz:electric_guitar_2` (darker), `sfz:electric_guitar_mute` (palm-mute chugs) |
| Bass (DI → amp) | `sfz:bass_guitar`, `sfz:bass_guitar_warm`, `sfz:bass_guitar_mute` |
| Strings | `sfz:violins`, `sfz:violin_solo`, `sfz:violas`, `sfz:cellos`, `sfz:contrabass`, each with `_pizz`, `_spic` (short), `_trem`; `sfz:harp` |
| Brass | `sfz:french_horn` (+`_stac`, `_mute`), `sfz:trumpet` (+`_vib`, `_stac`), `sfz:trombone` (+`_stac`), `sfz:tuba` (+`_stac`) |
| Woodwinds | `sfz:flute`, `sfz:oboe`, `sfz:clarinet`, `sfz:bassoon` (each + `_stac`), `sfz:piccolo` |
| Mallets | `sfz:glockenspiel`, `sfz:marimba`, `sfz:xylophone` |

Stay inside each instrument's range (shown by `list_instruments`). Orchestral sections sound best with
long legato notes and velocity/volume swells. If a library isn't installed the track falls back to a GM
sound and a warning tells you how to install it.

**Built-in synths** – `"instrument": "synth:<type>"`, tweak with `"synth_params"`:
- `808` – booming hip-hop/trap bass with pitch drop; long notes in octave 1-2, use `slide_to` for glides.
- `sub` – clean sine sub bass.  `reese` – detuned gritty bass (DnB/dubstep).
- `supersaw` – huge EDM chords/leads.  `pluck` – short EDM pluck.  `pad` – slow wide pad.  `saw`, `square` – leads.
- params: attack, decay, sustain, release (seconds / 0-1), voices, detune (cents), drive, level.

**GM sounds** (basic quality, 128 instruments + kits): e.g. `"Vibraphone"`, `"Rock Organ"`, `"Choir Aahs"`,
`"Music Box"`; drums: `"instrument": "drums", "kit": "Standard|Room|Power|Electronic|808/909|Jazz|Brush"`.

**VST3 instrument** (advanced) – `"vst3": "C:/Program Files/Common Files/VST3/Vital.vst3"`.

## 3. Guitar & bass amps (real amp captures)

`sfz:` guitars and basses are clean DI recordings played through Neural Amp Modeler captures of real amps
plus a speaker cabinet impulse response. Pick a rig with `"amp"`:

| rig | sound |
|---|---|
| `metal` | EVH 5150 boosted + Mesa 4x12: modern metal |
| `djent` | Peavey 6505+ boosted + tight cab: metalcore/djent |
| `thrash` | Mesa Mark IV + V30: tight thrash/prog |
| `rock` | Marshall JCM900 + Marshall 4x12: hard rock |
| `classic_rock` | Marshall JCM2000 crunch |
| `indie` | Vox AC15 edge-of-breakup |
| `clean` | Fender Twin Reverb clean |
| `bass_grit` | Tech21 dUg preamp + Ampeg 8x10 (rock/metal bass) |
| `bass_clean` | clean bass through a bass cab (default for sfz basses) |

Customize: `"amp": {"preset": "metal", "drive_db": 8, "cab": "v30"}` (amps: 5150 6505 mesa_mark4 jcm900 jcm2000
ac15 twin bass_dug; cabs: mesa_4x12 v30 marshall_4x12 metal_chug bass_svt bass_modern).
Guitars sound huge with `double_track: true`. Use `sfz:electric_guitar_mute` for chugs and fast riffs.

## 4. Effects & mixing

Mixing is automatic: each track gets role-based EQ (high-pass, mud cut), the low end is kept mono, and the
master is compressed, limited and normalized to the `loudness` target. You add character:

- `"reverb"` on the song + `"reverb_send"` per track (sends default by role when the bus is on).
- Per track `"effects"` list, items are presets (string) or objects:

| type | main params |
|---|---|
| distortion | drive_db |
| reverb | room_size 0-1, wet_level, dry_level, damping, width |
| delay | time_beats (tempo-synced) or delay_seconds, feedback, mix |
| chorus / phaser | rate_hz, depth, mix |
| compressor | threshold_db, ratio, attack_ms, release_ms |
| limiter | threshold_db |
| highpass / lowpass | hz |
| eq (peak) | hz, gain_db, q |
| lowshelf / highshelf | hz, gain_db |
| filter (ladder) | cutoff_hz, resonance |
| gain | gain_db |
| bitcrush | bit_depth |
| noisegate / clipping | threshold_db |
| pitchshift | semitones |
| vst3 | path, params |

**Presets:** `drum_bus`, `lofi`, `vinyl_warmth`, `room_reverb`, `hall_reverb`, `edm_lead`, `808_saturation`,
`clean_guitar`, `glue`; legacy amp-simulation presets for GM guitars: `metal_amp`, `rock_amp`, `crunch`, `bass_amp`.
Song-level `"auto_eq": false` or track-level `"auto_eq": false` turns off automatic EQ.

## 5. Genre recipes

### Hip-hop (boom bap / lo-fi) – 80-95 BPM, swing 0.1-0.2, loudness streaming
- Drums: `sfz:acoustic_drums` + `effects: ["drum_bus"]` (dusty: add a lowpass ~9 kHz). Kick on 1 and the "and"
  of 2/3, snare on 2 & 4, 16th/8th hats with ghost notes (`g`, `o`). `humanize` 5-8 ms.
- Keys: `sfz:rhodes` or `sfz:grand_piano`, jazzy 7th & 9th chords (`Am9 Dm9 Gm7 Cmaj7`), `vinyl_warmth` or `lofi`.
- Bass: `sfz:bass_guitar` or `synth:sub`, follows chord roots. Reverb bus `room`.

### Trap – 130-150 BPM (feels half-time), no swing, loudness loud
- `sfz:trap_kit` (or `sfz:808_kit`); snare/clap on beat 3 of each bar; hi-hats in 16ths with 32nd rolls
  (a clip with `"step": 0.125`); open hat accents.
- 808: `synth:808` long notes on roots (octave 1-2) with `slide_to` glides, `808_saturation`; kick with the 808.
- Dark minor melody: `sfz:grand_piano`, `sfz:glockenspiel`, `sfz:violins_pizz`, strings pads (`sfz:violins`).

### Rock – 110-150 BPM, loudness streaming
- Drums: `sfz:acoustic_drums`, 8th hats or ride, kick 1 & 3, snare 2 & 4, crash on section starts, tom fills.
- Guitars: `sfz:electric_guitar` + `"amp": "rock"` (or `classic_rock`), `double_track: true`, power chords
  (`E5 A5 D5`, oct 2-3) in 8ths; verses: clean arpeggios with `"amp": "clean"` + chorus.
- Bass: `sfz:bass_guitar` (`bass_clean` or `bass_grit`), root 8ths locked to kick. Reverb bus `plate`.

### Metal – 90-110 (half-time/breakdown) or 160-220 BPM, loudness loud
- Drums: `sfz:acoustic_drums`, double kick 16ths, snare 2 & 4 (or blast beats), china/crash accents.
- Rhythm: `sfz:electric_guitar_mute` (chugs) and `sfz:electric_guitar` (sustained chords), both with
  `"amp": "metal"` (or `djent`/`thrash`), `double_track: true`, `humanize` 6 ms. Power chords around E2/D2
  (`"E5", "oct": 2`), chromatic riffs (E F F# G), tritones (E–Bb), Phrygian (E F G A B C D).
- Bass: `sfz:bass_guitar` + `"amp": "bass_grit"`, doubling the riff roots an octave down.
- Leads: `sfz:electric_guitar` single notes + `"amp": "metal"`, `vib` on long notes, `bend` for expression, delay.

### Classical / cinematic – 60-120 BPM, no drums, loudness dynamic or cinematic
- Sections: `sfz:violins` (melody), `sfz:violas`, `sfz:cellos`, `sfz:contrabass`, `sfz:french_horn`,
  `sfz:trumpet`, `sfz:trombone`, `sfz:flute`, `sfz:oboe`, `sfz:clarinet`, `sfz:harp`, `sfz:grand_piano`;
  use `_pizz`/`_spic` for rhythmic ostinatos; timpani via GM `"Timpani"`.
- Real voice-leading (melody on top, bass on bottom), long legato notes, dynamics with velocity and
  `automation.volume` swells, `humanize` timing 12-20 ms. Reverb bus `hall`; pan like an orchestra
  (violins left, cellos/basses right).

### EDM – house 122-128, future bass/dubstep 140-150 (half-time), DnB 170-176, loudness loud or club
- Drums: `sfz:909_kit` (house/techno) or `sfz:808_kit`, four-on-the-floor, clap on 2 & 4, open hats on off-beats,
  build-ups: snare rolls getting denser with rising velocity.
- Chords: `synth:supersaw` / `synth:pad`, `duck` on the kick (sidechain pump), reverb bus `plate`.
- Filter sweeps: `"automation": {"filter": [[start_beat, 400], [end_beat, 12000]]}` for intros and builds.
- Bass: `synth:sub` / `synth:reese` also ducked; lead: `synth:pluck`/`synth:saw` with delay, `vib` on long notes.
- Structure: intro 8 · build 8 · drop 16 · break 8 · build 8 · drop 16 · outro 8 bars.

## 6. Vocals (AI singer)

Add a `"vocals"` section to the song, render it, then call `add_vocals` (CLI: `python -m studio vocals <name>`).
The singer is generated by ACE-Step 1.5 on the GPU (a few minutes per take) and mixed over your instrumental.

```json
"vocals": {
  "lyrics": "[intro]\n\n[verse]\nWindows down on a Sunday drive\n...\n[chorus]\nTurn it up, turn it up tonight\n...",
  "style": "male classic rock vocalist, warm slightly raspy voice, upbeat and joyful",
  "language": "en",
  "volume": 1.0,
  "takes": 2
}
```

- **Structure must match the music:** write lyric sections (`[intro]`, `[verse]`, `[pre-chorus]`, `[chorus]`,
  `[bridge]`, `[outro]`) in the same order as the song's musical sections, and give each section enough bars
  (a 4-line verse needs ~8 bars). Leave an instrumental `[intro]` (empty) so the singer doesn't start at bar 0.
- **Singable lyrics:** short lines (6-10 syllables), simple words, rhymes at line ends, a repeated hook in the chorus.
- **Leave room:** keep guitars/keys moderate in sung sections; the vocal needs space in the 1-4 kHz range.
- **style** describes the voice: gender, age, timbre (raspy, breathy, powerful), genre, mood.
- **language**: ISO code (en, es, fr, de, ja, zh, ...). English is the most reliable.
- Takes differ a lot: generate 2-3 (`takes`) and let the user choose. Words are sometimes slurred;
  if a take is off, run again with another `seed`.

## 7. Songwriting checklist
1. Pick key, tempo, genre and a structure (intro / verse / chorus / bridge / outro); 32-96 bars is typical.
2. Write each section as clips and reuse them with `repeat`; change something every 4-8 bars (fills,
   extra layer, drop out drums) so it doesn't loop boringly.
3. Keep bass and kick locked; keep parts in their register (bass low, pads mid, lead high).
4. Humanize acoustic instruments, keep electronic ones tight. Use velocity for dynamics.
5. Balance volumes: drums 0.9, bass 0.8, chords 0.5-0.6, lead 0.7, pads 0.4.
6. Render, check `warnings` and `loudness`; call `play_song` so the user can listen; iterate.
7. Optional: `enhance_song` runs an AI realism pass (ACE-Step) on the finished mix. It keeps the original.

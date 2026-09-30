# 🎸 AI Music Studio

**Let Claude Code, Codex, or any MCP-capable AI produce real music on your own PC.**
Describe a song in plain words; the AI composes it, and the studio performs it on **real recorded
instruments**, plays guitars through **captures of real amplifiers**, adds an **AI singer**, then mixes and
masters it. Everything runs locally: no subscriptions, no uploads, no DAW needed.

> *"Write an upbeat classic-rock song about Sunday drives, with a raspy male singer, and play it."*

The AI writes the song as JSON (like source code for music), so every note is editable, and you get
**MP3 + WAV + MIDI + separate instrument stems** to take into any DAW.

---

## 🎧 Listen

Every track below was composed by an AI agent and rendered 100% locally by this project
(download or open the MP3s in [`demos/`](demos)):

| Demo | What it shows |
|---|---|
| [rock_lucky_ones_ai_vocals.mp3](demos/rock_lucky_ones_ai_vocals.mp3) | classic rock + **AI singer** (lyrics recognized back at 98% accuracy) |
| [rock_lucky_ones_instrumental.mp3](demos/rock_lucky_ones_instrumental.mp3) | the same song before vocals |
| [metal.mp3](demos/metal.mp3) / [metal_ai_enhanced.mp3](demos/metal_ai_enhanced.mp3) | 5150 amp capture, double-tracked guitars, lead bends; before/after the AI realism pass |
| [rock_open_road.mp3](demos/rock_open_road.mp3) | clean-to-crunch Marshall guitars |
| [trap.mp3](demos/trap.mp3) | sliding 808s, trap kit, grand piano, strings |
| [hiphop_boom_bap.mp3](demos/hiphop_boom_bap.mp3) | swung acoustic drums, Rhodes, bass |
| [classical_orchestra.mp3](demos/classical_orchestra.mp3) | strings, flute, horns, harp with crescendos |
| [edm_house.mp3](demos/edm_house.mp3) | 909 kit, supersaws, sidechain pumping, filter sweeps |

## What's inside

| Layer | Details |
|---|---|
| 🎹 **Real instruments** | [sfizz](https://sfz.tools/sfizz) SFZ engine + free libraries: Salamander Grand Piano, 1977 Rhodes, Virtuosity acoustic drums, Karoryfer DI guitars & basses, VSCO 2 orchestra (strings, brass, woodwinds, harp; auto-mapped), synthesized 808 / 909 / trap kits |
| 🔊 **Real amps** | Neural Amp Modeler captures (EVH 5150, Peavey 6505+, Mesa Mark IV, Marshall JCM900/2000, Vox AC15, Fender Twin, dUg bass preamp) + speaker cabinet IRs. Self-contained PyTorch inference, verified bit-exact against the reference implementation |
| 🎤 **AI vocals** | Lyrics → sung vocal over your instrumental with [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) (local GPU), multiple takes **auto-ranked by lyric accuracy** (local speech recognition checks what was actually sung), vocal chain (EQ, compression, delay, plate) |
| 🎻 **Expression** | pitch bends, 808 slides, vibrato, sustain pedal, MIDI CC curves, volume/pan/filter automation, humanize, strum, double-tracked guitars, sidechain ducking |
| 🎚️ **Mix & master** | role-based auto EQ, shared reverb bus, mono low end, glue compression, look-ahead limiter, LUFS loudness targets (streaming −14, loud −9, dynamic −18...) with a true-peak ceiling |
| ✨ **AI realism pass** | optional ACE-Step "cover" re-synthesis that keeps your song's structure |
| 🤖 **Any AI agent** | MCP server (10 tools) + a plain CLI, so it works with Claude Code, Codex, Cursor, or a shell script |

## Quick start (Windows)

Requirements: Windows 10/11, Python 3.11-3.12, git, ~6 GB disk (+ ~20 GB and an NVIDIA GPU with 8 GB+
VRAM for AI vocals / realism pass).

```powershell
git clone https://github.com/perzibel/ai-music-studio.git
cd ai-music-studio
powershell -ExecutionPolicy Bypass -File setup.ps1 -WithAceStep   # omit -WithAceStep for instrumental-only
```

Setup creates a virtual environment, downloads the sound engine, sample libraries, amp models and cabinet
IRs, and registers the MCP server with Claude Code and Codex (if installed).

Then open **a new** Claude Code or Codex session anywhere and ask for a song:

> Make a 1-minute dark trap beat at 140 BPM with sliding 808s and piano, and play it.

> Write a heavy metal song in E minor with a half-time breakdown and a guitar solo with bends.

> Compose a sad cinematic piece for strings, French horn and harp.

> Write a fun classic-rock love song for my wife using these messages: ... Add a male singer.

Give feedback in plain words ("drums louder", "make the chorus bigger") and it re-renders.

## Command line (no AI agent needed)

```powershell
.\.venv\Scripts\python.exe -m studio render examples\rock_vocals.json --play   # instrumental
.\.venv\Scripts\python.exe -m studio vocals lucky_ones --takes 2 --play          # add the AI singer
.\.venv\Scripts\python.exe -m studio enhance iron_tide "heavy metal, live band" --play
.\.venv\Scripts\python.exe -m studio instruments guitar
.\.venv\Scripts\python.exe -m studio library        # list / download sample libraries
.\.venv\Scripts\python.exe -m studio guide          # the full song format
```

Output goes to `output/<song>/`: `mix.mp3/.wav`, `mix_vocals*.mp3`, `mix_enhanced.mp3`, `song.mid`,
`stems/`, `song.json`.

## Examples

`examples/` has one song per genre: `hiphop`, `trap`, `metal`, `rock`, `classical`, `edm`, and
`rock_vocals` (with lyrics for the AI singer). `examples/basic/` has GM-only versions that need no downloads.

## How a song looks

```json
{
  "title": "Lucky Ones", "bpm": 132, "reverb": {"type": "plate"}, "loudness": "streaming",
  "tracks": [
    {"name": "Drums", "instrument": "sfz:acoustic_drums",
     "clips": [{"bar": 0, "repeat": 8, "pattern": {"kick": "x.......x.x.....", "snare": "....x.......x...",
                                                    "hihat": "x.o.x.o.x.o.x.o."}}]},
    {"name": "Guitar", "instrument": "sfz:electric_guitar", "amp": "classic_rock", "double_track": true,
     "clips": [{"bar": 0, "chords": ["A5", "D5", "A5", "E5"], "every": 4, "oct": 2}]}
  ],
  "vocals": {"lyrics": "[verse]\nWindows down on a Sunday drive\n...", "style": "male classic rock vocalist"}
}
```

See [GUIDE.md](GUIDE.md) for the full format (notes, patterns, chords, expression, amps, mixing, genre recipes).

## MCP tools

`get_composition_guide` · `list_instruments` · `list_sound_sources` · `render_song` · `add_vocals` ·
`enhance_song` · `install_library` · `list_songs` · `get_song` · `play_song`

## Project layout

```
studio/          the engine: song parsing, rendering, sfizz bridge, NAM amp inference, mixing,
                 mastering, vocals, ACE-Step bridge, MCP server, CLI
examples/        songs per genre (JSON)
demos/           rendered MP3s
tools/           dev helpers: render all examples, stem levels, lyric check, MCP smoke test,
                 a script that generates a song programmatically
GUIDE.md         the composition guide the AI reads
setup.ps1        one-command install
```

## Limitations

- Windows only for now (setup script, sfizz binary). Mac/Linux support is a planned contribution.
- It sounds like a good home production, not a major-label record; the AI composes "blind" (it can't hear).
- AI vocals vary per take and sometimes slur words; generate a few takes. English is most reliable.
- AI features need an NVIDIA GPU (8 GB works with INT8 quantization; generation takes a few minutes).
- VST3 plugin hosting exists but is untested.

## Credits & licenses

Code: **GPL-3.0** (see [LICENSE](LICENSE); required by Spotify's pedalboard, which is GPL-3.0).

Nothing third-party is bundled; setup downloads it from the original sources:
Salamander Grand Piano (CC-BY, Alexander Holm) · jRhodes3c (Jeff Learman; free to use in music,
CC BY-NC-SA for redistributing the samples) · Virtuosity Drums (CC0, Versilian Studios & Karoryfer) ·
Black And Green Guitars / Black And Blue Basses (CC0, Karoryfer Samples) · VSCO 2 CE (CC0, Versilian
Studios) · GeneralUser GS (S. Christian Collins) · NAM captures from the community
[NAM_models](https://github.com/pelennor2170/NAM_models) collection · cabinet IRs from free packs
collected in [fnpngn/IR](https://github.com/fnpngn/IR) (free to use, not for resale).
Engines: [sfizz](https://github.com/sfztools/sfizz), [tinysoundfont](https://github.com/nwhitehead/pytinysoundfont),
[pedalboard](https://github.com/spotify/pedalboard), [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) (MIT).

Music you make is yours, but check each sample library's license before commercial release, and each
amp capture/IR author's terms before redistributing them.

# Local AI Music Studio App — Design

## Intent and why

The user wants to make music on their own PC without spending Claude/Codex tokens and without opening a chat each time. Today, every song goes through a conversation with an AI assistant that runs scripts by hand. This project builds a local web app in front of the existing `ai-music-studio` engine (ACE-Step 1.5 on the local GPU) and the other local tools already on the machine (Whisper transcription, Ollama LLMs, yt-dlp, ffmpeg), so the user can make and keep working on songs with no AI-assistant session and no recurring cost.

## Goals

- Make a finished song from four starting points without typing commands: an idea, a voice memo, a reference track, or continuing a saved song.
- Keep the two things that matter most as free text — lyrics and instructions — while offering tap-to-assist pickers that write into that text rather than hiding behind separate settings.
- Let the AI write some, all, or none of the lyrics, on a four-level dial.
- Accept a reference as an uploaded file, a link (e.g. YouTube via yt-dlp), or a path already on the user's PC.
- Keep every generated take for a song so the user builds on previous work instead of starting from zero each time.
- Export a finished song as separate instrument tracks (stems) plus MIDI, so it drops into Cubase (or any DAW) as real multitrack material, not just one mixed file.
- Let the user see and edit a song's notes (pitch up/down, timing) per instrument track in a piano-roll editor, then re-render the edited version through the AI.
- Run entirely offline on the user's own hardware (RTX 4060, 8 GB VRAM): no tokens, no recurring cost, no cloud dependency.

## Non-goals

- Not replacing Cubase or any DAW: the app exports to Cubase, it doesn't try to become one.
- Not sheet music or notation display: MIDI piano-roll only.
- Not multi-user or hosted: single local user, single machine.
- Not trying to literally reproduce a named artist's sound (e.g. "Demi Lovato"); style words translate the intent (bright pop, polished female vocals), described honestly as "sounds like," not an impersonation claim.

## Anti-goals (would mean failure even if "technically working")

- Any screen that feels like a form to fill in before something interesting happens. Rejected twice already during this design.
- Hiding core controls behind a multi-step wizard with Back/Next. Explicitly rejected.
- A cluttered, jargon-labeled wireframe-style screen. Explicitly rejected ("too complicated, I don't understand anything").
- A generation step that hangs the whole app with no feedback. This happened for real during manual testing this session: ACE-Step froze for 30+ minutes on this 8 GB GPU without `--offload`. The app must always run generation in the background with visible progress, and must always pass GPU-safe settings for this hardware.

## Constraints

- **Hardware.** Single RTX 4060, 8 GB VRAM, shared with the user's other running desktop apps. ACE-Step must run with `--offload` or it can hang indefinitely — observed directly in this session, not a theoretical risk.
- **No paid or cloud services.** Ollama (already installed: qwen3 8b/14b and others), Whisper via `faster-whisper` (already installed), yt-dlp (already installed), and ffmpeg (already installed) are the only local AI helpers available, and are what back the picker-assist and lyric-help features.
- **ACE-Step 1.5** (already installed under `engines/ACE-Step-1.5`) is the only music-generation engine. Its task types (`text2music`, `cover`, `repaint`, `lego`, `extract`, `complete`) and its 5Hz LM "Simple Mode" (`create_sample`) are the real capabilities this app can call. The design must not invent capabilities ACE-Step doesn't have.
- **Stem separation and MIDI note extraction** need tools not yet confirmed on this machine: either ACE-Step's own `extract`/`lego` tasks, or installing `demucs`, for stems; a note-detection library (e.g. Basic Pitch) for converting audio to MIDI. These need a spike to confirm before the note-editor is built.
- **No dependency on an AI-assistant session.** Generation jobs can run far longer than a 30-minute tool idle timeout (hit directly this session). The app must be its own long-lived local process, not something driven through Claude/Codex tool calls.

## The approved flow and screen

A single persistent "studio" workspace per song. No multi-step wizard: every control for making a song is visible on one screen at once. Visual direction: dark, studio-gear look (near-black panels, one warm-amber accent, monospace for technical labels) — meant to read as "expert tool with an AI co-producer," not a consumer wizard. This was iterated three times in front of the user and approved in this form. A reference HTML sketch of the approved screen is kept at `.superpowers/brainstorm/2095-1793519839/content/studio-v3.html` in this repo.

Top to bottom:

1. **Song header** — song name, a small "AI co-producer ready" badge, and the version/take count for this song.
2. **Start from** (a compact row, not large cards) — An idea / A voice memo / A reference song (file or link) / Load a saved song. Picking one changes what the Reference and Lyrics sections show; it does not open a new wizard page. **Load a saved song** opens a simple "My Songs" list under the song name in the header: scrollable, type-to-filter by name, no separate library screen for now (my call — the simplest thing that still lets the user find a song among many; can grow into a richer browser later if the list gets unwieldy).
3. **Lyrics** section:
   - A free-text box for the actual words.
   - A four-stop "effort bar" above it, in the style of ChatGPT's reasoning-effort selector: **Complete manual** → **AI helps with current lyrics** → **AI creates extra lyrics** → **All AI lyrics**. This decides how much of the Lyrics box the AI may touch or fill when the song is generated.
   - Starting from a voice memo pre-fills this box from a Whisper transcription (as done manually earlier this session), rather than leaving it blank.
4. **Instructions** section:
   - A free-text box: "what do you want to hear" — style, mood, structure, anything about the sound.
   - Tap-to-assist picker rows above the box: **Sound** (genre tiles, each with a 10-second preview rendered once and cached, not regenerated per click), **Voice** (male / female / instrumental), **Feel** (slow / mid / fast). Tapping a tile inserts or updates a short phrase in the Instructions text below, rather than setting a hidden parameter. The text box is what actually gets sent, and stays editable by hand.
5. **Reference** section (optional) — three tabs: upload a file, paste a link (passed to yt-dlp), or browse a path on the user's own PC (a local file picker, no upload needed).
6. **Already made for this song** — every previous take for this song, playable inline, each with "build on this" to continue from that take (via `repaint`/`cover`) instead of generating from scratch.
7. **Output row** — number of takes to generate; a checkbox "Give me separate tracks, ready for Cubase" (exports stems plus MIDI alongside the normal mixed file); a collapsed "More options" for song length, tempo (BPM), and key, for anyone who wants to set them instead of leaving them to the AI.
8. **Bottom bar** — "Open this song's folder" (opens the song's output directory in Explorer) and the main "Make the song" button, always reachable without scrolling past anything required.

## A second screen: the note editor (not yet mocked up)

From the original ask ("divide things into MIDI tracks, up and lower notes, work on a song instead of creating a new one each time"), confirmed again when discussing the Cubase export: once a song (or a stem export) exists, the user can open a **piano-roll editor** per instrument track.

- Each instrument (vocals, drums, bass, keys, guitar, etc., whatever the stem split produced) is its own lane.
- Within a lane, notes show as draggable bars: drag up or down to change pitch, drag the edges to change length or timing, delete, or draw new ones.
- Playback uses the studio's existing sampled instruments (already installed in this project) so edits are heard immediately, without waiting on the AI.
- A "make it sound real again" action re-renders the edited version through ACE-Step (`cover`/`repaint` from the edited MIDI) — the same path already used today for turning a recording into a song.
- Every edit is saved as a new version of the same song (visible in "Already made for this song" and the version indicator in the header), never as a brand-new song, so the user is always continuing, never restarting.

This screen reuses the same dark visual language as the main studio screen. Its exact layout is left to the builder, within the craft floor applied at build time; it has not been mocked up with the user yet.

## How each starting point maps to the engine (resolved)

A design-doc review flagged this as the single biggest scope driver: only `text2music` exists in the codebase today (`studio/generate.py`); the other task types were implied by the flow above but never pinned down. Resolved from what was already proven hands-on this session and from ACE-Step's own documented parameters, read directly from its code during this project:

- **An idea** → `text2music`, already implemented. Instructions text becomes the caption; the Lyrics box, per the effort-bar setting, becomes the lyrics (AI-written, left as typed, or blended by the local LLM at the two middle settings).
- **A voice memo** → the path already used successfully today: Whisper transcribes the memo into the Lyrics box, then `cover` with the memo as `src_audio` turns it into a full song (`audio_cover_strength` ~0.6, as used this session). The memo is a real performance reference, not just a dictation shortcut.
- **A reference song** (file or link) → `cover`, with the reference passed as ACE-Step's own `reference_audio` field (not `src_audio`) and a low `audio_cover_strength` (~0.2), matching ACE-Step's own guidance for style-transfer use. A link is downloaded with yt-dlp first.
- **Load a saved song / "build on this"** → `repaint` for touching up part of an existing take, or `cover` using that take as `src_audio` for a fuller remake; which one depends on whether the user picked a range to redo, decided at build time.

This is new, not-yet-proven engine work beyond the one path already tested (see the next bullet in "What's left to the builder").

## What's left to the builder

- Exact tech stack for the local web app. A small local server plus a browser UI is the natural fit since the whole engine is already Python (e.g. FastAPI/Flask with a plain HTML/JS front end, or an equivalent lightweight setup). No framework is mandated by this conversation. It should start from one Desktop shortcut, matching the existing `AI Music Studio.cmd` pattern.
- Exact mechanism for turning picker taps into Instructions text (append vs. replace vs. smart-merge) — implement the simplest version (append-or-toggle a known phrase) and adjust if it feels wrong in use.
- Which stem-separation tool to install and verify (ACE-Step's own `extract`/`lego` tasks vs. installing `demucs`), and which note-detection tool to install and verify (e.g. Basic Pitch) — unconfirmed on this machine; needs a spike before committing to the full note-editor build.
- **Confirm `cover`, `repaint`, `lego`, `extract`, and `complete` are stable on this 8 GB card before shipping on them.** Only `text2music` has been exercised directly, and it hung for 30+ minutes until `--offload` was found. Each of the other task types needs the same kind of hands-on check (right flags, VRAM headroom) before the voice-memo, reference-track, and "build on this" flows can be trusted — do this before building on top of them, not after.
- Exact wiring from Ollama (qwen3 models already installed) into the Instructions/Lyrics assist levels: which local model, what prompt, and how its output lands in the text boxes.
- Caching strategy for the 10-second genre preview clips and 1-second instrument preview sounds (generate once, store under the project, reuse) so they don't cost GPU time on every page load.
- All detailed visual polish beyond the approved mockup direction (exact spacing, responsive behavior, empty/loading/error states) follows the project's design craft floor at build time.

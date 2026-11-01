# Voice Mode (dictation)

How voice dictation records, when a recording ends on its own, when it submits the prompt without
being asked to, where the audio goes, and what an external process can observe about any of it.

Verified against 2.1.226 (prettified) with every constant, gate and stream parameter below
re-confirmed in the installed 2.1.227 native binary. Style: landmark.

## The two modes

Settings live under the `voice` key: `voice.enabled`, `voice.mode`, `voice.autoSubmit`. Relocate the
schema with `rg -n 'Voice mode settings'`; the enclosing object carries all three, each with a
`.describe()` string:

| Key                 | Values           | Schema description (verbatim, stable anchor)                    |
| ------------------- | ---------------- | --------------------------------------------------------------- |
| `voice.enabled`     | boolean          | —                                                               |
| `voice.mode`        | `hold` \| `tap`  | `'hold' (default): hold to talk. 'tap': tap to start, tap to stop+submit.` |
| `voice.autoSubmit`  | boolean          | `Submit the prompt when hold-to-talk is released (hold mode only)` |

`voice.mode` defaults to `hold` (read as `voice?.mode ?? "hold"`). The activation key is the
`voice:pushToTalk` keybinding; how a hold-and-release is reconstructed from keyboard auto-repeat is
documented in `KEYBOARD_INPUT_DECODING.md`.

There is a third, separate mode in the code — focus mode — which is not the user-facing hold/tap
setting. It has its own shorter silence timeout and its own teardown path, and it flushes each final
transcript immediately rather than accumulating one.

## Self-termination: tap mode ends on its own, hold mode never does

This is the load-bearing finding. In tap mode two timers are armed at tap-to-start, and either one
will finish the recording with no keystroke at all.

Relocate with `rg -n '\[voice\] Toggle'`. Expect two sibling timer-arming functions whose callbacks
log these strings and then call the same finish routine the manual tap calls:

- `[voice] Toggle silence timeout — auto-finishing`
- `[voice] Toggle max-duration cap — auto-finishing`

A third, in focus mode only: `[voice] Focus silence timeout — tearing down session`, plus a
re-arming path logging `[voice] Re-arming focus recording after silence timeout`.

| Timer                  | Value    | Mode  | Armed                | Re-armed on speech?                |
| ---------------------- | -------- | ----- | -------------------- | ---------------------------------- |
| Toggle silence timeout | 15000 ms | tap   | at tap-to-start      | Yes — on every transcript callback |
| Toggle max-duration    | 120000ms | tap   | at tap-to-start      | No — hard cap from the tap         |
| Focus silence timeout  | 5000 ms  | focus | at focus-gained      | Yes                                |

The three values sit in one run of numeric constants near the voice hook, in the order
`200, 600, 2000, 5000, 15000, 120000, 16`. The leading `200` is the auto-repeat release delay used by
the hold heuristic; `600` is the default key-event debounce. Locate the run by grepping the log
strings above and reading the timeout argument each timer passes.

Behavioral specifics that are easy to get wrong:

- The 15s silence timer is re-armed from the transcript callback on both interim and final results.
  It therefore measures 15s since the last recognized speech, not 15s of wall clock. It is armed
  immediately at tap-to-start, so tapping and then saying nothing self-finishes at 15s.
- The 120s cap is armed once and never re-armed. It is a true ceiling on a single tap-mode recording.
- Both timers are gated on a ref set only in the tap branch of the key handler (`[voice] toggle:
  starting recording`). Hold mode arms neither: it has no silence timeout and no duration cap, and
  cannot self-terminate. It ends only on the key-release heuristic.
- "Silence" means no transcript callback arrived from the STT stream — it is recognition-driven, not
  an audio-level threshold. The SoX fallback backend separately applies its own level-based silence
  effect (see below), but that path is not used when the native addon loads.
- An auto-finish and a manual second tap converge on the same finish routine, so they are
  indistinguishable from inside the app and produce identical downstream behavior.

## The submit gate: tap mode always submits, `autoSubmit` notwithstanding

Relocate with `rg -n 'voice_transcript_insert'`. In the same function that splices the final
transcript into the input buffer at the recorded anchor, expect a boolean of this shape:

    (mode === "tap" || autoSubmitSetting) && wordCount(transcript) >= 3

and a guarded call to the input ref's `submit` immediately after.

Consequences:

- The condition is an OR, so `voice.autoSubmit: false` does not stop tap mode from submitting. There
  is no way to keep tap mode from auto-sending; the only opt-out is `voice.mode: "hold"`.
- The three-word floor applies to both modes. Below it the transcript is inserted into the input
  buffer and left there — but the recording has still ended.
- Because auto-finish and manual tap share the finish routine, a 15s-silence or 120s-cap termination
  submits exactly as a deliberate second tap would.
- Word count is `max(whitespace-split count, Intl.Segmenter word-like count)`, so scripts without
  spaces (Japanese, Chinese, Thai) still reach the threshold.

The submit goes through the same input-submit handler as pressing Enter — voice passes only the flag
that bypasses the "autocomplete suggestions are showing" early return. Nothing about the submit path
is voice-specific, so `UserPromptSubmit` hooks fire normally (see Observability).

Escape while recording routes to the cancel path (`[voice] cancelRecording: discarding without
submit`), which discards the transcript rather than inserting it.

## Audio capture: native addon, with a SoX subprocess as fallback

Relocate with `rg -n 'isNativeAudioAvailable'`. Two backends, tried in order:

1. A bundled native addon. The loader tries an embedded require first, then
   `./vendor/audio-capture/<arch>-<platform>/audio-capture.node` and a sibling path. On a normal
   single-file install this resolves in-process — there is no child process and no addon file on
   disk. Availability is just "did the module load".
2. SoX, spawned as `rec` reading raw 16-bit 16 kHz mono to stdout. Relocate with `rg -n 'SoX rec
   spawn failed'`. When silence detection is enabled this path appends SoX's own
   `silence 1 0.1 3% 1 2.0 3%` effect, which stops capture after 2.0s below a 3% threshold — a
   level-based stop that exists only on this backend.

Missing-dependency messages are good anchors for the install story: `Voice mode requires SoX for
audio recording`, and a WSL-specific variant mentioning `libsox-fmt-pulse`. Voice mode is refused
outright in remote/no-device environments (`Voice mode requires microphone access`), gated in part on
`CLAUDE_CODE_REMOTE`.

## The speech-to-text stream

Relocate with `rg -n 'voice_stream'`. The recorder opens a WebSocket per recording:

- Path: `/api/ws/speech_to_text/voice_stream`, on `BASE_API_URL` with `https`/`http` rewritten to
  `wss`/`ws`. `VOICE_STREAM_BASE_URL` overrides the base and logs
  `[voice_stream] Using VOICE_STREAM_BASE_URL override:`.
- Auth: `Authorization: Bearer <OAuth accessToken>`, plus `x-app: cli` and
  `anthropic-client-platform`. No token means no stream (`[voice_stream] No OAuth token available`).
- Query parameters: `encoding=linear16`, `sample_rate=16000`, `channels=1`, `endpointing_ms=300`,
  `utterance_end_ms=1000`, `language`, `use_conversation_engine=true`, `stt_provider=deepgram-nova3`.
- Keyterms, when configured, are sent in an `x-config-keyterms` header: comma-joined, commas stripped
  from each term, non-ASCII stripped, deduped, and truncated to a 1024-char budget.
- Audio is sent as raw chunks, coalesced to a 32000-byte batch size on the replay path. Finalize has
  two guard timers, roughly 5000 ms safety and 1500 ms no-data.

So voice mode streams raw microphone audio to Anthropic's API host, transcribed by Deepgram Nova-3 as
the STT provider. That is inherent to the feature, not opt-in behavior.

### `CLAUDE_CODE_VOICE_FORWARD_INTERIMS_TYPED`

The only voice-specific env var in the bundle. Relocate with
`rg -n 'CLAUDE_CODE_VOICE_FORWARD_INTERIMS_TYPED'`; the enclosing predicate is exported as
`isTypedInterimsEnabled` and falls back to the `tengu_brick_follow` gate (default off) when the env
var is not truthy.

Its entire effect is to add `forward_interims=typed` to the WebSocket query string. It shapes what
the server sends back — the stream of provisional transcripts that populates the input live — and
adds nothing to the upload. It is not a telemetry or data-sharing switch.

## Observability: what an external process can and cannot see

Relevant when integrating voice mode with anything outside Claude Code (a mute/unmute chain, an
indicator, a watchdog). The short version: there is no voice-specific external signal.

What does not exist:

- No voice hook event. The hook-event list (relocate by grepping `UserPromptExpansion`, which sits in
  the same array) contains no voice entry.
- The `voiceState` value (`idle` / `recording` / `processing`) is in-memory UI store state, consumed
  only by TUI components. It is never written to disk or exported.
- No state file, OSC sequence, bell, or terminal-title change on any voice transition.
- No audio cue. The native addon exports playback functions, but they have no call sites.
- On a normal install, no child process to watch — capture is in-process (see above). Only the SoX
  fallback yields an observable `rec` process whose exit marks the end of recording.

What does exist:

- `UserPromptSubmit` fires on an auto-submit, because the voice path reuses the ordinary submit
  handler. This is the one precise, poll-free "recording ended and was sent" edge. It is not
  complete: a sub-three-word auto-finish ends the recording and fires nothing. It is also delayed
  relative to the timer, since finalize plus the STT round-trip happen first.
- The tap-mode recording indicator is screen-scrapable. While recording in tap mode it renders
  `REC` preceded by a record glyph (`⏺` U+23FA on macOS, `●` U+25CF elsewhere) and followed by
  `· tap to send`; `processing` renders a spinner; `idle` renders nothing. Relocate with
  `rg -n 'tap to send'`. Polling for `REC` present→absent covers the sub-three-word case that the
  hook misses.
- Debug logs carry every transition under the `[voice]` and `[voice_stream]` prefixes, if debug
  output is being captured.

For a blind self-heal timer, the bound is the 120s cap plus finalize and transcription time. In
practice the 15s silence timer fires first in almost every real case.

## Telemetry

`tengu_voice_toggled` (fields `enabled`, `tap_mode`), `tengu_voice_recording_started`
(`focusTriggered`, `sttLanguage`, `sttLanguageIsDefault`, `sttLanguageFellBack`,
`systemLocaleLanguage`), `tengu_voice_recording_completed` (`transcriptChars`,
`recordingDurationMs`, `hadAudioSignal`, `retried`, `silentDropRetried`, `wsConnected`,
`focusTriggered`), `tengu_voice_init_gate`, `tengu_voice_silent_drop_replay`,
`tengu_voice_stream_early_retry`, `tengu_voice_circuit_breaker_tripped`.

Repeated failures trip a circuit breaker that pauses voice
(`voice_start_breaker_paused`). Error codes worth knowing: `voice_transcription_no_speech`,
`voice_transcription_connection_failed`, `voice_transcription_finalize_failed`,
`voice_start_recording_unavailable`, `voice_start_capture_failed`,
`voice_start_module_not_loaded`. A no-speech error surfaces only when the recording ran longer than
2000 ms and produced nothing.

## Configurability summary

| Want                              | Possible? | How                                                        |
| --------------------------------- | --------- | ---------------------------------------------------------- |
| Disable tap-mode auto-submit      | No        | Gate is an OR; `voice.autoSubmit: false` has no effect     |
| Lengthen/disable the 15s silence  | No        | Hardcoded constant, no setting and no env override         |
| Lengthen/disable the 120s cap     | No        | Hardcoded constant, no setting and no env override         |
| Avoid keystroke-free termination  | Yes       | `voice.mode: "hold"` arms neither timer                    |
| Disable hold-mode auto-submit     | Yes       | `voice.autoSubmit: false` (or leave unset)                 |
| Point the STT stream elsewhere    | Yes       | `VOICE_STREAM_BASE_URL`                                    |

## Tripwires

Re-runnable checks against a newer bundle:

- □ `voice.mode` still defaults to `hold`, and `autoSubmit` still describes itself as hold-mode only
- □ Both `[voice] Toggle silence timeout` and `[voice] Toggle max-duration cap` strings still present
- □ Timer values still 15000 and 120000; focus timeout still 5000
- □ Silence timer still re-armed from the transcript callback on interim results, not just final
- □ Max-duration timer still armed once, not re-armed
- □ Submit gate still `(mode === "tap" || autoSubmit) && wordCount >= 3` — still an OR, still 3
- □ Both timers still gated on the tap-branch ref, so hold mode still arms neither
- □ `stt_provider` still `deepgram-nova3`; endpoint still `/api/ws/speech_to_text/voice_stream`
- □ `CLAUDE_CODE_VOICE_FORWARD_INTERIMS_TYPED` still only adds `forward_interims=typed`
- □ Hook-event list still contains no voice event
- □ Tap indicator still renders `tap to send`

## Version notes

- 2.1.226/227: tap-mode silence timeout 15000 ms, max-duration cap 120000 ms, focus silence timeout
  5000 ms; submit gate `(tap || autoSubmit) && words >= 3`; `stt_provider=deepgram-nova3`. Constants,
  gates and stream parameters identical between the two versions.

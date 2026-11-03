---
verified: 2.1.317
verified_on: 2026-11-03
section: Sessions, context, and history
style: landmark
scope: >-
  Voice dictation: enablement gates, hold vs tap, tap-mode self-termination, auto-submit and
  double-tap send, STT stream and recovery, what an external process can observe
landmarks:
  - '[voice] Toggle silence timeout'
  - voice_transcript_insert
  - speech_to_text/voice_stream
  - allow_voice_mode
  - awaitingVoiceSubmitDoubleTap
---
# Voice Mode (dictation)

How voice dictation records, when a recording ends on its own, when it submits the prompt without
being asked to, where the audio goes, and what an external process can observe about any of it.
Style: landmark.

The 2.1.317 bundle analyzed is the macOS arm64 binary, so platform checks are folded to `darwin` and
the addon directory to `arm64-darwin`; the Linux and WSL branches below are read from the strings
that remain.

## Enabling voice mode

Voice is live in the prompt only when all three hold:

- the user has turned it on: `voice.enabled`, falling back to the top-level `voiceEnabled` key
  (`Enable voice mode (hold-to-talk dictation)`) when `voice.enabled` is unset;
- the user is signed in with a Claude.ai OAuth token;
- the organization policy restriction `allow_voice_mode` allows it.

Relocate with `rg -n 'allow_voice_mode'`: the gate that ANDs the auth check with that policy key
also hides the `/voice` command when it fails, and a once-per-session `tengu_voice_init_gate` event
records each input (`user_intent_store`, `user_intent_disk`, `has_voice_auth`, `voice_mode_allowed`,
`auth_version`).

`/voice [hold|tap|off]` (description `Toggle voice mode`, not available non-interactively) is the
switch. Relocate with `rg -n 'Use hold, tap, or off'`. With no argument it toggles. Enabling runs,
in order: a recording-availability check, an OAuth check
(`Voice mode requires a Claude.ai account. Please run /login to sign in.`), a recorder-dependency
check (`No audio recording tool found.`), and a microphone permission probe that starts and
immediately stops a native recording (`Microphone access is denied. To enable it, go to`, naming the
macOS Privacy & Security → Microphone pane). It then writes both `voiceEnabled` and
`voice.enabled`/`voice.mode` to user settings and confirms with `Hold <key> to record.` or
`Tap <key> (with input empty) to start, tap again to send.`, where `<key>` is the `voice:pushToTalk`
binding in the `Chat` context (default `space`). It may append a dictation-language note; an
unsupported `language` setting falls back to English
(`is not a supported dictation language; using English`).

A startup tip advertises the command (`Use /voice to enable push-to-talk dictation`) when voice is
allowed, never configured, and the session is not remote or over SSH.

## The two modes

Settings live under the `voice` key: `voice.enabled`, `voice.mode`, `voice.autoSubmit`. Relocate the
schema with `rg -n 'Voice mode settings'`; the enclosing object carries all three, two with a
`.describe()` string (verbatim, stable anchors):

| Key                | Values          | Schema description                                      |
| ------------------ | --------------- | ------------------------------------------------------- |
| `voice.enabled`    | boolean         | —                                                       |
| `voice.mode`       | `hold` \| `tap` | `'hold' (default): hold to talk. 'tap': tap to start,`  |
|                    |                 | `tap to stop+submit.`                                   |
| `voice.autoSubmit` | boolean         | `Submit the prompt when hold-to-talk is released (hold` |
|                    |                 | `mode only)`                                            |

`voice.mode` defaults to `hold` (read as `voice?.mode ?? "hold"`); `voice.autoSubmit` counts only
when it is exactly `true`. The activation key is the `voice:pushToTalk` keybinding; how a
hold-and-release is reconstructed from keyboard auto-repeat is documented in
`KEYBOARD_INPUT_DECODING.md`.

- Hold mode ends a recording when the key's auto-repeat stops: the recorder arms a 200 ms release
  timer on each repeat and finishes when it fires. If no auto-repeat arrives after the first press,
  it arms that release timer anyway after 600 ms (2000 ms for a binding that is not a single
  printable character).
- Tap mode starts a recording only when the input is empty. A tap on a non-empty input is not
  consumed and reaches the input as an ordinary keystroke. Repeats within 120 ms of the previous
  press are swallowed, so one physical tap toggles once.

The recorder also contains a focus mode (record while the terminal has focus, with its own silence
timeout and teardown, flushing each final transcript immediately). It is unreachable in 2.1.317: the
prompt's only call into the voice hook (`rg -n '\.useVoice\('`) passes focus mode off, and no
setting turns it on. Its log strings (`[voice] Focus silence timeout — tearing down session`,
`[voice] Re-arming focus recording after silence timeout`,
`[voice] Focus mode: flushing final transcript immediately`) are present but never fire.

## Self-termination: tap mode ends on its own, hold mode never does

This is the load-bearing finding. In tap mode two timers are armed at tap-to-start, and either one
will finish the recording with no keystroke at all.

Relocate with `rg -n '\[voice\] Toggle'`. Expect two sibling timer-arming methods whose callbacks
log these strings and then call the same finish routine the manual tap calls:

- `[voice] Toggle silence timeout — auto-finishing`
- `[voice] Toggle max-duration cap — auto-finishing`

The tap-to-start branch logs `[voice] toggle: starting recording`, sets a tap-mode flag, starts the
session, and arms both timers.

| Timer                  | Value     | Mode  | Armed           | Re-armed on speech?         |
| ---------------------- | --------- | ----- | --------------- | --------------------------- |
| Toggle silence timeout | 15000 ms  | tap   | at tap-to-start | Yes, on every transcript    |
| Toggle max-duration    | 120000 ms | tap   | at tap-to-start | No, a hard cap from the tap |
| Focus silence timeout  | 5000 ms   | focus | unreachable     | Yes                         |

The values sit in the recorder module's constant block, in the order `200, 600` (hold release timer,
first-press fallback) then `5000, 15000, 120000, 16` (focus, toggle silence, toggle cap, and the
length of the audio-level meter history). Locate the block by grepping the log strings above and
reading the timeout argument each timer passes.

Behavioral specifics that are easy to get wrong:

- The 15s silence timer is re-armed from the transcript callback on both interim and final results.
  It therefore measures 15s since the last recognized speech, not 15s of wall clock. It is armed
  immediately at tap-to-start, so tapping and then saying nothing self-finishes at 15s.
- The 120s cap is armed once and never re-armed: a true ceiling on a single tap-mode recording.
- Both timers are gated on the tap-mode flag, which only the tap branch sets. Hold mode arms
  neither: it has no silence timeout and no duration cap, and ends only on the key-release
  heuristic.
- "Silence" means no transcript callback arrived from the STT stream — it is recognition-driven, not
  an audio-level threshold. The recorder always starts capture with silence detection off, so
  neither backend applies a level-based stop (see Audio capture).
- An auto-finish and a manual second tap converge on the same finish routine
  (`[voice] finishRecording: stopping recording, transitioning to processing`), so they are
  indistinguishable from inside the app and produce identical downstream behavior.
- On the SoX backend, the `rec` process exiting on its own also calls the finish routine.

## The submit gate: tap mode always submits, `autoSubmit` notwithstanding

Relocate with `rg -n 'voice_transcript_insert'`. In the function that splices the final transcript
into the input buffer at the anchor recorded when recording began, expect a boolean of this shape:

    (mode === "tap" || autoSubmitSetting) && wordCount(transcript) >= 3

and a guarded call to the input's `submit` immediately after.

Consequences:

- The condition is an OR, so `voice.autoSubmit: false` does not stop tap mode from submitting. There
  is no way to keep tap mode from auto-sending; the only opt-out is `voice.mode: "hold"`.
- The three-word floor applies to both modes. Below it the transcript is inserted into the input
  buffer and left there — but the recording has still ended.
- Because auto-finish and manual tap share the finish routine, a 15s-silence or 120s-cap termination
  submits exactly as a deliberate second tap would.
- Word count is `max(whitespace-split count, Intl.Segmenter word-like count)`, so scripts without
  spaces (Japanese, Chinese, Thai) still reach the threshold.
- If the input no longer matches what voice last wrote into it, the transcript is dropped rather
  than inserted, reported as `input_diverged`; with no anchor it is dropped as `no_anchor`.

The submit goes through the same prompt-submit handler as pressing Enter — voice passes only the
flag that bypasses the `[onSubmit] early return: suggestions showing` check. Nothing about the
submit path is voice-specific, so `UserPromptSubmit` hooks fire normally (see Observability).

### Hold mode: double-tap to send

When a hold-mode transcript is inserted but not submitted (autoSubmit off, or under three words),
the app sets `awaitingVoiceSubmitDoubleTap`. Relocate with `rg -n 'awaitingVoiceSubmitDoubleTap'`.
While it is set, two presses of the push-to-talk key within 300 ms, with the cursor at the end of
the input and voice idle, submit the input 120 ms later with the first press's echoed character
stripped. Any other key, a press away from the end, or the start of a new recording clears the flag.
This applies only when the binding is a single printable character, such as the default `space`.

### Cancel

Escape or Ctrl+C while voice is recording or processing routes to the cancel path
(`[voice] cancelRecording: discarding without submit`), which discards the transcript rather than
inserting it; a finalize still in flight is ignored when it resolves.

## Audio capture: native addon, with a SoX subprocess as fallback

Relocate with `rg -n 'isNativeAudioAvailable'`. Two backends, tried in order:

1. A bundled native addon (`[voice] audio-capture-napi loaded in`). The loader tries the addon
   embedded in the binary first, then `./vendor/audio-capture/<arch>-<platform>/audio-capture.node`
   and `../audio-capture/<arch>-<platform>/audio-capture.node` (Linux also tries a `-musl` variant).
   On a normal single-file install this resolves in-process — there is no child process and no addon
   file on disk. Availability is just "did the module load".
2. SoX, spawned as `rec` reading raw signed 16-bit 16 kHz mono to stdout. Relocate with
   `rg -n 'SoX rec spawn failed'`. The spawner appends SoX's `silence 1 0.1 3% 1 2.0 3%` effect only
   when silence detection is requested, and the voice recorder never requests it, so a voice
   recording on SoX runs until stopped. Stop is `SIGTERM` to `rec`.

When the native addon loads, recording is available. Otherwise the availability check needs both
`sox` and `rec` on `PATH`. Messages worth anchoring on:

- `Voice mode requires microphone access, but no audio device is available in this environment.` —
  refused outright when `CLAUDE_CODE_REMOTE` is set.
- `Voice mode could not find a working audio recorder in WSL.` — the WSL variant, recommending
  `sudo apt install sox libsox-fmt-pulse`.
- `Voice mode requires SoX for audio recording.` — with `brew install sox` when Homebrew is present,
  else a per-OS manual list.
- `Voice mode requires a microphone, but SoX could not open an audio capture device.`

## The speech-to-text stream

Relocate with `rg -n 'speech_to_text/voice_stream'`. The recorder opens a WebSocket per recording,
buffering captured audio until it connects:

- Path: `/api/ws/speech_to_text/voice_stream`, on `BASE_API_URL` with `https`/`http` rewritten to
  `wss`/`ws`. The client honors the configured proxy and TLS settings.
- Auth: `Authorization: Bearer <OAuth accessToken>`, plus `User-Agent`, `x-app: cli` and
  `anthropic-client-platform`. No token means no stream: `[voice_stream] No OAuth token available`,
  then `[voice] Failed to connect to voice_stream (no OAuth token?)`.
- Query parameters: `encoding=linear16`, `sample_rate=16000`, `channels=1`, `endpointing_ms=300`,
  `utterance_end_ms=1000`, `language` (default `en`), `use_conversation_engine=true`, and
  `forward_interims=typed` when enabled (below). No STT provider is named on the wire.
- Keyterms are always sent, in an `x-config-keyterms` header. The list is a fixed set of 14
  developer terms (`MCP`, `symlink`, `grep`, `regex`, `localhost`, `codebase`, `TypeScript`, `JSON`,
  `OAuth`, `webhook`, `gRPC`, `dotfiles`, `subagent`, `worktree`), the project root's directory
  name, and the words of the current git branch name (split on case changes and `-_./`, 3–20 chars),
  capped at 50 terms. Before sending, commas become spaces, non-printable-ASCII is removed,
  whitespace collapses, duplicates drop, and the comma-joined header is truncated to a 1024-char
  budget.
- Control frames: `{"type":"KeepAlive"}` on connect and every 8000 ms; finalize sends
  `{"type":"CloseStream"}`. Server frames handled: `TranscriptInterim`/`TranscriptText` (interim),
  `TranscriptEndpoint` (final), `TranscriptError`, and `error`.
- Audio buffered before connect is flushed in frames coalesced to 32000 bytes. Finalize resolves on
  the post-CloseStream endpoint, the socket closing, or one of two guard timers: 5000 ms safety and
  1500 ms no-data (cleared once any transcript arrives after CloseStream). An unreported interim is
  promoted to final before finalize resolves (`[voice_stream] Promoting unreported interim`).

Recovery paths:

- Early retry: the first non-fatal stream error before any transcript reconnects once after 250 ms
  (`tengu_voice_stream_early_retry`).
- Silent-drop replay: when finalize resolves by the no-data timer although audio had signal and the
  socket had connected, and nothing was transcribed, the captured audio is replayed once on a fresh
  connection in 32000-byte frames (`[voice] Silent-drop detected`,
  `tengu_voice_silent_drop_replay`).
- Mid-stream salvage: on a stream error after speech, accumulated text is still injected
  (`[voice] mid-stream error: salvaging`).
- Circuit breaker: 3 early failures within 10000 ms pause new sessions until one succeeds
  (`rg -n 'early failures in'`, `tengu_voice_circuit_breaker_tripped`). A transcript clears the
  count.
- Connection diagnosis: when a recording ends empty without the socket ever connecting and no
  connect-failure code was captured, a `GET <BASE_API_URL>/api/hello` probe with a 1500 ms timeout
  classifies the failure (`http_<status>`, `cf_mitigated_<status>`, `timeout`, `fetch_failed`). It
  is skipped as `skipped_privacy` when `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`,
  `DISABLE_TELEMETRY` or `DO_NOT_TRACK` is set.

So voice mode streams raw microphone audio to Anthropic's API host, along with the project directory
name and git branch words as keyterms. That is inherent to the feature, not opt-in behavior.

### Environment variables

`CLAUDE_CODE_VOICE_FORWARD_INTERIMS_TYPED`: relocate with
`rg -n 'CLAUDE_CODE_VOICE_FORWARD_INTERIMS_TYPED'`. When truthy it enables typed interims; otherwise
the `tengu_brick_follow` gate (default off) decides. Its entire effect is to add
`forward_interims=typed` to the WebSocket query string. It shapes what the server sends back — the
stream of provisional transcripts that populates the input live — and adds nothing to the upload. It
is not a telemetry or data-sharing switch.

`VOICE_STREAM_BASE_URL` is registered as an env var and listed among endpoint-override variables
that other code checks, but the stream URL builder does not read it: the stream always targets
`BASE_API_URL`. No other voice-specific env var exists in the bundle.

## Observability: what an external process can and cannot see

Relevant when integrating voice mode with anything outside Claude Code (a mute/unmute chain, an
indicator, a watchdog). The short version: there is no voice-specific external signal.

What does not exist:

- No voice hook event. The hook-event list (relocate by grepping `UserPromptExpansion`, which sits
  in the same array) contains no voice entry.
- The `voiceState` value (`idle` / `recording` / `processing`) is in-memory UI store state, consumed
  only by TUI components. It is never written to disk or exported.
- No state file, OSC sequence, bell, or terminal-title change on any voice transition.
- No audio cue. The native addon exports playback functions, but they have no call sites.
- On a normal install, no child process to watch — capture is in-process (see above). Only the SoX
  fallback yields an observable `rec` process whose exit marks the end of recording.

What does exist:

- `UserPromptSubmit` fires on an auto-submit and on a hold-mode double-tap send, because both reuse
  the ordinary submit handler. This is the one precise, poll-free "recording ended and was sent"
  edge. It is not complete: a sub-three-word auto-finish ends the recording and fires nothing. It is
  also delayed relative to the timer, since finalize plus the STT round-trip happen first.
- The recording indicator is screen-scrapable. Relocate with `rg -n 'tap to send'`. In tap mode it
  renders `REC` preceded by a record glyph (`⏺` U+23FA on macOS, `●` U+25CF elsewhere) and followed
  by `· tap to send`; in hold mode it renders `listening…`; `processing` renders an animated
  indicator (`Voice: processing…` under reduced motion); `idle` renders nothing. During hold-mode
  warmup the footer shows `keep holding…`. Polling for `REC` present→absent covers the
  sub-three-word case that the hook misses.
- Debug logs carry every transition under the `[voice]` and `[voice_stream]` prefixes, if debug
  output is being captured.

For a blind self-heal timer, the bound is the 120s cap plus finalize (at most the 5000 ms safety
timer) and transcription time, plus one replay when a silent drop is detected. In practice the 15s
silence timer fires first in almost every real case.

## Telemetry

Voice events and their fields:

- `tengu_voice_toggled`: `enabled`, plus `tap_mode` on enable.
- `tengu_voice_init_gate`: `user_intent_store`, `user_intent_disk`, `has_voice_auth`,
  `voice_mode_allowed`, `auth_version`.
- `tengu_voice_recording_started`: `focusTriggered`, `sttLanguage`, `sttLanguageIsDefault`,
  `sttLanguageFellBack`, `systemLocaleLanguage`.
- `tengu_voice_recording_completed`: `transcriptChars`, `recordingDurationMs`, `hadAudioSignal`,
  `retried`, `silentDropRetried`, `wsConnected`, `focusTriggered`.
- `tengu_voice_silent_drop_replay`: `recordingDurationMs`, `chunkCount`.
- `tengu_voice_stream_early_retry` and `tengu_voice_circuit_breaker_tripped`: no fields.

Outcomes also go out as generic feature-health events `tengu_feature_ok`, `tengu_feature_bad` and
`tengu_feature_sad`, keyed by `feature_name` (`voice_start`, `voice_stream_connect`,
`voice_transcription`, `voice_transcript_insert`, `voice_cancel`) with an `error_code`. Codes worth
knowing: `voice_start_module_not_loaded`, `voice_start_breaker_paused`,
`voice_start_recording_unavailable`, `voice_start_capture_failed`, `voice_stream_no_auth`,
`voice_stream_connection_error`, `voice_stream_connect_exception`,
`voice_transcription_no_audio_signal`, `voice_transcription_no_speech`,
`voice_transcription_connection_failed_<reason>`, `voice_transcription_finalize_failed`,
`voice_transcription_partial_salvaged`, and the insert outcomes `no_anchor` and `input_diverged`.

An empty-transcript error surfaces only when the recording ran longer than 2000 ms. The message
picks the likeliest cause: no audio signal (`No audio detected from microphone.`), no connection
(`Voice connection failed. Check your network and try again.`), else `No speech detected.`

## Configurability summary

| Want                              | Possible? | How                                           |
| --------------------------------- | --------- | --------------------------------------------- |
| Disable tap-mode auto-submit      | No        | Gate is an OR; `autoSubmit: false` is ignored |
| Lengthen/disable the 15s silence  | No        | Hardcoded; no setting or env override         |
| Lengthen/disable the 120s cap     | No        | Hardcoded; no setting or env override         |
| Avoid keystroke-free termination  | Yes       | `voice.mode: "hold"` arms neither timer       |
| Disable hold-mode auto-submit     | Yes       | `voice.autoSubmit: false` (or leave unset)    |
| Send a hold-mode transcript later | Yes       | Double-tap push-to-talk, or press Enter       |
| Point the STT stream elsewhere    | No        | `VOICE_STREAM_BASE_URL` is not read           |
| Stop keyterms being sent          | No        | Built-in terms, project, branch always go     |

## Tripwires

Re-runnable checks against a newer bundle:

- □ `voice.mode` still defaults to `hold`, and `autoSubmit` still describes itself as hold-mode only
- □ Voice still requires Claude.ai OAuth and the `allow_voice_mode` policy
- □ Strings `[voice] Toggle silence timeout` and `[voice] Toggle max-duration cap` still present
- □ Timer values still 15000 and 120000; hold release still 200; focus timeout still 5000
- □ Silence timer still re-armed from the transcript callback on interim results, not just final
- □ Max-duration timer still armed once, not re-armed
- □ Submit gate still `(mode === "tap" || autoSubmit) && wordCount >= 3` — still an OR, still 3
- □ Both timers still gated on the tap-mode flag, so hold mode still arms neither
- □ The only `.useVoice(` call site still passes focus mode off
- □ Recorder still starts capture with silence detection off
- □ Endpoint still `/api/ws/speech_to_text/voice_stream`; no provider parameter on the query
- □ `VOICE_STREAM_BASE_URL` still unread by the stream URL builder
- □ `CLAUDE_CODE_VOICE_FORWARD_INTERIMS_TYPED` still only adds `forward_interims=typed`
- □ Keyterms still always sent, still including project name and git branch words
- □ Hook-event list still contains no voice event
- □ Tap indicator still renders `tap to send`

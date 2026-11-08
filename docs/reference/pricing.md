# Pricing

The rates behind `estimated_cost_usd` on every usage record and standalone endpoint response (`/stt/transcribe`, `/tts/synthesize`, `/llm/chat`). They are public pay-as-you-go list
prices, kept as a static table in the platform, so an estimate can always be
reproduced. They are estimates, not your invoice: a contract rate, a promotion or a tax changes
what you actually pay. How the estimate is built: [Usage Accounting](usage-accounting.md).

Every model the platform prices is listed on this page, with the date its rate was checked.

## OpenAI text models (`cascade`, and the `duplex` backend)

Per 1M tokens. [Source](https://developers.openai.com/api/docs/pricing), checked 2026-09-06;
`gpt-6-*` checked 2026-10-17.

| Model | Input | Cached input | Output |
|---|---|---|---|
| `gpt-4.1` | $2.00 | $0.50 | $8.00 |
| `gpt-4.1-mini` | $0.40 | $0.10 | $1.60 |
| `gpt-4.1-nano` | $0.10 | $0.025 | $0.40 |
| `gpt-4o` | $2.50 | $1.25 | $10.00 |
| `gpt-4o-mini` | $0.15 | $0.075 | $0.60 |
| `gpt-5` | $1.25 | $0.125 | $10.00 |
| `gpt-5-mini` | $0.25 | $0.025 | $2.00 |
| `gpt-5-nano` | $0.05 | $0.005 | $0.40 |
| `gpt-5.2` | $1.75 | $0.175 | $14.00 |
| `gpt-5.4` | $2.50 | $0.25 | $15.00 |
| `gpt-5.4-mini` | $0.75 | $0.075 | $4.50 |
| `gpt-5.5` | $5.00 | $0.50 | $30.00 |
| `gpt-5.6-sol` | $4.00 | $0.40 | $20.00 |
| `gpt-5.6-terra` | $2.00 | $0.20 | $12.00 |
| `gpt-5.6-luna` | $0.20 | $0.02 | $1.20 |
| `gpt-6-luna` | $0.10 | $0.01 | $0.50 |
| `gpt-6-sol` | $2.00 | $0.20 | $10.00 |

No longer accepted since 1.6.0, still priced so that older calls keep their estimate:
`gpt-5.1` ($1.25 / $0.125 / $10.00) and `gpt-5.4-nano` ($0.20 / $0.02 / $1.25).

## OpenAI realtime models (`pipeline` and `realtime`)

Per 1M tokens. Same source, checked 2026-09-06; the `2.1` models checked 2026-10-17.

| Model | Audio in | Cached audio in | Text in | Cached text in | Image in | Audio out | Text out |
|---|---|---|---|---|---|---|---|
| `gpt-realtime` | $32 | $0.40 | $4 | $0.40 | $5 | $64 | $16 |
| `gpt-realtime-1.5` | $32 | $0.40 | $4 | $0.40 | $5 | $64 | $16 |
| `gpt-realtime-2` | $32 | $0.40 | $4 | $0.40 | $5 | $64 | $24 |
| `gpt-realtime-2025-08-28` | $32 | $0.40 | $4 | $0.40 | $5 | $64 | $16 |
| `gpt-realtime-2.1` | $32 | $0.40 | $4 | $0.40 | $5 | $64 | $24 |
| `gpt-realtime-mini` | $10 | $0.30 | $0.60 | $0.06 | $0.80 | $20 | $2.40 |
| `gpt-realtime-2.1-mini` | $10 | $0.30 | $0.60 | $0.06 | $0.80 | $20 | $2.40 |

## GPT-Live (`duplex`)

| Model | Rate |
|---|---|
| `gpt-live-1` | $0.05 per minute of open session, billed per second |

The backend model's tokens are billed on top, at its rate in the text-model table. Checked
2026-10-17.

## Service tiers

`service_tier` scales an OpenAI token rate: `flex` is 0.5x, `fast` and `priority` are 2x
([source](https://developers.openai.com/api/docs/pricing), checked 2026-10-21). GPT-Live's per-second
voice rate is not scaled.

## Gemini Live (`realtime`)

Per 1M tokens, paid tier. [Source](https://ai.google.dev/gemini-api/docs/pricing), checked
2026-09-22. Thinking tokens bill as output text, but the Gemini plugin does not report them, so an extended-thinking call is estimated low. Google publishes no Live API cache discount, so
cached input is estimated at the full rate.

| Model | Text in | Audio in | Image/video in | Text out | Audio out |
|---|---|---|---|---|---|
| `gemini-3.8-live` | $0.75 | $3.00 | $1.00 | $4.50 | $12.00 |
| `gemini-3.8-live-extended-thinking` | $0.75 | $3.00 | $1.00 | $4.50 | $12.00 |
| `gemini-3.1-flash-live-preview` | $0.75 | $3.00 | $1.00 | $4.50 | $12.00 |
| `gemini-2.5-flash-native-audio-preview-12-2025` | $0.50 | $3.00 | $3.00 | $2.00 | $12.00 |

## Speech-to-text

| Provider | Model | Rate | Source, checked |
|---|---|---|---|
| OpenAI | `gpt-transcribe` | $0.0045 per minute | [OpenAI](https://developers.openai.com/api/docs/pricing), 2026-09-06 |
| OpenAI | `gpt-4o-transcribe` | $2.50 audio in, $10 text out, per 1M tokens | same |
| OpenAI | `gpt-4o-transcribe-diarize` | $2.50 audio in, $10 text out, per 1M tokens | same |
| OpenAI | `gpt-4o-mini-transcribe` | $1.25 audio in, $5 text out, per 1M tokens | same |
| OpenAI | `gpt-4o-mini-transcribe-2025-12-15` | $1.25 audio in, $5 text out, per 1M tokens | same |
| OpenAI | `whisper-1` | $0.006 per minute | same |
| Sarvam | `saaras:v3` | INR 30 per hour (about $0.36) | [Sarvam](https://docs.sarvam.ai/api-reference-docs/pricing), 2026-09-06 |
| Sarvam | `saaras:v4` | INR 30 per hour (about $0.36) | same |
| Deepgram | `nova-3` | $0.0077 per minute | [Deepgram](https://deepgram.com/pricing), 2026-09-22 |
| Deepgram | `nova-3-general` | $0.0077 per minute | same |
| Deepgram | `nova-3-multilingual` | $0.0092 per minute | same |
| Deepgram | `flux-general-en` | $0.0077 per minute | same |
| Deepgram | `flux-general-multi` | $0.0078 per minute | same |
| ElevenLabs | `scribe_v1` | $0.22 per hour | [ElevenLabs](https://elevenlabs.io/pricing/api), 2026-09-06 |
| ElevenLabs | `scribe_v2` | $0.22 per hour | same |
| ElevenLabs | `scribe_v2_realtime` | $0.39 per hour | same |
| Cartesia | `ink-2` | about $0.42 per hour (derived) | [Cartesia](https://cartesia.ai/pricing), 2026-09-22 |
| Cartesia | `ink-whisper` | about $0.42 per hour (derived) | same |

Deepgram is priced at its **regular** rate; the page sometimes shows a lower promotional one. An
estimate that is a little high survives the promotion ending.

## Text-to-speech

Per 1K characters unless noted.

| Provider | Model | Rate | Source, checked |
|---|---|---|---|
| ElevenLabs | `eleven_v4` | $0.08 | [ElevenLabs](https://elevenlabs.io/pricing/api), 2026-10-17 |
| ElevenLabs | `eleven_v4_turbo` | $0.04 | same |
| ElevenLabs | `eleven_v3` | $0.08 | same |
| ElevenLabs | `eleven_v3_conversational` | $0.04 | same |
| ElevenLabs | `eleven_multilingual_v2` | $0.08 | same |
| ElevenLabs | `eleven_turbo_v2`, `eleven_turbo_v2_5` | $0.04 | same |
| ElevenLabs | `eleven_flash_v2`, `eleven_flash_v2_5` | $0.04 | same |
| ElevenLabs | `eleven_multilingual_v1`, `eleven_monolingual_v1` | $0.10 | retired by ElevenLabs and no longer accepted; kept so older usage still prices |
| Sarvam | `bulbul:v3` | INR 30 per 10K characters (about $0.036 per 1K) | [Sarvam](https://docs.sarvam.ai/api-reference-docs/pricing), 2026-09-06 |
| Sarvam | `bulbul:v4-flash` | INR 20 per 10K characters (about $0.024 per 1K) | [Sarvam blog](https://www.sarvam.ai/blogs/bulbul-v4-flash), 2026-10-17 — list price; a launch offer halves it until 2026-11-12 |
| Cartesia | `sonic-3` | about $0.039 (derived) | [Cartesia](https://cartesia.ai/pricing), 2026-09-22 |
| Mistral | `voxtral-mini-tts-2603` | $0.016 | [Mistral](https://mistral.ai/pricing/api), 2026-09-22 |

**Cartesia is derived, not quoted.** Cartesia publishes plan tiers, not a per-unit price. These
rates come from the Startup tier ($49 a month for 1.25M credits). Replace them with your contract
rate if you have one.

**Sarvam is priced in INR** and converted at a fixed 1 USD = INR 83.75. Only USD is returned by the
API.

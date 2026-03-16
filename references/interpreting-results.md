# Interpreting Results

## First Table

- `Target Name`: official provider endpoint being probed
- `Exit IP / Result`: the IP observed by that target

This table answers the main question: which IP does each provider actually see?

## Rollup Table

- `Exit IP`: unique observed IP
- `Geo`: country/city/ISP style location summary returned by the verifier
- `Profile`: combined IP-intel labels, for example `Hosting, VPN, ISP`
- `Score`: `0-100`, where higher is cleaner and lower risk
- `Confidence`: how consistently multiple IP-intel sources agreed on the high-level direction
- `Purity`: visual bar where greener is cleaner and redder is dirtier

## How To Use It For OpenClaw

- Test the full set of providers that are currently configured and available in OpenClaw for the current run.
- Do not silently narrow the check to only the currently active provider unless the user explicitly requests an active-only test.
- If some configured providers have no measurable official target, list them as untested.
- If most or all provider targets show the same clean-looking IP, the path is probably suitable.
- If providers split across different IPs, OpenClaw traffic is likely not leaving through one consistent path.
- If the only observed IP scores as `Hosting`, `VPN`, or `Proxy`, assume the egress is not residential enough.
- Use the same direct/proxy path OpenClaw actually uses, otherwise the result is not representative.

## Chat Rendering Guidance

When the result is sent through Telegram or another chat surface:

- Keep the two-section structure from the CLI mental model.
- Prefer compact grouped blocks over wide pipe tables when the UI is narrow.
- Group repeated targets under the same IP instead of printing the same IP on every line.
- Use aligned key-value lines for the rollup if a full table would wrap.
- Always keep `Geo` in the rollup section, even if the user did not ask for it explicitly.
- Replace color-only meaning with text cues such as `Cleanliness`, `Signal Bar`, and a confidence cue.
- Add light, bright emoji anchors and tree glyphs so the message is easier to scan in Telegram.
- Group the report by tested path or port, but prefer a single shared code block when comparing multiple paths.
- Collapse multiple low-level probes into the OpenClaw provider name the user actually sees in the model/auth menu.

## Text Replacements For Visual Signals

Use these when the original CLI color/purity feel would otherwise be lost:

- `Cleanliness`
  - Human label derived from score
  - Example: `Very Clean`, `Clean`, `Fair`, `Borderline`, `Risky`, `Dirty`

- `Signal Bar`
  - Fixed-width 6-slot chat-friendly bar
  - Prefer a light hierarchy, for example: `🥗🍙🍙🍙▫️▫️`
  - If emoji look bad in the target UI, fall back to Unicode circles, for example: `●●●●○○`
  - `🥗` should stay sparse. Let `🍙` carry most mid-range positive weight so the bar does not look too heavy.

- `Confidence Cue`
  - Short word after confidence to convey stability
  - Example: `59% mixed`, `88% strong`

- `Emoji Anchors`
  - Use a small number of section markers such as `🌈`, `🧭`, `🍃`, `🪄`
  - Do not spam emojis on every line

- `Grouped Tree Layout`
  - Inside code blocks, prefer:
    - source label like `[direct]` or `[http://127.0.0.1:7890]`
    - one IP line
    - child target lines using `├─` and `└─`

- `Light Divider`
  - A single divider line near the top of each code block can make the message feel more polished

- `Path-Scoped Blocks`
  - Keep target hits and rollup together for each tested path
  - Prefer one shared code block for the whole report
  - Separate paths with decorated headers instead of opening a new code block each time

- `Active Channel Marker`
  - When the current OpenClaw provider is known, prefix that provider line with `⭐`
  - This is preferred over Markdown bold inside code blocks, since bold will not render there

- `Provider Labeling`
  - Prefer user-facing provider names such as `OpenAI`, `Anthropic`, `MiniMax`, `xAI (Grok)`, `Mistral AI`, `Together AI`, and `Copilot`
  - Avoid raw probe labels such as `OpenAI OAuth`, `ChatGPT`, `Platform`, `Anthropic Console`, or `Mistral API` in the final chat summary

- `Conclusion Discipline`
  - Keep conclusion text compact
  - Emphasize the detection result itself over narrative explanation
- Good conclusion elements:
    - final exit IP
    - profile/risk direction
    - same-path or split-path finding
  - Avoid long retrospective wording unless the user explicitly asks for debugging detail

- `Untested Providers`
  - If OpenClaw is configured with providers that are outside the measurable target set, show them explicitly as untested
  - Do not silently treat "not tested" as if it were "passed"

These should supplement, not replace:

- `Geo`
- `Profile`
- `Score`
- `Confidence`

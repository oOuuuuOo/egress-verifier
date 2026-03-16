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

## Text Replacements For Visual Signals

Use these when the original CLI color/purity feel would otherwise be lost:

- `Cleanliness`
  - Human label derived from score
  - Example: `Very Clean`, `Clean`, `Fair`, `Borderline`, `Risky`, `Dirty`

- `Signal Bar`
  - Fixed-width 10-slot chat-friendly bar
  - Prefer cute but intuitive markers, for example: `🍔🍔🍔🍔🍔🍔🍔🍟▫️▫️`
  - If emoji look bad in the target UI, fall back to Unicode circles, for example: `●●●●●●●○○○`

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

- `Active Channel Marker`
  - When the current OpenClaw provider is known, prefix that provider line with `⭐`
  - This is preferred over Markdown bold inside code blocks, since bold will not render there

These should supplement, not replace:

- `Geo`
- `Profile`
- `Score`
- `Confidence`

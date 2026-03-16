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

## Text Replacements For Visual Signals

Use these when the original CLI color/purity feel would otherwise be lost:

- `Cleanliness`
  - Human label derived from score
  - Example: `Very Clean`, `Clean`, `Fair`, `Borderline`, `Risky`, `Dirty`

- `Signal Bar`
  - Fixed-width 10-slot ASCII bar
  - Example: `[#######---]`

- `Confidence Cue`
  - Short word after confidence to convey stability
  - Example: `59% mixed`, `88% strong`

These should supplement, not replace:

- `Geo`
- `Profile`
- `Score`
- `Confidence`

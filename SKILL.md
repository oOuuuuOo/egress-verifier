---
name: openclaw-egress-verifier
description: Verify whether OpenClaw-related model/API traffic exits through a clean residential-looking IP by probing official provider endpoints and summarizing IP risk. Use this skill when you need to check whether direct traffic or a local proxy port is reaching AI providers with the expected egress quality before production use.
---

# OpenClaw Egress Verifier

## Overview

Use this skill to verify whether OpenClaw-facing traffic reaches official AI provider endpoints with a clean-looking exit IP. The bundled verifier probes provider domains, extracts the observed egress IP when possible, and summarizes residential-vs-non-residential risk.

## When To Use It

- Before routing OpenClaw through a new residential proxy, Clash port, or local proxy.
- After changing VPS networking, tunneling, or outbound policy.
- When AI responses look degraded and you want to rule out dirty egress.
- When you want a quick report showing which official providers see which exit IP.

## Workflow

1. Decide the real network path OpenClaw uses.
   Usually this is `direct`, a local `http/socks` port, or a local proxy exposed by Clash/Mihomo.
2. Run the wrapper script from `scripts/run_verifier.sh`.
3. Read the first table as the per-provider observed exit IP.
4. Read the rollup table as the IP-quality summary for unique exit IPs.
5. When reporting results back to the user, preserve the verifier's richness:
   include exit IP, Geo, Profile, Score, Confidence, and the overall summary.

## Quick Start

Run direct:

```bash
./scripts/run_verifier.sh direct
```

Run through a local proxy port:

```bash
./scripts/run_verifier.sh 7890
```

Run through a full proxy URL:

```bash
./scripts/run_verifier.sh socks5://127.0.0.1:7891
```

If the host does not already have the verifier dependencies, create a local venv first:

```bash
python3 -m venv venv
./venv/bin/pip install -r scripts/requirements.txt
OPENCLAW_EGRESS_PYTHON=./venv/bin/python ./scripts/run_verifier.sh direct
```

## What Is Bundled

- `scripts/openclaw_egress_verifier.py`
  The verifier engine copied from the working project.
- `assets/targets.toml`
  Official provider targets that currently return real exit IPs.
- `references/interpreting-results.md`
  How to read score, confidence, profile, and purity.

## Rules

- Prefer the same outbound path OpenClaw really uses.
- Do not add provider targets that only prove reachability. Keep targets focused on real exit-IP reflection.
- If a provider does not expose a stable official IP-reflection endpoint, leave it out rather than inventing a fake signal.
- Preserve the existing output shape unless the user explicitly asks to redesign it.
- Always include `Geo` when summarizing a unique exit IP. Do not drop it just because the CLI table hides it.
- For chat surfaces such as Telegram, prefer a compact ASCII/Markdown table inside a code block instead of loose bullets.
- Keep the content rich, but mirror the CLI mental model:
  one section for per-target IPs, one section for unique IP rollup, then a short conclusion.
- In narrow chat UIs, do not render wide pipe tables that wrap badly. Prefer compact grouped lists in code blocks.
- If many targets share the same IP, group them under that IP instead of repeating the same long IPv6 on every line.
- Keep total wording tight. Avoid repeating the same verdict in the heading, summary, and conclusion.
- Replace terminal-only visuals such as color and bar charts with compact text signals that still preserve reading feel.
- Always add a short cleanliness band and a signal bar in chat output so the user can feel the result at a glance.
- Prefer emoji or natural Unicode symbols over engineering-style placeholders such as `[####---]`.
- Use a small number of bright, friendly section emojis and line-prefix markers to improve scanability.
- Do not rely on real text color in chat. Simulate emphasis with emoji, spacing, and concise labels.
- When the currently configured OpenClaw provider/channel is known, mark it explicitly inside the grouped list.
- Group chat output by tested path or port. Each tested path should read like one self-contained block.
- Prefer a single shared code block when multiple tested paths are being compared in one reply.
- Distinguish each tested path header with decorative divider characters so the eye can jump between them quickly.

## Updating Targets

When adding providers, only keep targets that satisfy all of the following:

- Official provider-owned domain
- Stable endpoint
- No authentication required for the probe
- Returns the caller's real observed IP at the target side

If you need help interpreting the report, read `references/interpreting-results.md`.

## Reporting Template

When OpenClaw reports results in chat, use this structure:

1. Short one-line finding.
2. Prefer one compact shared code block for the whole report.
3. Inside that block, separate each tested path with a decorated header and keep its hits+rollup together.
4. A short conclusion in prose.

Preferred chat rendering:

```text
🌈 Result: HTTP 和 SOCKS 都落到同一个出口 IPv6。

╭─ 🧪 [http://127.0.0.1:18080] ─────────
│  🧭 Target hits
│  └─ 2600:1700:...:72f0
│     ├─ ⭐ OpenAI OAuth / ChatGPT / Platform
│     ├─ Anthropic Console / Claude
│     ├─ MiniMax Intl Web / Platform
│     ├─ xAI Grok
│     ├─ Mistral API / Chat
│     ├─ Together AI
│     └─ Microsoft Copilot
│  🍃 Rollup
│  Geo         : US Warrenville AT&T Enterprises, LLC
│  Profile     : ISP, Business
│  Score       : 75 Moderate Risk
│  Confidence  : 59% mixed
│  Cleanliness : 🌼 Clean
│  Signal Bar  : 🍔🍔🍔🍔🍔🍔🍔🍟▫️▫️
╰───────────────────────────────────────

╭─ 🧪 [socks5://127.0.0.1:11080] ──────
│  🧭 Target hits
│  └─ 2600:1700:...:72f0
│     ├─ ⭐ OpenAI OAuth / ChatGPT / Platform
│     ├─ Anthropic Console / Claude
│     ├─ MiniMax Intl Web / Platform
│     ├─ xAI Grok
│     ├─ Mistral API / Chat
│     ├─ Together AI
│     └─ Microsoft Copilot
│  🍃 Rollup
│  Geo         : US Warrenville AT&T Enterprises, LLC
│  Profile     : ISP, Business
│  Score       : 75 Moderate Risk
│  Confidence  : 59% mixed
│  Cleanliness : 🌼 Clean
│  Signal Bar  : 🍔🍔🍔🍔🍔🍔🍔🍟▫️▫️
╰───────────────────────────────────────
```

🪄 Conclusion
当前各测试路径的结果一致，说明这些本地链路当前落到同一个出口。

## Chat Signal Mapping

When terminal colors are unavailable, add these text replacements:

- `Cleanliness`
  - `90-100`: `Very Clean`
  - `75-89`: `Clean`
  - `60-74`: `Fair`
  - `40-59`: `Borderline`
  - `20-39`: `Risky`
  - `0-19`: `Dirty`

- `Signal Bar`
  - Render a fixed-width 10-slot bar
  - Prefer lively but intuitive symbols in chat:
    - strong/clean segment: `🍔`
    - transitional/risk segment: `🍟`
    - remaining/empty slots: `▫️`
  - If emoji rendering is poor, fall back to Unicode circles:
    - retained cleanliness: `●`
    - remaining/empty slots: `○`
  - Example:
    - `92` -> `🍔🍔🍔🍔🍔🍔🍔🍔🍔▫️`
    - `75` -> `🍔🍔🍔🍔🍔🍔🍔🍟▫️▫️`
    - `38` -> `🍔🍔🍔🍟🍟▫️▫️▫️▫️▫️`
    - `0` -> `🍟🍟🍟▫️▫️▫️▫️▫️▫️▫️`

- `Confidence Cue`
  - Append a short cue after confidence:
    - `80-100`: `strong`
    - `60-79`: `usable`
    - `40-59`: `mixed`
    - `0-39`: `weak`

Preferred rollup line in chat:

```text
Confidence : 59% mixed
```

- `Section Emojis`
  - Use them sparingly:
    - `🌈` result
    - `🧭` per-target section
    - `🍃` rollup section
    - `🪄` conclusion

- `Cleanliness Emoji`
  - Add a small severity cue before the cleanliness word:
    - `🌿 Very Clean`
    - `🌼 Clean`
    - `🍋 Fair`
    - `🟠 Borderline`
    - `🌶️ Risky`
    - `🔥 Dirty`

- `Tree Layout`
  - For repeated IP groups, use lightweight tree glyphs:
    - `└─`, `├─`
  - This makes sections easier to scan than flat wrapped lines.

- `Light Divider`
  - One short divider line inside each code block helps chunk the message without becoming noisy.
  - Example:
    - `──────── 🧭 Per-target exit IPs ────────`

- `Block Grouping Rule`
  - Prefer one shared code block for the whole message.
  - Keep each tested path self-contained inside that block.
  - Use a decorated path header to separate paths clearly.

- `Path Header Style`
  - Make each tested path easy to spot with a header line such as:
    - `╭─ 🧪 [http://127.0.0.1:18080] ─────────`
    - `╰───────────────────────────────────────`

- `Active Channel Marker`
  - If the current OpenClaw model/auth provider is known, mark that line with `⭐`
  - Keep only one primary active marker unless the user is deliberately testing multiple active providers
  - Example:

```text
   ├─ ⭐ OpenAI OAuth / ChatGPT / Platform
```

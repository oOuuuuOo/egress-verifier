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
2. Determine which OpenClaw providers are currently configured and available in this workspace.
3. Run the wrapper script from `scripts/run_verifier.sh`, passing all of those configured providers with repeated `--provider`.
4. Read the first table as the per-provider observed exit IP.
5. Read the rollup table as the IP-quality summary for unique exit IPs.
6. When reporting results back to the user, preserve the verifier's richness:
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

Run all providers currently configured in OpenClaw:

```bash
./scripts/run_verifier.sh 7890 --provider OpenAI --provider Anthropic
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
- Test the full set of providers currently configured and available in OpenClaw for this run.
- Do not limit the run to only the currently selected or currently active provider unless the user explicitly asks for that narrower check.
- Do not default to the whole provider superset unless the user explicitly asks for a broad sweep.
- If OpenClaw has configured providers that do not exist in the bundled measurable target set, do not silently drop them. Report them as untested.
- Do not add provider targets that only prove reachability. Keep targets focused on real exit-IP reflection.
- If a provider does not expose a stable official IP-reflection endpoint, leave it out rather than inventing a fake signal.
- Preserve the existing output shape unless the user explicitly asks to redesign it.
- Always include `Geo` when summarizing a unique exit IP. Do not drop it just because the CLI table hides it.
- For chat surfaces such as Telegram, prefer a compact ASCII/Markdown table inside a code block instead of loose bullets.
- Keep the content rich, but mirror the CLI mental model:
  one section for per-target IPs, one section for unique IP rollup, then a short conclusion.
- In narrow chat UIs, do not render wide pipe tables that wrap badly. Prefer compact grouped lists in code blocks.
- If many targets share the same IP, group them under that IP instead of repeating the same long IPv6 on every line.
- When the main exit IP is long, prefer putting it on its own short line outside the code block.
- Keep the long exit IP outside the code block. Inside each path block, use section headers plus tree lines to preserve hierarchy without repeating the IP.
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
- In chat output, provider names should align with OpenClaw's channel names rather than raw probe labels.
- If multiple internal probes belong to one provider, collapse them into the single provider name the OpenClaw user expects.
- Keep `Geo` very short in chat output. Prefer `flag + highest-level useful geography/provider hint`, for example `🇺🇸 AT&T`.
- Avoid long raw strings such as full legal entity names, repeated country codes, or full ASN labels in the chat rollup.
- Prefer short rollup field names in chat. Use `Geo`, `Tags`, `Risk`, `Clean`, `Conf`, and `Rate`.

## Updating Targets

When adding providers, only keep targets that satisfy all of the following:

- Official provider-owned domain
- Stable endpoint
- No authentication required for the probe
- Returns the caller's real observed IP at the target side

If you need help interpreting the report, read `references/interpreting-results.md`.

## Provider Filter

`assets/targets.toml` is a provider superset, not a mandate to test everything every time.

Use repeated `--provider` flags to match the full OpenClaw provider set currently configured for the current run:

```bash
./scripts/run_verifier.sh direct --provider OpenAI --provider Anthropic --provider "xAI (Grok)"
```

Current provider labels in the bundled target file include:

- `OpenAI`
- `Anthropic`
- `MiniMax`
- `xAI (Grok)`
- `Mistral AI`
- `Together AI`
- `Copilot`

If a requested provider has no measurable target in `assets/targets.toml`, it should appear in the final report as `Untested providers` rather than being silently omitted.

Important:

- `configured providers` means all providers currently available in the user's OpenClaw configuration for this workspace/session.
- It does not mean only the single provider currently selected in the UI.
- If OpenClaw has 6 configured providers and only 1 is currently active, the default verification scope should still include all 6 configured providers unless the user asks for active-only behavior.

## Reporting Template

When OpenClaw reports results in chat, use this structure:

1. Short one-line finding.
2. Put the main observed exit IP on a short line before the code block when that reduces wrapping.
3. Prefer one compact shared code block for the whole report.
4. Inside that block, separate each tested path with a decorated header and keep its hits+rollup together.
5. A short conclusion in prose.

Preferred chat rendering:

```text
🌈 Result: HTTP 和 SOCKS 都落到同一个出口 IPv6。

IP: `2600:1700:...:72f0`

╭─ 🧪 [http://127.0.0.1:18080] ─────────
│  Hits
│  ├─ ⭐ OpenAI
│  ├─ Anthropic
│  ├─ MiniMax
│  ├─ xAI (Grok)
│  ├─ Mistral AI
│  ├─ Together AI
│  └─ Microsoft Copilot
│  Roll
│  ├─ Geo  : 🇺🇸 AT&T
│  ├─ Tags : ISP, Business
│  ├─ Risk : 75 Moderate
│  ├─ Clean: 🌼 Fair
│  ├─ Conf : 59% mixed
│  └─ Rate : ●●●◐○○
╰───────────────────────────────────────

╭─ 🧪 [socks5://127.0.0.1:11080] ──────
│  Hits
│  ├─ ⭐ OpenAI
│  ├─ Anthropic
│  ├─ MiniMax
│  ├─ xAI (Grok)
│  ├─ Mistral AI
│  ├─ Together AI
│  └─ Microsoft Copilot
│  Roll
│  ├─ Geo  : 🇺🇸 AT&T
│  ├─ Tags : ISP, Business
│  ├─ Risk : 75 Moderate
│  ├─ Clean: 🌼 Fair
│  ├─ Conf : 59% mixed
│  └─ Rate : ●●●◐○○
╰───────────────────────────────────────
```

🪄 Conclusion
当前各测试路径的结果一致，说明这些本地链路当前落到同一个出口。

## Conclusion Style

- Keep the conclusion short and detection-first.
- Prefer 2 to 4 short lines, or 1 very short paragraph.
- Focus on:
  - final observed exit IP
  - profile/risk direction
  - whether tested paths matched or differed
- Only mention root-cause explanation if it is truly useful and can fit in one short sentence.
- Avoid long retrospective narration such as "this time it became reasonable because..." unless the user explicitly asks for debugging context.

Preferred conclusion pattern:

```text
🪄 Conclusion

direct 的真实落地 IP 是 2607:9d00:2000:55::2。
该出口当前呈现 Hosting, VPN 特征。
这次 direct 与代理结果已分离，说明当前检测链路有效。
```

## Chat Signal Mapping

When terminal colors are unavailable, add these text replacements:

- `Risk`
  - Short risk label derived from score
  - Example: `92 Low`, `75 Moderate`, `38 High`

- `Clean`
  - Short cleanliness band derived from score
  - Add one light emoji before the word for faster reading
  - Example: `🌿 Very Clean`, `🌼 Clean`, `🍋 Fair`, `🌶️ Risky`, `🔥 Dirty`

- `Rate`
  - Render a fixed-width continuous 6-slot progress bar
  - Prefer compact continuous symbols with half-step support, for example: `●●●◐○○`
  - If a brighter style is needed, keep it continuous rather than mixing unrelated icons
  - Example:
    - `92` -> `●●●●◐○`
    - `75` -> `●●●◐○○`
    - `68` -> `●●●○○○`
    - `38` -> `●◐○○○○`
    - `0` -> `○○○○○○`

- `Conf`
  - Append a short cue after confidence:
    - `80-100`: `strong`
    - `60-79`: `usable`
    - `40-59`: `mixed`
    - `0-39`: `weak`

Preferred rollup line in chat:

```text
Conf : 59% mixed
```

- `Section Emojis`
  - Use them sparingly:
    - `🌈` result
    - `🧭` per-target section
    - `🍃` rollup section
    - `🪄` conclusion

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
   ├─ ⭐ OpenAI
```

- `Provider Naming Rule`
  - In chat output, prefer the OpenClaw-facing provider name:
    - `OpenAI`
    - `Anthropic`
    - `MiniMax`
    - `Moonshot AI`
    - `Google`
    - `xAI (Grok)`
    - `Mistral AI`
    - `Together AI`
    - `Copilot`
  - Do not expose low-level probe names such as `OAuth`, `Platform`, `Console`, `Web`, or `API` unless the user explicitly asks for probe-level detail.

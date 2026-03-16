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
2. A compact code block for grouped per-target exit IPs.
3. A compact code block for unique exit-IP rollup.
4. A short conclusion in prose.

Preferred chat rendering:

```text
Result: HTTP 和 SOCKS 都落到同一个出口 IPv6。

Per-target exit IPs
```text
2600:1700:...:72f0
  OpenAI OAuth / ChatGPT / Platform
  Anthropic Console / Claude
  MiniMax Intl Web / Platform
  xAI Grok
  Mistral API / Chat
  Together AI
  Microsoft Copilot
```

Exit IP rollup
```text
IP         : 2600:1700:...:72f0
Geo        : US Warrenville AT&T Enterprises, LLC
Profile    : ISP, Business
Score      : 75 Moderate Risk
Confidence : 59%
```

Conclusion
当前路径对已覆盖的官方目标呈现单一出口，整体更像 ISP/住宅侧，而不是明显机房/VPN 出口。
```

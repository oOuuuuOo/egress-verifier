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

## Updating Targets

When adding providers, only keep targets that satisfy all of the following:

- Official provider-owned domain
- Stable endpoint
- No authentication required for the probe
- Returns the caller's real observed IP at the target side

If you need help interpreting the report, read `references/interpreting-results.md`.

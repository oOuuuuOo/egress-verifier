# Egress Verifier

![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-4f46e5?style=flat-square)
![Egress Verification](https://img.shields.io/badge/Focus-Egress%20Verification-0f766e?style=flat-square)
![AI Routing](https://img.shields.io/badge/Use%20Case-AI%20Routing-2563eb?style=flat-square)
![IP Quality](https://img.shields.io/badge/Checks-IP%20Quality-f59e0b?style=flat-square)
![Provider Side](https://img.shields.io/badge/Measures-Provider--Observed%20IP-7c3aed?style=flat-square)

`egress-verifier` is an OpenClaw skill for checking what IP official AI provider endpoints actually see when your traffic leaves the machine.

It is built for the real-world situation where a model chain may look correct locally, but the final egress is still wrong: a VPS IP leaks out, a dirty proxy is still in use, IPv4 and IPv6 split unexpectedly, or one provider sees a different path from the others.

## Why This Skill Exists

When you run OpenClaw through `direct`, Clash, Mihomo, a local HTTP/SOCKS port, or a residential tunnel, the question that matters is not "did the proxy process start?".

The real question is:

- what exit IP does the provider actually see
- whether all configured providers are leaving through the same path
- whether that exit looks clean enough for AI usage

This skill exists to answer that question before you trust a route in production.

## When You Should Use It

Use this skill when you are:

- moving OpenClaw onto a new residential proxy or home IP tunnel
- checking whether `direct` and local proxy modes really split as expected
- validating Clash/Mihomo ports before daily use
- comparing IPv4 and IPv6 behavior indirectly through provider-side observations
- trying to reduce model degradation, strange refusals, low-quality answers, or API-side account risk caused by bad egress

## What You Gain

This skill helps you:

- verify the real provider-observed exit IP instead of guessing from local config
- catch misrouting early, before AI traffic starts leaking through the wrong path
- spot when different providers are seeing different exits
- judge whether an exit looks more like ISP/residential, business, hosting, VPN, or proxy infrastructure
- make better routing decisions for OpenAI, Anthropic, MiniMax, Copilot, and other supported providers

## What Pitfalls It Helps You Avoid

This skill is especially useful for avoiding these common traps:

- assuming `direct` is truly direct when environment proxy variables are still being inherited
- assuming a local proxy port is clean because it works, even though providers still see a VPS or hosting IP
- assuming all providers share one exit path when only the currently active channel was checked
- trusting reachability-only tests that never reveal the final provider-side IP
- over-trusting one IP reputation site without comparing multiple signals

## How It Works

The bundled verifier probes official provider-owned endpoints that can reflect the caller's real exit IP. It then combines multiple IP-intel sources into a practical AI-usage profile.

The current output is designed to answer:

- which IP each provider saw
- whether all configured providers converged on the same exit
- what kind of network that exit resembles
- whether the route looks acceptable for AI model/API usage

## Typical Usage

Test the real direct path:

```bash
./scripts/run_verifier.sh direct --show-summary-only
```

Test a local proxy port:

```bash
./scripts/run_verifier.sh 7890
```

Test only the providers currently configured in OpenClaw:

```bash
./scripts/run_verifier.sh 7890 --provider OpenAI --provider Anthropic --provider "xAI (Grok)"
```

## Example Results

The examples below use fake data and masked IPs. They are only meant to show the reporting style and how to interpret different outcomes.

### Example 1: One Stable, Usable Exit

This is the happy path: all configured providers converge on one exit, and the profile looks acceptable for AI use.

```text
🌈 Result: all configured providers converged on one exit IPv6.

IP: `2600:db8:1111:22::8`

╭─ 🧪 [http://127.0.0.1:18080]
│  Hits
│  ├─ ⭐ OpenAI
│  ├─ Anthropic
│  ├─ MiniMax
│  └─ Copilot
│  Roll
│  ├─ Geo  : 🇺🇸 ISP
│  ├─ Tags : ISP, Business
│  ├─ Risk : 74 Moderate
│  ├─ Clean: 🌼 Clean
│  ├─ Conf : 68% usable
│  └─ Rate : ●●●◐○○
╰──────────────

🪄 Conclusion
The configured providers are leaving through one consistent exit.
This route looks generally usable for AI traffic.
```

### Example 2: Hosting/VPN-Looking Exit

This is the case you usually want to catch before production use: the path works, but the final provider-side exit still looks like hosting or VPN infrastructure.

```text
🌈 Result: the configured providers converged on one non-residential exit.

IP: `2001:db8:44:55::19`

╭─ 🧪 [direct]
│  Hits
│  ├─ ⭐ OpenAI
│  ├─ MiniMax
│  └─ Copilot
│  Roll
│  ├─ Geo  : 🇳🇱 Hosting
│  ├─ Tags : Hosting, VPN
│  ├─ Risk : 33 High
│  ├─ Clean: 🌶️ Risky
│  ├─ Conf : 91% strong
│  └─ Rate : ●◐○○○○
╰──────────────

🪄 Conclusion
The route is stable, but the final exit still looks like hosting/VPN infrastructure.
This is the kind of path that can be usable technically while still being risky for AI quality or account safety.
```

### Example 3: Split Exit Across Providers

This is the "routing inconsistency" case: the path is not leaking through one clean route. Different providers are seeing different exits.

```text
🌈 Result: configured providers did not converge on one exit.

╭─ 🧪 [socks5://127.0.0.1:11080]
│  Hits
│  ├─ ⭐ OpenAI         -> 203.0.113.24
│  ├─ Anthropic        -> 203.0.113.24
│  ├─ MiniMax          -> 198.51.100.17
│  └─ Copilot          -> 198.51.100.17
│  Roll
│  ├─ Geo  : 🌍 Split
│  ├─ Tags : Mixed paths
│  ├─ Risk : 48 Elevated
│  ├─ Clean: 🍋 Fair
│  ├─ Conf : 62% usable
│  └─ Rate : ●●◐○○○
╰──────────────

🪄 Conclusion
The proxy path is not producing one consistent provider-side exit.
Before trusting this route, fix the split and retest.
```

### Why These Examples Matter

These examples map directly to common operational decisions:

- Example 1:
  this is the kind of result you want before daily OpenClaw use.
- Example 2:
  this is the kind of result that explains why a route may still feel "wrong" even if requests technically succeed.
- Example 3:
  this is the kind of result that reveals hidden routing mistakes, dual-stack surprises, or policy mismatches.

## What Is In This Repo

- `SKILL.md`
  The OpenClaw skill instructions and reporting rules.
- `scripts/run_verifier.sh`
  Wrapper for local execution.
- `scripts/openclaw_egress_verifier.py`
  The verifier engine used by the skill.
- `assets/targets.toml`
  Official measurable targets that return target-side observed IPs.
- `OPENCLAW_INSTALL.md`
  Installation guide for cloning this skill into an OpenClaw skills directory.

## Important Boundary

This project intentionally does not keep targets that only prove reachability.

If a provider endpoint is official but cannot reliably reveal the target-side observed exit IP, it is not treated as a first-class measurement target here. That keeps the report focused on what actually matters for AI routing decisions.

## Install

See [OPENCLAW_INSTALL.md](./OPENCLAW_INSTALL.md).

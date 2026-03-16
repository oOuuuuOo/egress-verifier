# OpenClaw Install Guide

This repository is an OpenClaw skill bundle. OpenClaw does not need the files copied by hand one-by-one; it only needs this folder to exist under one of its skill search paths.

## Repo

```text
https://github.com/oOuuuuOo/egress-verifier.git
```

## Install Into One Workspace

Use this when the skill should only apply to one OpenClaw workspace or one agent workspace.

```bash
mkdir -p ./skills
git clone https://github.com/oOuuuuOo/egress-verifier.git ./skills/openclaw-egress-verifier
```

If the repo already exists locally:

```bash
cd ./skills/openclaw-egress-verifier
git pull --ff-only
```

## Install As A Shared Skill

Use this when every OpenClaw agent on the same machine should be able to see the skill.

```bash
mkdir -p ~/.openclaw/skills
git clone https://github.com/oOuuuuOo/egress-verifier.git ~/.openclaw/skills/openclaw-egress-verifier
```

If already installed:

```bash
cd ~/.openclaw/skills/openclaw-egress-verifier
git pull --ff-only
```

## Refresh OpenClaw

After cloning or updating the repo:

- Start a new OpenClaw session, or
- Ask the agent to refresh skills, or
- Restart the gateway if your setup caches skill state

OpenClaw loads skills from:

- `<workspace>/skills`
- `~/.openclaw/skills`

Workspace skills override shared skills if the skill name conflicts.

## Dependencies

The skill runs a Python verifier script.

If the host does not already have the dependencies, install them in a local virtual environment inside the cloned skill:

```bash
cd ~/.openclaw/skills/openclaw-egress-verifier
python3 -m venv venv
./venv/bin/pip install -r scripts/requirements.txt
OPENCLAW_EGRESS_PYTHON=./venv/bin/python ./scripts/run_verifier.sh direct
```

The wrapper script will also try these Python interpreters automatically:

1. `OPENCLAW_EGRESS_PYTHON`
2. `./venv/bin/python` inside the skill folder
3. `/home/split-tunnel/venv/bin/python`
4. `python3`

## How To Use In OpenClaw

Example prompts:

```text
Use $openclaw-egress-verifier to verify whether my current direct traffic exits through a clean IP.
```

```text
Use $openclaw-egress-verifier to test whether proxy port 7890 reaches official AI targets with a clean-looking exit IP.
```

## Important Limitation

This skill only keeps targets that return the target-side observed exit IP. It intentionally does not keep provider endpoints that only prove reachability.

## When To Use ClawHub Instead

If you want one-command installation like:

```bash
clawhub install <skill-slug>
```

then publish this repository as a ClawHub skill first. A plain GitHub repository is best used with `git clone` into one of OpenClaw's skill directories.

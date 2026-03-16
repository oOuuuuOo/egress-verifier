# egress-verifier

OpenClaw skill for verifying whether official AI provider endpoints see a clean-looking exit IP.

## Skill path

- `SKILL.md`
- `scripts/run_verifier.sh`
- `assets/targets.toml`

## Example

```bash
./scripts/run_verifier.sh direct --show-summary-only
./scripts/run_verifier.sh 7890
```

# Starter Packs

Pre-configured capability bundles for quick onboarding.

## Available Packs

| Pack | Description | Use When |
|------|-------------|----------|
| `minimal.yaml` | Validation only — pre-commit hooks + CI | You just want quality gates, nothing else |
| `standard.yaml` | Validation + planning + PR ops + docs | **Recommended for most teams** |
| `full.yaml` | Everything available | You want all capabilities from day one |

## How to Use

1. Pick a starter pack
2. Run `Sync-CapabilityPacks.ps1` with the pack file:
   ```powershell
   pwsh scripts/repo-ops/Sync-CapabilityPacks.ps1 -PackFile starter-packs/standard.yaml
   ```
3. The script syncs all capabilities listed in the pack to your repo

See [Pack Adoption Guide](../docs/for-developers/Pack-Adoption-Guide.md) for details.

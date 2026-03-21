---
scope: all
---

# Devops Config

### SOPS-Encrypted File Editing

- Never hand-edit SOPS-encrypted files directly — always use `sops` to decrypt, edit, and re-encrypt
- Manual edits break the verification hash, causing silent decryption failures at runtime
- In devcontainer env configs, prefer IP addresses (127.0.0.1) over hostnames (localhost) to avoid DNS resolution differences across networks

```yaml
# Bad - editing .env.enc by hand
vim .devcontainer/.env.enc  # hash now invalid

# Good
sops .devcontainer/.env.enc  # decrypts, opens editor, re-encrypts with valid hash
```

_Sources: PR #6053, PR #5204_

### Remove Stale Config on Auth Changes

- When switching authentication mechanisms (e.g., API keys to JWTs), audit and remove old config entries
- Stale credentials create confusion about which auth is active and remain a security risk if unmonitored

```hcl
# Bad - old API key config left behind after switching to JWT auth
internal_api_key = "..."  # unused, now authenticating via JWT from microservice

# Good - delete the superseded config entry entirely
```

_Sources: PR #5857_

### Build-Time vs Runtime Config in Next.js

- next.config.js is evaluated at build time — environment-specific values cannot vary between deploys
- Next.js 14 middleware runs in edge runtime, also limited to build-time env vars
- For environment-specific HTTP headers (e.g., CSP), set them at the k8s ingress layer for deployed environments
- Keep app-level header config only for local development where there is no ingress

_Sources: PR #6106_

### Dependency Version Bumps in PRs

- Isolate dependency version bumps from feature changes — bump in a separate preceding PR
- Version bumps can introduce subtle breaking changes and must be independently evaluable and revertible
- When adding new dependencies, verify license compatibility (e.g., BSD-3-Clause distribution requirements)
- Confirm license comments survive the build/minification pipeline

_Sources: PR #6150, PR #5516_

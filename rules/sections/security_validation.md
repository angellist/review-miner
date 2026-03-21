---
scope: all
---

# Security Validation

### Domain and Origin Validation

- Never use `String.includes()` for domain or origin validation — it allows bypass via crafted subdomains.
- Use exact match or suffix match with a leading dot (`.example.com`) for boundary checking.

```ts
// Bad — "usvc.com.evil.com".includes("usvc.com") === true
if (hostname.includes("usvc.com")) { allow(); }

// Good
if (hostname === "usvc.com" || hostname.endsWith(".usvc.com")) { allow(); }
```

_Sources: PR #6481_

### Sensitive Data Exclusion Lists

- When a system captures sensitive headers (auth tokens, API keys), ensure those headers are also stripped from persistence and hashing logic.
- Maintain a single, consistent exclusion list — don't add a header to capture without also adding it to the strip list.
- Audit new header additions against serialization, logging, and hash computation paths.

_Sources: PR #6855_

### Enum-Based Authorization Checks

- When checking enum values for access control, be precise about which values grant access.
- Semantically similar enum values (e.g., `approved` vs `approved_funds_only`) may have different access implications — include only the exact states that should pass.

```ts
// Bad — approved_funds_only is not full approval
const APPROVED_STATES = ["approved", "approved_funds_only"];

// Good
const APPROVED_STATES = [UserIppState.approved];
```

_Sources: PR #7127_

### Input Validation and Sanitization

- Validate string inputs (IDs, names, emails) for empty strings explicitly — empty strings pass some truthiness checks but cause downstream bugs.
- Use proven validation libraries (e.g., zod's `.email()`) instead of hand-rolled regexes for complex formats like email.
- Centralize validation logic into shared utilities so edge cases are fixed in one place.

```ts
// Bad — hand-rolled regex, scattered across services
const emailRegex = /^[a-zA-Z0-9+_.-]+@[a-zA-Z0-9.-]+$/;

// Good — use zod, centralized
import { z } from "zod";
const emailSchema = z.string().email();
```

_Sources: PR #7186, PR #3120_

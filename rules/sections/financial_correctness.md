---
scope: fullstack
---

# Financial Correctness

### Dollar-to-Cents Conversion

- Never use floating-point multiplication to convert dollar strings to cents — parse integer and decimal parts as strings and combine arithmetically.
- Keep intermediate calculations and return values in cents; converting to dollars mid-calculation introduces fractional cents that don't match integer storage.
- Money parsing functions should be strict by default: validate input format, reject ambiguous values (commas, scientific notation, >2 decimal places), and throw on invalid input.
- In TypeScript, use `toCentsStrict` (not a lenient conversion) when building monetary values in financial pipelines — it fails loudly on invalid or ambiguous amounts where silent precision loss is unacceptable.

```ts
// Bad — floating-point precision error
const cents = parseFloat("1.1") * 100; // 110.00000000000001

// Good — string-based parsing
const [dollars, frac = "0"] = "1.10".split(".");
const cents = Number(dollars) * 100 + Number(frac.padEnd(2, "0"));
```

_Sources: PR #5992, PR #6645, PR #7041_

### Transfer-Type-Specific Modeling

- Model ACH and wire transfer details as separate records — routing numbers and supported fields differ between payment rails.
- Apply transfer-type-specific validation (currency, fields, limits) rather than one-size-fits-all logic. ACH is USD-only; wires may support FX.
- Name payment method enums by mechanism (`internal`, `ach`, `wire`), not assumed outcome (`instant`, `balance`). Misleading names propagate false assumptions through the codebase and UI.

```ruby
# Bad — single record for both ACH and wire
bank_detail: { routing_number, account_number, transfer_type }

# Good — separate records per rail
ach_detail: { ach_routing_number, account_number }
wire_detail: { wire_routing_number, account_number, swift_code }
```

_Sources: PR #5687, PR #6048, PR #6093_

### Null vs Zero in Financial Fields

- Never coalesce null monetary values to zero. Null often means "use the default" — replacing it with zero changes the semantic meaning and causes incorrect calculations downstream.
- Make financial fields optional (nullable) when "not set" is a valid state distinct from zero.
- In Ruby, use `&.to_d` instead of `.to_d` when nil is semantically meaningful — `nil.to_d` silently returns `BigDecimal(0)`, corrupting "no value" into "zero".
- Guard against nil on optional monetary fields before performing comparisons or arithmetic.

```ruby
# Bad — nil.to_d silently becomes 0
total_carry: params[:total_carry].to_d

# Good — preserves nil semantics
total_carry: params[:total_carry]&.to_d
```

_Sources: PR #4103, PR #20247, PR #19232, PR #17788_

### Numeric Literals in Financial Code

- Use TypeScript numeric separators to visually distinguish dollars from cents in large cent values (`1_000_00` for $1,000.00).
- Extract financial magic numbers into named constants at module scope — even seemingly obvious values like a $1 threshold.
- Keep ordered constants (account numbers, enum values) in natural sort order to make gaps and duplicates visible during review.

```ts
// Bad — easy to miscount zeros
const limit = 100000;

// Good — self-documenting
const LIMIT_CENTS = 1_000_00; // $1,000.00
```

_Sources: PR #5774, PR #4616, PR #23155, PR #18265_

### GraphQL Monetary Types

- Use the project's Money type (not raw numerics or strings) for monetary input fields in GraphQL mutations.
- Use the `prepare` method on GraphQL input types to encapsulate Money conversion, eliminating repetitive boilerplate at call sites.
- Always enforce the expected currency explicitly rather than assuming it from context.
- Frontend should construct Money objects at the form boundary, not pass raw strings for backend conversion.

```ruby
# Good — prepare method handles conversion once
class MoneyInputType < BaseInputType
  argument :fractional, Integer
  argument :currency, String

  def prepare
    Money.new(fractional, currency)
  end
end
```

_Sources: PR #5834, PR #4886, PR #22880, PR #17200, PR #25056_

### Zero Handling in Financial UI

- Always handle the zero case explicitly for numeric financial values — zero is truthy-falsy-ambiguous and needs its own code path.
- Use TypeScript type predicates to combine type narrowing with domain validation in a single reusable helper.

```ts
// Good — reusable guard for non-zero financial values
const isNonZeroNumber = (value?: unknown): value is number =>
  typeof value === "number" && value > 0;
```

_Sources: PR #3068_

### Fail Loud on Invalid Financial State

- Prefer loud failures (assertions, exceptions, `Hash#fetch`) over silent fallbacks when a value represents invalid state.
- Use `Hash#fetch` over `Hash#[]` in monetary lookups — `fetch` raises a clear `KeyError` with the missing key, while `[]` returns nil that may silently become zero via `.to_d`.
- Don't add nil guards that mask real bugs. When a value is unexpectedly nil, investigate the root cause rather than papering over it.
- Use non-null assertions (`T.must`, `!`) over optional chaining when null represents a genuinely impossible state.

```ruby
# Bad — silent zero on missing key
amount = rates[currency].to_d

# Good — explicit error on missing key
amount = rates.fetch(currency)
```

_Sources: PR #22131, PR #20535, PR #26069, PR #23279, PR #20504_

### Summing Money Objects

- When summing Money objects in Ruby, always provide an explicit Money zero initializer with the correct currency — the default integer `0` accumulator causes coercion bugs.
- Ensure `sum` results are cast to BigDecimal (via `.to_d` or `sum(0.to_d)`) — an empty array's `sum` returns Integer `0`, breaking decimal arithmetic downstream.
- When aggregating monetary values, handle the empty-collection case explicitly — a sum of zero should still carry currency metadata.
- Never force currency conversion implicitly during summation; preserve the original currency.
- For large result sets, prefer ActiveRecord's SQL-level `sum(:column_name)` over Ruby's `Enumerable#sum` with a block — the block form loads all records into memory before summing.

```ruby
# Bad — integer 0 accumulator loses currency
closings.sum(&:wired_or_requested_amount)

# Good — explicit Money zero with currency
closings.sum(Money.zero(fund.currency), &:wired_or_requested_amount)

# For large sets, push to SQL
payments.sum(:amount_cents)
```

_Sources: PR #22505, PR #18484, PR #25294, PR #23279, PR #5016_

### Use Domain Accessors Over Raw Columns

- Use canonical domain accessors (like `wired_or_requested_amount`) instead of raw database columns (like `amount_cents`). These accessors encapsulate business rules about which value to use in different states.
- Use domain model methods (like `usd?`, `currency_is_usd?`) for currency checks rather than hardcoding string literals.
- Use `monetize` gem declarations (`amount` instead of `amount_cents`) rather than passing raw cent values. If a model is missing its `monetize` declaration, add it.
- Before writing inline lookups, check whether an InfoService or domain helper already provides the data.

```ruby
# Bad — raw column, no business logic
investment.amount_cents

# Good — encapsulates edge cases
investment.wired_or_requested_amount
```

_Sources: PR #26140, PR #26156, PR #17288, PR #22880, PR #21574, PR #25829_

### Multi-Currency Separation

- Never mix upstream (cost basis) and downstream (proceeds) currency logic — cost to relieve is determined solely by original purchase terms.
- Use the actual transaction amount (`wired_amount`) rather than dynamically converting at a floating exchange rate. Floating rates cause historical values to shift.
- When hardcoding a currency assumption, encode it in the function name (e.g., `formatUsdAmount` not `formatAmount`).
- Never filter by currency when you need a cross-currency total — convert each value to the target currency instead.
- Be explicit about which exchange rate (original vs current) each variable uses; add inline comments in FX-heavy code.

```ruby
# Bad — floating rate changes historical values
investment.purchase_price.exchange_to('USD', as_of: date)

# Good — actual amount at transaction time
investment.wired_amount
```

_Sources: PR #17288, PR #17863, PR #22814, PR #26140, PR #25829_

### Guard Against Division and Negative Edge Cases

- When dividing monetary values, always guard against zero denominators — `0.to_money / 0.to_money` produces NaN in Ruby, which poisons downstream comparisons.
- Guard against negative values where the domain does not permit them using explicit floors (e.g., `[value, 0].max`).
- Validate financial calculation results before proceeding — prefer raising on anomalies over silently producing invalid state.
- Apply explicit rounding to monetary results before storing or displaying — omitting rounding produces fractional-cent values that cause mismatches in tax forms and balance sheets.

```ruby
# Bad — NaN poisons max comparison
ratio = invested / total_cost
[0.0, ratio].max  # ArgumentError if NaN

# Good — explicit guard
return BigDecimal(0) if total_cost.zero?
ratio = invested / total_cost
```

_Sources: PR #17100, PR #23260, PR #23005, PR #19247_

### Accounting Transaction Semantics

- Don't reuse accounting transaction commands for different business events — each command has specific semantic meaning that determines how downstream processes handle the data.
- Name transaction types after business events (e.g., "Convertible equity instrument changed"), not generic CRUD operations (e.g., "Convertible equity updated").
- Accounting transactions should be self-contained — no ActiveRecord associations back to mutable fund state. All needed data must be captured in metadata or event payload at creation time.
- Ledger entry handlers should be pure transformations that operate only on data passed to them, not query external state.
- Domain model flags consumed by downstream handlers must reflect the underlying financial reality, not surface-level type names.

_Sources: PR #20567, PR #21169, PR #20856, PR #24516, PR #22280_

### Accounting Metadata Completeness

- Every new transaction type that creates or modifies assets must include corresponding metadata records — don't assume existing handlers cover new types.
- Use the full metadata handler rather than partial metadata updates when adding new accounting transaction handlers.
- Ledger dimensions are not optional — they tie values together for financial statement generation. Check the closest existing handler for required dimensions.
- When adding new debit/credit accounts, verify the full lifecycle: creation, accrual, AND liquidation/write-off.

_Sources: PR #20567, PR #21597, PR #20856, PR #25436, PR #17341_

### Journal Entry Conventions

- Always list debits before credits — mirrors universal accounting convention.
- Construct journal entries as a single declarative structure rather than building debits and credits separately.
- When handlers use different amount conventions (absolute vs delta vs negative), add clear comments explaining the rationale.
- Understand the debit/credit resolution logic (account type + amount sign) before questioning negative amounts; document this interaction clearly.

_Sources: PR #21673, PR #26417, PR #21701_

### Fund Lifecycle Date Handling

- Handle pre-inception date logic at the command/orchestration layer rather than plumbing fund dates into individual transaction models.
- Use domain-specific `effective_datetime` rather than `Time.current` — wall-clock time is rarely correct for business events that may be backdated.
- Never backdate `knowledge_datetime` through normal UI flows. Open periods use current time; closed periods block mutations entirely.
- When merging records with date-dependent accounting effects, derive dates per-record rather than assuming a single date applies to all.

_Sources: PR #20463, PR #20939, PR #19711, PR #25232_

### Nominee and Ownership Proration

- In nominee/beneficial ownership structures, always attribute monetary amounts by ownership percentage when booking per-asset entries.
- Every monetary attribute on per-asset-interest records must reflect proportional ownership — the full amount belongs only at the aggregate level.
- When splitting monetary values across parties, use a dedicated equitable allocation utility rather than manual division to avoid biased rounding.

```ruby
# Bad — full amount on each interest (double-booking)
build_entry(amount: command.fair_value)

# Good — prorated by ownership
build_entry(amount: command.fair_value * ownership_percentage)
```

_Sources: PR #22280, PR #23468_

### Use Closed/Effective Amounts Over Raw Commitments

- Use the "effective" or "closed" amount rather than the raw commitment amount for financial calculations — raw commitments can include pending increases that haven't been formally accepted.
- When validating financial completion states, prefer querying the authoritative aggregate status (e.g., "is fund 100% called") over checking individual transaction amounts.
- When replacing expensive live calculations with cached values, verify that the cache is fresh enough for the use case.

_Sources: PR #26056, PR #22873, PR #23248_

### Idempotency in Financial Commands

- Keep command handlers simple and prescriptive about expected state rather than building complex "figure everything out" reconciliation logic.
- Add idempotency guards close to the data mutation (within the command), not in upstream orchestration layers that lack full context.
- When a service method can be invoked concurrently, prefer `create_or_find_by!` over guard-clause-then-create patterns to avoid TOCTOU race conditions.
- Avoid calling commands from within other commands — command chaining makes audit trails recursive and hard to follow.

_Sources: PR #25929, PR #22943, PR #21670_

### Financial Calculation Testing

- When implementing complex financial calculations, add specs using concrete worked examples — dry-run figures from development make ideal test fixtures.
- Never use relative time expressions like `2.years.ago` in test factories for date-sensitive calculations — use explicit fixed dates.
- Proactively add test cases for reversal/refund scenarios even if current logic appears to handle them.
- Test factories for double-entry accounting should produce balanced, realistic data by default.
- Walk through financial math with concrete numbers in comments — coincidental correctness (works for one value but not others) is a common bug source.
- When writing concurrent/race condition tests for financial operations, don't bypass model validations with `force` flags — the protection mechanism (balance checks, etc.) often lives inside those validations, and bypassing them makes the test pass for the wrong reason.
- Tests for accounting services that split entries by participant type (e.g., QP vs non-QP) must assert on individual ledger entries rather than net balances — net assertions don't verify the split is correct.

_Sources: PR #21764, PR #24446, PR #23468, PR #24571, PR #17976, PR #18031, PR #19048, PR #5812, PR #26875_

### Date Parsing in Financial Contexts

- Always parse date strings in UTC (e.g., `moment.utc()`) rather than local time for period boundaries, accounting cutoffs, or ledger calculations.
- When validating entries against accounting period boundaries, consider the cumulative effect of multiple period closes — don't scope checks to a single period.

_Sources: PR #18252, PR #22671_

### Sign and Display Transformations

- Keep sign/display transformations (like inverting amounts for UI presentation) in the presenter or view layer, not in service objects.
- In the frontend, always use the structured money type (e.g., IMoney with `fractional`) rather than display strings — passing formatted display amounts to formatting functions causes double-formatting.

_Sources: PR #21162, PR #23948_

### Atomic Financial Operations

- Wrap parent record creation and associated financial data (e.g., share class + accounting valuations) in a database transaction to prevent orphaned records.
- When implementing cancel/undo operations, clean up all dependent records created after the original entity.
- When splitting PRs, keep tightly coupled domain logic (fund state changes + ledger entries) reviewable side by side.
- Never make external API calls (fund movements, payment execution) inside database transactions — if the API call succeeds but the transaction rolls back, funds have moved with no corresponding DB record. Use Temporal workflows for durable coordination of external side effects with DB state.

_Sources: PR #26156, PR #24782, PR #21673, PR #6022_

### Scope-Respecting Financial Operations

- When working with domain models scoped to a partition (e.g., membership class), verify that related operations respect the same scope boundary.
- When matching records across entities by name (e.g., share classes during transfers), validate that key financial attributes are identical — raise a clear error listing mismatched fields.
- Distinguish between "what we expect to affect" (pre-application) and "what we actually affected" (post-application) when querying related records.
- Type-specific predicate methods in financial services should guard with an explicit `return false` for non-matching fund types before checking their condition — implicit fallthrough breaks as fund type diversity grows.
- When filtering for specific asset types in accounting logic, use explicit per-type checks rather than negating a broad module or concern — broad negations silently include future subtypes.

_Sources: PR #21842, PR #26156, PR #22655, PR #26839, PR #27006_

### Financial Data Migration Safety

- Always add a reconciliation check comparing old and new system outputs before flipping feature flags on migrated financial data.
- When migrating identifier fields across services, make both old and new fields nilable during transition with a validation requiring at least one to be set.
- Identify a distinguishing marker unique to the old system to verify migration completeness and detect if old code paths are still hit.

_Sources: PR #23565, PR #24898, PR #18661_

### BigDecimal for All Financial Numerics

- Use BigDecimal for percentage and ratio parameters, not Integer or Float — integer division silently truncates in Ruby, and mixing types causes rounding errors.
- JSON serialization/deserialization produces Float, not BigDecimal. Convert at the boundary (e.g., in accessor methods) before passing into financial calculations.
- Always call `.to_d` on numeric values before they enter financial arithmetic — don't rely on implicit coercion.

```ruby
# Bad — JSON value is Float; integer coercion truncates
def compute_fee(percentage)
  amount * percentage  # percentage may be Float from JSON
end

# Good — convert at the boundary
def value_with_pattern
  BigDecimal(overridden_fields["value"].to_s)
end
```

_Sources: PR #23963, PR #24876, PR #19136, PR #18609_

### Asset Accounting Invariants

- Asset cost basis cannot go negative — when returns exceed total cost, the excess must be classified as realized gain/loss (RGL), not subtracted from cost.
- When an accounting edge case isn't covered by existing rules, add a validation to block the operation with a clear error rather than allowing incorrect entries to be written.
- Verify complex financial calculations against accountant-provided reference outputs (e.g., Excel FV function) before shipping — code correctness alone is insufficient.

```ruby
# Bad — silently books negative cost basis
cost_basis -= return_amount

# Good — cap at zero, book excess as RGL
rgl_amount = [return_amount - cost_basis, Money.zero].max
cost_basis = [cost_basis - return_amount, Money.zero].max
```

_Sources: PR #25457, PR #18111, PR #25387_

### Double-Booking via Parallel Conditionals

- When conditional branches in a financial handler are mutually exclusive, always use if/else — parallel if statements allow both branches to execute, causing double-booking.
- Treat a missing `else` in accounting code as a correctness bug, not a style issue.

```ruby
# Bad — both branches can execute, double-books entries
if condition_a
  book_entry_a(amount)
end
if condition_b
  book_entry_b(amount)
end

# Good — mutually exclusive
if condition_a
  book_entry_a(amount)
else
  book_entry_b(amount)
end
```

_Sources: PR #19015_

### Verify Accounting Classifications with Domain Experts

- Always verify ledger categories, account mappings, and classification choices with accountants before merging — engineers should not unilaterally decide accounting categorizations.
- Validate complex financial calculations against accountant-provided reference outputs (e.g., Excel FV function, worked examples) before shipping.
- Accounting transaction descriptions should include identifying details (like company or asset name) to make ledger entries self-documenting and reduce ambiguity during audits.
- When financial or legal definitions in code are uncertain and need external confirmation, file an explicit ticket and add a `# TODO` comment pointing to it — don't leave it as a mental note or PR comment that gets forgotten after merge.

_Sources: PR #21842, PR #25387, PR #25457, PR #26994_

### Prevent Double-Counting in Financial Aggregations

- When combining records from multiple queries or associations that may overlap (e.g., nominee structures with shared entities), always deduplicate with `uniq`.
- In calculations involving multiple related entities (e.g., same-entity closings), be explicit about which components (cash vs. in-kind) belong to which entity — mixing per-entity amounts into aggregate sums causes double-counting.

```ruby
# Bad — overlapping queries may include same record twice
assets = fund.direct_assets + fund.nominee_assets
total = assets.sum(&:cost_basis)

# Good — deduplicate before aggregation
assets = (fund.direct_assets + fund.nominee_assets).uniq
total = assets.sum(&:cost_basis)
```

_Sources: PR #15210, PR #22310_

### Monetary Field and Variable Naming

- Use explicit naming conventions that indicate the unit for monetary API fields (e.g., `allocation_cents` not `allocation`).
- Name monetary variables after what they represent (identity), not how they are consumed (usage context) — e.g., `total_cost_basis_of_upstream` not `total_to_potentially_relieve`.
- When a method accepts multiple monetary parameters that could be confused, use names that convey scope (fund-level vs. member-level) and purpose (total vs. delta).
- Encode scope and exclusions in variable names — `cash_excluding_mirror` is far clearer than `available`.
- Methods with an `_amount` suffix must always return a Money type, never nil — callers expect a well-typed value and nil breaks the naming contract.

_Sources: PR #22756, PR #18585, PR #17468, PR #17288, PR #23279_

### Flatten Accounting Transaction Model Hierarchies

- In accounting transaction model hierarchies, inherit from the abstract base class rather than sibling concrete classes — the DRY savings rarely outweigh the confusion of unexpected inheritance chains.
- Match the established interface contract (method signatures, parameter types) across sibling handler classes in the same family.
- Keep orchestration methods ("directors") thin by delegating domain logic to dedicated service methods ("actors").

```ruby
# Bad — child inherits from sibling, surprising chain
class GasFeeContribution < NewInvestmentWired
end

# Good — flat hierarchy, explicit attributes
class GasFeeContribution < AccountingTransactionBase
  attr_json :amount, :currency, :asset_id
end
```

_Sources: PR #20072, PR #20856_

### Extract Financial Domain Identifiers as Constants

- Extract domain-specific labels and category names (account names, ledger categories) used in financial calculations or statement generation to named constants.
- Reference defined constants instead of hardcoding string literals for type safety and single-source-of-truth maintenance.
- When constants involve side effects (e.g., DB lookups), prefer static/number-based variants over dynamic named lookups.

```ruby
# Bad — magic string buried in service
where(account_name: "Syndication costs")

# Good — constant defined on model
where(account_number: Account::SYNDICATION_COSTS_NUMBER)
```

_Sources: PR #18025, PR #19247_

### Defensive Currency Constraints

- Add explicit currency validations early — even if current usage is single-currency. Defensive constraints prevent accidental multi-currency complexity from sneaking in before the system is designed to handle it.
- Don't add configurability for values the system constrains to a single option. Exposing unused currency parameters creates false flexibility that misleads future developers.
- When performing currency arithmetic, be explicit about subunit assumptions — hardcoding cents-to-dollars (dividing by 100) breaks for currencies without subunits (e.g., JPY).

```ruby
# Bad — accepts currency but system only supports USD
def create_airdrop(amount:, currency: "USD")
  # currency param is never anything but USD
end

# Good — hardcode constraint, validate at boundary
validates :currency, inclusion: { in: ["USD"] }
```

_Sources: PR #21670, PR #21539, PR #25262_

### Document Financial Calculation Logic

- Walk through financial math with concrete numbers in comments — coincidental correctness (works for one value but not others) is a common bug source.
- When handlers use different amount conventions (absolute vs delta vs negative), add clear comments explaining the rationale to prevent "fixing" correct behavior.
- In FX-heavy code, annotate which exchange rate (original vs current) and point-in-time each variable represents.
- Extract complex boolean conditions in financial logic into named intermediate variables that communicate business intent.

```ruby
# Bad — abstract variable names hide coincidental correctness
result = setup_amount * (percentage * 100)

# Good — concrete walkthrough exposes the bug
# For 10%: $1000 * (0.10 * 100) = $10,000 ✓
# For 20%: $1000 * (0.20 * 100) = $20,000 ✗ (should be $2,000)
result = setup_amount * FIXED_MULTIPLIER
```

_Sources: PR #17976, PR #17288, PR #20218, PR #22976, PR #26417, PR #17247, PR #22706, PR #23193, PR #19557_

### No Hidden Side Effects in Financial Object Construction

- Don't create ledger entries or accounting records as a side effect of constructing domain objects — callers won't expect that building an allocation implicitly writes to the general ledger.
- Make financial record creation explicit: require entries as arguments or use a separate creation step.
- Method names should accurately reflect all side effects — if a method named for one operation also books accounting entries, extract the additional behavior into a clearly named method.

```ruby
# Bad — constructor silently creates GL entries
allocation = Allocation.new(entries: generate_entries!)

# Good — entries passed explicitly
entries = GeneralLedger.build_entries(params)
allocation = Allocation.new(entries: entries)
```

_Sources: PR #17412, PR #24302_

### Pessimistic Locking in Financial State Machines

- Use `with_lock` (row-level locking) in financial state machines when you need to both prevent race conditions between a state read and mutation, and ensure multiple DB writes (e.g., ledger entry + state transition) commit atomically.
- Encapsulate `with_lock` inside the method that performs the check-then-write operation, not in callers — putting it in callers makes it easy to forget and distributes the concurrency contract across call sites.
- When using optimistic locking, reload the record after persistence to get the latest `lock_version` for retry scenarios; audit each reload — computed fields that query the DB directly don't need reloads.
- Add specs that explicitly document and verify locking assumptions, especially non-obvious ones like "this lock does NOT prevent stale reads."

```ruby
# Bad — lock in caller; every caller must remember
def process_webhook(payment)
  payment.with_lock { payment_service.reject!(payment) }
end

# Good — lock encapsulated in the operation
def reject!(payment)
  payment.with_lock do
    return unless payment.can_reject?
    create_ledger_entry!(payment)
    payment.update!(state: :rejected)
  end
end
```

_Sources: PR #5667, PR #7035, PR #5162, PR #5812_

### Origin/Destination Mapping in Payment Construction

- When building payment service calls that take both origin and destination objects, explicitly verify which side each field belongs to at every use site — using the wrong side compiles silently but sends funds to the wrong account.
- Treat mismatched origin/destination fields as a correctness bug requiring targeted review, not just a naming issue.

```ruby
# Bad — origin fields passed where destination is required
SEPA::CreditTransfer.new(
  account_number: origin.account_number,   # wrong side
  routing_number: origin.routing_number    # wrong side
)

# Good — fields match the transfer direction
SEPA::CreditTransfer.new(
  account_number: destination.account_number,
  routing_number: destination.routing_number
)
```

_Sources: PR #5620_

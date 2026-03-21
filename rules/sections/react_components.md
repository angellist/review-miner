---
scope: frontend
---

# React Components

### Positive Boolean Props

- Name boolean props with positive prefixes (`show*`, `is*`, `has*`, `allow*`), not negative (`hide*`, `isHidden`)
- Default to `true` when the common case is to show the element
- Don't name a boolean prop after a CSS property (`padding`, `border`, `shadow`) — it implies a value, not a toggle; use `includePadding`, `hasBorder` instead

```tsx
// Bad — double negation when consuming; CSS property name implies a value
<Panel hideStats={!shouldShow} isContentHidden={!expanded} padding={true} />

// Good
<Panel showStats={true} isExpanded={expanded} includePadding={true} />
```

_Sources: PR #5485, PR #6184, PR #4455, PR #2010, PR #2547_

### Reuse Existing Hooks and Design System Components

- Before writing custom logic, search for existing hooks (`useMutationOrToast`, `useNovaToast`, `useMobile`)
- Before building custom UI behavior (popovers, animations), check ADAPT for built-in components
- Before writing date/time or error formatting helpers, check shared utilities (`@/lib/datetime.ts`, `@/lib/errors.ts`)
- Don't wrap a single function call in a custom hook — only create hooks when you need React lifecycle integration
- Know what your component library handles internally (e.g., Adapt's Button with `type='submit'` manages submission state)

```tsx
// Bad — custom popover positioning + custom toast
const [pos, setPos] = useState(calculatePosition(ref));
toast({ title: 'Error', variant: 'destructive' });

// Good — design system + project hooks
<AnchoredPopover trigger={ref}>...</AnchoredPopover>
const { showError } = useNovaToast();
```

_Sources: PR #2857, PR #2871, PR #5503, PR #2673, PR #2735, PR #3805, PR #4621, PR #17480, PR #18582, PR #19013, PR #19264_

### Conditional Rendering Readability

- Use guard clauses with early `return null` for conditional rendering instead of wrapping entire JSX in ternaries
- Extract complex inline conditionals into named helper functions or variables above the return
- For nested ternaries, extract into sub-components rather than `renderContent` helpers
- Avoid `renderX()` methods — they bypass hooks composition rules and lose TypeScript type inference; extract as proper functional components instead
- Push repeated conditional rendering logic down into child components rather than repeating ternaries in the parent

```tsx
// Bad
return tagValue ? <Tag>{complex ? a : b}</Tag> : <></>;

// Good
if (!tagValue) return null;
const label = buildLabel(complex, a, b);
return <Tag>{label}</Tag>;
```

_Sources: PR #7184, PR #3813, PR #3932, PR #4648, PR #3696, PR #21555, PR #22105, PR #22630, PR #2062, PR #2072_

### Modal and Drawer Lifecycle

- Show modals immediately with a skeleton loading state rather than delaying open until data loads
- Control animated drawers/blades via `isOpen` prop, not conditional mount/unmount (which skips transitions)
- Don't keep form-containing modals always-mounted for animation — stale form state persists across open/close cycles
- If always-mounted is required, reset form state on open via `useEffect`

_Sources: PR #2629, PR #2974, PR #7250, PR #19769_

### Shared Component API Design

- Make changes to shared components opt-in via new props, not default behavior changes
- Make non-essential slots optional — don't force callers to pass empty content
- When a prop has the same value at every call site, move it to a default inside the component
- Prefer configuration props (e.g. `columns` array) over type-discriminator props (`dashboardType`) that embed domain knowledge
- Audit all consumers before changing a shared component's state management contract
- When modifying a shared component for a specific use case (e.g., admin pages), leave a comment documenting the change is use-case-specific

```tsx
// Bad — domain knowledge in generic component
<MembersTable dashboardType="meridian" />

// Good — caller declares configuration
<MembersTable columns={['member', 'status', 'date-added']} />
```

_Sources: PR #5283, PR #5469, PR #6669, PR #4575, PR #4033, PR #6682, PR #25275_

### Form Patterns

- Use the project's `<Form>` component even for simple forms — consistency matters
- Inside forms, import RHF-wrapped components (e.g. from `rhf/` path), not raw design system inputs
- The component that renders a form should own its lifecycle — don't hoist form state to a parent just to pass it down
- Export form config (schema, defaults) as a named object, not as static properties on the component function

```tsx
// Bad — raw Select silently drops values from form submission
import { Select } from '@adapt/core';

// Good — RHF version wires into form context
import { Select } from '@adapt/rhf';
```

_Sources: PR #5443, PR #3672, PR #3681, PR #4040_

### Error Feedback for Network Calls

- Always surface mutation/fetch errors to the user via toast or inline error state
- Use project hooks (`useMutationOrToast`, `useNovaToast`) instead of manual toast configuration
- Use existing error extraction utilities (e.g., `lib/errors.ts`) rather than displaying raw error objects
- Silent failures erode user trust, especially in financial UIs

_Sources: PR #2871, PR #5485, PR #5503, PR #2857, PR #18734, PR #19264_

### Component Composition Over Conditional Branching

- A "mode" prop threaded through many sub-expressions is a code smell — split into separate components sharing composable pieces
- When a component renders nothing (pure side effects), convert it to a custom hook
- Extract significant inline logic (fetching, state, effects) into dedicated hooks when it obscures rendering intent
- Use `children` for nested/collapsible content instead of custom content props

```tsx
// Bad — mode prop threaded everywhere
<Dashboard type="admin" />  // branches in 12 places internally

// Good — composition
<AdminDashboard />   // shares useMetrics(), <StatsPanel /> with
<UserDashboard />    // different top-level layout
```

_Sources: PR #3976, PR #2670, PR #4892, PR #6184, PR #3060_

### Loading States

- Use skeleton loaders, not misleading default text, during data fetching
- Open modals immediately with skeleton content rather than blocking on async data
- Always handle error states alongside loading states — a spinner without error fallback creates an infinite spinner on failure
- Only use loading state indicators for genuinely async operations; setting loading flags around synchronous updates causes extra re-renders
- Return `null` (not `<></>`) when conditionally rendering nothing

```tsx
// Bad — shows "Any" while loading, looks like real data
{loading ? 'Any' : investmentType}

// Good
{loading ? <Skeleton width={80} /> : investmentType}
```

_Sources: PR #4898, PR #2629, PR #3795, PR #17480, PR #22308, PR #22594_

### Responsive Layout

- Prefer CSS-based responsive design (`display: none`, responsive props) over JS conditional rendering for layout differences
- Multi-column layouts with financial data should collapse to single-column on mobile breakpoints
- In responsive design systems where breakpoints cascade upward, only specify the breakpoint where the value changes — redundant entries obscure actual responsive behavior

```tsx
// Bad — renders both trees, extra reconciliation
{isMobile ? <MobileLayout /> : <DesktopLayout />}

// Good — CSS handles visibility
<Box display={{ xs: 'none', md: 'flex' }}>...</Box>
```

_Sources: PR #6570, PR #4925, PR #22763_

### Prop Naming and Structure

- Name layout props by semantic position (`breadcrumbsPrefix`), not generic names
- When a component consumes multiple fields from one object, pass the whole object instead of individual props
- When both a full object and a subfield are passed, make the subfield optional with a default from the object
- Avoid redundant JSX wrappers — pass strings directly when the prop accepts a string
- Use `isOpen: boolean` and `onClose: () => void` for modal/dialog visibility and dismissal props
- Prefer a single enum/state value over multiple boolean flags for mutually exclusive states
- For props that are required but may be null during loading, use `string | null` rather than optional (`?:`)
- Place destructured parameters with default values at the end of the parameter list
- When extending props via intersection or Omit, ensure the implementation actually passes through the advertised props

```tsx
// Bad — multiple booleans for mutually exclusive states
<Button isDealStarted={true} isDealStopped={false} />

// Good — single enum value
<Button dealState="started" />
```

_Sources: PR #5470, PR #3060, PR #4206, PR #6751, PR #22511, PR #23867, PR #24923, PR #18115, PR #18211_

### Avoid Unnecessary Abstraction

- Don't create wrapper components that just pass props through — use the underlying component directly
- Don't create hooks that wrap a single non-React function call
- Don't wrap design system props in intermediate layers — pass them directly
- Review AI-generated components for redundant indirection

```tsx
// Bad — wrapper adds nothing
const StatusCell = (props) => <InteractionTag {...props} />;

// Good — use directly
<InteractionTag status={status} />
```

_Sources: PR #6682, PR #4621, PR #4743_

### Centralize URLs and Constants

- Define external URLs and cross-app links in centralized path constants (`paths.venture.*`, `lib/paths`), not inline in components
- Extract enumerable domain data (network lists, supported currencies, status values) to a constants file; prefer sourcing from a data model or API if the list may change
- Move static data (route paths, config objects, constant arrays) outside the component function body to avoid re-allocation on every render
- Use design system tokens for z-index values, not hardcoded numbers
- Establish a consistent convention for absent values in display (e.g. always EMDASH for missing data)

_Sources: PR #7265, PR #3344, PR #6201, PR #20720, PR #20796, PR #23580, PR #23804, PR #18046_

### Video and Media Elements

- When using `autoPlay` on video elements, always include `muted` (browser autoplay policy) and `playsInline` (iOS Safari fullscreen prevention)

```tsx
// Bad — autoplay silently fails
<video autoPlay loop src={url} />

// Good
<video autoPlay loop muted playsInline src={url} />
```

_Sources: PR #6770_

### Use Semantic Interactive Elements

- Use design system `<Button>` over generic containers (`<Box>`, `<div>`) for interactive elements
- Generic containers lack built-in disabled state, focus management, and accessibility
- If you must use a container, manually guard click handlers and add ARIA attributes
- Don't use disabled form inputs to display read-only data — use plain text instead, reserving inputs for editable fields

_Sources: PR #3094, PR #18582_

### Use Design System Primitives Over Raw HTML and CSS

- Use `<Box>`, `<Text>`, `<Stack>` from ADAPT instead of raw `<div>`, `<p>`, `<span>`
- Use component props (`marginBottom`, `color`, `textAlign`) instead of custom SCSS or inline styles
- Use `<Stack direction='horizontal'>` for flex layouts instead of `<Box display='flex'>`
- Use `<Skeleton>` for loading states, `<NullState>` for empty states
- Convert pixel values to design system tokens
- Use `<Stack>` for spacing between elements, never `<br/>` tags
- Preserve semantic HTML in list-like components — use `<Stack as='ul'>` or `<Box as='ul'>` for lists of items

```tsx
// Bad — raw HTML with inline styles
<div style={{ display: 'flex', marginBottom: '16px' }}>
  <p style={{ color: '#666' }}>Loading...</p>
</div>

// Good — design system primitives
<Stack direction='horizontal' gap='200'>
  <Text color='text70'>
    <Skeleton lines={3} />
  </Text>
</Stack>
```

_Sources: PR #22763, PR #26568, PR #26508, PR #26503, PR #26605, PR #26728, PR #25583, PR #26558, PR #17756, PR #19264, PR #24661_

### Don't Repeat Default Prop Values

- Don't explicitly set props to their default values (e.g., `direction='vertical'` on Stack, `gap='100'`)
- It adds visual noise and misleads readers into thinking the value was intentionally changed
- Know the defaults of your design system components

_Sources: PR #26210, PR #26605, PR #26395_

### Render Modals and Dialogs Once, Not in Loops

- Never render modals or dialogs inside `.map()` loops — only one can be open at a time
- Render the dialog once outside the loop, use state to track which item is active
- This avoids unnecessary DOM nodes and prevents subtle bugs from multiple instances

```tsx
// Bad — N dialog instances in DOM
{items.map(item => (
  <Dialog key={item.id} onConfirm={() => delete(item.id)}>...</Dialog>
))}

// Good — single dialog, state-controlled
<Dialog isOpen={!!deleteId} onConfirm={() => delete(deleteId)}>
  {items.find(i => i.id === deleteId)?.name}
</Dialog>
```

_Sources: PR #26728_

### Sync Form State with Displayed Defaults

- Never set a default/initial value only on the UI component without initializing form state
- The form submits its internal state, not what the user sees on screen
- This mismatch between displayed defaults and submitted values causes incidents

```tsx
// Bad — visual default not in form state
<Input defaultValue="100" name="amount" />

// Good — form state matches display
useForm({ defaultValues: { amount: "100" } });
```

_Sources: PR #21948_

### Map Enum Values to Display Names

- Never display raw backend enum values directly in the UI, even with simple transforms
- Simple capitalization produces awkward results for camelCase values like 'inReview'
- Use an explicit display-name mapping dictionary

```tsx
// Bad — raw transform
<Tag>{status.charAt(0).toUpperCase() + status.slice(1)}</Tag>

// Good — explicit mapping
const STATUS_LABELS: Record<Status, string> = {
  inReview: 'In Review', published: 'Published',
};
<Tag>{STATUS_LABELS[status]}</Tag>
```

_Sources: PR #22586_

### Explicit Timezone Handling for Date Display

- When displaying dates from an API, be explicit about timezone handling
- If the API returns ISO datetimes with a time component, pass `timeZone: 'utc'` to date formatters
- Pure date strings (YYYY-MM-DD) without time components are safe without this

_Sources: PR #25110_

### Prefer `type` Over `interface` for Props

- Use `type Props = { ... }` for React component props, not `interface IProps`
- Avoid Hungarian notation (no `I` prefix on type names)
- Types are more flexible (support unions, intersections) and the codebase convention uses `type Props`

_Sources: PR #25154, PR #26568, PR #18322_

### Use `href` for Navigation Buttons

- When a button's purpose is navigation, use `href` instead of `onPress` with programmatic navigation
- This preserves native browser link behaviors (middle-click, right-click, cmd/ctrl-click)
- Improves accessibility for screen readers

_Sources: PR #24601_

### Disable Instead of Hide for Async Eligibility

- Never hide interactive elements based on async checks that complete after user interaction
- Disable the element with a tooltip explaining why it's unavailable
- Show an error state in any modal/dialog that opens while ineligible

_Sources: PR #26508_

### Warn Before Irreversible Financial Actions

- For destructive or irreversible financial operations, show a clear contextual warning
- Display the warning at the moment the user commits (e.g., when a checkbox is checked), not just in general modal copy
- Financial UIs must make consequences explicit to prevent costly mistakes

_Sources: PR #25982_

### Mark Deprecated Components with @deprecated

- When duplicating a component to create a replacement, mark the old one with `/** @deprecated */`
- Makes the intent clear to other developers and prevents accidental use
- Rename components when the feature they're named after is removed

_Sources: PR #18615, PR #22708_

### Keep Presentation Logic Out of API Payloads

- Send structured JSON data from backend services, not pre-formatted strings
- Let the consuming presentation layer handle formatting and rendering
- Pre-formatted strings in APIs are brittle, hard to localize, and limit downstream flexibility

_Sources: PR #17964_

### Encapsulate Visibility Logic in the Component

- When a component's visibility depends on a condition, push that condition into the component itself
- Have the component accept the relevant data and return null when it should not render
- This prevents condition drift across multiple call sites

```tsx
// Bad — visibility duplicated at every call site
{shouldShowCallout && <Callout data={data} />}

// Good — component decides internally
<Callout data={data} />  // returns null if !shouldShow(data)
```

_Sources: PR #25406_

### Check Container Built-in Props Before Custom Rendering

- Check if container components (Table, Modal) have built-in props for common states (empty, loading, error)
- Use the `emptyState` table prop instead of separate conditional `<NullState>` rendering
- Use `<Skeleton isLoading={loading}>` wrapping instead of custom loading conditions

_Sources: PR #26503_

### Consistent Prop Naming Across Components

- Props that serve the same semantic purpose should use the same name across all related/sibling components
- When two names exist for the same concept (e.g., `density` vs `size`), normalize to one — let the type system express per-component valid values
- When renaming a prop as part of an API change, also rename all associated type aliases and exports

```tsx
// Bad — sibling components use different names for the same concept
<CopyButton content="..." />
<CopyCell value="..." />  // should also be `content`

// Good — consistent naming lets developers transfer knowledge
<CopyButton content="..." />
<CopyCell content="..." />
```

_Sources: PR #2299, PR #2303_

### Avoid Top-Level Discriminated Unions on Props

- Don't express conditional prop relationships via a top-level discriminated union — TypeScript inference degrades noticeably beyond 2-3 variants
- Bundle dependent properties into a nested config type instead
- Extend existing config objects with new fields rather than adding parallel top-level props

```tsx
// Bad — top-level union breaks prop forwarding and confuses TypeScript
type Props = BaseProps & (CompactProps | NonCompactProps);

// Good — nested config keeps the props object flat
type Props = { compact?: boolean | { emphasizeLabel: boolean } };
```

_Sources: PR #2303, PR #2322_

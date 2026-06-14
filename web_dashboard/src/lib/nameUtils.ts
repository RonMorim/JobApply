/**
 * Shared user-identity helpers — display name, initials, greeting name.
 *
 * Single source of truth used by Header.tsx, page.tsx, and Overview.tsx.
 * All three previously duplicated similar but subtly different logic; this
 * module centralises the behaviour so a change here propagates everywhere.
 *
 * Priority order for display name resolution
 * ──────────────────────────────────────────
 *  1. user_metadata.full_name  (set automatically by Google / GitHub OAuth)
 *  2. user_metadata.name       (alternative metadata key used by some providers)
 *  3. KNOWN_EMAIL_NAMES        (explicit override for users who signed up via
 *                               email/password before their profile was enriched)
 *  4. email prefix             (last-resort fallback — cosmetic only; never shown
 *                               in greetings because it may contain digits/numbers)
 *
 * Updating a user's real name
 * ───────────────────────────
 * The cleanest permanent fix is to write full_name into the user's Supabase
 * metadata once (e.g. via the profile-builder interview).  Until that happens
 * the KNOWN_EMAIL_NAMES map below provides an explicit override.  Remove the
 * entry once user_metadata.full_name is populated for that account.
 */

// ── Known email → full name overrides ────────────────────────────────────────
// Used when user_metadata has not been populated yet (email/password sign-up
// without a subsequent profile update).  Keys must be lower-cased.

const KNOWN_EMAIL_NAMES: Record<string, string> = {
  'ronmorim98@gmail.com': 'Ron Morim',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Returns the best available display name for a user.
 *
 * Falls back to the raw email prefix as an absolute last resort so the avatar
 * always has something to show.  Components that need a human-readable greeting
 * should use `getGreetingName()` instead, which filters out email-prefix strings
 * that contain digits.
 */
export function resolveDisplayName(
  email?:    string | null,
  metadata?: Record<string, unknown> | null,
): string {
  // 1. OAuth / profile metadata (most reliable)
  const metaName = ((metadata?.full_name ?? metadata?.name) ?? '') as string
  if (metaName.trim()) return metaName.trim()

  // 2. Explicit override for known accounts
  const key = (email ?? '').toLowerCase()
  if (key && KNOWN_EMAIL_NAMES[key]) return KNOWN_EMAIL_NAMES[key]

  // 3. Raw email prefix — cosmetic fallback only
  if (email) return email.split('@')[0]

  return ''
}

/**
 * Returns two-character initials from a resolved display name.
 *
 * "Ron Morim"   → "RM"  (first letter of first word + first letter of last word)
 * "Ron"         → "RO"  (single word — first two characters)
 * "ronmorim98"  → "RO"  (single token — first two characters)
 * ""            → "?"   (unknown user)
 */
export function getInitials(displayName: string): string {
  const trimmed = displayName.trim()
  if (!trimmed) return '?'

  const words = trimmed.split(/\s+/).filter(Boolean)
  if (words.length >= 2) {
    // "Ron Morim" → words[0][0]="R", words[last][0]="M" → "RM"
    return (words[0][0] + words[words.length - 1][0]).toUpperCase()
  }

  // Single word (includes email-prefix style like "ronmorim98")
  return trimmed.slice(0, 2).toUpperCase()
}

/**
 * Returns a first name suitable for use in a greeting.
 *
 * Specifically, this function returns an empty string when the first token of
 * the display name contains a digit — which indicates an email prefix rather
 * than a real name.  Callers must render the greeting without a name in that
 * case (e.g. "Good morning" rather than "Good morning, ronmorim98").
 *
 * "Ron Morim"   → "Ron"
 * "Ron"         → "Ron"
 * "ronmorim98"  → ""    (contains digit — omit from greeting)
 * ""            → ""
 */
export function getGreetingName(displayName: string): string {
  if (!displayName.trim()) return ''
  const firstName = displayName.trim().split(/\s+/)[0] ?? ''
  // Reject tokens that look like email prefixes (contain any digit)
  if (/\d/.test(firstName)) return ''
  return firstName
}

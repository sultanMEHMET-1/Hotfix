const SITE_NAMES: Record<string, string> = {
  "permit-application": "Permit portal",
  "record-update": "Inventory desk",
  "wikipedia-article": "Wikipedia",
  "python-latest-release": "Python releases",
};

/** What a person calls the site behind a workflow. Unknown ids fall back to the id with spaces. */
export function workflowLabel(id: string): string {
  const known = SITE_NAMES[id];
  if (known) return known;
  const spaced = id.replace(/-/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

const SITE_HINTS: Record<string, string> = {
  "permit-application": "Looks up a permit",
  "record-update": "Edits a price on the site",
  "wikipedia-article": "Looks up an article heading",
  "python-latest-release": "Reads the latest release",
};

/** A few words on what running this workflow does. Unknown ids have none, so they get no tooltip. */
export function workflowHint(id: string): string | undefined {
  return SITE_HINTS[id];
}

const SITE_NAMES: Record<string, string> = {
  "permit-application": "Permit portal",
  "record-update": "Inventory desk",
};

/** What a person calls the site behind a workflow. Unknown ids fall back to the id with spaces. */
export function workflowLabel(id: string): string {
  const known = SITE_NAMES[id];
  if (known) return known;
  const spaced = id.replace(/-/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

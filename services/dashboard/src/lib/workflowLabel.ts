const SITE_NAMES: Record<string, string> = {
  "permit-application": "Permit portal",
  "record-update": "Inventory desk",
  "wikipedia-article": "Wikipedia",
  "python-latest-release": "Python releases",
  "books-travel-first-book": "Books",
  "quotes-love-first-quote": "Quotes",
};

/** True for a workflow created from a sentence. */
export const isCreated = (id: string): boolean => id.startsWith("custom-");

/** The site a created or built-in public workflow reads, for the create panel; undefined for any other workflow. */
export type PublicSite = "wikipedia" | "python" | "books" | "quotes";

export function publicSite(id: string): PublicSite | undefined {
  if (id === "wikipedia-article" || id.startsWith("custom-wikipedia-")) return "wikipedia";
  if (id === "python-latest-release" || id.startsWith("custom-python-")) return "python";
  if (id === "books-travel-first-book" || id.startsWith("custom-books-")) return "books";
  if (id === "quotes-love-first-quote" || id.startsWith("custom-quotes-")) return "quotes";
  return undefined;
}

/** The page title: a created workflow shows its whole goal (the picker button shortens it). */
export function workflowTitle(id: string, goal?: string): string {
  return isCreated(id) && goal ? goal.replace(/\.$/, "") : workflowLabel(id, goal);
}

/** What a person calls the site behind a workflow. A created workflow is named by its goal; unknown ids fall back to the id with spaces. */
export function workflowLabel(id: string, goal?: string): string {
  const known = SITE_NAMES[id];
  if (known) return known;
  if (isCreated(id) && goal) return goal.length > 28 ? `${goal.slice(0, 27).trimEnd()}…` : goal.replace(/\.$/, "");
  const spaced = id.replace(/-/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

const SITE_HINTS: Record<string, string> = {
  "permit-application": "Looks up a permit",
  "record-update": "Edits a price on the site",
  "wikipedia-article": "Looks up an article heading",
  "python-latest-release": "Reads the latest release",
  "books-travel-first-book": "Reads the first Travel book",
  "quotes-love-first-quote": "Reads the first love quote",
};

/** A few words on what running this workflow does. Unknown ids have none, so they get no tooltip. */
export function workflowHint(id: string): string | undefined {
  return SITE_HINTS[id] ?? (isCreated(id) ? "Created from a sentence" : undefined);
}

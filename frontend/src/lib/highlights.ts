/**
 * Selecting passages in rendered documents and highlighting them again later.
 *
 * Passages are stored as text rather than DOM positions, because the document is re-rendered
 * every time it changes. Matching ignores whitespace, which differs between a selection's text
 * and the text nodes it spans, and uses the text before the passage to tell repeats apart.
 */

const CONTEXT_LENGTH = 160;
const PREFIX_MATCH_LENGTH = 40;
export const ACTIVE_HIGHLIGHT = "yv-active";
export const THREAD_HIGHLIGHT = "yv-thread";

export interface TextSelection {
  quote: string;
  prefix: string;
  suffix: string;
  /** Bounding box of the selection relative to the top-level window's viewport. */
  rect: DOMRect;
}

export interface Passage {
  quote: string;
  prefix: string | null;
}

/** The current selection, if it lies within `root`. */
export function selectionWithin(root: Node): TextSelection | null {
  const document = root.ownerDocument;
  const view = document?.defaultView;
  const selection = view?.getSelection();
  if (!document || !view || !selection || selection.isCollapsed || selection.rangeCount === 0) {
    return null;
  }
  const range = selection.getRangeAt(0);
  if (!root.contains(range.commonAncestorContainer)) {
    return null;
  }
  const quote = selection.toString().trim();
  if (!quote) {
    return null;
  }
  const before = document.createRange();
  before.selectNodeContents(root);
  before.setEnd(range.startContainer, range.startOffset);
  const after = document.createRange();
  after.selectNodeContents(root);
  after.setStart(range.endContainer, range.endOffset);

  return {
    quote,
    prefix: before.toString().slice(-CONTEXT_LENGTH),
    suffix: after.toString().slice(0, CONTEXT_LENGTH),
    rect: topLevelRect(range.getBoundingClientRect(), view),
  };
}

function topLevelRect(rect: DOMRect, view: Window): DOMRect {
  const frame = view.frameElement;
  if (!frame) {
    return rect;
  }
  const offset = frame.getBoundingClientRect();
  return new DOMRect(rect.x + offset.x, rect.y + offset.y, rect.width, rect.height);
}

interface CharacterPosition {
  node: Text;
  offset: number;
}

/** Locates a passage in the text under `root`, returning a range covering it. */
export function findPassage(root: Node, passage: Passage): Range | null {
  const document = root.ownerDocument;
  if (!document) {
    return null;
  }
  const positions: CharacterPosition[] = [];
  let text = "";
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const value = node.nodeValue ?? "";
    value.split("").forEach((character, offset) => {
      if (!/\s/.test(character)) {
        text += character;
        positions.push({ node: node as Text, offset });
      }
    });
  }

  const needle = compact(passage.quote);
  if (!needle) {
    return null;
  }
  const expectedPrefix = compact(passage.prefix ?? "").slice(-PREFIX_MATCH_LENGTH);
  let best = -1;
  for (let index = text.indexOf(needle); index !== -1; index = text.indexOf(needle, index + 1)) {
    if (best === -1) {
      best = index;
    }
    if (expectedPrefix && text.slice(0, index).endsWith(expectedPrefix)) {
      best = index;
      break;
    }
  }
  if (best === -1) {
    return null;
  }
  const start = positions[best];
  const end = positions[best + needle.length - 1];
  if (!start || !end) {
    return null;
  }
  const range = document.createRange();
  range.setStart(start.node, start.offset);
  range.setEnd(end.node, end.offset + 1);
  return range;
}

function compact(value: string): string {
  return value.replace(/\s+/g, "");
}

/**
 * Paints ranges with the CSS Custom Highlight API in the window that owns `root`. Browsers
 * without the API simply show no highlight.
 */
export function paintHighlights(root: Node, name: string, ranges: Range[]) {
  const view = root.ownerDocument?.defaultView as (Window & typeof globalThis) | null | undefined;
  const registry = view?.CSS?.highlights;
  if (!registry || typeof view.Highlight !== "function") {
    return;
  }
  if (ranges.length === 0) {
    registry.delete(name);
  } else {
    registry.set(name, new view.Highlight(...ranges));
  }
}

export const HIGHLIGHT_STYLES = `
::highlight(${THREAD_HIGHLIGHT}) { background-color: rgba(250, 204, 21, 0.18); }
::highlight(${ACTIVE_HIGHLIGHT}) { background-color: rgba(250, 204, 21, 0.5); color: inherit; }
`;

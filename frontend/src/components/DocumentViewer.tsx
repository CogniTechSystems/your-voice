import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import type { DocumentFormat } from "../api/types";
import {
  ACTIVE_HIGHLIGHT,
  HIGHLIGHT_STYLES,
  THREAD_HIGHLIGHT,
  findPassage,
  paintHighlights,
  selectionWithin,
  type Passage,
  type TextSelection,
} from "../lib/highlights";
import { Markdown } from "./Markdown";

export type ViewMode = "preview" | "source";

interface Props {
  content: string;
  format: DocumentFormat;
  mode: ViewMode;
  /** Set while the agent is writing this document, to follow the newest text. */
  live?: boolean;
  activePassage?: Passage | null;
  passages?: Passage[];
  onDiscuss?: (selection: TextSelection) => void;
}

const FRAME_STYLES = `
html { color-scheme: light; }
body { margin: 0; padding: 24px; font-family: system-ui, sans-serif; line-height: 1.55; }
${HIGHLIGHT_STYLES}
`;

/**
 * Shows an output document and lets the reader select a passage to discuss. HTML is rendered
 * in a sandboxed frame with scripts disabled.
 */
export function DocumentViewer({
  content,
  format,
  mode,
  live = false,
  activePassage = null,
  passages = [],
  onDiscuss,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [frameRoot, setFrameRoot] = useState<HTMLElement | null>(null);
  const [frameHeight, setFrameHeight] = useState(480);
  const [selection, setSelection] = useState<TextSelection | null>(null);
  const framed = format === "html" && mode === "preview";
  // Polling recreates the passage objects, so effects depend on their text instead.
  const activeKey = activePassage ? JSON.stringify(activePassage) : "";
  const passagesKey = JSON.stringify(passages);
  const passagesRef = useRef({ activePassage, passages });
  passagesRef.current = { activePassage, passages };

  const captureSelection = useCallback(() => {
    const target = framed ? frameRef.current?.contentDocument?.body : bodyRef.current;
    setSelection(target ? selectionWithin(target) : null);
  }, [framed]);

  const onFrameLoad = () => {
    const frameDocument = frameRef.current?.contentDocument;
    if (!frameDocument) {
      return;
    }
    const style = frameDocument.createElement("style");
    style.textContent = FRAME_STYLES;
    frameDocument.head.prepend(style);
    frameDocument.addEventListener("mouseup", captureSelection);
    frameDocument.addEventListener("keyup", captureSelection);
    setFrameHeight(Math.max(frameDocument.documentElement.scrollHeight, 200));
    setFrameRoot(frameDocument.body);
  };

  useEffect(() => {
    setSelection(null);
  }, [content, mode]);

  useEffect(() => {
    const scroller = scrollRef.current;
    if (live && scroller) {
      scroller.scrollTop = scroller.scrollHeight;
    }
  }, [live, content, frameHeight]);

  useLayoutEffect(() => {
    const root = framed ? frameRoot : bodyRef.current;
    if (!root) {
      return undefined;
    }
    const { activePassage: active, passages: all } = passagesRef.current;
    const others = all
      .filter((passage) => JSON.stringify(passage) !== activeKey)
      .map((passage) => findPassage(root, passage))
      .filter((range): range is Range => range !== null);
    const activeRange = active ? findPassage(root, active) : null;
    paintHighlights(root, THREAD_HIGHLIGHT, others);
    paintHighlights(root, ACTIVE_HIGHLIGHT, activeRange ? [activeRange] : []);
    return () => {
      paintHighlights(root, THREAD_HIGHLIGHT, []);
      paintHighlights(root, ACTIVE_HIGHLIGHT, []);
    };
  }, [framed, frameRoot, content, mode, activeKey, passagesKey]);

  useEffect(() => {
    const root = framed ? frameRoot : bodyRef.current;
    const active = passagesRef.current.activePassage;
    if (!root || !active || live) {
      return;
    }
    findPassage(root, active)?.startContainer.parentElement?.scrollIntoView({
      block: "center",
      behavior: "smooth",
    });
    // Scroll only when another passage is chosen or the view changes, not on every update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKey, framed, frameRoot, mode]);

  const discuss = () => {
    if (selection && onDiscuss) {
      onDiscuss(selection);
      setSelection(null);
      (framed ? frameRef.current?.contentWindow : window)?.getSelection()?.removeAllRanges();
    }
  };

  const scrollerBox = scrollRef.current?.getBoundingClientRect();
  const buttonPosition =
    selection && scrollerBox
      ? {
          top: selection.rect.bottom - scrollerBox.top + (scrollRef.current?.scrollTop ?? 0) + 6,
          left: Math.min(
            Math.max(selection.rect.left - scrollerBox.left, 8),
            scrollerBox.width - 170,
          ),
        }
      : null;

  return (
    <div
      ref={scrollRef}
      className={`document-view${live ? " document-live" : ""}`}
      onMouseUp={framed ? undefined : captureSelection}
      onKeyUp={framed ? undefined : captureSelection}
    >
      {framed ? (
        <iframe
          ref={frameRef}
          title="HTML preview"
          className="document-frame"
          sandbox="allow-same-origin"
          srcDoc={content}
          style={{ height: frameHeight }}
          onLoad={onFrameLoad}
        />
      ) : (
        <div ref={bodyRef} className="document-body">
          {mode === "source" || format === "text" ? (
            <pre className={mode === "source" ? "document-source" : "document-text"}>{content}</pre>
          ) : (
            <Markdown>{content}</Markdown>
          )}
        </div>
      )}
      {buttonPosition && onDiscuss && !live && (
        <button
          type="button"
          className="discuss-button"
          style={buttonPosition}
          onMouseDown={(event) => event.preventDefault()}
          onClick={discuss}
        >
          Discuss selection
        </button>
      )}
    </div>
  );
}

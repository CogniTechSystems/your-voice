import { useEffect, useRef } from "react";

import { Markdown } from "./Markdown";

const FOLLOW_THRESHOLD_PX = 24;

/**
 * Collapsible, height-limited view of a model's reasoning. While `live` is set the view keeps
 * the newest text in sight unless the reader has scrolled up.
 */
export function Reasoning({ text, live = false }: { text: string; live?: boolean }) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);

  useEffect(() => {
    const body = bodyRef.current;
    if (live && body && followRef.current) {
      body.scrollTop = body.scrollHeight;
    }
  }, [live, text]);

  const onScroll = () => {
    const body = bodyRef.current;
    if (body) {
      followRef.current =
        body.scrollHeight - body.scrollTop - body.clientHeight < FOLLOW_THRESHOLD_PX;
    }
  };

  return (
    <details className="reasoning" open={live || undefined}>
      <summary>{live ? "Thinking…" : "Thinking"}</summary>
      <div ref={bodyRef} className="reasoning-body" onScroll={onScroll}>
        <Markdown>{text}</Markdown>
      </div>
    </details>
  );
}

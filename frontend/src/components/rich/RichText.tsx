import { useEffect, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import styles from "./rich.module.css";

// GitHub's safe default, widened only to allow inline/base64 images (common in
// self-contained reports). Scripts, event handlers (onerror/onclick, …) and
// unknown URL protocols are still stripped, so even agent output that scraped a
// hostile page cannot inject active content.
const schema = {
  ...defaultSchema,
  protocols: {
    ...defaultSchema.protocols,
    src: [...(defaultSchema.protocols?.src ?? []), "data"],
  },
};

// Decorators run *after* sanitization, so they only ever touch already-safe
// nodes: links open in a new tab without leaking the opener, images stay
// responsive and lazy, and wide tables scroll instead of overflowing the bubble.
const components: Components = {
  a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" />,
  img: (props) => <img {...props} alt={props.alt ?? ""} loading="lazy" />,
  table: (props) => (
    <div className={styles.tableWrap}>
      <table {...props} />
    </div>
  ),
};

function looksLikeHtmlDocument(s: string): boolean {
  const head = s.trimStart().slice(0, 200).toLowerCase();
  return head.startsWith("<!doctype html") || head.startsWith("<html");
}

// A full, self-contained HTML report renders in a sandboxed iframe so its own
// CSS and images survive intact. The sandbox omits `allow-scripts`, so nothing
// inside can execute JavaScript; `allow-same-origin` is granted only so we can
// measure the content and size the frame to it (no scrollbars-in-a-box).
function HtmlReport({ html }: { html: string }) {
  const ref = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(240);

  useEffect(() => {
    const frame = ref.current;
    if (!frame) return;
    let observer: ResizeObserver | undefined;
    const measure = () => {
      try {
        const el = frame.contentDocument?.documentElement;
        if (el) setHeight(el.scrollHeight);
      } catch {
        /* same-origin guard — ignore if unreadable */
      }
    };
    const onLoad = () => {
      measure();
      const body = frame.contentDocument?.body;
      if (body && "ResizeObserver" in window) {
        observer = new ResizeObserver(measure);
        observer.observe(body);
      }
    };
    frame.addEventListener("load", onLoad);
    measure();
    return () => {
      frame.removeEventListener("load", onLoad);
      observer?.disconnect();
    };
  }, [html]);

  return (
    <iframe
      ref={ref}
      title="HTML report"
      className={styles.htmlFrame}
      sandbox="allow-same-origin"
      srcDoc={html}
      style={{ height }}
    />
  );
}

// Renders agent/activity text as rich content: GFM markdown (tables, lists,
// task lists, links), sanitized inline HTML, images, and full HTML reports.
// `compact` tightens spacing for the narrow activity panel.
export function RichText({ content, compact }: { content: string; compact?: boolean }) {
  if (looksLikeHtmlDocument(content)) {
    return <HtmlReport html={content} />;
  }
  return (
    <div className={`${styles.rich} ${compact ? styles.compact : ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, schema]]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

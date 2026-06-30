import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RichText } from "./RichText";

describe("RichText", () => {
  it("renders GFM markdown: headings, emphasis, and tables", () => {
    const { container } = render(
      <RichText content={"# Title\n\n**bold** text\n\n| A | B |\n| - | - |\n| 1 | 2 |"} />,
    );
    expect(container.querySelector("h1")?.textContent).toBe("Title");
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(table?.querySelectorAll("tbody tr")).toHaveLength(1);
  });

  it("opens links in a new tab without leaking the opener", () => {
    const { container } = render(<RichText content={"[site](https://example.com)"} />);
    const a = container.querySelector("a");
    expect(a).toHaveAttribute("href", "https://example.com");
    expect(a).toHaveAttribute("target", "_blank");
    expect(a).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders images lazily and responsively", () => {
    const { container } = render(<RichText content={"![alt](https://example.com/x.png)"} />);
    const img = container.querySelector("img");
    expect(img).toHaveAttribute("src", "https://example.com/x.png");
    expect(img).toHaveAttribute("loading", "lazy");
  });

  it("strips script tags and inline event handlers (XSS)", () => {
    const { container } = render(
      <RichText content={'<script>window.__xss = 1</script><img src="x" onerror="window.__xss = 1">'} />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.innerHTML).not.toContain("onerror");
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });

  it("renders a full HTML document inside a sandboxed, script-free iframe", () => {
    const html =
      "<!doctype html><html><body><h1>Report</h1><img src='data:image/png;base64,AAAA'></body></html>";
    const { container } = render(<RichText content={html} />);
    const frame = container.querySelector("iframe");
    expect(frame).not.toBeNull();
    expect(frame).toHaveAttribute("srcdoc", html);
    const sandbox = frame?.getAttribute("sandbox") ?? "";
    expect(sandbox).toContain("allow-same-origin");
    expect(sandbox).not.toContain("allow-scripts");
  });
});

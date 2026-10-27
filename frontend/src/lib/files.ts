import type { DocumentFormat } from "../api/types";

export const ACCEPTED_FILES = ".md,.markdown,.html,.htm,.txt";

const FORMAT_LABELS: Record<DocumentFormat, string> = {
  markdown: "Markdown",
  html: "HTML",
  text: "Plain text",
};

export function formatLabel(format: DocumentFormat): string {
  return FORMAT_LABELS[format];
}

export function formatForName(name: string): DocumentFormat {
  const extension = name.toLowerCase().split(".").pop();
  if (extension === "html" || extension === "htm") {
    return "html";
  }
  if (extension === "txt") {
    return "text";
  }
  return "markdown";
}

export interface TextFile {
  title: string;
  format: DocumentFormat;
  content: string;
}

/** Reads uploaded text files, titling each after its file name without the extension. */
export function readTextFiles(files: FileList | null): Promise<TextFile[]> {
  return Promise.all(
    Array.from(files ?? []).map(async (file) => ({
      title: file.name.replace(/\.[^.]+$/, ""),
      format: formatForName(file.name),
      content: await file.text(),
    })),
  );
}

export function downloadText(name: string, content: string, format: DocumentFormat) {
  const type =
    format === "html" ? "text/html" : format === "markdown" ? "text/markdown" : "text/plain";
  const url = URL.createObjectURL(new Blob([content], { type: `${type};charset=utf-8` }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name.split("/").pop() ?? name;
  link.click();
  URL.revokeObjectURL(url);
}

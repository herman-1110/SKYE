"use client";
import * as pdfjs from "pdfjs-dist";

// Configure worker once at module load. Bundled locally by webpack via the
// new URL(..., import.meta.url) asset pattern — no third-party CDN dependency,
// so PDF upload keeps working even on networks that block external CDNs.
if (typeof window !== "undefined" && !pdfjs.GlobalWorkerOptions.workerSrc) {
  pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    "pdfjs-dist/build/pdf.worker.min.mjs",
    import.meta.url,
  ).toString();
}

export interface RasterPage {
  pageNumber: number;     // 1-indexed
  file: File;             // PNG, ready to pass straight to uploadFloor()
  width: number;          // natural pixel width of the rasterised PNG
  height: number;
  previewUrl: string;     // object URL — caller is responsible for revokeRasterPages()
}

// Keep a margin below uploadFloor()'s 10MB cap (encoding overhead, rounding).
const MAX_PAGE_BYTES = 9.5 * 1024 * 1024;
const MIN_SCALE = 0.5;

async function renderPageToPngBlob(
  page: pdfjs.PDFPageProxy,
  scale: number,
): Promise<{ blob: Blob; width: number; height: number }> {
  const viewport = page.getViewport({ scale });

  const canvas = document.createElement("canvas");
  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D context unavailable");

  await page.render({ canvasContext: ctx, viewport }).promise;

  const blob: Blob = await new Promise((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("Canvas toBlob returned null"))),
      "image/png",
    );
  });

  return { blob, width: canvas.width, height: canvas.height };
}

/**
 * Render every page of a PDF to a PNG File at the given scale.
 * scale=2.0 gives ~retina-quality output (good enough for floor plans).
 * If a page's rasterised PNG would exceed the upload size cap, it's
 * progressively re-rendered at a lower scale until it fits.
 */
export async function rasterisePdfPages(
  pdfFile: File,
  scale: number = 2.0,
): Promise<RasterPage[]> {
  const buf = await pdfFile.arrayBuffer();
  const pdf = await pdfjs.getDocument({ data: buf }).promise;
  const baseName = pdfFile.name.replace(/\.pdf$/i, "");
  const out: RasterPage[] = [];

  for (let n = 1; n <= pdf.numPages; n++) {
    const page = await pdf.getPage(n);

    let currentScale = scale;
    let { blob, width, height } = await renderPageToPngBlob(page, currentScale);

    while (blob.size > MAX_PAGE_BYTES && currentScale > MIN_SCALE) {
      currentScale = Math.max(MIN_SCALE, currentScale * 0.75);
      ({ blob, width, height } = await renderPageToPngBlob(page, currentScale));
    }

    if (blob.size > MAX_PAGE_BYTES) {
      throw new Error(
        `Page ${n} is too large to upload even at minimum render quality ` +
        `(${(blob.size / 1024 / 1024).toFixed(1)}MB). Try a smaller page size.`,
      );
    }

    out.push({
      pageNumber: n,
      file: new File([blob], `${baseName}-page-${n}.png`, { type: "image/png" }),
      width,
      height,
      previewUrl: URL.createObjectURL(blob),
    });
  }

  return out;
}

/** Free the object URLs created by rasterisePdfPages(). Call on unmount / replacement. */
export function revokeRasterPages(pages: RasterPage[]): void {
  pages.forEach((p) => URL.revokeObjectURL(p.previewUrl));
}

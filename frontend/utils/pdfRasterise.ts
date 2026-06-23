"use client";
import * as pdfjs from "pdfjs-dist";

// Configure worker once at module load. CDN worker pinned to the installed pdf.js
// version so we don't have to copy/serve a static worker file in Next.js.
if (typeof window !== "undefined" && !pdfjs.GlobalWorkerOptions.workerSrc) {
  pdfjs.GlobalWorkerOptions.workerSrc =
    `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`;
}

export interface RasterPage {
  pageNumber: number;     // 1-indexed
  file: File;             // PNG, ready to pass straight to uploadFloor()
  width: number;          // natural pixel width of the rasterised PNG
  height: number;
  previewUrl: string;     // object URL — caller is responsible for revokeRasterPages()
}

/**
 * Render every page of a PDF to a PNG File at the given scale.
 * scale=2.0 gives ~retina-quality output (good enough for floor plans).
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

    out.push({
      pageNumber: n,
      file: new File([blob], `${baseName}-page-${n}.png`, { type: "image/png" }),
      width: canvas.width,
      height: canvas.height,
      previewUrl: URL.createObjectURL(blob),
    });
  }

  return out;
}

/** Free the object URLs created by rasterisePdfPages(). Call on unmount / replacement. */
export function revokeRasterPages(pages: RasterPage[]): void {
  pages.forEach((p) => URL.revokeObjectURL(p.previewUrl));
}

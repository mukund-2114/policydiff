import { useLayoutEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { api, type FindingSide } from "../api";

// Shows the PDF page a clause is on, with a marker over the clause. pdf.js needs its worker file, so
// it is loaded from the package. The boxes are saved when the document is chunked, in PDF points
// from the top left of the page, so they are scaled by (shown width / page width).
pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

export function PdfClause({ side }: { side: FindingSide }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [pageWidth, setPageWidth] = useState(0); // the page's own width in points

  // Follow the container's width, so the page grows when the layout does.
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const watch = new ResizeObserver(() => setWidth(Math.floor(el.clientWidth)));
    watch.observe(el);
    return () => watch.disconnect();
  }, []);

  const page = side.boxes[0]?.page ?? side.page ?? 1;
  const scale = pageWidth ? width / pageWidth : 0;

  return (
    <div ref={box} className="w-full overflow-hidden rounded-ctl border border-border">
      {width > 0 && (
        <Document file={api.fileUrl(side.version_id)} loading={<p className="p-3 text-muted">Loading the PDF...</p>} error={<p className="p-3 text-danger">The PDF could not be shown.</p>}>
          <div className="relative">
            <Page
              pageNumber={page}
              width={width}
              renderTextLayer={false}
              renderAnnotationLayer={false}
              onLoadSuccess={(p) => setPageWidth(p.originalWidth)}
            />
            {side.boxes
              .filter((b) => b.page === page)
              .map((b, i) => (
                <div
                  key={i}
                  className="absolute rounded-sm bg-warn/30 outline outline-1 outline-warn"
                  style={{
                    left: b.bbox[0] * scale,
                    top: b.bbox[1] * scale,
                    width: (b.bbox[2] - b.bbox[0]) * scale,
                    height: (b.bbox[3] - b.bbox[1]) * scale,
                  }}
                />
              ))}
          </div>
        </Document>
      )}
    </div>
  );
}

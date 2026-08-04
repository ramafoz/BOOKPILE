const MAX_OCR_PHOTO_BYTES = 24 * 1024 * 1024;

export interface CoverOcrProgress {
  status: string;
  progress: number;
}

export interface CoverOcrResult {
  text: string;
  lines: string[];
}

export async function readCoverText(
  file: File,
  languages: string[],
  onProgress: (progress: CoverOcrProgress) => void,
  signal: AbortSignal,
): Promise<CoverOcrResult> {
  if (!file.type.startsWith("image/")) {
    throw new Error("Choose an image of the book's front cover.");
  }
  if (file.size > MAX_OCR_PHOTO_BYTES) {
    throw new Error("The cover photo must be 24 MB or smaller.");
  }

  const { createWorker, PSM } = await import("tesseract.js");
  let worker: Awaited<ReturnType<typeof createWorker>> | null = null;
  const abort = () => {
    if (worker) void worker.terminate();
  };
  signal.addEventListener("abort", abort, { once: true });

  try {
    if (signal.aborted) throw new DOMException("OCR cancelled", "AbortError");
    worker = await createWorker(languages, undefined, {
      logger: ({ status, progress }) => onProgress({ status, progress }),
    });
    if (signal.aborted) throw new DOMException("OCR cancelled", "AbortError");
    await worker.setParameters({
      tessedit_pageseg_mode: PSM.SPARSE_TEXT,
      preserve_interword_spaces: "1",
    });
    const result = await worker.recognize(
      file,
      { rotateAuto: true },
      { text: true },
    );
    if (signal.aborted) throw new DOMException("OCR cancelled", "AbortError");

    const text = result.data.text.trim();
    const lines = text
      .split(/\r?\n/)
      .map((line) => line.split(/\s+/).join(" "))
      .filter((line, index, all) => line.length > 1 && all.indexOf(line) === index);
    if (!lines.length) {
      throw new Error(
        "No useful cover text was recognized. Try a straighter, sharper photo with less glare.",
      );
    }
    return { text, lines };
  } finally {
    signal.removeEventListener("abort", abort);
    if (worker) await worker.terminate().catch(() => undefined);
  }
}

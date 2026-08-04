const MAX_BARCODE_PHOTO_BYTES = 24 * 1024 * 1024;

export async function decodeIsbnBarcodePhoto(file: File): Promise<string> {
  if (!file.type.startsWith("image/")) {
    throw new Error("Choose an image containing the book barcode.");
  }
  if (file.size > MAX_BARCODE_PHOTO_BYTES) {
    throw new Error("The barcode photo must be 24 MB or smaller.");
  }

  const [{ BrowserMultiFormatReader }, { BarcodeFormat, DecodeHintType }] =
    await Promise.all([import("@zxing/browser"), import("@zxing/library")]);
  const hints = new Map();
  hints.set(DecodeHintType.POSSIBLE_FORMATS, [BarcodeFormat.EAN_13]);
  hints.set(DecodeHintType.TRY_HARDER, true);
  const reader = new BrowserMultiFormatReader(hints);
  const temporaryUrl = URL.createObjectURL(file);

  try {
    const result = await reader.decodeFromImageUrl(temporaryUrl);
    const code = result.getText().replace(/\D/g, "");
    if (code.length !== 13 || !code.startsWith("978") && !code.startsWith("979")) {
      throw new Error("The detected barcode is not an ISBN-13 book barcode.");
    }
    return code;
  } catch (error) {
    if (error instanceof Error && error.message.includes("not an ISBN-13")) {
      throw error;
    }
    throw new Error(
      "No ISBN barcode could be read. Try a closer, sharper photo with the whole barcode visible.",
    );
  } finally {
    URL.revokeObjectURL(temporaryUrl);
  }
}

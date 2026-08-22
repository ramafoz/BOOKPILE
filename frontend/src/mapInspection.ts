export function nextInspectionId(
  currentId: number | null,
  selectedId: number,
  keepSelected = false,
): number | null {
  if (!keepSelected && currentId === selectedId) return null;
  return selectedId;
}

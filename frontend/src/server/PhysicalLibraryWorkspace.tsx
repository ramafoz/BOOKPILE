import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Boxes, Layers3, Pencil, Plus, Ruler, Settings2, Trash2 } from "lucide-react";

import {
  PhysicalBookcase,
  PhysicalContainer,
  PhysicalLibrary,
  PhysicalShelf,
  ServerApiError,
  VisualLayout,
  serverApi,
} from "./serverApi";
import TimedNoticeStack from "./TimedNoticeStack";
import { useTimedNotices } from "./timedNotices";
import { physicalMapGeometry } from "./serverMapGeometry";


type EditTarget =
  | { kind: "BOOKCASE"; item: PhysicalBookcase }
  | { kind: "SHELF"; item: PhysicalShelf }
  | { kind: "CONTAINER"; item: PhysicalContainer };

type DimensionDraft = {
  first: string;
  second: string;
  third: string;
};

function errorMessage(error: unknown): string {
  return error instanceof ServerApiError
    ? error.message
    : "BOOKPILE could not complete that request.";
}

function optionalNumber(value: string): number | null {
  const cleaned = value.trim();
  return cleaned ? Number.parseInt(cleaned, 10) : null;
}

function dimensions(values: Array<number | null>, labels: string[]): string {
  const recorded = values.map((value, index) => value ? `${labels[index]} ${value} mm` : null).filter(Boolean);
  return recorded.length ? recorded.join(" · ") : "Dimensions not recorded";
}

function NumericField({
  label,
  value,
  onChange,
  min,
  max,
  step = 0.1,
  disabled = false,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState(String(Number(value.toFixed(2))));
  useEffect(() => {
    if (document.activeElement !== inputRef.current) {
      setText(String(Number(value.toFixed(2))));
    }
  }, [value]);
  return <label>{label}<input
    ref={inputRef}
    type="number"
    min={min}
    max={max}
    step={step}
    value={text}
    disabled={disabled}
    required
    onChange={(event) => {
      const next = event.target.value;
      setText(next);
      if (next.trim() === "" || next === "-" || next === "." || next === "-.") return;
      const parsed = Number(next);
      if (Number.isFinite(parsed)) onChange(parsed);
    }}
    onBlur={() => setText(String(Number(value.toFixed(2))))}
  /></label>;
}

function EditDialog({
  libraryId,
  target,
  busy,
  onClose,
  onSaved,
  onError,
}: {
  libraryId: string;
  target: EditTarget;
  busy: boolean;
  onClose: () => void;
  onSaved: (value: PhysicalLibrary) => void;
  onError: (value: string) => void;
}) {
  const [name, setName] = useState(target.kind === "BOOKCASE" ? target.item.name : "");
  const [description, setDescription] = useState(target.kind === "BOOKCASE" ? target.item.description ?? "" : "");
  const [number, setNumber] = useState(target.kind === "BOOKCASE" ? "" : String(target.kind === "SHELF" ? target.item.shelf_number : target.item.container_number));
  const [size, setSize] = useState<DimensionDraft>(() => {
    if (target.kind === "BOOKCASE") return {
      first: target.item.height_mm?.toString() ?? "",
      second: target.item.width_mm?.toString() ?? "",
      third: target.item.depth_mm?.toString() ?? "",
    };
    if (target.kind === "SHELF") return {
      first: target.item.usable_height_mm?.toString() ?? "",
      second: target.item.usable_width_mm?.toString() ?? "",
      third: target.item.usable_depth_mm?.toString() ?? "",
    };
    return { first: "", second: "", third: "" };
  });

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      let result: PhysicalLibrary;
      if (target.kind === "BOOKCASE") {
        result = await serverApi.updateBookcase(libraryId, target.item.id, {
          name,
          description: description.trim() || null,
          height_mm: optionalNumber(size.first),
          width_mm: optionalNumber(size.second),
          depth_mm: optionalNumber(size.third),
        });
      } else if (target.kind === "SHELF") {
        result = await serverApi.updateShelf(libraryId, target.item.id, {
          shelf_number: Number.parseInt(number, 10),
          usable_height_mm: optionalNumber(size.first),
          usable_width_mm: optionalNumber(size.second),
          usable_depth_mm: optionalNumber(size.third),
        });
      } else {
        result = await serverApi.updateContainer(
          libraryId,
          target.item.id,
          Number.parseInt(number, 10),
        );
      }
      onSaved(result);
    } catch (error) {
      onError(errorMessage(error));
    }
  }

  return <div className="server-modal-backdrop"><section className="server-physical-dialog" role="dialog" aria-modal="true">
    <p className="server-card-eyebrow">Physical library maintenance</p>
    <h2>Edit {target.kind === "BOOKCASE" ? "bookcase" : target.kind === "SHELF" ? "shelf" : "container"}</h2>
    <form onSubmit={(event) => void submit(event)}>
      {target.kind === "BOOKCASE" ? <>
        <label>Name *<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={160} /></label>
        <label>Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} /></label>
      </> : <label>{target.kind === "SHELF" ? "Shelf" : "Container"} number *<input type="number" min="1" value={number} onChange={(event) => setNumber(event.target.value)} required /></label>}
      {target.kind !== "CONTAINER" && <fieldset><legend>Optional physical dimensions</legend><div className="server-dimension-grid">
        <label>{target.kind === "BOOKCASE" ? "Height" : "Usable height"} (mm)<input type="number" min="1" value={size.first} onChange={(event) => setSize({ ...size, first: event.target.value })} /></label>
        <label>{target.kind === "BOOKCASE" ? "Width" : "Usable width"} (mm)<input type="number" min="1" value={size.second} onChange={(event) => setSize({ ...size, second: event.target.value })} /></label>
        <label>{target.kind === "BOOKCASE" ? "Depth" : "Usable depth"} (mm)<input type="number" min="1" value={size.third} onChange={(event) => setSize({ ...size, third: event.target.value })} /></label>
      </div></fieldset>}
      <div className="server-dialog-actions"><button type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="server-primary-action" type="submit" disabled={busy}>Save changes</button></div>
    </form>
  </section></div>;
}

function GeometryDialog({
  libraryId,
  data,
  onClose,
  onSaved,
  onError,
}: {
  libraryId: string;
  data: PhysicalLibrary;
  onClose: () => void;
  onSaved: (value: PhysicalLibrary) => void;
  onError: (value: string) => void;
}) {
  const [draft, setDraft] = useState<VisualLayout>(() => structuredClone(data.layout));
  const [bookcaseId, setBookcaseId] = useState(data.bookcases[0]?.id ?? "");
  const [shelfId, setShelfId] = useState(data.bookcases.flatMap((item) => item.shelves)[0]?.id ?? "");
  const allContainers = data.bookcases.flatMap((bookcase) => bookcase.shelves.flatMap((shelf) => shelf.containers.map((container) => ({ bookcase, shelf, container }))));
  const [containerId, setContainerId] = useState(allContainers[0]?.container.id ?? "");
  const [outsideKind, setOutsideKind] = useState<"READING" | "LOANED">("READING");
  const [saving, setSaving] = useState(false);
  const selectedBookcase = draft.bookcases.find((item) => item.bookcase_id === bookcaseId);
  const selectedBookcaseRecord = data.bookcases.find((item) => item.id === bookcaseId);
  const selectedShelf = draft.shelves.find((item) => item.shelf_id === shelfId);
  const selectedShelfRecord = data.bookcases.flatMap((item) => item.shelves).find((item) => item.id === shelfId);
  const selectedShelfBookcase = selectedShelfRecord
    ? data.bookcases.find((item) => item.id === selectedShelfRecord.bookcase_id)
    : undefined;
  const selectedShelfFurniture = selectedShelfBookcase
    ? draft.bookcases.find((item) => item.bookcase_id === selectedShelfBookcase.id)
    : undefined;
  const selectedContainer = draft.containers.find((item) => item.container_id === containerId);
  const selectedContainerContext = allContainers.find((item) => item.container.id === containerId);
  const selectedOutside = draft.outside_areas.find((item) => item.area_kind === outsideKind);
  const draftGeometry = physicalMapGeometry({ ...data, layout: draft });
  const selectedContainerShelfRect = draftGeometry.shelves.find((item) => item.shelfId === selectedContainerContext?.shelf.id);
  const containerShelfWidthMm = selectedContainerContext?.shelf.usable_width_mm ?? selectedContainerShelfRect?.width ?? 1;
  const containerShelfHeightMm = selectedContainerContext?.shelf.usable_height_mm ?? selectedContainerShelfRect?.height ?? 1;
  const selectedSupportLayout = selectedContainer?.support_container_id
    ? draft.containers.find((item) => item.container_id === selectedContainer.support_container_id)
    : null;
  const supportTopPercent = selectedSupportLayout?.y ?? 100;
  const supportClearanceMm = selectedContainer
    ? (supportTopPercent - selectedContainer.y - selectedContainer.height) / 100 * containerShelfHeightMm
    : 0;
  const supportContainers = selectedContainerContext
    ? allContainers.filter(({ shelf, container }) => (
      shelf.id === selectedContainerContext.shelf.id &&
      container.layer === selectedContainerContext.container.layer &&
      container.container_type !== selectedContainerContext.container.container_type &&
      container.book_count > 0
    ))
    : [];

  const selectedBookcaseShelves = selectedBookcaseRecord?.shelves ?? [];
  const selectedShelfContainers = selectedShelfRecord?.containers ?? [];
  const verticalShelfDistribution = selectedShelfFurniture?.shelf_direction === "TOP_TO_BOTTOM" ||
    selectedShelfFurniture?.shelf_direction === "BOTTOM_TO_TOP";

  function selectBookcase(nextBookcaseId: string) {
    setBookcaseId(nextBookcaseId);
    const nextBookcase = data.bookcases.find((item) => item.id === nextBookcaseId);
    const nextShelf = nextBookcase?.shelves[0];
    setShelfId(nextShelf?.id ?? "");
    setContainerId(nextShelf?.containers[0]?.id ?? "");
  }

  function selectShelf(nextShelfId: string) {
    setShelfId(nextShelfId);
    const nextShelf = data.bookcases.flatMap((item) => item.shelves).find((item) => item.id === nextShelfId);
    setContainerId(nextShelf?.containers[0]?.id ?? "");
  }

  function changeHomogeneity(checked: boolean) {
    if (!selectedBookcase || selectedBookcase.homogeneous_structure === checked) return;
    if (checked && !window.confirm(
      "Make this furniture homogeneous? Independent shelf frames and separators will be recalculated when you save. This may move shelf boundaries.",
    )) return;
    updateBookcase("homogeneous_structure", checked);
  }

  function updateBookcase(field: keyof NonNullable<typeof selectedBookcase>, value: number | string | boolean) {
    setDraft((current) => ({ ...current, bookcases: current.bookcases.map((item) => item.bookcase_id === bookcaseId ? { ...item, [field]: value } : item) }));
  }

  function updateShelf(changes: Partial<NonNullable<typeof selectedShelf>>) {
    setDraft((current) => ({ ...current, shelves: current.shelves.map((item) => item.shelf_id === shelfId ? { ...item, ...changes } : item) }));
  }

  function updateContainer(changes: Partial<NonNullable<typeof selectedContainer>>) {
    setDraft((current) => ({ ...current, containers: current.containers.map((item) => item.container_id === containerId ? { ...item, ...changes } : item) }));
  }

  function chooseSupport(value: string) {
    if (!selectedContainer) return;
    if (value === "SHELF") {
      updateContainer({ support_kind: "SHELF", support_container_id: null, y: 100 - selectedContainer.height });
      return;
    }
    const support = draft.containers.find((item) => item.container_id === value);
    if (!support) return;
    const width = Math.min(selectedContainer.width, 100 - support.x);
    updateContainer({
      support_kind: "CONTAINER",
      support_container_id: value,
      y: Math.max(0, support.y - selectedContainer.height),
      x: support.x,
      width,
    });
  }

  function shelfDisplayValue(field: "x_mm" | "floor_y_mm" | "width_mm" | "height_mm"): number {
    if (!selectedShelf || !selectedShelfFurniture) return 0;
    const denominator = field === "x_mm" || field === "width_mm"
      ? selectedShelfFurniture.width_mm
      : selectedShelfFurniture.height_mm;
    return draft.geometry_mode === "MANUAL"
      ? selectedShelf[field] / denominator * 100
      : selectedShelf[field];
  }

  function updateShelfGeometry(field: "x_mm" | "floor_y_mm" | "width_mm" | "height_mm", value: number) {
    if (!selectedShelfFurniture) return;
    const denominator = field === "x_mm" || field === "width_mm"
      ? selectedShelfFurniture.width_mm
      : selectedShelfFurniture.height_mm;
    updateShelf({
      [field]: draft.geometry_mode === "MANUAL" ? value / 100 * denominator : value,
      ...(draft.geometry_mode === "MANUAL" && field === "width_mm" ? { width_source: "ENTERED" as const } : {}),
      ...(draft.geometry_mode === "MANUAL" && field === "height_mm" ? { height_source: "ENTERED" as const } : {}),
    });
  }

  function shelfStructureValue(value: number, axis: "WIDTH" | "HEIGHT"): number {
    if (!selectedShelfFurniture || draft.geometry_mode === "PHYSICAL") return value;
    const span = axis === "WIDTH" ? selectedShelfFurniture.width_mm : selectedShelfFurniture.height_mm;
    return value / span * 100;
  }

  function updateShelfStructure(
    field: "left_frame_mm" | "right_frame_mm" | "top_closure_mm" | "bottom_board_mm" | "separator_after_mm",
    value: number,
    axis: "WIDTH" | "HEIGHT",
  ) {
    if (!selectedShelfFurniture) return;
    const span = axis === "WIDTH" ? selectedShelfFurniture.width_mm : selectedShelfFurniture.height_mm;
    updateShelf({ [field]: draft.geometry_mode === "PHYSICAL" ? value : value / 100 * span });
  }

  function updateContainerMillimetres(field: "start" | "bottom" | "width" | "height", value: number) {
    if (!selectedContainer) return;
    const height = selectedContainer.height;
    const width = selectedContainer.width;
    const clearance = supportTopPercent - selectedContainer.y - height;
    const horizontal = value / containerShelfWidthMm * 100;
    const alignment = selectedContainerContext?.container.container_type === "ROW"
      ? selectedContainer.row_anchor
      : selectedContainer.pile_alignment;
    if (field === "start") {
      if (alignment === "RIGHT") updateContainer({ x: horizontal - width });
      else if (alignment === "CENTER") updateContainer({ x: horizontal - width / 2 });
      else updateContainer({ x: horizontal });
    }
    else if (field === "bottom") updateContainer({ y: supportTopPercent - height - value / containerShelfHeightMm * 100 });
    else if (field === "width") {
      const nextWidth = value / containerShelfWidthMm * 100;
      if (alignment === "RIGHT") updateContainer({ width: nextWidth, x: selectedContainer.x + width - nextWidth });
      else if (alignment === "CENTER") updateContainer({ width: nextWidth, x: selectedContainer.x + width / 2 - nextWidth / 2 });
      else updateContainer({ width: nextWidth });
    }
    else {
      const nextHeight = value / containerShelfHeightMm * 100;
      updateContainer({ height: nextHeight, y: supportTopPercent - clearance - nextHeight });
    }
  }

  function displayedContainerStartMm(): number {
    if (!selectedContainer || !selectedContainerContext) return 0;
    if (selectedContainerContext.container.container_type === "ROW") {
      return (selectedContainer.row_anchor === "RIGHT"
        ? selectedContainer.x + selectedContainer.width
        : selectedContainer.x) / 100 * containerShelfWidthMm;
    }
    if (selectedContainer.pile_alignment === "RIGHT") {
      return (selectedContainer.x + selectedContainer.width) / 100 * containerShelfWidthMm;
    }
    if (selectedContainer.pile_alignment === "CENTER") {
      return (selectedContainer.x + selectedContainer.width / 2) / 100 * containerShelfWidthMm;
    }
    return selectedContainer.x / 100 * containerShelfWidthMm;
  }

  function containerDisplayValue(field: "start" | "bottom" | "width" | "height"): number {
    if (!selectedContainer) return 0;
    if (draft.geometry_mode === "PHYSICAL") {
      if (field === "start") return displayedContainerStartMm();
      if (field === "bottom") return supportClearanceMm;
      if (field === "width") return selectedContainer.width / 100 * containerShelfWidthMm;
      return selectedContainer.height / 100 * containerShelfHeightMm;
    }
    if (field === "start") return displayedContainerStartMm() / containerShelfWidthMm * 100;
    if (field === "bottom") return supportTopPercent - selectedContainer.y - selectedContainer.height;
    return field === "width" ? selectedContainer.width : selectedContainer.height;
  }

  function updateContainerDisplay(field: "start" | "bottom" | "width" | "height", value: number) {
    const millimetres = draft.geometry_mode === "PHYSICAL"
      ? value
      : value / 100 * (field === "start" || field === "width" ? containerShelfWidthMm : containerShelfHeightMm);
    updateContainerMillimetres(field, millimetres);
  }

  function updateOutside(field: "x" | "floor" | "width" | "height", value: number) {
    setDraft((current) => ({
      ...current,
      outside_areas: current.outside_areas.map((item) => {
        if (item.area_kind !== outsideKind) return item;
        if (field === "x") return { ...item, x_mm: value };
        if (field === "floor") return { ...item, y_mm: value };
        if (field === "width") return { ...item, width_mm: value };
        return { ...item, height_mm: value };
      }),
    }));
  }

  async function save() {
    const modeChanged = draft.geometry_mode !== data.layout.geometry_mode;
    const homogeneityChanged = draft.bookcases.some((item) => {
      const previous = data.layout.bookcases.find((entry) => entry.bookcase_id === item.bookcase_id);
      return previous && previous.homogeneous_structure !== item.homogeneous_structure;
    });
    if (modeChanged && !window.confirm(
      "This recalculates shared shelf geometry. Previewed values will replace the current derived layout only if every shelf fits. Continue?",
    )) return;
    setSaving(true);
    try {
      onSaved(await serverApi.updateVisualLayout(libraryId, {
        ...draft,
        refresh_shelves_from_physical: draft.geometry_mode === "PHYSICAL" || Boolean(homogeneityChanged),
      }));
    } catch (caught) {
      onError(errorMessage(caught));
    } finally {
      setSaving(false);
    }
  }

  const numberField = (
    label: string,
    value: number,
    onChange: (value: number) => void,
    options: { min?: number; max?: number; step?: number; disabled?: boolean } = {},
  ) => <NumericField label={label} value={value} onChange={onChange} {...options} />;

  return <div className="server-modal-backdrop"><section className="server-physical-dialog server-geometry-dialog" role="dialog" aria-modal="true">
    <p className="server-card-eyebrow">Visual workspace</p><h2>Customize library map</h2>
    <p className="server-field-help">Precise controls are implemented first. Direct dragging and the visual map will reuse the proven Local camera and geometry in the next increment.</p>
    <div className="server-geometry-sections">
      <fieldset><legend>Geometry mode</legend>
        <label>Projection<select value={draft.geometry_mode} onChange={(event) => setDraft((current) => ({ ...current, geometry_mode: event.target.value as "MANUAL" | "PHYSICAL" }))}><option value="MANUAL">Manual proportions</option><option value="PHYSICAL">Physical dimensions</option></select></label>
        <small>{draft.geometry_mode === "PHYSICAL" ? "Entered exterior furniture and interior shelf measurements govern the projection. Missing axes use labelled fallbacks; invalid structures cannot be applied." : "Furniture uses millimetre-shaped map units. Shelf and container controls are percentages of their parent; physical metadata remains informative."}</small>
      </fieldset>
      <fieldset><legend>Furniture geometry (mm)</legend>
        <label>Bookcase<select value={bookcaseId} onChange={(event) => selectBookcase(event.target.value)}>{data.bookcases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        {selectedBookcase && <>
          <div className="server-dimension-grid">
            {numberField("Horizontal — left edge", selectedBookcase.x_mm, (value) => updateBookcase("x_mm", value), { step: 1 })}
            {numberField("Floor baseline", selectedBookcase.floor_y_mm, (value) => updateBookcase("floor_y_mm", value), { step: 1 })}
            {numberField("Exterior width", selectedBookcase.width_mm, (value) => updateBookcase("width_mm", value), { min: 5, step: 1, disabled: draft.geometry_mode === "PHYSICAL" && Boolean(selectedBookcaseRecord?.width_mm) })}
            {numberField("Exterior height", selectedBookcase.height_mm, (value) => updateBookcase("height_mm", value), { min: 5, step: 1, disabled: draft.geometry_mode === "PHYSICAL" && Boolean(selectedBookcaseRecord?.height_mm) })}
          </div>
          <label>Fixed shelf distribution<select value={selectedBookcase.shelf_direction} onChange={(event) => updateBookcase("shelf_direction", event.target.value)} disabled={Boolean(selectedBookcaseRecord?.shelves.length)}><option value="TOP_TO_BOTTOM">Top to bottom</option><option value="BOTTOM_TO_TOP">Bottom to top</option><option value="LEFT_TO_RIGHT">Left to right</option><option value="RIGHT_TO_LEFT">Right to left</option></select></label>
          <label className="server-check server-compact-check"><input type="checkbox" checked={selectedBookcase.homogeneous_structure} onChange={(event) => changeHomogeneity(event.target.checked)} /> Homogeneous structure</label>
          <div className="server-dimension-grid">
            {numberField("Left frame", selectedBookcase.frame_left_mm, (value) => updateBookcase("frame_left_mm", value), { min: 0, step: 1 })}
            {numberField("Right frame", selectedBookcase.frame_right_mm, (value) => updateBookcase("frame_right_mm", value), { min: 0, step: 1 })}
            {numberField("Upper closure", selectedBookcase.top_closure_mm, (value) => updateBookcase("top_closure_mm", value), { min: 0, step: 1 })}
            {numberField("Lower closure / board", selectedBookcase.bottom_closure_mm, (value) => updateBookcase("bottom_closure_mm", value), { min: 5, step: 1 })}
            {numberField("Separator thickness", selectedBookcase.separator_thickness_mm, (value) => updateBookcase("separator_thickness_mm", value), { min: 5, step: 1 })}
          </div>
          <small>{selectedBookcaseRecord && selectedBookcaseRecord.width_mm && selectedBookcaseRecord.height_mm ? "Exterior dimensions are entered physical metadata." : "Missing exterior measurements use editable fallback map millimetres (2200 × 800 × 280 defaults)."}</small>
        </>}
      </fieldset>
      <fieldset><legend>Shelf compartment {draft.geometry_mode === "PHYSICAL" ? "(mm)" : "(% of furniture)"}</legend>
        <label>Shelf<select value={shelfId} onChange={(event) => selectShelf(event.target.value)}><option value="">{selectedBookcaseShelves.length ? "Choose shelf" : "This furniture has no shelves"}</option>{selectedBookcaseShelves.map((shelf) => <option key={shelf.id} value={shelf.id}>{selectedBookcaseRecord?.name} · Shelf {shelf.shelf_number}</option>)}</select></label>
        {selectedShelf && selectedShelfFurniture && <>
          <div className="server-dimension-grid">
            {numberField(draft.geometry_mode === "PHYSICAL" ? "Derived left edge (mm)" : "Left edge (%)", shelfDisplayValue("x_mm"), (value) => updateShelfGeometry("x_mm", value), { min: 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: draft.geometry_mode === "PHYSICAL" })}
            {numberField(draft.geometry_mode === "PHYSICAL" ? "Derived floor baseline (mm)" : "Floor baseline (%)", shelfDisplayValue("floor_y_mm"), (value) => updateShelfGeometry("floor_y_mm", value), { min: 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: draft.geometry_mode === "PHYSICAL" })}
            {numberField(draft.geometry_mode === "PHYSICAL" ? "Derived interior width (mm)" : "Width (%)", shelfDisplayValue("width_mm"), (value) => updateShelfGeometry("width_mm", value), { min: draft.geometry_mode === "PHYSICAL" ? 5 : .1, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: draft.geometry_mode === "PHYSICAL" })}
            {numberField(draft.geometry_mode === "PHYSICAL" ? "Derived interior height (mm)" : "Height (%)", shelfDisplayValue("height_mm"), (value) => updateShelfGeometry("height_mm", value), { min: draft.geometry_mode === "PHYSICAL" ? 5 : .1, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: draft.geometry_mode === "PHYSICAL" })}
          </div>
          <small>Width: {(selectedShelf.width_source ?? "derived").toLowerCase()} · Height: {(selectedShelf.height_source ?? "derived").toLowerCase()}. Entered physical dimensions are edited in Library layout, not overwritten here.</small>
          <label className="server-check server-compact-check"><input type="checkbox" checked={selectedShelf.open_top} onChange={(event) => updateShelf({ open_top: event.target.checked })} disabled={Boolean(selectedShelfRecord?.usable_width_mm && selectedShelfRecord.usable_width_mm !== selectedShelfFurniture.width_mm)} /> Open top shelf</label>
          {!selectedShelfFurniture.homogeneous_structure && <>
            <div className="server-geometry-subsection"><b>Independent shelf structure</b><small>Frames define this shelf's usable rectangle. Alignment adjustment is retained only for exceptional asymmetric measured shelves.</small></div>
            <div className="server-dimension-grid">
              {verticalShelfDistribution && numberField(`Left frame (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, shelfStructureValue(selectedShelf.left_frame_mm, "WIDTH"), (value) => updateShelfStructure("left_frame_mm", value, "WIDTH"), { min: 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}
              {verticalShelfDistribution && numberField(`Right frame (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, shelfStructureValue(selectedShelf.right_frame_mm, "WIDTH"), (value) => updateShelfStructure("right_frame_mm", value, "WIDTH"), { min: 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}
              {!verticalShelfDistribution && numberField(`Upper closure (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, shelfStructureValue(selectedShelf.top_closure_mm, "HEIGHT"), (value) => updateShelfStructure("top_closure_mm", value, "HEIGHT"), { min: 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}
              {!verticalShelfDistribution && numberField(`Lower board (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, shelfStructureValue(selectedShelf.bottom_board_mm, "HEIGHT"), (value) => updateShelfStructure("bottom_board_mm", value, "HEIGHT"), { min: 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}
              {selectedShelf.separator_after_mm !== null && numberField(`Following separator (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, shelfStructureValue(selectedShelf.separator_after_mm, selectedShelfFurniture.shelf_direction === "TOP_TO_BOTTOM" || selectedShelfFurniture.shelf_direction === "BOTTOM_TO_TOP" ? "HEIGHT" : "WIDTH"), (value) => updateShelfStructure("separator_after_mm", value, selectedShelfFurniture.shelf_direction === "TOP_TO_BOTTOM" || selectedShelfFurniture.shelf_direction === "BOTTOM_TO_TOP" ? "HEIGHT" : "WIDTH"), { min: draft.geometry_mode === "PHYSICAL" ? 5 : 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}
            </div>
            <details className="server-geometry-advanced"><summary>Advanced alignment adjustment</summary>
              <label>Horizontal alignment<select value={selectedShelf.alignment} onChange={(event) => updateShelf({ alignment: event.target.value as "LEFT" | "CENTER" | "RIGHT" })}><option value="LEFT">Left</option><option value="CENTER">Centre</option><option value="RIGHT">Right</option></select></label>
              {numberField(draft.geometry_mode === "PHYSICAL" ? "Additional offset (mm)" : "Additional offset (%)", draft.geometry_mode === "PHYSICAL" ? selectedShelf.offset_mm : selectedShelf.offset_mm / selectedShelfFurniture.width_mm * 100, (value) => updateShelf({ offset_mm: draft.geometry_mode === "PHYSICAL" ? value : value / 100 * selectedShelfFurniture.width_mm }), { step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}
            </details>
            {selectedShelf.separator_after_mm !== null && <label>Separator anchor<select value={selectedShelf.separator_anchor} onChange={(event) => updateShelf({ separator_anchor: event.target.value as "TOP" | "BOTTOM" })}><option value="BOTTOM">Lower board</option><option value="TOP">Upper closure</option></select></label>}
          </>}
        </>}
      </fieldset>
      <fieldset><legend>Container geometry and support {draft.geometry_mode === "PHYSICAL" ? "(mm)" : "(% of shelf)"}</legend><label>Container<select value={containerId} onChange={(event) => setContainerId(event.target.value)}><option value="">{selectedShelfRecord ? (selectedShelfContainers.length ? "Choose container" : "This shelf has no containers") : "Choose a shelf first"}</option>{selectedShelfContainers.map((container) => <option key={container.id} value={container.id}>{selectedBookcaseRecord?.name} · S{selectedShelfRecord?.shelf_number} · {container.layer === "BACKGROUND" ? "BG" : "FG"} {container.container_type === "ROW" ? "Row" : "Pile"} {container.container_number}</option>)}</select></label>{selectedContainer && selectedContainerContext && <><div className="server-dimension-grid">{numberField(`${selectedContainerContext.container.container_type === "ROW" ? "Anchor" : "Alignment"} position (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, containerDisplayValue("start"), (value) => updateContainerDisplay("start", value), { min: 0, max: draft.geometry_mode === "PHYSICAL" ? containerShelfWidthMm : 100, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}{numberField(`Bottom clearance (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, containerDisplayValue("bottom"), (value) => updateContainerDisplay("bottom", value), { min: 0, max: draft.geometry_mode === "PHYSICAL" ? containerShelfHeightMm : 100, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: selectedContainer.support_kind === "CONTAINER" || selectedContainerContext.container.layer === "FOREGROUND" })}{numberField(`Width (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, containerDisplayValue("width"), (value) => updateContainerDisplay("width", value), { min: draft.geometry_mode === "PHYSICAL" ? 1 : .1, max: draft.geometry_mode === "PHYSICAL" ? containerShelfWidthMm : 100, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: draft.geometry_mode === "PHYSICAL" && selectedContainerContext.container.book_count > 0 })}{numberField(`Height (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, containerDisplayValue("height"), (value) => updateContainerDisplay("height", value), { min: draft.geometry_mode === "PHYSICAL" ? 1 : .1, max: draft.geometry_mode === "PHYSICAL" ? containerShelfHeightMm : 100, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: draft.geometry_mode === "PHYSICAL" && selectedContainerContext.container.book_count > 0 })}</div><small>{draft.geometry_mode === "PHYSICAL" && selectedContainerContext.container.book_count > 0 ? "Occupied width and height are derived from the books' physical dimensions and documented fallbacks. Change the anchor, alignment or support here; edit book measurements to change occupied size." : "Manual values are percentages of the selected shelf. Bottom clearance is relative to the immediate support; zero means physical contact."} Only shelf-supported background containers may use a visual depth offset.</small>{selectedContainerContext.container.container_type === "ROW" && <label>Row growth anchor<select value={selectedContainer.row_anchor} onChange={(event) => updateContainer({ row_anchor: event.target.value as "LEFT" | "RIGHT" })}><option value="LEFT">Left edge fixed — grow right</option><option value="RIGHT">Right edge fixed — grow left</option></select></label>}<label>Rests on<select value={selectedContainer.support_kind === "CONTAINER" ? selectedContainer.support_container_id ?? "" : "SHELF"} onChange={(event) => chooseSupport(event.target.value)}><option value="SHELF">Shelf bottom</option>{supportContainers.map(({ bookcase, shelf, container }) => <option key={container.id} value={container.id}>{bookcase.name} · Shelf {shelf.shelf_number} · {container.layer === "BACKGROUND" ? "Background" : "Foreground"} {container.container_type === "ROW" ? "Row" : "Pile"} {container.container_number}</option>)}</select><small>Only a non-empty opposite-type container in this shelf and layer can be used.</small></label>{selectedContainerContext.container.container_type === "PILE" && <label>Pile alignment<select value={selectedContainer.pile_alignment} onChange={(event) => updateContainer({ pile_alignment: event.target.value as "LEFT" | "CENTER" | "RIGHT" })}><option value="LEFT">Left</option><option value="CENTER">Centre</option><option value="RIGHT">Right</option></select></label>}</>}</fieldset>
      <fieldset>
        <legend>Outside-library areas (mm)</legend>
        <label>Area<select value={outsideKind} onChange={(event) => setOutsideKind(event.target.value as "READING" | "LOANED")}><option value="READING">Reading</option><option value="LOANED">On loan</option></select></label>
        {selectedOutside && <><div className="server-dimension-grid">
          {numberField("Horizontal", selectedOutside.x_mm, (value) => updateOutside("x", value), { step: 1 })}
          {numberField("Floor baseline", selectedOutside.y_mm, (value) => updateOutside("floor", value), { step: 1 })}
          {numberField("Width", selectedOutside.width_mm, (value) => updateOutside("width", value), { min: 1, step: 1 })}
          {numberField("Height", selectedOutside.height_mm, (value) => updateOutside("height", value), { min: 1, step: 1 })}
        </div><small>Horizontal marks the left edge; Floor baseline marks the bottom edge. Width and Height extend right and upward from those coordinates.</small></>}
      </fieldset>
    </div>
    <div className="server-dialog-actions"><button type="button" onClick={onClose} disabled={saving}>Cancel</button><button className="server-primary-action" type="button" onClick={() => void save()} disabled={saving}>{saving ? "Saving…" : "Save visual layout"}</button></div>
  </section></div>;
}

export default function PhysicalLibraryWorkspace({
  libraryId,
}: {
  libraryId: string;
}) {
  const [data, setData] = useState<PhysicalLibrary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { notices, pushNotice, dismissNotice } = useTimedNotices();
  const [editing, setEditing] = useState<EditTarget | null>(null);
  const [layoutEditing, setLayoutEditing] = useState(false);
  const [bookcaseName, setBookcaseName] = useState("");
  const [bookcaseDirection, setBookcaseDirection] = useState<"TOP_TO_BOTTOM" | "BOTTOM_TO_TOP" | "LEFT_TO_RIGHT" | "RIGHT_TO_LEFT">("TOP_TO_BOTTOM");
  const [bookcaseHomogeneous, setBookcaseHomogeneous] = useState(true);
  const [bookcaseSize, setBookcaseSize] = useState<DimensionDraft>({ first: "", second: "", third: "" });
  const [shelfBookcase, setShelfBookcase] = useState("");
  const [shelfNumber, setShelfNumber] = useState("1");
  const [containerShelf, setContainerShelf] = useState("");
  const [containerNumber, setContainerNumber] = useState("1");
  const [containerType, setContainerType] = useState<"ROW" | "PILE">("ROW");
  const [containerLayer, setContainerLayer] = useState<"BACKGROUND" | "FOREGROUND">("BACKGROUND");

  const shelves = useMemo(
    () => data?.bookcases.flatMap((bookcase) => bookcase.shelves.map((shelf) => ({ bookcase, shelf }))) ?? [],
    [data],
  );

  useEffect(() => {
    setBusy(true);
    setError(null);
    void serverApi.physicalLibrary(libraryId)
      .then((value) => {
        setData(value);
        setShelfBookcase(value.bookcases[0]?.id ?? "");
        const firstShelf = value.bookcases.flatMap((item) => item.shelves)[0];
        setContainerShelf(firstShelf?.id ?? "");
      })
      .catch((caught) => setError(errorMessage(caught)))
      .finally(() => setBusy(false));
  }, [libraryId]);

  function accept(value: PhysicalLibrary, message: string) {
    setData(value);
    pushNotice(message);
    setError(null);
    setEditing(null);
  }

  async function mutate(action: () => Promise<PhysicalLibrary>, message: string) {
    setBusy(true);
    setError(null);
    try {
      accept(await action(), message);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function remove(kind: EditTarget["kind"], id: string, label: string) {
    if (!window.confirm(`Delete ${label}? BOOKPILE will refuse if it still contains other physical-library records.`)) return;
    setBusy(true);
    setError(null);
    try {
      if (kind === "BOOKCASE") await serverApi.deleteBookcase(libraryId, id);
      else if (kind === "SHELF") await serverApi.deleteShelf(libraryId, id);
      else await serverApi.deleteContainer(libraryId, id);
      accept(await serverApi.physicalLibrary(libraryId), `${label} deleted.`);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <section className="server-dashboard-panel"><h3>Library layout</h3><p>{busy ? "Loading physical library…" : error ?? "Physical library unavailable."}</p></section>;

  return <section className="server-physical-workspace">
    <header><div><p className="server-card-eyebrow">Shared physical structure</p><h3>Library layout</h3><p>{data.can_edit ? "Build and maintain furniture, shelves, rows and piles, then define their visual geometry and support." : "Read-only physical hierarchy. Your Viewer access includes the Library Map."}</p></div><div className="server-physical-heading-actions">{data.can_edit && <button type="button" onClick={() => setLayoutEditing(true)}><Settings2 size={17} /> Visual layout</button>}<Ruler size={30} /></div></header>
    {error && <div className="server-message error">{error}</div>}
    <TimedNoticeStack notices={notices} onDismiss={dismissNotice} />

    {data.can_edit && <div className="server-physical-builders">
      <form onSubmit={(event) => { event.preventDefault(); void mutate(() => serverApi.createBookcase(libraryId, { name: bookcaseName, description: null, height_mm: optionalNumber(bookcaseSize.first), width_mm: optionalNumber(bookcaseSize.second), depth_mm: optionalNumber(bookcaseSize.third), shelf_direction: bookcaseDirection, homogeneous_structure: bookcaseHomogeneous }), "Bookcase added.").then(() => { setBookcaseName(""); setBookcaseSize({ first: "", second: "", third: "" }); }); }}>
        <span>1</span><h4>Add bookcase</h4><label>Name *<input required maxLength={160} value={bookcaseName} onChange={(event) => setBookcaseName(event.target.value)} /></label>
        <details className="server-builder-details"><summary>Initial structure and dimensions</summary>
          <label>Shelf numbering direction<select value={bookcaseDirection} onChange={(event) => setBookcaseDirection(event.target.value as typeof bookcaseDirection)}><option value="TOP_TO_BOTTOM">Top to bottom</option><option value="BOTTOM_TO_TOP">Bottom to top</option><option value="LEFT_TO_RIGHT">Left to right</option><option value="RIGHT_TO_LEFT">Right to left</option></select></label>
          <label className="server-check server-compact-check"><input type="checkbox" checked={bookcaseHomogeneous} onChange={(event) => setBookcaseHomogeneous(event.target.checked)} /> Homogeneous shelf structure</label>
          <div className="server-dimension-grid"><label>Exterior height (mm)<input type="number" min="1" value={bookcaseSize.first} onChange={(event) => setBookcaseSize({ ...bookcaseSize, first: event.target.value })} /></label><label>Exterior width (mm)<input type="number" min="1" value={bookcaseSize.second} onChange={(event) => setBookcaseSize({ ...bookcaseSize, second: event.target.value })} /></label><label>Exterior depth (mm)<input type="number" min="1" value={bookcaseSize.third} onChange={(event) => setBookcaseSize({ ...bookcaseSize, third: event.target.value })} /></label></div>
          <small>Direction becomes fixed after the first shelf is added. Blank dimensions use independent map fallbacks and remain physically unrecorded.</small>
        </details>
        <button type="submit" disabled={busy}><Plus size={16} /> Add bookcase</button>
      </form>
      <form onSubmit={(event) => { event.preventDefault(); void mutate(() => serverApi.createShelf(libraryId, { bookcase_id: shelfBookcase, shelf_number: Number.parseInt(shelfNumber, 10), usable_height_mm: null, usable_width_mm: null, usable_depth_mm: null }), "Shelf added."); }}>
        <span>2</span><h4>Add shelf</h4><label>Bookcase *<select required value={shelfBookcase} onChange={(event) => setShelfBookcase(event.target.value)}><option value="">Choose bookcase</option>{data.bookcases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Number *<input type="number" min="1" required value={shelfNumber} onChange={(event) => setShelfNumber(event.target.value)} /></label><button type="submit" disabled={busy || !shelfBookcase}><Plus size={16} /> Add shelf</button>
      </form>
      <form onSubmit={(event) => { event.preventDefault(); void mutate(() => serverApi.createContainer(libraryId, { shelf_id: containerShelf, container_type: containerType, layer: containerLayer, container_number: Number.parseInt(containerNumber, 10) }), "Container added."); }}>
        <span>3</span><h4>Add container</h4><label>Shelf *<select required value={containerShelf} onChange={(event) => setContainerShelf(event.target.value)}><option value="">Choose shelf</option>{shelves.map(({ bookcase, shelf }) => <option key={shelf.id} value={shelf.id}>{bookcase.name} · Shelf {shelf.shelf_number}</option>)}</select></label><div className="server-inline-fields"><label>Type<select value={containerType} onChange={(event) => setContainerType(event.target.value as "ROW" | "PILE")}><option value="ROW">Row</option><option value="PILE">Pile</option></select></label><label>Layer<select value={containerLayer} onChange={(event) => setContainerLayer(event.target.value as "BACKGROUND" | "FOREGROUND")}><option value="BACKGROUND">Background</option><option value="FOREGROUND">Foreground</option></select></label><label>Number<input type="number" min="1" required value={containerNumber} onChange={(event) => setContainerNumber(event.target.value)} /></label></div><button type="submit" disabled={busy || !containerShelf}><Plus size={16} /> Add container</button>
      </form>
    </div>}

    <div className="server-physical-tree">{data.bookcases.map((bookcase) => <article key={bookcase.id}>
      <header><div><Boxes size={21} /><span><b>{bookcase.name}</b><small>{bookcase.book_count} {bookcase.book_count === 1 ? "book" : "books"} · {bookcase.shelves.length} {bookcase.shelves.length === 1 ? "shelf" : "shelves"}</small></span></div>{data.can_edit && <div><button title="Edit bookcase" type="button" onClick={() => setEditing({ kind: "BOOKCASE", item: bookcase })}><Pencil size={16} /></button><button title="Delete bookcase" type="button" onClick={() => void remove("BOOKCASE", bookcase.id, bookcase.name)}><Trash2 size={16} /></button></div>}</header>
      {bookcase.description && <p>{bookcase.description}</p>}<small>{dimensions([bookcase.height_mm, bookcase.width_mm, bookcase.depth_mm], ["H", "W", "D"])}</small>
      <div className="server-shelf-list">{bookcase.shelves.map((shelf) => <section key={shelf.id}>
        <header><div><Layers3 size={18} /><span><b>Shelf {shelf.shelf_number}</b><small>{shelf.book_count} {shelf.book_count === 1 ? "book" : "books"}</small></span></div>{data.can_edit && <div><button title="Edit shelf" type="button" onClick={() => setEditing({ kind: "SHELF", item: shelf })}><Pencil size={15} /></button><button title="Delete shelf" type="button" onClick={() => void remove("SHELF", shelf.id, `Shelf ${shelf.shelf_number}`)}><Trash2 size={15} /></button></div>}</header>
        <small>{dimensions([shelf.usable_height_mm, shelf.usable_width_mm, shelf.usable_depth_mm], ["usable H", "usable W", "usable D"])}</small>
        <div className="server-container-list">{shelf.containers.map((container) => <div key={container.id}><span><b>{container.layer === "BACKGROUND" ? "Background" : "Foreground"} {container.container_type === "ROW" ? "Row" : "Pile"} {container.container_number}</b><small>{container.book_count} {container.book_count === 1 ? "book" : "books"}</small></span>{data.can_edit && <span><button title="Edit container" type="button" onClick={() => setEditing({ kind: "CONTAINER", item: container })}><Pencil size={14} /></button><button title="Delete container" type="button" onClick={() => void remove("CONTAINER", container.id, `${container.layer.toLowerCase()} ${container.container_type.toLowerCase()} ${container.container_number}`)}><Trash2 size={14} /></button></span>}</div>)}</div>
      </section>)}</div>
    </article>)}{!data.bookcases.length && <div className="server-empty-catalogue"><Boxes size={38} /><h4>No physical structure yet</h4><p>{data.can_edit ? "Add the first bookcase above." : "The Owners have not configured the Library Map yet."}</p></div>}</div>

    {editing && <EditDialog libraryId={libraryId} target={editing} busy={busy} onClose={() => setEditing(null)} onSaved={(value) => accept(value, "Physical library updated.")} onError={setError} />}
    {layoutEditing && <GeometryDialog libraryId={libraryId} data={data} onClose={() => setLayoutEditing(false)} onSaved={(value) => { accept(value, "Visual layout saved."); setLayoutEditing(false); }} onError={(value) => { setError(value); setLayoutEditing(false); void serverApi.physicalLibrary(libraryId).then(setData).catch(() => undefined); }} />}
  </section>;
}

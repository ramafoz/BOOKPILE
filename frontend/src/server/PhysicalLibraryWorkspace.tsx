import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Boxes, ChevronDown, ChevronUp, Layers3, LockKeyhole, Pencil, Plus, Ruler, Settings2, Trash2, X } from "lucide-react";

import {
  PhysicalBookcase,
  PhysicalContainer,
  PhysicalLibrary,
  PhysicalShelf,
  VisualLayout,
  serverApi,
} from "./serverApi";
import TimedNoticeStack from "./TimedNoticeStack";
import { useTimedNotices } from "./timedNotices";
import { physicalMapGeometry, previewPhysicalShelfLayout } from "./serverMapGeometry";
import type { AppLocale } from "./locale";
import { physicalCopy, type PhysicalCopy } from "./physicalCopy";


type EditTarget =
  | { kind: "BOOKCASE"; item: PhysicalBookcase }
  | { kind: "SHELF"; item: PhysicalShelf }
  | { kind: "CONTAINER"; item: PhysicalContainer };

type DimensionDraft = {
  first: string;
  second: string;
  third: string;
};

function errorMessage(_error: unknown, copy: PhysicalCopy): string {
  return copy("requestFailed");
}

function optionalNumber(value: string): number | null {
  const cleaned = value.trim();
  return cleaned ? Number.parseInt(cleaned, 10) : null;
}

function dimensions(values: Array<number | null>, labels: string[], copy: PhysicalCopy): string {
  const recorded = values.map((value, index) => value ? `${labels[index]} ${value} mm` : null).filter(Boolean);
  return recorded.length ? recorded.join(" · ") : copy("dimensionsMissing");
}

function dimensionSourceLabel(source: "ENTERED" | "FALLBACK" | "DERIVED" | null | undefined, copy: PhysicalCopy): string {
  if (source === "ENTERED") return copy("sourceEntered");
  if (source === "FALLBACK") return copy("sourceFallback");
  return copy("sourceDerived");
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
  locale,
  onClose,
  onSaved,
  onError,
}: {
  libraryId: string;
  target: EditTarget;
  busy: boolean;
  locale: AppLocale;
  onClose: () => void;
  onSaved: (value: PhysicalLibrary) => void;
  onError: (value: string) => void;
}) {
  const copy = physicalCopy(locale);
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
      onError(errorMessage(error, copy));
    }
  }

  return <div className="server-modal-backdrop"><section className="server-physical-dialog" role="dialog" aria-modal="true">
    <p className="server-card-eyebrow">{copy("maintenance")}</p>
    <h2>{copy("editTarget", { target: copy(target.kind === "BOOKCASE" ? "bookcase" : target.kind === "SHELF" ? "shelf" : "container") })}</h2>
    <form onSubmit={(event) => void submit(event)}>
      {target.kind === "BOOKCASE" ? <>
        <label>{copy("nameRequired")}<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={160} /></label>
        <label>{copy("description")}<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} /></label>
      </> : <label>{copy("numberRequired", { target: copy(target.kind === "SHELF" ? "shelf" : "container") })}<input type="number" min="1" value={number} onChange={(event) => setNumber(event.target.value)} required /></label>}
      {target.kind !== "CONTAINER" && <fieldset><legend>{copy("optionalDimensions")}</legend><div className="server-dimension-grid">
        <label>{copy(target.kind === "BOOKCASE" ? "height" : "usableHeight")} (mm)<input type="number" min="1" value={size.first} onChange={(event) => setSize({ ...size, first: event.target.value })} /></label>
        <label>{copy(target.kind === "BOOKCASE" ? "width" : "usableWidth")} (mm)<input type="number" min="1" value={size.second} onChange={(event) => setSize({ ...size, second: event.target.value })} /></label>
        <label>{copy(target.kind === "BOOKCASE" ? "depth" : "usableDepth")} (mm)<input type="number" min="1" value={size.third} onChange={(event) => setSize({ ...size, third: event.target.value })} /></label>
      </div></fieldset>}
      <div className="server-dialog-actions"><button type="button" onClick={onClose} disabled={busy}>{copy("cancel")}</button><button className="server-primary-action" type="submit" disabled={busy}>{copy("saveChanges")}</button></div>
    </form>
  </section></div>;
}

export type GeometrySelection =
  | { kind: "BOOKCASE"; id: string }
  | { kind: "SHELF"; id: string }
  | { kind: "CONTAINER"; id: string };

export function GeometryDialog({
  libraryId,
  data,
  locale,
  onClose,
  onSaved,
  onError,
  presentation = "MODAL",
  collapsed = false,
  onToggleCollapsed,
  initialSelection = null,
  onDraftChange,
  baselineLayout,
  onSelectionChange,
}: {
  libraryId: string;
  data: PhysicalLibrary;
  locale: AppLocale;
  onClose: () => void;
  onSaved: (value: PhysicalLibrary) => void;
  onError: (value: string) => void;
  presentation?: "MODAL" | "PANEL";
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  initialSelection?: GeometrySelection | null;
  onDraftChange?: (value: VisualLayout) => void;
  baselineLayout?: VisualLayout;
  onSelectionChange?: (value: GeometrySelection) => void;
}) {
  const copy = physicalCopy(locale);
  const [draft, setDraft] = useState<VisualLayout>(() => structuredClone(data.layout));
  const [bookcaseId, setBookcaseId] = useState(data.bookcases[0]?.id ?? "");
  const [shelfId, setShelfId] = useState(data.bookcases.flatMap((item) => item.shelves)[0]?.id ?? "");
  const allContainers = data.bookcases.flatMap((bookcase) => bookcase.shelves.flatMap((shelf) => shelf.containers.map((container) => ({ bookcase, shelf, container }))));
  const [containerId, setContainerId] = useState(allContainers[0]?.container.id ?? "");
  const [outsideKind, setOutsideKind] = useState<"READING" | "LOANED">("READING");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    onDraftChange?.(draft);
  }, [draft, onDraftChange]);

  useEffect(() => {
    if (!initialSelection) return;
    if (initialSelection.kind === "BOOKCASE") {
      const bookcase = data.bookcases.find((item) => item.id === initialSelection.id);
      const shelf = bookcase?.shelves[0];
      setBookcaseId(initialSelection.id);
      setShelfId(shelf?.id ?? "");
      setContainerId(shelf?.containers[0]?.id ?? "");
    }
    else if (initialSelection.kind === "SHELF") {
      const shelf = data.bookcases.flatMap((item) => item.shelves).find((item) => item.id === initialSelection.id);
      if (shelf) {
        setBookcaseId(shelf.bookcase_id);
        setShelfId(shelf.id);
        setContainerId(shelf.containers[0]?.id ?? "");
      }
    } else {
      const context = data.bookcases.flatMap((bookcase) => bookcase.shelves.flatMap((shelf) => shelf.containers.map((container) => ({ bookcase, shelf, container })))).find((item) => item.container.id === initialSelection.id);
      if (context) {
        setBookcaseId(context.bookcase.id);
        setShelfId(context.shelf.id);
        setContainerId(context.container.id);
      }
    }
  }, [initialSelection, data.bookcases]);
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
  const selectedContainerRecordContext = allContainers.find((item) => item.container.id === containerId);
  const selectedContainerHasMeasurements = data.books.some((book) => book.container_id === containerId && [book.height_mm, book.width_mm, book.thickness_mm].some((value) => value !== null));
  const selectedContainerContext = selectedContainerRecordContext
    ? { ...selectedContainerRecordContext, container: { ...selectedContainerRecordContext.container, book_count: selectedContainerHasMeasurements ? selectedContainerRecordContext.container.book_count : 0 } }
    : undefined;
  const selectedOutside = draft.outside_areas.find((item) => item.area_kind === outsideKind);
  const projectedDraft = useMemo(() => previewPhysicalShelfLayout(data, draft), [data, draft]);
  const projectedSelectedShelf = projectedDraft.shelves.find((item) => item.shelf_id === shelfId);
  const draftGeometry = physicalMapGeometry({ ...data, layout: projectedDraft });
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
    onSelectionChange?.({ kind: "BOOKCASE", id: nextBookcaseId });
  }

  function selectShelf(nextShelfId: string) {
    setShelfId(nextShelfId);
    const nextShelf = data.bookcases.flatMap((item) => item.shelves).find((item) => item.id === nextShelfId);
    setContainerId(nextShelf?.containers[0]?.id ?? "");
    onSelectionChange?.({ kind: "SHELF", id: nextShelfId });
  }

  function selectContainer(nextContainerId: string) {
    setContainerId(nextContainerId);
    if (nextContainerId) onSelectionChange?.({ kind: "CONTAINER", id: nextContainerId });
  }

  function changeHomogeneity(checked: boolean) {
    if (!selectedBookcase || selectedBookcase.homogeneous_structure === checked) return;
    if (checked && !window.confirm(
      copy("homogeneousConfirm"),
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
    const alignment = selectedContainerContext?.container.container_type === "ROW"
      ? selectedContainer.row_anchor
      : selectedContainer.pile_alignment;
    const x = alignment === "RIGHT"
      ? support.x + support.width - width
      : alignment === "CENTER"
        ? support.x + (support.width - width) / 2
        : support.x;
    updateContainer({
      support_kind: "CONTAINER",
      support_container_id: value,
      y: Math.max(0, support.y - selectedContainer.height),
      x,
      width,
    });
  }

  function shelfDisplayValue(field: "x_mm" | "floor_y_mm" | "width_mm" | "height_mm"): number {
    if (!selectedShelf || !selectedShelfFurniture) return 0;
    const displayedShelf = draft.geometry_mode === "PHYSICAL" ? (projectedSelectedShelf ?? selectedShelf) : selectedShelf;
    const denominator = field === "x_mm" || field === "width_mm"
      ? selectedShelfFurniture.width_mm
      : selectedShelfFurniture.height_mm;
    return draft.geometry_mode === "MANUAL"
      ? displayedShelf[field] / denominator * 100
      : displayedShelf[field];
  }

  function updateShelfGeometry(field: "x_mm" | "floor_y_mm" | "width_mm" | "height_mm", value: number) {
    if (!selectedShelfFurniture) return;
    const denominator = field === "x_mm" || field === "width_mm"
      ? selectedShelfFurniture.width_mm
      : selectedShelfFurniture.height_mm;
    updateShelf({
      [field]: draft.geometry_mode === "MANUAL" ? value / 100 * denominator : value,
      ...(field === "width_mm" && !selectedShelfRecord?.usable_width_mm ? { width_source: "ENTERED" as const } : {}),
      ...(field === "height_mm" && !selectedShelfRecord?.usable_height_mm ? { height_source: "ENTERED" as const } : {}),
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
    const baseline = baselineLayout ?? data.layout;
    const modeChanged = draft.geometry_mode !== baseline.geometry_mode;
    const homogeneityChanged = draft.bookcases.some((item) => {
      const previous = baseline.bookcases.find((entry) => entry.bookcase_id === item.bookcase_id);
      return previous && previous.homogeneous_structure !== item.homogeneous_structure;
    });
    if (modeChanged && !window.confirm(
      copy("recalculateConfirm"),
    )) return;
    setSaving(true);
    try {
      onSaved(await serverApi.updateVisualLayout(libraryId, {
        ...draft,
        refresh_shelves_from_physical: draft.geometry_mode === "PHYSICAL" || Boolean(homogeneityChanged),
      }));
    } catch (caught) {
      onError(errorMessage(caught, copy));
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

  const editor = <section className={`server-physical-dialog server-geometry-dialog ${presentation === "PANEL" ? "server-geometry-panel" : ""} ${collapsed ? "collapsed" : ""}`} role="dialog" aria-modal={presentation === "MODAL" ? "true" : undefined}>
    <header className="server-geometry-panel-heading"><div><p className="server-card-eyebrow">{copy("visualWorkspace")}</p><h2>{copy("customizeMap")}</h2></div>{presentation === "PANEL" && <span><button type="button" onClick={onToggleCollapsed} title={copy(collapsed ? "expandEditor" : "minimizeEditor")}>{collapsed ? <ChevronDown size={17} /> : <ChevronUp size={17} />}<span>{copy(collapsed ? "expand" : "minimize")}</span></button><button type="button" onClick={onClose} title={copy("cancelEditing")}><X size={17} /><span>{copy("cancel")}</span></button></span>}</header>
    {!collapsed && <>
    <p className="server-field-help">{copy("preciseHelp")}</p>
    <div className="server-geometry-sections">
      <fieldset><legend>{copy("geometryMode")}</legend>
        <label>{copy("projection")}<select value={draft.geometry_mode} onChange={(event) => setDraft((current) => ({ ...current, geometry_mode: event.target.value as "MANUAL" | "PHYSICAL" }))}><option value="MANUAL">{copy("manualProportions")}</option><option value="PHYSICAL">{copy("physicalDimensions")}</option></select></label>
        <small>{copy(draft.geometry_mode === "PHYSICAL" ? "physicalModeHelp" : "manualModeHelp")}</small>
      </fieldset>
      <fieldset><legend>{copy("furnitureGeometry")}</legend>
        <label>{copy("bookcase")}<select value={bookcaseId} onChange={(event) => selectBookcase(event.target.value)}>{data.bookcases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        {selectedBookcase && <>
          {draft.geometry_mode === "PHYSICAL" && selectedBookcaseRecord && (selectedBookcaseRecord.width_mm || selectedBookcaseRecord.height_mm) && <div className="server-geometry-locked-notice" role="note">
            <LockKeyhole size={18} />
            <span><b>{copy("sizeFixed")}</b> {copy("sizeFixedHelp", { dimensions: copy(selectedBookcaseRecord.width_mm && selectedBookcaseRecord.height_mm ? "exteriorBoth" : selectedBookcaseRecord.width_mm ? "exteriorWidth" : "exteriorHeight"), pronoun: selectedBookcaseRecord.width_mm && selectedBookcaseRecord.height_mm ? "them" : "it" })}</span>
          </div>}
          <div className="server-dimension-grid">
            {numberField(copy("horizontalLeft"), selectedBookcase.x_mm, (value) => updateBookcase("x_mm", value), { step: 1 })}
            {numberField(copy("floorBaseline"), selectedBookcase.floor_y_mm, (value) => updateBookcase("floor_y_mm", value), { step: 1 })}
            {numberField(copy("exteriorWidth"), selectedBookcase.width_mm, (value) => updateBookcase("width_mm", value), { min: 5, step: 1, disabled: draft.geometry_mode === "PHYSICAL" && Boolean(selectedBookcaseRecord?.width_mm) })}
            {numberField(copy("exteriorHeight"), selectedBookcase.height_mm, (value) => updateBookcase("height_mm", value), { min: 5, step: 1, disabled: draft.geometry_mode === "PHYSICAL" && Boolean(selectedBookcaseRecord?.height_mm) })}
          </div>
          <label>{copy("fixedDistribution")}<select value={selectedBookcase.shelf_direction} onChange={(event) => updateBookcase("shelf_direction", event.target.value)} disabled={Boolean(selectedBookcaseRecord?.shelves.length)}><option value="TOP_TO_BOTTOM">{copy("topBottom")}</option><option value="BOTTOM_TO_TOP">{copy("bottomTop")}</option><option value="LEFT_TO_RIGHT">{copy("leftRight")}</option><option value="RIGHT_TO_LEFT">{copy("rightLeft")}</option></select></label>
          <label className="server-check server-compact-check"><input type="checkbox" checked={selectedBookcase.homogeneous_structure} onChange={(event) => changeHomogeneity(event.target.checked)} /> {copy("homogeneous")}</label>
          <div className="server-geometry-subsection"><b>{copy("sharedStructure")}</b><small>{copy("sharedStructureHelp")}</small></div>
          <div className="server-dimension-grid">
            {numberField(copy("leftFrame"), selectedBookcase.frame_left_mm, (value) => updateBookcase("frame_left_mm", value), { min: 0, step: 1 })}
            {numberField(copy("rightFrame"), selectedBookcase.frame_right_mm, (value) => updateBookcase("frame_right_mm", value), { min: 0, step: 1 })}
            {numberField(copy("upperClosure"), selectedBookcase.top_closure_mm, (value) => updateBookcase("top_closure_mm", value), { min: 0, step: 1 })}
            {numberField(copy("lowerClosure"), selectedBookcase.bottom_closure_mm, (value) => updateBookcase("bottom_closure_mm", value), { min: 5, step: 1 })}
            {numberField(copy("separatorThickness"), selectedBookcase.separator_thickness_mm, (value) => updateBookcase("separator_thickness_mm", value), { min: 5, step: 1 })}
          </div>
          {!(draft.geometry_mode === "PHYSICAL" && selectedBookcaseRecord && (selectedBookcaseRecord.width_mm || selectedBookcaseRecord.height_mm)) && <small>{copy("fallbackExterior")}</small>}
        </>}
      </fieldset>
      <fieldset><legend>{copy("shelfCompartment", { unit: draft.geometry_mode === "PHYSICAL" ? "(mm)" : "(%)" })}</legend>
        <label>{copy("shelf")}<select value={shelfId} onChange={(event) => selectShelf(event.target.value)}><option value="">{copy(selectedBookcaseShelves.length ? "chooseShelf" : "noShelves")}</option>{selectedBookcaseShelves.map((shelf) => <option key={shelf.id} value={shelf.id}>{selectedBookcaseRecord?.name} · {copy("shelfNumber", { number: shelf.shelf_number })}</option>)}</select></label>
        {selectedShelf && selectedShelfFurniture && <>
          {draft.geometry_mode === "PHYSICAL" && selectedShelfRecord && (selectedShelfRecord.usable_width_mm || selectedShelfRecord.usable_height_mm) && <div className="server-geometry-locked-notice" role="note">
            <LockKeyhole size={18} />
            <span><b>{copy("recordedSizeFixed")}</b> {copy("shelfFixedHelp", { dimensions: copy(selectedShelfRecord.usable_width_mm && selectedShelfRecord.usable_height_mm ? "interiorBoth" : selectedShelfRecord.usable_width_mm ? "interiorWidth" : "interiorHeight"), structure: copy(selectedShelfFurniture.homogeneous_structure ? "sharedStructureReference" : "independentStructureReference") })}</span>
          </div>}
          <div className="server-dimension-grid">
            {numberField(copy(draft.geometry_mode === "PHYSICAL" ? "derivedLeft" : "leftPercent"), shelfDisplayValue("x_mm"), (value) => updateShelfGeometry("x_mm", value), { min: 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: draft.geometry_mode === "PHYSICAL" })}
            {numberField(copy(draft.geometry_mode === "PHYSICAL" ? "derivedFloor" : "floorPercent"), shelfDisplayValue("floor_y_mm"), (value) => updateShelfGeometry("floor_y_mm", value), { min: 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: draft.geometry_mode === "PHYSICAL" })}
            {numberField(draft.geometry_mode === "PHYSICAL" ? `${copy("interiorWidth")} (mm)` : copy("widthPercent"), shelfDisplayValue("width_mm"), (value) => updateShelfGeometry("width_mm", value), { min: draft.geometry_mode === "PHYSICAL" ? 5 : .1, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: draft.geometry_mode === "PHYSICAL" && Boolean(selectedShelfRecord?.usable_width_mm) })}
            {numberField(draft.geometry_mode === "PHYSICAL" ? `${copy("interiorHeight")} (mm)` : copy("heightPercent"), shelfDisplayValue("height_mm"), (value) => updateShelfGeometry("height_mm", value), { min: draft.geometry_mode === "PHYSICAL" ? 5 : .1, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: draft.geometry_mode === "PHYSICAL" && Boolean(selectedShelfRecord?.usable_height_mm) })}
          </div>
          <small>{copy("sourceSummary", { width: dimensionSourceLabel(selectedShelf.width_source, copy), height: dimensionSourceLabel(selectedShelf.height_source, copy) })}</small>
          {draft.geometry_mode === "PHYSICAL" && ((!selectedShelfRecord?.usable_width_mm && selectedShelf.width_source === "ENTERED") || (!selectedShelfRecord?.usable_height_mm && selectedShelf.height_source === "ENTERED")) && <button className="server-geometry-reset" type="button" onClick={() => updateShelf({
            ...(!selectedShelfRecord?.usable_width_mm ? { width_source: "FALLBACK" as const } : {}),
            ...(!selectedShelfRecord?.usable_height_mm ? { height_source: "FALLBACK" as const } : {}),
          })}>{copy("resetAutomatic")}</button>}
          <label className="server-check server-compact-check"><input type="checkbox" checked={selectedShelf.open_top} onChange={(event) => updateShelf({ open_top: event.target.checked })} disabled={Boolean(selectedShelfRecord?.usable_width_mm && selectedShelfRecord.usable_width_mm !== selectedShelfFurniture.width_mm)} /> {copy("openTop")}</label>
          {!selectedShelfFurniture.homogeneous_structure && <>
            <div className="server-geometry-subsection"><b>{copy("independentStructure")}</b><small>{copy("independentHelp")}</small></div>
            <div className="server-dimension-grid">
              {verticalShelfDistribution && numberField(`${copy("leftFrame")} (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, shelfStructureValue(selectedShelf.left_frame_mm, "WIDTH"), (value) => updateShelfStructure("left_frame_mm", value, "WIDTH"), { min: 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}
              {verticalShelfDistribution && numberField(`${copy("rightFrame")} (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, shelfStructureValue(selectedShelf.right_frame_mm, "WIDTH"), (value) => updateShelfStructure("right_frame_mm", value, "WIDTH"), { min: 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}
              {!verticalShelfDistribution && numberField(`${copy("upperClosure")} (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, shelfStructureValue(selectedShelf.top_closure_mm, "HEIGHT"), (value) => updateShelfStructure("top_closure_mm", value, "HEIGHT"), { min: 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}
              {!verticalShelfDistribution && numberField(`${copy("lowerBoard")} (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, shelfStructureValue(selectedShelf.bottom_board_mm, "HEIGHT"), (value) => updateShelfStructure("bottom_board_mm", value, "HEIGHT"), { min: 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}
              {selectedShelf.separator_after_mm !== null && numberField(`${copy("followingSeparator")} (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, shelfStructureValue(selectedShelf.separator_after_mm, selectedShelfFurniture.shelf_direction === "TOP_TO_BOTTOM" || selectedShelfFurniture.shelf_direction === "BOTTOM_TO_TOP" ? "HEIGHT" : "WIDTH"), (value) => updateShelfStructure("separator_after_mm", value, selectedShelfFurniture.shelf_direction === "TOP_TO_BOTTOM" || selectedShelfFurniture.shelf_direction === "BOTTOM_TO_TOP" ? "HEIGHT" : "WIDTH"), { min: draft.geometry_mode === "PHYSICAL" ? 5 : 0, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}
            </div>
            <details className="server-geometry-advanced"><summary>{copy("advancedAlignment")}</summary>
              <label>{copy("horizontalAlignment")}<select value={selectedShelf.alignment} onChange={(event) => updateShelf({ alignment: event.target.value as "LEFT" | "CENTER" | "RIGHT" })}><option value="LEFT">{copy("left")}</option><option value="CENTER">{copy("centre")}</option><option value="RIGHT">{copy("right")}</option></select></label>
              {numberField(`${copy("alignmentOffset")} (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, draft.geometry_mode === "PHYSICAL" ? selectedShelf.offset_mm : selectedShelf.offset_mm / selectedShelfFurniture.width_mm * 100, (value) => updateShelf({ offset_mm: draft.geometry_mode === "PHYSICAL" ? value : value / 100 * selectedShelfFurniture.width_mm }), { step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}
            </details>
            {selectedShelf.separator_after_mm !== null && <label>{copy("separatorAnchor")}<select value={selectedShelf.separator_anchor} onChange={(event) => updateShelf({ separator_anchor: event.target.value as "TOP" | "BOTTOM" })}><option value="BOTTOM">{copy("lowerBoard")}</option><option value="TOP">{copy("upperClosure")}</option></select></label>}
          </>}
        </>}
      </fieldset>
      <fieldset><legend>{copy("containerGeometry", { unit: draft.geometry_mode === "PHYSICAL" ? "(mm)" : "(%)" })}</legend><label>{copy("container")}<select value={containerId} onChange={(event) => selectContainer(event.target.value)}><option value="">{copy(selectedShelfRecord ? (selectedShelfContainers.length ? "chooseContainer" : "noContainers") : "chooseShelfFirst")}</option>{selectedShelfContainers.map((container) => <option key={container.id} value={container.id}>{selectedBookcaseRecord?.name} · S{selectedShelfRecord?.shelf_number} · {copy(container.layer === "BACKGROUND" ? "backgroundShort" : "foregroundShort")} {copy(container.container_type === "ROW" ? "row" : "pile")} {container.container_number}</option>)}</select></label>{selectedContainer && selectedContainerContext && <><div key={selectedContainer.container_id} className="server-dimension-grid">{numberField(copy(selectedContainerContext.container.container_type === "ROW" ? "anchorPosition" : "alignmentPosition", { unit: `(${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})` }), containerDisplayValue("start"), (value) => updateContainerDisplay("start", value), { min: 0, max: draft.geometry_mode === "PHYSICAL" ? containerShelfWidthMm : 100, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1 })}{numberField(copy("bottomClearance", { unit: `(${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})` }), containerDisplayValue("bottom"), (value) => updateContainerDisplay("bottom", value), { min: 0, max: draft.geometry_mode === "PHYSICAL" ? containerShelfHeightMm : 100, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: selectedContainer.support_kind === "CONTAINER" || selectedContainerContext.container.layer === "FOREGROUND" })}{numberField(`${copy("width")} (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, containerDisplayValue("width"), (value) => updateContainerDisplay("width", value), { min: draft.geometry_mode === "PHYSICAL" ? 1 : .1, max: draft.geometry_mode === "PHYSICAL" ? containerShelfWidthMm : 100, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: draft.geometry_mode === "PHYSICAL" && selectedContainerContext.container.book_count > 0 })}{numberField(`${copy("height")} (${draft.geometry_mode === "PHYSICAL" ? "mm" : "%"})`, containerDisplayValue("height"), (value) => updateContainerDisplay("height", value), { min: draft.geometry_mode === "PHYSICAL" ? 1 : .1, max: draft.geometry_mode === "PHYSICAL" ? containerShelfHeightMm : 100, step: draft.geometry_mode === "PHYSICAL" ? 1 : .1, disabled: draft.geometry_mode === "PHYSICAL" && selectedContainerContext.container.book_count > 0 })}</div><small>{copy(draft.geometry_mode === "PHYSICAL" && selectedContainerContext.container.book_count > 0 ? "occupiedHelp" : "envelopeHelp")} {copy("depthOffsetHelp")}</small>{selectedContainerContext.container.container_type === "ROW" && <label>{copy("rowAnchor")}<select value={selectedContainer.row_anchor} onChange={(event) => updateContainer({ row_anchor: event.target.value as "LEFT" | "RIGHT" })}><option value="LEFT">{copy("leftGrowRight")}</option><option value="RIGHT">{copy("rightGrowLeft")}</option></select></label>}<label>{copy("restsOn")}<select value={selectedContainer.support_kind === "CONTAINER" ? selectedContainer.support_container_id ?? "" : "SHELF"} onChange={(event) => chooseSupport(event.target.value)}><option value="SHELF">{copy("shelfBottom")}</option>{supportContainers.map(({ bookcase, shelf, container }) => <option key={container.id} value={container.id}>{bookcase.name} · {copy("shelfNumber", { number: shelf.shelf_number })} · {copy(container.layer === "BACKGROUND" ? "background" : "foreground")} {copy(container.container_type === "ROW" ? "row" : "pile")} {container.container_number}</option>)}</select><small>{copy("supportHelp")}</small></label>{selectedContainerContext.container.container_type === "PILE" && <label>{copy("pileAlignment")}<select value={selectedContainer.pile_alignment} onChange={(event) => updateContainer({ pile_alignment: event.target.value as "LEFT" | "CENTER" | "RIGHT" })}><option value="LEFT">{copy("left")}</option><option value="CENTER">{copy("centre")}</option><option value="RIGHT">{copy("right")}</option></select></label>}</>}</fieldset>
      {selectedContainer && selectedContainerContext?.container.container_type === "ROW" && !selectedContainerHasMeasurements && <fieldset className="server-container-shortcuts"><legend>{copy("unmeasuredRow")}</legend><p>{copy("unmeasuredRowHelp")}</p><button type="button" onClick={() => updateContainer({ x: 0, width: 100, row_anchor: "LEFT" })}>{copy("fillShelf")}</button></fieldset>}
      <fieldset>
        <legend>{copy("outsideAreas")}</legend>
        <label>{copy("area")}<select value={outsideKind} onChange={(event) => setOutsideKind(event.target.value as "READING" | "LOANED")}><option value="READING">{copy("reading")}</option><option value="LOANED">{copy("onLoan")}</option></select></label>
        {selectedOutside && <><div className="server-dimension-grid">
          {numberField(copy("horizontal"), selectedOutside.x_mm, (value) => updateOutside("x", value), { step: 1 })}
          {numberField(copy("floorBaseline"), selectedOutside.y_mm, (value) => updateOutside("floor", value), { step: 1 })}
          {numberField(copy("width"), selectedOutside.width_mm, (value) => updateOutside("width", value), { min: 1, step: 1 })}
          {numberField(copy("height"), selectedOutside.height_mm, (value) => updateOutside("height", value), { min: 1, step: 1 })}
        </div><small>{copy("areaHelp")}</small></>}
      </fieldset>
    </div>
    <div className="server-dialog-actions"><button type="button" onClick={onClose} disabled={saving}>{copy("cancel")}</button><button className="server-primary-action" type="button" onClick={() => void save()} disabled={saving}>{copy(saving ? "saving" : "applyLayout")}</button></div>
    </>}
  </section>;
  return presentation === "MODAL" ? <div className="server-modal-backdrop">{editor}</div> : editor;
}

export default function PhysicalLibraryWorkspace({
  libraryId,
  locale,
}: {
  libraryId: string;
  locale: AppLocale;
}) {
  const copy = useMemo(() => physicalCopy(locale), [locale]);
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
      .catch((caught) => setError(errorMessage(caught, copy)))
      .finally(() => setBusy(false));
  }, [copy, libraryId]);

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
      setError(errorMessage(caught, copy));
    } finally {
      setBusy(false);
    }
  }

  async function remove(kind: EditTarget["kind"], id: string, label: string) {
    if (!window.confirm(copy("deleteConfirm", { label }))) return;
    setBusy(true);
    setError(null);
    try {
      if (kind === "BOOKCASE") await serverApi.deleteBookcase(libraryId, id);
      else if (kind === "SHELF") await serverApi.deleteShelf(libraryId, id);
      else await serverApi.deleteContainer(libraryId, id);
      accept(await serverApi.physicalLibrary(libraryId), copy("deleted", { label }));
    } catch (caught) {
      setError(errorMessage(caught, copy));
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <section className="server-dashboard-panel"><h3>{copy("layout")}</h3><p>{busy ? copy("loadingPhysical") : error ?? copy("unavailable")}</p></section>;

  return <section className="server-physical-workspace">
    <header><div><p className="server-card-eyebrow">{copy("sharedPhysical")}</p><h3>{copy("structure")}</h3><p>{copy(data.can_edit ? "ownerHelp" : "viewerHelp")}</p></div><div className="server-physical-heading-actions">{data.can_edit && <button type="button" onClick={() => setLayoutEditing(true)}><Settings2 size={17} /> {copy("visualLayout")}</button>}<Ruler size={30} /></div></header>
    {error && <div className="server-message error">{error}</div>}
    <TimedNoticeStack notices={notices} onDismiss={dismissNotice} />

    {data.can_edit && <div className="server-physical-builders">
      <form onSubmit={(event) => { event.preventDefault(); void mutate(() => serverApi.createBookcase(libraryId, { name: bookcaseName, description: null, height_mm: optionalNumber(bookcaseSize.first), width_mm: optionalNumber(bookcaseSize.second), depth_mm: optionalNumber(bookcaseSize.third), shelf_direction: bookcaseDirection, homogeneous_structure: bookcaseHomogeneous }), copy("addedBookcase")).then(() => { setBookcaseName(""); setBookcaseSize({ first: "", second: "", third: "" }); }); }}>
        <span>1</span><h4>{copy("addBookcase")}</h4><label>{copy("nameRequired")}<input required maxLength={160} value={bookcaseName} onChange={(event) => setBookcaseName(event.target.value)} /></label>
        <details className="server-builder-details"><summary>{copy("initialStructure")}</summary>
          <label>{copy("numberingDirection")}<select value={bookcaseDirection} onChange={(event) => setBookcaseDirection(event.target.value as typeof bookcaseDirection)}><option value="TOP_TO_BOTTOM">{copy("topBottom")}</option><option value="BOTTOM_TO_TOP">{copy("bottomTop")}</option><option value="LEFT_TO_RIGHT">{copy("leftRight")}</option><option value="RIGHT_TO_LEFT">{copy("rightLeft")}</option></select></label>
          <label className="server-check server-compact-check"><input type="checkbox" checked={bookcaseHomogeneous} onChange={(event) => setBookcaseHomogeneous(event.target.checked)} /> {copy("homogeneousShelf")}</label>
          <div className="server-dimension-grid"><label>{copy("exteriorHeight")} (mm)<input type="number" min="1" value={bookcaseSize.first} onChange={(event) => setBookcaseSize({ ...bookcaseSize, first: event.target.value })} /></label><label>{copy("exteriorWidth")} (mm)<input type="number" min="1" value={bookcaseSize.second} onChange={(event) => setBookcaseSize({ ...bookcaseSize, second: event.target.value })} /></label><label>{copy("exteriorDepth")} (mm)<input type="number" min="1" value={bookcaseSize.third} onChange={(event) => setBookcaseSize({ ...bookcaseSize, third: event.target.value })} /></label></div>
          <small>{copy("directionHelp")}</small>
        </details>
        <button type="submit" disabled={busy}><Plus size={16} /> {copy("addBookcase")}</button>
      </form>
      <form onSubmit={(event) => { event.preventDefault(); void mutate(() => serverApi.createShelf(libraryId, { bookcase_id: shelfBookcase, shelf_number: Number.parseInt(shelfNumber, 10), usable_height_mm: null, usable_width_mm: null, usable_depth_mm: null }), copy("addedShelf")); }}>
        <span>2</span><h4>{copy("addShelf")}</h4><label>{copy("bookcase")} *<select required value={shelfBookcase} onChange={(event) => setShelfBookcase(event.target.value)}><option value="">{copy("chooseBookcase")}</option>{data.bookcases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>{copy("number")} *<input type="number" min="1" required value={shelfNumber} onChange={(event) => setShelfNumber(event.target.value)} /></label><button type="submit" disabled={busy || !shelfBookcase}><Plus size={16} /> {copy("addShelf")}</button>
      </form>
      <form onSubmit={(event) => { event.preventDefault(); void mutate(() => serverApi.createContainer(libraryId, { shelf_id: containerShelf, container_type: containerType, layer: containerLayer, container_number: Number.parseInt(containerNumber, 10) }), copy("addedContainer")); }}>
        <span>3</span><h4>{copy("addContainer")}</h4><label>{copy("shelf")} *<select required value={containerShelf} onChange={(event) => setContainerShelf(event.target.value)}><option value="">{copy("chooseShelf")}</option>{shelves.map(({ bookcase, shelf }) => <option key={shelf.id} value={shelf.id}>{bookcase.name} · {copy("shelfNumber", { number: shelf.shelf_number })}</option>)}</select></label><div className="server-inline-fields"><label>{copy("type")}<select value={containerType} onChange={(event) => setContainerType(event.target.value as "ROW" | "PILE")}><option value="ROW">{copy("row")}</option><option value="PILE">{copy("pile")}</option></select></label><label>{copy("layer")}<select value={containerLayer} onChange={(event) => setContainerLayer(event.target.value as "BACKGROUND" | "FOREGROUND")}><option value="BACKGROUND">{copy("background")}</option><option value="FOREGROUND">{copy("foreground")}</option></select></label><label>{copy("number")}<input type="number" min="1" required value={containerNumber} onChange={(event) => setContainerNumber(event.target.value)} /></label></div><button type="submit" disabled={busy || !containerShelf}><Plus size={16} /> {copy("addContainer")}</button>
      </form>
    </div>}

    <div className="server-physical-tree">{data.bookcases.map((bookcase) => <article key={bookcase.id}>
      <header><div><Boxes size={21} /><span><b>{bookcase.name}</b><small>{copy(bookcase.book_count === 1 ? "bookCount" : "booksCount", { count: bookcase.book_count })} · {copy(bookcase.shelves.length === 1 ? "shelfCount" : "shelvesCount", { count: bookcase.shelves.length })}</small></span></div>{data.can_edit && <div><button title={copy("editBookcase")} type="button" onClick={() => setEditing({ kind: "BOOKCASE", item: bookcase })}><Pencil size={16} /></button><button title={copy("deleteBookcase")} type="button" onClick={() => void remove("BOOKCASE", bookcase.id, bookcase.name)}><Trash2 size={16} /></button></div>}</header>
      {bookcase.description && <p>{bookcase.description}</p>}<small>{dimensions([bookcase.height_mm, bookcase.width_mm, bookcase.depth_mm], ["H", "W", "D"], copy)}</small>
      <div className="server-shelf-list">{bookcase.shelves.map((shelf) => <section key={shelf.id}>
        <header><div><Layers3 size={18} /><span><b>{copy("shelfNumber", { number: shelf.shelf_number })}</b><small>{copy(shelf.book_count === 1 ? "bookCount" : "booksCount", { count: shelf.book_count })}</small></span></div>{data.can_edit && <div><button title={copy("editShelf")} type="button" onClick={() => setEditing({ kind: "SHELF", item: shelf })}><Pencil size={15} /></button><button title={copy("deleteShelf")} type="button" onClick={() => void remove("SHELF", shelf.id, copy("shelfNumber", { number: shelf.shelf_number }))}><Trash2 size={15} /></button></div>}</header>
        <small>{dimensions([shelf.usable_height_mm, shelf.usable_width_mm, shelf.usable_depth_mm], ["H", "W", "D"], copy)}</small>
        <div className="server-container-list">{shelf.containers.map((container) => <div key={container.id}><span><b>{copy(container.layer === "BACKGROUND" ? "background" : "foreground")} {copy(container.container_type === "ROW" ? "row" : "pile")} {container.container_number}</b><small>{copy(container.book_count === 1 ? "bookCount" : "booksCount", { count: container.book_count })}</small></span>{data.can_edit && <span><button title={copy("editContainer")} type="button" onClick={() => setEditing({ kind: "CONTAINER", item: container })}><Pencil size={14} /></button><button title={copy("deleteContainer")} type="button" onClick={() => void remove("CONTAINER", container.id, `${copy(container.layer === "BACKGROUND" ? "background" : "foreground")} ${copy(container.container_type === "ROW" ? "row" : "pile")} ${container.container_number}`)}><Trash2 size={14} /></button></span>}</div>)}</div>
      </section>)}</div>
    </article>)}{!data.bookcases.length && <div className="server-empty-catalogue"><Boxes size={38} /><h4>{copy("noStructure")}</h4><p>{copy(data.can_edit ? "addFirst" : "ownersNotConfigured")}</p></div>}</div>

    {editing && <EditDialog libraryId={libraryId} target={editing} busy={busy} locale={locale} onClose={() => setEditing(null)} onSaved={(value) => accept(value, copy("updated"))} onError={setError} />}
    {layoutEditing && <GeometryDialog libraryId={libraryId} data={data} locale={locale} onClose={() => setLayoutEditing(false)} onSaved={(value) => { accept(value, copy("layoutSaved")); setLayoutEditing(false); }} onError={(value) => { setError(value); setLayoutEditing(false); void serverApi.physicalLibrary(libraryId).then(setData).catch(() => undefined); }} />}
  </section>;
}

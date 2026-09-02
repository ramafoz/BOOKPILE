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
  const selectedContainer = draft.containers.find((item) => item.container_id === containerId);
  const selectedContainerContext = allContainers.find((item) => item.container.id === containerId);
  const selectedOutside = draft.outside_areas.find((item) => item.area_kind === outsideKind);
  const draftGeometry = physicalMapGeometry({ ...data, layout: draft });
  const selectedShelfRect = draftGeometry.shelves.find((item) => item.shelfId === shelfId);
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

  function updateBookcase(field: "x_mm" | "floor_y_mm" | "width_mm" | "height_mm", value: number) {
    setDraft((current) => ({ ...current, bookcases: current.bookcases.map((item) => item.bookcase_id === bookcaseId ? { ...item, [field]: value } : item) }));
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

  function updateShelfMapHeight(value: number) {
    if (!selectedShelf || !selectedShelfRect) return;
    const context = data.bookcases.find((bookcase) => bookcase.shelves.some((shelf) => shelf.id === shelfId));
    if (!context || context.shelves.length < 2) return;
    const siblingLayouts = context.shelves
      .map((shelf) => draft.shelves.find((item) => item.shelf_id === shelf.id))
      .filter((item): item is NonNullable<typeof item> => Boolean(item));
    const totalWeight = siblingLayouts.reduce((sum, item) => sum + item.height_weight, 0);
    const otherWeight = totalWeight - selectedShelf.height_weight;
    const totalHeight = context.shelves.reduce((sum, shelf) => sum + (draftGeometry.shelves.find((item) => item.shelfId === shelf.id)?.height ?? 0), 0);
    const bounded = Math.min(Math.max(value, 1), Math.max(1, totalHeight - 1));
    const heightWeight = bounded * otherWeight / (totalHeight - bounded);
    setDraft((current) => ({
      ...current,
      shelves: current.shelves.map((item) => item.shelf_id === shelfId ? { ...item, height_weight: heightWeight } : item),
    }));
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
    setSaving(true);
    try {
      onSaved(await serverApi.updateVisualLayout(libraryId, draft));
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
      <fieldset><legend>Geometry mode</legend><label>Projection<select value={draft.geometry_mode} onChange={(event) => setDraft((current) => ({ ...current, geometry_mode: event.target.value as "MANUAL" | "PHYSICAL" }))}><option value="MANUAL">Manual proportions</option><option value="PHYSICAL">Physical dimensions</option></select></label><small>{draft.geometry_mode === "PHYSICAL" ? "Saving recalculates furniture, shelves and occupied containers from recorded millimetres. Missing axes use documented independent fallbacks; conflicts remain visible as warnings." : "Recorded dimensions are informative. The saved manual map geometry remains authoritative."}</small></fieldset>
      <fieldset><legend>Furniture geometry (mm)</legend><label>Bookcase<select value={bookcaseId} onChange={(event) => setBookcaseId(event.target.value)}>{data.bookcases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{selectedBookcase && <><div className="server-dimension-grid">{numberField("Horizontal", selectedBookcase.x_mm, (value) => updateBookcase("x_mm", value), { step: 1 })}{numberField("Floor baseline", selectedBookcase.floor_y_mm, (value) => updateBookcase("floor_y_mm", value), { step: 1 })}{numberField("Width", selectedBookcase.width_mm, (value) => updateBookcase("width_mm", value), { min: 1, step: 1 })}{numberField("Height", selectedBookcase.height_mm, (value) => updateBookcase("height_mm", value), { min: 1, step: 1 })}</div>{selectedBookcaseRecord && (!selectedBookcaseRecord.width_mm || !selectedBookcaseRecord.height_mm) && <small>Physical dimensions are not recorded. These editable map dimensions are independent fallback geometry, not inherited furniture measurements.</small>}</>}</fieldset>
      <fieldset><legend>Shelf map size (mm)</legend><label>Shelf<select value={shelfId} onChange={(event) => setShelfId(event.target.value)}>{data.bookcases.flatMap((bookcase) => bookcase.shelves.map((shelf) => <option key={shelf.id} value={shelf.id}>{bookcase.name} · Shelf {shelf.shelf_number}</option>))}</select></label>{selectedShelf && selectedShelfRect && <>{numberField("Displayed height (mm)", selectedShelfRect.height, updateShelfMapHeight, { min: 1, step: 1 })}{data.bookcases.find((bookcase) => bookcase.shelves.some((shelf) => shelf.id === shelfId))?.shelves.length === 1 && <small>A single shelf fills the bookcase's available map height.</small>}</>}</fieldset>
      <fieldset><legend>Container geometry and support (mm)</legend><label>Container<select value={containerId} onChange={(event) => setContainerId(event.target.value)}>{allContainers.map(({ bookcase, shelf, container }) => <option key={container.id} value={container.id}>{bookcase.name} · S{shelf.shelf_number} · {container.layer === "BACKGROUND" ? "BG" : "FG"} {container.container_type === "ROW" ? "Row" : "Pile"} {container.container_number}</option>)}</select></label>{selectedContainer && selectedContainerContext && <><div className="server-dimension-grid">{numberField(selectedContainerContext.container.container_type === "ROW" ? "Anchor position (mm)" : "Alignment position (mm)", displayedContainerStartMm(), (value) => updateContainerMillimetres("start", value), { min: 0, max: containerShelfWidthMm, step: 1 })}{numberField("Bottom clearance (mm)", supportClearanceMm, (value) => updateContainerMillimetres("bottom", value), { min: 0, max: containerShelfHeightMm, step: 1, disabled: selectedContainer.support_kind === "CONTAINER" || selectedContainerContext.container.layer === "FOREGROUND" })}{numberField("Width (mm)", selectedContainer.width / 100 * containerShelfWidthMm, (value) => updateContainerMillimetres("width", value), { min: 1, max: containerShelfWidthMm, step: 1, disabled: draft.geometry_mode === "PHYSICAL" && selectedContainerContext.container.book_count > 0 })}{numberField("Height (mm)", selectedContainer.height / 100 * containerShelfHeightMm, (value) => updateContainerMillimetres("height", value), { min: 1, max: containerShelfHeightMm, step: 1, disabled: draft.geometry_mode === "PHYSICAL" && selectedContainerContext.container.book_count > 0 })}</div><small>{draft.geometry_mode === "PHYSICAL" && selectedContainerContext.container.book_count > 0 ? "Occupied width and height are derived from the books' physical dimensions and documented fallbacks. Change the anchor, alignment or support here; edit book measurements to change occupied size." : "Anchor/alignment positions are coordinates measured from the shelf's left edge. Bottom clearance is relative to the immediate support: 0 mm means direct contact with the shelf or supporting container."} Only shelf-supported background containers may use a visual depth offset.</small>{selectedContainerContext.container.container_type === "ROW" && <label>Row growth anchor<select value={selectedContainer.row_anchor} onChange={(event) => updateContainer({ row_anchor: event.target.value as "LEFT" | "RIGHT" })}><option value="LEFT">Left edge fixed — grow right</option><option value="RIGHT">Right edge fixed — grow left</option></select></label>}<label>Rests on<select value={selectedContainer.support_kind === "CONTAINER" ? selectedContainer.support_container_id ?? "" : "SHELF"} onChange={(event) => chooseSupport(event.target.value)}><option value="SHELF">Shelf bottom</option>{supportContainers.map(({ bookcase, shelf, container }) => <option key={container.id} value={container.id}>{bookcase.name} · Shelf {shelf.shelf_number} · {container.layer === "BACKGROUND" ? "Background" : "Foreground"} {container.container_type === "ROW" ? "Row" : "Pile"} {container.container_number}</option>)}</select><small>Only a non-empty opposite-type container in this shelf and layer can be used.</small></label>{selectedContainerContext.container.container_type === "PILE" && <label>Pile alignment<select value={selectedContainer.pile_alignment} onChange={(event) => updateContainer({ pile_alignment: event.target.value as "LEFT" | "CENTER" | "RIGHT" })}><option value="LEFT">Left</option><option value="CENTER">Centre</option><option value="RIGHT">Right</option></select></label>}</>}</fieldset>
      <fieldset>
        <legend>Outside-library areas</legend>
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
      <form onSubmit={(event) => { event.preventDefault(); void mutate(() => serverApi.createBookcase(libraryId, { name: bookcaseName, description: null, height_mm: null, width_mm: null, depth_mm: null }), "Bookcase added.").then(() => setBookcaseName("")); }}>
        <span>1</span><h4>Add bookcase</h4><label>Name *<input required maxLength={160} value={bookcaseName} onChange={(event) => setBookcaseName(event.target.value)} /></label><button type="submit" disabled={busy}><Plus size={16} /> Add bookcase</button>
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

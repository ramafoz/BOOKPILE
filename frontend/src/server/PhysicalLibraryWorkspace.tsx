import { FormEvent, useEffect, useMemo, useState } from "react";
import { BookOpen, Boxes, Layers3, MapPin, Pencil, Plus, Ruler, Settings2, Trash2 } from "lucide-react";

import {
  PhysicalBookcase,
  PhysicalContainer,
  PhysicalLibrary,
  PhysicalShelf,
  ServerApiError,
  VisualLayout,
  serverApi,
} from "./serverApi";


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
  const selectedShelf = draft.shelves.find((item) => item.shelf_id === shelfId);
  const selectedContainer = draft.containers.find((item) => item.container_id === containerId);
  const selectedContainerContext = allContainers.find((item) => item.container.id === containerId);
  const selectedOutside = draft.outside_areas.find((item) => item.area_kind === outsideKind);
  const supportRows = selectedContainerContext
    ? allContainers.filter(({ shelf, container }) => (
      shelf.id === selectedContainerContext.shelf.id &&
      container.layer === selectedContainerContext.container.layer &&
      container.container_type === "ROW" &&
      container.book_count > 0
    ))
    : [];

  function updateBookcase(field: "x" | "y" | "width" | "height", value: number) {
    setDraft((current) => ({ ...current, bookcases: current.bookcases.map((item) => item.bookcase_id === bookcaseId ? { ...item, [field]: value } : item) }));
  }

  function updateContainer(changes: Partial<NonNullable<typeof selectedContainer>>) {
    setDraft((current) => ({ ...current, containers: current.containers.map((item) => item.container_id === containerId ? { ...item, ...changes } : item) }));
  }

  function choosePileSupport(value: string) {
    if (!selectedContainer) return;
    if (value === "SHELF") {
      updateContainer({ pile_support_kind: "SHELF", pile_support_container_id: null, y: 100 - selectedContainer.height });
      return;
    }
    const support = draft.containers.find((item) => item.container_id === value);
    if (!support) return;
    const width = Math.min(selectedContainer.width, 100 - support.x);
    updateContainer({
      pile_support_kind: "ROW",
      pile_support_container_id: value,
      y: Math.max(0, support.y - selectedContainer.height),
      x: support.x,
      width,
    });
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
    options: { min?: number; max?: number; step?: number } = {},
  ) => <label>{label}<input type="number" min={options.min} max={options.max} step={options.step ?? 0.1} value={value} onChange={(event) => onChange(Number(event.target.value))} required /></label>;

  return <div className="server-modal-backdrop"><section className="server-physical-dialog server-geometry-dialog" role="dialog" aria-modal="true">
    <p className="server-card-eyebrow">Visual workspace</p><h2>Customize library map</h2>
    <p className="server-field-help">Precise controls are implemented first. Direct dragging and the visual map will reuse the proven Local camera and geometry in the next increment.</p>
    <div className="server-geometry-sections">
      <fieldset><legend>Furniture</legend><label>Bookcase<select value={bookcaseId} onChange={(event) => setBookcaseId(event.target.value)}>{data.bookcases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{selectedBookcase && <div className="server-dimension-grid">{numberField("Horizontal", selectedBookcase.x, (value) => updateBookcase("x", value))}{numberField("Vertical", selectedBookcase.y, (value) => updateBookcase("y", value))}{numberField("Width", selectedBookcase.width, (value) => updateBookcase("width", value), { min: 0.1 })}{numberField("Height", selectedBookcase.height, (value) => updateBookcase("height", value), { min: 0.1 })}</div>}</fieldset>
      <fieldset><legend>Shelf proportions</legend><label>Shelf<select value={shelfId} onChange={(event) => setShelfId(event.target.value)}>{data.bookcases.flatMap((bookcase) => bookcase.shelves.map((shelf) => <option key={shelf.id} value={shelf.id}>{bookcase.name} · Shelf {shelf.shelf_number}</option>))}</select></label>{selectedShelf && numberField("Relative height", selectedShelf.height_weight, (value) => setDraft((current) => ({ ...current, shelves: current.shelves.map((item) => item.shelf_id === shelfId ? { ...item, height_weight: value } : item) })), { min: 0.25, max: 8, step: 0.25 })}</fieldset>
      <fieldset><legend>Container geometry and support</legend><label>Container<select value={containerId} onChange={(event) => setContainerId(event.target.value)}>{allContainers.map(({ bookcase, shelf, container }) => <option key={container.id} value={container.id}>{bookcase.name} · S{shelf.shelf_number} · {container.layer === "BACKGROUND" ? "BG" : "FG"} {container.container_type === "ROW" ? "Row" : "Pile"} {container.container_number}</option>)}</select></label>{selectedContainer && selectedContainerContext && <><div className="server-dimension-grid">{numberField("Start", selectedContainer.x, (value) => updateContainer({ x: value }), { min: 0, max: 100 })}{numberField("Vertical", selectedContainer.y, (value) => updateContainer({ y: value }), { min: 0, max: 100 })}{numberField("Width", selectedContainer.width, (value) => updateContainer({ width: value }), { min: 0.1, max: 100 })}{numberField("Height", selectedContainer.height, (value) => updateContainer({ height: value }), { min: 0.1, max: 100 })}</div>{selectedContainerContext.container.container_type === "ROW" ? <label>Row growth anchor<select value={selectedContainer.row_anchor} onChange={(event) => updateContainer({ row_anchor: event.target.value as "LEFT" | "RIGHT" })}><option value="LEFT">Left edge fixed — grow right</option><option value="RIGHT">Right edge fixed — grow left</option></select></label> : <label>Pile rests on<select value={selectedContainer.pile_support_kind === "ROW" ? selectedContainer.pile_support_container_id ?? "" : "SHELF"} onChange={(event) => choosePileSupport(event.target.value)}><option value="SHELF">Shelf bottom</option>{supportRows.map(({ bookcase, shelf, container }) => <option key={container.id} value={container.id}>{bookcase.name} · Shelf {shelf.shelf_number} · {container.layer === "BACKGROUND" ? "Background" : "Foreground"} Row {container.container_number}</option>)}</select><small>Only non-empty rows in this shelf and layer can support a pile.</small></label>}</>}</fieldset>
      <fieldset>
        <legend>Outside-library areas</legend>
        <label>Area<select value={outsideKind} onChange={(event) => setOutsideKind(event.target.value as "READING" | "LOANED")}><option value="READING">Reading</option><option value="LOANED">On loan</option></select></label>
        {selectedOutside && <div className="server-dimension-grid">
          {numberField("Horizontal", selectedOutside.x, (value) => setDraft((current) => ({ ...current, outside_areas: current.outside_areas.map((item) => item.area_kind === outsideKind ? { ...item, x: value } : item) })))}
          {numberField("Vertical", selectedOutside.y, (value) => setDraft((current) => ({ ...current, outside_areas: current.outside_areas.map((item) => item.area_kind === outsideKind ? { ...item, y: value } : item) })))}
          {numberField("Width", selectedOutside.width, (value) => setDraft((current) => ({ ...current, outside_areas: current.outside_areas.map((item) => item.area_kind === outsideKind ? { ...item, width: value } : item) })), { min: 0.1 })}
          {numberField("Height", selectedOutside.height, (value) => setDraft((current) => ({ ...current, outside_areas: current.outside_areas.map((item) => item.area_kind === outsideKind ? { ...item, height: value } : item) })), { min: 0.1 })}
        </div>}
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
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<EditTarget | null>(null);
  const [layoutEditing, setLayoutEditing] = useState(false);
  const [bookcaseName, setBookcaseName] = useState("");
  const [shelfBookcase, setShelfBookcase] = useState("");
  const [shelfNumber, setShelfNumber] = useState("1");
  const [containerShelf, setContainerShelf] = useState("");
  const [containerNumber, setContainerNumber] = useState("1");
  const [containerType, setContainerType] = useState<"ROW" | "PILE">("ROW");
  const [containerLayer, setContainerLayer] = useState<"BACKGROUND" | "FOREGROUND">("BACKGROUND");
  const [placementBook, setPlacementBook] = useState("");
  const [placementContainer, setPlacementContainer] = useState("");
  const [placementPosition, setPlacementPosition] = useState("");

  const shelves = useMemo(
    () => data?.bookcases.flatMap((bookcase) => bookcase.shelves.map((shelf) => ({ bookcase, shelf }))) ?? [],
    [data],
  );
  const containers = useMemo(
    () => shelves.flatMap(({ bookcase, shelf }) => shelf.containers.map((container) => ({
      container,
      label: `${bookcase.name} · Shelf ${shelf.shelf_number} · ${container.layer === "BACKGROUND" ? "Background" : "Foreground"} ${container.container_type === "ROW" ? "Row" : "Pile"} ${container.container_number}`,
    }))),
    [shelves],
  );
  const selectedPlacementBook = data?.books.find((book) => book.id === placementBook);
  const selectedLocation = selectedPlacementBook?.container_id
    ? containers.find(({ container }) => container.id === selectedPlacementBook.container_id)?.label
    : null;

  useEffect(() => {
    setBusy(true);
    setError(null);
    void serverApi.physicalLibrary(libraryId)
      .then((value) => {
        setData(value);
        setShelfBookcase(value.bookcases[0]?.id ?? "");
        const firstShelf = value.bookcases.flatMap((item) => item.shelves)[0];
        setContainerShelf(firstShelf?.id ?? "");
        const firstBook = value.books[0];
        setPlacementBook(firstBook?.id ?? "");
        setPlacementContainer(firstBook?.container_id ?? "");
        setPlacementPosition(firstBook?.position?.toString() ?? "");
      })
      .catch((caught) => setError(errorMessage(caught)))
      .finally(() => setBusy(false));
  }, [libraryId]);

  function accept(value: PhysicalLibrary, message: string) {
    setData(value);
    setNotice(message);
    setError(null);
    setEditing(null);
  }

  async function mutate(action: () => Promise<PhysicalLibrary>, message: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
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

  function choosePlacementBook(bookId: string) {
    setPlacementBook(bookId);
    const book = data?.books.find((item) => item.id === bookId);
    setPlacementContainer(book?.container_id ?? "");
    setPlacementPosition(book?.position?.toString() ?? "");
  }

  async function savePlacement(event: FormEvent) {
    event.preventDefault();
    if (!placementBook) return;
    const containerId = placementContainer || null;
    const position = containerId ? Number.parseInt(placementPosition, 10) : null;
    await mutate(
      () => serverApi.updateBookPlacement(
        libraryId,
        placementBook,
        containerId,
        position,
      ),
      containerId ? "Book placed. Positions were renumbered safely." : "Book removed from its physical location. The former container was compacted.",
    );
  }

  if (!data) return <section className="server-dashboard-panel"><h3>Library layout</h3><p>{busy ? "Loading physical library…" : error ?? "Physical library unavailable."}</p></section>;

  return <section className="server-physical-workspace">
    <header><div><p className="server-card-eyebrow">Shared physical structure</p><h3>Library layout</h3><p>{data.can_edit ? "Build and maintain furniture, shelves, rows and piles, then define their visual geometry and support." : "Read-only physical hierarchy. Your Viewer access includes the Library Map."}</p></div><div className="server-physical-heading-actions">{data.can_edit && <button type="button" onClick={() => setLayoutEditing(true)}><Settings2 size={17} /> Visual layout</button>}<Ruler size={30} /></div></header>
    {error && <div className="server-message error">{error}</div>}
    {notice && <div className="server-message success">{notice}</div>}

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

    {data.can_edit && <form className="server-book-placement" onSubmit={(event) => void savePlacement(event)}>
      <header><div><BookOpen size={20} /><span><b>Position books</b><small>Insert a book safely, move it, or remove its physical location.</small></span></div><MapPin size={22} /></header>
      <div className="server-placement-grid">
        <label>Book *<select required value={placementBook} onChange={(event) => choosePlacementBook(event.target.value)}><option value="">Choose book</option>{data.books.map((book) => <option key={book.id} value={book.id}>{book.title} — {book.author}</option>)}</select></label>
        <label>Destination container<select value={placementContainer} onChange={(event) => { const value = event.target.value; setPlacementContainer(value); if (!value) setPlacementPosition(""); else if (!placementPosition) { const occupied = data.books.filter((book) => book.container_id === value && book.id !== placementBook).length; setPlacementPosition(String(occupied + 1)); } }}><option value="">No physical location</option>{containers.map(({ container, label }) => <option key={container.id} value={container.id}>{label}</option>)}</select></label>
        <label>Position *<input type="number" min="1" required={Boolean(placementContainer)} disabled={!placementContainer} value={placementPosition} onChange={(event) => setPlacementPosition(event.target.value)} /></label>
        <button type="submit" disabled={busy || !placementBook || (Boolean(placementContainer) && !placementPosition)}><MapPin size={16} /> Save position</button>
      </div>
      <p><b>Current position:</b> {selectedLocation ? `${selectedLocation} · Position ${selectedPlacementBook?.position}` : "Not stored in the physical library"}</p>
      <small>Choosing an occupied position makes room automatically. The old container is always compacted, so persistent gaps cannot be created.</small>
    </form>}

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
    {layoutEditing && <GeometryDialog libraryId={libraryId} data={data} onClose={() => setLayoutEditing(false)} onSaved={(value) => { accept(value, "Visual layout saved."); setLayoutEditing(false); }} onError={(value) => { setError(value); setLayoutEditing(false); }} />}
  </section>;
}

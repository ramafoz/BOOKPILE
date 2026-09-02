import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BookOpen, Boxes, Check, ChevronDown, ChevronUp, Eye, Focus, Minus, Move, Plus, RotateCcw, Undo2, X } from "lucide-react";
import { BookDetails } from "./CatalogueWorkspace";
import { serverApi, type PhysicalBook, type PhysicalLibrary, type RearrangementOperation, type RearrangementRequest, type RearrangementResult, type ServerBook } from "./serverApi";
import {
  boundsForRects,
  cataloguePageMean,
  physicalMapGeometry,
  proportionalBookSegments,
  proportionalRearrangementSlots,
  type WorldRect,
} from "./serverMapGeometry";

interface Camera {
  x: number;
  y: number;
  width: number;
  height: number;
}

type Selection =
  | { kind: "BOOK"; book: PhysicalBook }
  | { kind: "CONTAINER"; containerId: string }
  | null;

function fitCamera(bounds: WorldRect, aspect: number): Camera {
  const padding = Math.max(2, Math.max(bounds.width, bounds.height) * 0.06);
  let width = bounds.width + padding * 2;
  let height = bounds.height + padding * 2;
  if (width / height > aspect) height = width / aspect;
  else width = height * aspect;
  return {
    x: bounds.x + bounds.width / 2 - width / 2,
    y: bounds.y + bounds.height / 2 - height / 2,
    width,
    height,
  };
}

function zoomCamera(camera: Camera, factor: number, anchorX?: number, anchorY?: number): Camera {
  const nextWidth = Math.min(1000, Math.max(.5, camera.width * factor));
  const nextHeight = nextWidth * camera.height / camera.width;
  const xRatio = anchorX === undefined ? .5 : (anchorX - camera.x) / camera.width;
  const yRatio = anchorY === undefined ? .5 : (anchorY - camera.y) / camera.height;
  return {
    x: (anchorX ?? camera.x + camera.width / 2) - nextWidth * xRatio,
    y: (anchorY ?? camera.y + camera.height / 2) - nextHeight * yRatio,
    width: nextWidth,
    height: nextHeight,
  };
}

export default function ServerLibraryMap({ libraryId }: { libraryId: string }) {
  const [data, setData] = useState<PhysicalLibrary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [inspectionMode, setInspectionMode] = useState<"BOOK" | "CONTAINER">("BOOK");
  const [details, setDetails] = useState<ServerBook | null>(null);
  const [detailsBusy, setDetailsBusy] = useState(false);
  const [rearranging, setRearranging] = useState(false);
  const [moveBookId, setMoveBookId] = useState("");
  const [oldPositionMode, setOldPositionMode] = useState<"COLLAPSE" | "LEAVE_GAP">("COLLAPSE");
  const [newPositionMode, setNewPositionMode] = useState<"SQUEEZE" | "SWAP" | "CONTINUE">("SQUEEZE");
  const [releaseShelfSpace, setReleaseShelfSpace] = useState(false);
  const [moveSteps, setMoveSteps] = useState<RearrangementOperation["steps"]>([]);
  const [completedMoves, setCompletedMoves] = useState<RearrangementOperation[]>([]);
  const [destinationContainer, setDestinationContainer] = useState("");
  const [destinationPosition, setDestinationPosition] = useState("");
  const [rearrangement, setRearrangement] = useState<RearrangementResult | null>(null);
  const [rearrangementBusy, setRearrangementBusy] = useState(false);
  const [rearrangementError, setRearrangementError] = useState("");
  const [rearrangementPanelCollapsed, setRearrangementPanelCollapsed] = useState(false);
  const [camera, setCamera] = useState<Camera>({ x: 0, y: 0, width: 100, height: 100 });
  const [cameraReady, setCameraReady] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<{ pointerId: number; x: number; y: number; camera: Camera } | null>(null);
  const pointersRef = useRef(new Map<number, { x: number; y: number }>());
  const pinchRef = useRef<{
    camera: Camera;
    distance: number;
    midpoint: { x: number; y: number };
    anchor: { x: number; y: number };
  } | null>(null);
  const gestureMovedRef = useRef(false);

  useEffect(() => {
    setData(null);
    setError(null);
    setSelection(null);
    cancelRearrangement();
    setCameraReady(false);
    void serverApi.physicalLibrary(libraryId)
      .then(setData)
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Library Map unavailable."));
  }, [libraryId]);

  useEffect(() => {
    const element = svgRef.current;
    if (!element) return;
    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      const anchor = pointInWorld(event.clientX, event.clientY);
      setCamera((current) => zoomCamera(current, event.deltaY > 0 ? 1.12 : .89, anchor.x, anchor.y));
    };
    element.addEventListener("wheel", handleWheel, { passive: false });
    return () => element.removeEventListener("wheel", handleWheel);
  });

  const displayData = useMemo(() => {
    if (!data || !rearrangement) return data;
    const placements = new Map(rearrangement.placements.map((item) => [item.book_id, item]));
    const layouts = new Map(rearrangement.container_layouts.map((item) => [item.container_id, item]));
    return {
      ...data,
      books: data.books.map((book) => placements.has(book.id) ? { ...book, ...placements.get(book.id) } : book),
      layout: { ...data.layout, containers: data.layout.containers.map((item) => layouts.get(item.container_id) ?? item) },
    };
  }, [data, rearrangement]);
  const geometry = useMemo(() => displayData ? physicalMapGeometry(displayData) : null, [displayData]);
  const meanPages = useMemo(() => data ? cataloguePageMean(data.books) : 200, [data]);
  const worldBounds = useMemo(
    () => boundsForRects([...(geometry?.bookcases ?? []), ...(data?.layout.outside_areas ?? [])]),
    [data, geometry],
  );

  const reset = useCallback(() => {
    const element = svgRef.current;
    const aspect = element && element.clientHeight ? element.clientWidth / element.clientHeight : 16 / 9;
    setCamera(fitCamera(worldBounds, Math.max(.25, aspect)));
    setCameraReady(true);
  }, [worldBounds]);

  useEffect(() => {
    if (data && !cameraReady) reset();
  }, [cameraReady, data, reset]);

  function pointInWorld(clientX: number, clientY: number) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return { x: camera.x, y: camera.y };
    return {
      x: camera.x + (clientX - rect.left) / rect.width * camera.width,
      y: camera.y + (clientY - rect.top) / rect.height * camera.height,
    };
  }

  function pointInCamera(clientX: number, clientY: number, value: Camera) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return { x: value.x, y: value.y };
    return {
      x: value.x + (clientX - rect.left) / rect.width * value.width,
      y: value.y + (clientY - rect.top) / rect.height * value.height,
    };
  }

  function beginPinch() {
    const points = [...pointersRef.current.values()];
    if (points.length !== 2) { pinchRef.current = null; return; }
    const midpoint = { x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2 };
    pinchRef.current = {
      camera,
      distance: Math.max(1, Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y)),
      midpoint,
      anchor: pointInCamera(midpoint.x, midpoint.y, camera),
    };
    dragRef.current = null;
  }

  function focus(rect: WorldRect) {
    const element = svgRef.current;
    const aspect = element && element.clientHeight ? element.clientWidth / element.clientHeight : 16 / 9;
    setCamera(fitCamera(rect, Math.max(.25, aspect)));
  }

  async function showDetails(book: PhysicalBook) {
    setDetailsBusy(true);
    setError(null);
    try { setDetails(await serverApi.book(libraryId, book.id)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Book information unavailable."); }
    finally { setDetailsBusy(false); }
  }

  function cancelRearrangement() {
    setRearranging(false); setMoveBookId(""); setMoveSteps([]); setCompletedMoves([]);
    setDestinationContainer(""); setDestinationPosition(""); setRearrangement(null);
    setRearrangementError(""); setReleaseShelfSpace(false);
    setRearrangementPanelCollapsed(false);
  }

  function rearrangementRequest(steps = moveSteps): RearrangementRequest {
    return {
      book_id: moveBookId,
      old_position_mode: newPositionMode === "SWAP" ? "LEAVE_GAP" : oldPositionMode,
      release_shelf_space: releaseShelfSpace,
      steps,
      completed_operations: completedMoves,
    };
  }

  function selectMoveBook(bookId: string) {
    if (moveSteps.length || (rearrangement && !rearrangement.complete)) return;
    setMoveBookId(bookId); setMoveSteps([]); setDestinationContainer("");
    setDestinationPosition(""); setRearrangementError("");
  }

  async function previewDestination(containerId = destinationContainer, positionText = destinationPosition) {
    const position = Number.parseInt(positionText, 10);
    if (!moveBookId || !containerId || !Number.isInteger(position) || position < 1) return;
    const steps = [...moveSteps, { container_id: containerId, position, new_position_mode: newPositionMode }];
    setRearrangementBusy(true); setRearrangementError("");
    try {
      const result = await serverApi.previewRearrangement(libraryId, rearrangementRequest(steps));
      setMoveSteps(steps); setRearrangement(result); setDestinationContainer(""); setDestinationPosition("");
    } catch (caught) {
      setRearrangementError(caught instanceof Error ? caught.message : "The destination could not be previewed.");
    } finally { setRearrangementBusy(false); }
  }

  function addAnotherMove() {
    if (!moveBookId || !rearrangement?.complete) return;
    setCompletedMoves([...completedMoves, {
      book_id: moveBookId,
      old_position_mode: newPositionMode === "SWAP" ? "LEAVE_GAP" : oldPositionMode,
      release_shelf_space: releaseShelfSpace,
      steps: moveSteps,
    }]);
    setMoveBookId(""); setMoveSteps([]); setDestinationContainer(""); setDestinationPosition("");
    setReleaseShelfSpace(false); setRearrangementError("");
  }

  function requestReadyToApply(): RearrangementRequest | null {
    if (moveBookId) return rearrangementRequest();
    if (!completedMoves.length) return null;
    const current = completedMoves.at(-1)!;
    return { ...current, completed_operations: completedMoves.slice(0, -1) };
  }

  async function undoLast() {
    if (moveSteps.length) {
      const steps = moveSteps.slice(0, -1);
      setMoveSteps(steps); setRearrangementError("");
      if (!steps.length && !completedMoves.length) { setRearrangement(null); return; }
      try { setRearrangement(await serverApi.previewRearrangement(libraryId, rearrangementRequest(steps))); }
      catch (caught) { setRearrangementError(caught instanceof Error ? caught.message : "Undo failed."); }
      return;
    }
    if (!completedMoves.length) return;
    const remaining = completedMoves.slice(0, -1);
    const restored = completedMoves.at(-1)!;
    setCompletedMoves(remaining); setMoveBookId(restored.book_id); setOldPositionMode(restored.old_position_mode);
    setReleaseShelfSpace(restored.release_shelf_space); setMoveSteps(restored.steps);
    try { setRearrangement(await serverApi.previewRearrangement(libraryId, { ...restored, completed_operations: remaining })); }
    catch (caught) { setRearrangementError(caught instanceof Error ? caught.message : "Undo failed."); }
  }

  async function applyRearrangement() {
    const request = requestReadyToApply();
    if (!rearrangement?.valid_to_apply || !request) return;
    setRearrangementBusy(true); setRearrangementError("");
    try {
      await serverApi.applyRearrangement(libraryId, request, rearrangement.revision);
      setData(await serverApi.physicalLibrary(libraryId));
      cancelRearrangement();
    } catch (caught) {
      setRearrangementError(caught instanceof Error ? caught.message : "The rearrangement could not be applied.");
    } finally { setRearrangementBusy(false); }
  }

  if (!data || !geometry) return <section className="server-map-loading"><p>{error ?? "Loading Library Map…"}</p></section>;
  const mapData = displayData ?? data;

  const booksByContainer = new Map<string, PhysicalBook[]>();
  mapData.books.forEach((book) => {
    if (!book.container_id) return;
    booksByContainer.set(book.container_id, [...(booksByContainer.get(book.container_id) ?? []), book]);
  });
  const selectedContainer = selection?.kind === "CONTAINER"
    ? geometry.containers.find((item) => item.containerId === selection.containerId)
    : null;
  const selectedBooks = selectedContainer ? booksByContainer.get(selectedContainer.containerId) ?? [] : [];

  return <section className="server-library-map">
    <header><div><p className="server-card-eyebrow">Visual library index</p><h3>Library Map</h3></div><div className="server-map-mode">{data.can_edit && <button type="button" className={rearranging ? "active" : ""} onClick={() => rearranging ? cancelRearrangement() : setRearranging(true)}><Move size={16} /> Reorganize books</button>}<span>Choose inspection mode</span><button type="button" disabled={rearranging} className={inspectionMode === "BOOK" ? "active" : ""} onClick={() => { setInspectionMode("BOOK"); setSelection(null); }}><BookOpen size={16} /> Books</button><button type="button" disabled={rearranging} className={inspectionMode === "CONTAINER" ? "active" : ""} onClick={() => { setInspectionMode("CONTAINER"); setSelection(null); }}><Boxes size={16} /> Containers</button></div></header>
    {error && <div className="server-map-error">{error}</div>}
    <div className="server-map-stage">
      <svg
        ref={svgRef}
        viewBox={`${camera.x} ${camera.y} ${camera.width} ${camera.height}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={(event) => {
          const target = event.target as SVGElement;
          if (event.button !== 0 || (event.pointerType === "mouse" && target.closest(".server-map-container, .server-map-book"))) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
          gestureMovedRef.current = false;
          if (pointersRef.current.size === 2) beginPinch();
          else dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, camera };
        }}
        onPointerMove={(event) => {
          if (pointersRef.current.has(event.pointerId)) pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
          const pinch = pinchRef.current;
          const points = [...pointersRef.current.values()];
          if (pinch && points.length === 2) {
            const distance = Math.max(1, Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y));
            const midpoint = { x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2 };
            const zoomed = zoomCamera(pinch.camera, pinch.distance / distance, pinch.anchor.x, pinch.anchor.y);
            const underFinger = pointInCamera(midpoint.x, midpoint.y, zoomed);
            setCamera({ ...zoomed, x: zoomed.x + pinch.anchor.x - underFinger.x, y: zoomed.y + pinch.anchor.y - underFinger.y });
            gestureMovedRef.current = true;
            return;
          }
          const drag = dragRef.current;
          const rect = svgRef.current?.getBoundingClientRect();
          if (!drag || !rect || drag.pointerId !== event.pointerId) return;
          if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 4) gestureMovedRef.current = true;
          setCamera({
            ...drag.camera,
            x: drag.camera.x - (event.clientX - drag.x) / rect.width * drag.camera.width,
            y: drag.camera.y - (event.clientY - drag.y) / rect.height * drag.camera.height,
          });
        }}
        onPointerUp={(event) => {
          pointersRef.current.delete(event.pointerId);
          pinchRef.current = null;
          dragRef.current = null;
          window.setTimeout(() => { gestureMovedRef.current = false; }, 0);
        }}
        onPointerCancel={(event) => {
          pointersRef.current.delete(event.pointerId);
          pinchRef.current = null;
          dragRef.current = null;
          gestureMovedRef.current = false;
        }}
        onClick={(event) => {
          if (gestureMovedRef.current) return;
          const target = event.target as SVGElement;
          if (!target.closest(".server-map-container, .server-map-book")) setSelection(null);
        }}
      >
        <rect className="server-map-world" x={camera.x} y={camera.y} width={camera.width} height={camera.height} />
        {geometry.bookcases.map((bookcase) => <g key={bookcase.bookcaseId}>
          <rect className="server-map-bookcase" x={bookcase.x} y={bookcase.y} width={bookcase.width} height={bookcase.height} rx=".5" />
          {geometry.shelves.filter((shelf) => shelf.bookcaseId === bookcase.bookcaseId).map((shelf) =>
            <rect key={shelf.shelfId} className="server-map-shelf" x={shelf.x} y={shelf.y} width={shelf.width} height={shelf.height} />)}
        </g>)}
        {[...geometry.containers].sort((a, b) => a.layer.localeCompare(b.layer)).map((container) => {
          const selected = selection?.kind === "CONTAINER" && selection.containerId === container.containerId;
          const containerBooks = booksByContainer.get(container.containerId) ?? [];
          const segments = proportionalBookSegments(container, containerBooks, meanPages);
          const gapPositions = rearrangement?.gaps.find((gap) => gap.container_id === container.containerId)?.positions ?? [];
          const activeBook = mapData.books.find((book) => book.id === (rearrangement?.next_active_book_id ?? moveBookId)) ?? null;
          const rearrangementSlots = rearranging && moveBookId
            ? proportionalRearrangementSlots(container, containerBooks, gapPositions, activeBook, meanPages)
            : [];
          return <g key={container.containerId} className={`server-map-container ${selected ? "selected" : ""} ${rearranging ? "rearranging" : ""}`} onClick={(event) => { event.stopPropagation(); if (gestureMovedRef.current) return; if (rearranging && moveBookId && (!rearrangement || !rearrangement.complete)) { const count = (booksByContainer.get(container.containerId) ?? []).length; void previewDestination(container.containerId, String(count + 1)); } else if (!rearranging && inspectionMode === "CONTAINER") setSelection({ kind: "CONTAINER", containerId: container.containerId }); }}>
            <rect x={container.x} y={container.y} width={container.width} height={container.height} rx=".2" />
            {(rearranging && moveBookId ? rearrangementSlots.filter((slot) => slot.book).map((slot) => ({ ...slot, book: slot.book! })) : segments).map((segment) => <rect
              key={segment.book.id}
              className={`server-map-book ${selection?.kind === "BOOK" && selection.book.id === segment.book.id ? "selected" : ""}`}
              x={segment.x} y={segment.y} width={segment.width} height={segment.height}
              onClick={(event) => { event.stopPropagation(); if (gestureMovedRef.current) return; if (rearranging) { if (!moveBookId) selectMoveBook(segment.book.id); else if (!rearrangement?.complete) void previewDestination(container.containerId, String(segment.book.position)); } else setSelection(inspectionMode === "BOOK" ? { kind: "BOOK", book: segment.book } : { kind: "CONTAINER", containerId: container.containerId }); }}
            ><title>{segment.book.title} — {segment.book.author}</title></rect>)}
            {rearrangementSlots.filter((slot) => !slot.book).map((slot) => <rect
              key={`${container.containerId}-target-${slot.position}`}
              className={`server-map-rearrangement-target ${slot.isEndTarget ? "end" : "gap"}`}
              x={slot.x} y={slot.y} width={slot.width} height={slot.height}
              onClick={(event) => { event.stopPropagation(); if (!rearrangement?.complete) void previewDestination(container.containerId, String(slot.position)); }}
            ><title>{slot.isEndTarget ? `New end position ${slot.position}` : `Empty position ${slot.position}`}</title></rect>)}
          </g>;
        })}
        {data.layout.outside_areas.map((area) => <g key={area.area_kind} className={`server-map-outside ${area.area_kind.toLowerCase()}`}>
          <rect x={area.x} y={area.y} width={area.width} height={area.height} rx="2" />
          <text x={area.x + area.width / 2} y={area.y + area.height / 2}>{area.area_kind === "READING" ? "Reading" : "On loan"}</text>
        </g>)}
      </svg>
      <div className="server-map-controls" aria-label="Map camera controls">
        <button type="button" title="Reset view" onClick={reset}><RotateCcw size={17} /></button>
        <button type="button" title="Zoom in" onClick={() => setCamera((value) => zoomCamera(value, .8))}><Plus size={17} /></button>
        <button type="button" title="Zoom out" onClick={() => setCamera((value) => zoomCamera(value, 1.25))}><Minus size={17} /></button>
      </div>
    </div>
    {rearranging && <aside className={`server-rearrangement-panel ${rearrangementPanelCollapsed ? "collapsed" : ""}`}>
      <header><div><p className="server-card-eyebrow">Draft movement</p><h4>{moveBookId ? (mapData.books.find((book) => book.id === (rearrangement?.next_active_book_id ?? moveBookId))?.title ?? "Choose a book") : "Choose a book on the map"}</h4></div><span><button type="button" onClick={() => setRearrangementPanelCollapsed((value) => !value)} title={rearrangementPanelCollapsed ? "Expand draft" : "Collapse draft"}>{rearrangementPanelCollapsed ? <ChevronDown size={17} /> : <ChevronUp size={17} />} {rearrangementPanelCollapsed ? "Expand" : "Collapse"}</button><button type="button" onClick={cancelRearrangement}><X size={17} /> Cancel draft</button></span></header>
      {!rearrangementPanelCollapsed && <>
      <div className="server-rearrangement-modes"><label>Old position<select disabled={moveSteps.length > 0 || newPositionMode === "SWAP"} value={newPositionMode === "SWAP" ? "LEAVE_GAP" : oldPositionMode} onChange={(event) => setOldPositionMode(event.target.value as "COLLAPSE" | "LEAVE_GAP")}><option value="COLLAPSE">Collapse</option><option value="LEAVE_GAP">Leave gap</option></select></label><label>New position<select disabled={moveSteps.length > 0} value={newPositionMode} onChange={(event) => { const value = event.target.value as "SQUEEZE" | "SWAP" | "CONTINUE"; setNewPositionMode(value); if (value === "SWAP") setOldPositionMode("LEAVE_GAP"); }}><option value="SQUEEZE">Squeeze</option><option value="SWAP">Swap</option><option value="CONTINUE">Continue</option></select></label></div>
      <label className="server-rearrangement-release"><input type="checkbox" disabled={moveSteps.length > 0} checked={releaseShelfSpace} onChange={(event) => setReleaseShelfSpace(event.target.checked)} /> Release shelf space if this move removes pages from its source container</label>
      <div className="server-rearrangement-destination"><label>Book<select disabled={moveSteps.length > 0} value={moveBookId} onChange={(event) => selectMoveBook(event.target.value)}><option value="">Choose on map or here</option>{mapData.books.filter((book) => book.container_id && book.position).map((book) => <option key={book.id} value={book.id}>{book.title} — {book.author}</option>)}</select></label><label>Destination container<select value={destinationContainer} onChange={(event) => setDestinationContainer(event.target.value)}><option value="">Choose on map or here</option>{data.bookcases.flatMap((bookcase) => bookcase.shelves.flatMap((shelf) => shelf.containers.map((container) => <option key={container.id} value={container.id}>{bookcase.name} · Shelf {shelf.shelf_number} · {container.layer === "BACKGROUND" ? "Background" : "Foreground"} {container.container_type === "ROW" ? "Row" : "Pile"} {container.container_number}</option>)))}</select></label><label>Position<input type="number" min="1" value={destinationPosition} onChange={(event) => setDestinationPosition(event.target.value)} /></label><button type="button" disabled={rearrangementBusy || !moveBookId || !destinationContainer || !destinationPosition || Boolean(rearrangement?.complete)} onClick={() => void previewDestination()}><Move size={16} /> Preview destination</button></div>
      {rearrangementError && <div className="server-message error">{rearrangementError}</div>}
      {rearrangement && <div className="server-rearrangement-summary">{rearrangement.movement_groups.map((group, index) => <section key={index}><b>Move {index + 1}</b><ul>{group.map((line, lineIndex) => <li key={lineIndex}>{line}</li>)}</ul></section>)}{rearrangement.warnings.map((warning) => <p key={warning}>{warning}</p>)}{!rearrangement.valid_to_apply && rearrangement.complete && !rearrangement.gaps.length && !rearrangement.geometry_errors.length && <p>This draft adds up to an unchanged arrangement. Add another move or cancel it.</p>}</div>}
      <footer><button type="button" disabled={rearrangementBusy || (!moveSteps.length && !completedMoves.length)} onClick={() => void undoLast()}><Undo2 size={16} /> Undo last step</button><button type="button" disabled={rearrangementBusy || !rearrangement?.complete || !moveBookId} onClick={addAnotherMove}><Plus size={16} /> Add another move</button><button className="confirm" type="button" disabled={rearrangementBusy || !rearrangement?.valid_to_apply || (!moveBookId && !completedMoves.length)} onClick={() => void applyRearrangement()}><Check size={16} /> Apply</button></footer>
      </>}
    </aside>}
    {selection && <aside className="server-map-inspector">
      <button type="button" className="server-map-inspector-close" onClick={() => setSelection(null)} title="Clear selection"><X size={17} /></button>
      {selection.kind === "BOOK" ? <><p className="server-card-eyebrow">Selected book</p><h4>{selection.book.title}</h4><p>{selection.book.author}</p><small>{selection.book.page_count ? `${selection.book.page_count} pages` : `Page count unknown · visual fallback ${Math.round(meanPages)} pages`}</small></> : <><p className="server-card-eyebrow">Selected container</p><h4>{selectedBooks.length} {selectedBooks.length === 1 ? "book" : "books"}</h4><ol>{selectedBooks.sort((a, b) => (a.position ?? 0) - (b.position ?? 0)).map((book) => <li key={book.id}><button type="button" onClick={() => { setInspectionMode("BOOK"); setSelection({ kind: "BOOK", book }); }}>{book.title}<small>{book.author}</small></button></li>)}</ol></>}
      <div><span className="server-map-inspector-actions">{selectedContainer && <button type="button" onClick={() => focus(selectedContainer)}><Focus size={16} /> Focus container</button>}{selection.kind === "BOOK" && <button type="button" onClick={() => void showDetails(selection.book)} disabled={detailsBusy}><Eye size={16} /> {detailsBusy ? "Loading…" : "Complete information"}</button>}</span><span><Move size={15} /> Read-only inspection</span></div>
    </aside>}
    {details && <BookDetails libraryId={libraryId} book={details} onClose={() => setDetails(null)} onEdit={null} />}
  </section>;
}

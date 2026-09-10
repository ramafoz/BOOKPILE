import { afterEach, describe, expect, it, vi } from "vitest";
import { cookieValue, serverApi } from "./serverApi";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("cookieValue", () => {
  it("finds and decodes the named CSRF cookie", () => {
    expect(cookieValue(
      "theme=green; bookpile_csrf=a%2Fb%2Bc; other=value",
      "bookpile_csrf",
    )).toBe("a/b+c");
  });

  it("does not accept a cookie whose name merely shares a prefix", () => {
    expect(cookieValue("bookpile_csrf_old=value", "bookpile_csrf")).toBeNull();
  });
});

describe("empty accepted responses", () => {
  it("treats a successful 202 without JSON as completion", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, { status: 202 }),
    );

    await expect(
      serverApi.requestPasswordReset("reader@example.com"),
    ).resolves.toBeUndefined();
  });
});

describe("Server catalogue requests", () => {
  it("loads one book through the selected reading perspective", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ state: "PENDING", sessions: [] }), { status: 200 }),
    );

    await serverApi.bookReading("library-1", "book-1", "owner-2");

    const url = new URL(String(fetchMock.mock.calls[0][0]), "http://bookpile.test");
    expect(url.pathname).toContain("/catalogue/book-1/reading");
    expect(url.searchParams.get("perspective_user_id")).toBe("owner-2");
  });

  it("protects personal reading and Goodreads writes with CSRF", async () => {
    vi.stubGlobal("document", { cookie: "bookpile_csrf=personal-token" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "session-1" }), { status: 201 }),
    );

    await serverApi.startReading("library-1", "book-1", "2026-09-07");

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("personal-token");
    expect(JSON.parse(String(options.body))).toEqual({ started_date: "2026-09-07" });
  });

  it("encodes repeated advanced filters without losing their AND/OR structure", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        library_id: "library-1", role: "VIEWER", can_edit: false,
        total: 0, limit: 25, offset: 0, books: [],
      }), { status: 200 }),
    );

    await serverApi.catalogue("library-1", {
      search: "Le Guin",
      language: ["English", "Galician"],
      genre: ["Fantasy", "Science Fiction"],
      page_max: 300,
      perspective_user_id: "owner-1",
      reading_state: "READ",
      reading_date_from: "2025-01-01",
    });

    const url = String(fetchMock.mock.calls[0][0]);
    const query = new URL(url, "http://bookpile.test").searchParams;
    expect(query.get("search")).toBe("Le Guin");
    expect(query.getAll("language")).toEqual(["English", "Galician"]);
    expect(query.getAll("genre")).toEqual(["Fantasy", "Science Fiction"]);
    expect(query.get("page_max")).toBe("300");
    expect(query.get("perspective_user_id")).toBe("owner-1");
    expect(query.get("reading_state")).toBe("READ");
    expect(query.get("reading_date_from")).toBe("2025-01-01");
  });

  it("loads statistics for a selected perspective and metadata filters", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ books: [], years: [] }), { status: 200 }),
    );

    await serverApi.readingStatistics("library-1", "owner-2", {
      language: "Galician", reading_year: 2026,
    });

    const url = new URL(String(fetchMock.mock.calls[0][0]), "http://bookpile.test");
    expect(url.pathname).toContain("/reading-overview/statistics");
    expect(url.searchParams.get("perspective_user_id")).toBe("owner-2");
    expect(url.searchParams.get("language")).toBe("Galician");
    expect(url.searchParams.get("reading_year")).toBe("2026");
  });

  it("sends CSRF protection with catalogue writes", async () => {
    vi.stubGlobal("document", { cookie: "bookpile_csrf=write-token" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "book-1" }), { status: 201 }),
    );

    await serverApi.createBook("library-1", {
      title: "A book", author: "An author", contributors: [],
      isbn_10: null, isbn_13: null, subtitle: null, page_count: null,
      publisher: null, current_ed_year: null, original_publication_year: null,
      language: null, original_language: null, translation_status: "UNKNOWN",
      edition_number: null, fiction_category: null, binding: null,
      publication_type: null, genre_text: null, series_name: null,
      series_volume: null, notes: null,
      acquisition_date: null, is_original_collection: false,
      height_mm: null, width_mm: null, thickness_mm: null,
    });

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("write-token");
    expect(options.method).toBe("POST");
  });

  it("surfaces Pydantic validation details to the user", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        detail: [{ msg: "Value error, ISBN-13 checksum is invalid" }],
      }), { status: 422 }),
    );

    await expect(serverApi.catalogue("library-1"))
      .rejects.toThrow("ISBN-13 checksum is invalid");
  });
});

describe("Physical library requests", () => {
  it("keeps physical writes library-scoped and CSRF protected", async () => {
    vi.stubGlobal("document", { cookie: "bookpile_csrf=layout-token" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        library_id: "library-1", role: "OWNER", can_edit: true, bookcases: [], books: [],
      }), { status: 201 }),
    );

    await serverApi.createContainer("library-1", {
      shelf_id: "shelf-1",
      container_type: "PILE",
      layer: "FOREGROUND",
      container_number: 2,
    });

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/libraries/library-1/physical-library/containers",
    );
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("layout-token");
    expect(JSON.parse(String(options.body))).toEqual({
      shelf_id: "shelf-1",
      container_type: "PILE",
      layer: "FOREGROUND",
      container_number: 2,
    });
  });

  it("updates a book placement through the map-scoped endpoint", async () => {
    vi.stubGlobal("document", { cookie: "bookpile_csrf=layout-token" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        library_id: "library-1", role: "OWNER", can_edit: true, bookcases: [], books: [],
      }), { status: 200 }),
    );

    await serverApi.updateBookPlacement("library-1", "book-1", "container-1", 2);

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/libraries/library-1/physical-library/books/book-1/placement",
    );
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.method).toBe("PUT");
    expect(JSON.parse(String(options.body))).toEqual({
      container_id: "container-1",
      position: 2,
    });
  });

  it("sends the complete revisioned visual layout with CSRF protection", async () => {
    vi.stubGlobal("document", { cookie: "bookpile_csrf=layout-token" });
    const layout = {
      revision: "a".repeat(64),
      geometry_mode: "MANUAL" as const,
      coordinate_system_version: 2,
      bookcases: [{ bookcase_id: "case-1", x_mm: -200, floor_y_mm: 1600, width_mm: 500, height_mm: 1600, shelf_direction: "TOP_TO_BOTTOM" as const, homogeneous_structure: true, frame_left_mm: 12.5, frame_right_mm: 12.5, top_closure_mm: 40, bottom_closure_mm: 40, separator_thickness_mm: 12.5 }],
      shelves: [{ shelf_id: "shelf-1", height_weight: 1, x_mm: 12.5, floor_y_mm: 40, width_mm: 475, height_mm: 1520, alignment: "CENTER" as const, offset_mm: 0, width_source: "DERIVED" as const, height_source: "DERIVED" as const, open_top: false, left_frame_mm: 12.5, right_frame_mm: 12.5, top_closure_mm: 40, bottom_board_mm: 40, separator_after_mm: null, separator_anchor: "BOTTOM" as const, separator_height_mm: null, separator_source: null }],
      containers: [{
        container_id: "container-1",
        x: 0,
        y: 50,
        width: 100,
        height: 50,
        row_anchor: "RIGHT" as const,
        support_kind: "SHELF" as const,
        support_container_id: null,
        pile_alignment: "RIGHT" as const,
      }],
      outside_areas: [
        { area_kind: "READING" as const, x_mm: 600, y_mm: 1400, width_mm: 400, height_mm: 400 },
        { area_kind: "LOANED" as const, x_mm: 1200, y_mm: 1400, width_mm: 400, height_mm: 400 },
      ],
      diagnostics: [],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        library_id: "library-1",
        role: "OWNER",
        can_edit: true,
        bookcases: [],
        books: [],
        layout,
      }), { status: 200 }),
    );

    await serverApi.updateVisualLayout("library-1", layout);

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/libraries/library-1/physical-library/layout",
    );
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.method).toBe("PUT");
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("layout-token");
    expect(JSON.parse(String(options.body))).toEqual(layout);
  });
});

describe("Library portability requests", () => {
  it("uploads the Local ZIP and selected reading Owner with CSRF protection", async () => {
    vi.stubGlobal("document", { cookie: "bookpile_csrf=import-token" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ import_id: "import-1", state: "READY" }), { status: 201 }),
    );
    const backup = new File(["zip"], "bookpile-full-backup.zip", { type: "application/zip" });

    await serverApi.preflightLocalImport("library-1", backup, "owner-2");

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/libraries/library-1/imports/local/preflight",
    );
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("import-token");
    expect(options.body).toBeInstanceOf(FormData);
    const body = options.body as FormData;
    expect(body.get("reading_owner_user_id")).toBe("owner-2");
    expect(body.get("backup")).toBe(backup);
  });

  it("uploads a portable Server ZIP without inferring a reading Owner", async () => {
    vi.stubGlobal("document", { cookie: "bookpile_csrf=import-token" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ import_id: "import-2", state: "READY" }), { status: 201 }),
    );
    const backup = new File(["zip"], "library-server.zip", { type: "application/zip" });

    await serverApi.preflightServerImport("library-1", backup);

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/libraries/library-1/imports/server/preflight",
    );
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.method).toBe("POST");
    const body = options.body as FormData;
    expect(body.get("backup")).toBe(backup);
    expect(body.has("reading_owner_user_id")).toBe(false);
  });

  it("requires an explicit repeated-archive decision when consolidating", async () => {
    vi.stubGlobal("document", { cookie: "bookpile_csrf=import-token" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ import_id: "import-1", state: "IMPORTED" }), { status: 200 }),
    );

    await serverApi.consolidateLocalImport("library-1", "import-1", true);

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.method).toBe("POST");
    expect(JSON.parse(String(options.body))).toEqual({
      allow_repeated_archive: true,
      member_mapping: {},
      allow_unmapped_personal_data: false,
    });
  });

  it("passes a new library name without inventing memberships in the client", async () => {
    vi.stubGlobal("document", { cookie: "bookpile_csrf=import-token" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ import_id: "import-1", library_id: "library-2", state: "IMPORTED" }), { status: 200 }),
    );

    await serverApi.consolidateLocalImportAsNewLibrary("library-1", "import-1", "Imported library", false);

    expect(String(fetchMock.mock.calls[0][0])).toContain("/consolidate-new-library");
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(options.body))).toEqual({
      name: "Imported library",
      allow_repeated_archive: false,
      member_mapping: {},
      allow_unmapped_personal_data: false,
    });
  });
});

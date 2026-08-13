import type { MetadataFilters, MetadataOptions } from "./types";

function optionLabel(value: string) {
  const labels: Record<string, string> = {
    FICTION: "Fiction",
    NON_FICTION: "Non-fiction",
    HARDCOVER: "Hardcover",
    PAPERBACK: "Paperback",
    FLEXIBOUND: "Flexibound",
    SPIRAL: "Spiral bound",
    STAPLED: "Stapled",
    CONVENTIONAL_BOOK: "Conventional book",
    COMIC_GRAPHIC_NOVEL: "Comic / graphic novel",
    ATLAS: "Atlas",
    REFERENCE: "Reference",
    ART_PHOTOGRAPHY_ILLUSTRATED: "Art / photography / illustrated",
    MAGAZINE_PERIODICAL: "Magazine / periodical",
    OTHER: "Other",
  };
  return labels[value] ?? value;
}

function MultiOptionFilter({
  label,
  values,
  selected,
  onChange,
}: {
  label: string;
  values: string[];
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  const summary = selected.length === 0
    ? `All ${label.toLowerCase()}`
    : selected.length === 1
      ? optionLabel(selected[0])
      : `${selected.length} selected`;
  return (
    <div className="metadata-multi-filter">
      <span>{label}</span>
      <details>
        <summary>{summary}</summary>
        <div className="metadata-option-list">
          {values.length === 0 ? (
            <small>No recorded values</small>
          ) : values.map((value) => (
            <label key={value}>
              <input
                type="checkbox"
                checked={selected.includes(value)}
                onChange={(event) => onChange(
                  event.target.checked
                    ? [...selected, value]
                    : selected.filter((item) => item !== value),
                )}
              />
              {optionLabel(value)}
            </label>
          ))}
          {selected.length > 0 && (
            <button type="button" onClick={() => onChange([])}>Clear selection</button>
          )}
        </div>
      </details>
    </div>
  );
}

export function MetadataFilterFields({
  filters,
  options,
  onChange,
}: {
  filters: MetadataFilters;
  options: MetadataOptions;
  onChange: (filters: MetadataFilters) => void;
}) {
  const set = <Key extends keyof MetadataFilters>(
    key: Key,
    value: MetadataFilters[Key],
  ) => onChange({ ...filters, [key]: value });

  return (
    <>
      <label>ISBN
        <input
          inputMode="numeric"
          placeholder="Exact ISBN-10 or ISBN-13"
          value={filters.isbn}
          onChange={(event) => set("isbn", event.target.value)}
        />
      </label>
      <MultiOptionFilter label="Languages" values={options.languages}
        selected={filters.languages} onChange={(value) => set("languages", value)} />
      <MultiOptionFilter label="Genres" values={options.genres}
        selected={filters.genres} onChange={(value) => set("genres", value)} />
      <MultiOptionFilter label="Publishers" values={options.publishers}
        selected={filters.publishers} onChange={(value) => set("publishers", value)} />
      <MultiOptionFilter label="Categories" values={options.fiction_categories}
        selected={filters.fictionCategories} onChange={(value) => set(
          "fictionCategories", value as MetadataFilters["fictionCategories"],
        )} />
      <MultiOptionFilter label="Bindings" values={options.bindings}
        selected={filters.bindings} onChange={(value) => set(
          "bindings", value as MetadataFilters["bindings"],
        )} />
      <MultiOptionFilter label="Publication types" values={options.publication_types}
        selected={filters.publicationTypes} onChange={(value) => set(
          "publicationTypes", value as MetadataFilters["publicationTypes"],
        )} />
      <MultiOptionFilter label="Series" values={options.series_names}
        selected={filters.seriesNames} onChange={(value) => set("seriesNames", value)} />
      <label>Part of a series?
        <select value={filters.seriesState} onChange={(event) => set(
          "seriesState", event.target.value as MetadataFilters["seriesState"],
        )}>
          <option value="ANY">All books</option>
          <option value="YES">Yes</option>
          <option value="NO">No</option>
        </select>
      </label>
      <label>Authors
        <select value={filters.authorStructure} onChange={(event) => set(
          "authorStructure",
          event.target.value as MetadataFilters["authorStructure"],
        )}>
          <option value="ANY">All books</option>
          <option value="SINGLE">Single author</option>
          <option value="MULTIPLE">Multiple authors</option>
        </select>
      </label>
      <fieldset className="metadata-range-filter">
        <legend>Number of pages</legend>
        <label>At least (≥)
          <input type="number" min="1" inputMode="numeric" value={filters.pageMin}
            onChange={(event) => set("pageMin", event.target.value)} />
        </label>
        <label>At most (≤)
          <input type="number" min="1" inputMode="numeric" value={filters.pageMax}
            onChange={(event) => set("pageMax", event.target.value)} />
        </label>
      </fieldset>
      <fieldset className="metadata-range-filter publication-year-filter">
        <legend>Publication year</legend>
        <label>Year type
          <select value={filters.publicationYearField} onChange={(event) => set(
            "publicationYearField",
            event.target.value as MetadataFilters["publicationYearField"],
          )}>
            <option value="current_ed_year">Current edition</option>
            <option value="original_publication_year">Original publication</option>
          </select>
        </label>
        <label>At least (≥)
          <input type="number" min="1000" max="9999" inputMode="numeric"
            value={filters.publicationYearMin}
            onChange={(event) => set("publicationYearMin", event.target.value)} />
        </label>
        <label>At most (≤)
          <input type="number" min="1000" max="9999" inputMode="numeric"
            value={filters.publicationYearMax}
            onChange={(event) => set("publicationYearMax", event.target.value)} />
        </label>
      </fieldset>
    </>
  );
}

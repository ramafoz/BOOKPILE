import { beforeAll } from "vitest";
import { availableLocales } from "./locale";
import { loadLocaleCatalogues } from "./localeCatalogues";

beforeAll(async () => {
  await Promise.all(availableLocales.map(loadLocaleCatalogues));
});

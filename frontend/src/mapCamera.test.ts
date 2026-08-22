import { describe, expect, it } from "vitest";
import {
  mapViewportPointToWorld,
  panMapCameraByPixels,
  zoomMapCamera,
  type MapCamera,
} from "./mapCamera";

const camera: MapCamera = { centerX: 10, centerY: 40, zoom: 2 };
const viewport = { width: 1200, height: 600 };

describe("map camera pointer mathematics", () => {
  it("maps the viewport centre to the camera centre", () => {
    expect(mapViewportPointToWorld(camera, viewport, { x: 600, y: 300 }))
      .toEqual({ centerX: 10, centerY: 40 });
  });

  it("moves the world with a dragged pointer", () => {
    const moved = panMapCameraByPixels(camera, { x: 200, y: -120 }, viewport);
    expect(moved.centerX).toBeLessThan(camera.centerX);
    expect(moved.centerY).toBeGreaterThan(camera.centerY);
    expect(moved.zoom).toBe(camera.zoom);
  });

  it("keeps an off-centre world anchor fixed while zooming", () => {
    const point = { x: 850, y: 180 };
    const anchor = mapViewportPointToWorld(camera, viewport, point);
    const zoomed = zoomMapCamera(camera, 1.8, anchor);
    const after = mapViewportPointToWorld(zoomed, viewport, point);
    expect(after.centerX).toBeCloseTo(anchor.centerX, 8);
    expect(after.centerY).toBeCloseTo(anchor.centerY, 8);
  });
});

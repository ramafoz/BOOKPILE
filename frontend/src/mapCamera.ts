export interface MapCamera {
  centerX: number;
  centerY: number;
  zoom: number;
}

export interface MapViewportSize {
  width: number;
  height: number;
}

export interface MapWorldRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface MapWorldBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export const LEGACY_MAP_CAMERA: MapCamera = {
  centerX: 0,
  centerY: 50,
  zoom: 1,
};
export const LEGACY_MAP_ASPECT_RATIO = 5 / 3;

export const MAP_MIN_ZOOM = 0.2;
export const MAP_MAX_ZOOM = 8;
export const MAP_PAN_FRACTION = 0.12;

export function clampMapZoom(zoom: number): number {
  return Math.min(MAP_MAX_ZOOM, Math.max(MAP_MIN_ZOOM, zoom));
}

export function panMapCamera(
  camera: MapCamera,
  direction: "up" | "down" | "left" | "right",
  viewport: MapViewportSize,
): MapCamera {
  const verticalDistance = 100 / camera.zoom * MAP_PAN_FRACTION;
  const horizontalSpan = viewport.height > 0
    ? 100 * viewport.width / (viewport.height * LEGACY_MAP_ASPECT_RATIO)
    : 100;
  const horizontalDistance = horizontalSpan / camera.zoom * MAP_PAN_FRACTION;
  if (direction === "up") {
    return { ...camera, centerY: camera.centerY - verticalDistance };
  }
  if (direction === "down") {
    return { ...camera, centerY: camera.centerY + verticalDistance };
  }
  if (direction === "left") {
    return { ...camera, centerX: camera.centerX - horizontalDistance };
  }
  return { ...camera, centerX: camera.centerX + horizontalDistance };
}

export function zoomMapCamera(
  camera: MapCamera,
  factor: number,
  anchor: Pick<MapCamera, "centerX" | "centerY"> = camera,
): MapCamera {
  const zoom = clampMapZoom(camera.zoom * factor);
  if (zoom === camera.zoom) return camera;
  const ratio = camera.zoom / zoom;
  return {
    centerX: anchor.centerX - (anchor.centerX - camera.centerX) * ratio,
    centerY: anchor.centerY - (anchor.centerY - camera.centerY) * ratio,
    zoom,
  };
}

export function boundsForMapRects(
  rects: MapWorldRect[],
): MapWorldBounds | null {
  if (rects.length === 0) return null;
  return rects.reduce<MapWorldBounds>(
    (bounds, rect) => ({
      minX: Math.min(bounds.minX, rect.x),
      minY: Math.min(bounds.minY, rect.y),
      maxX: Math.max(bounds.maxX, rect.x + rect.width),
      maxY: Math.max(bounds.maxY, rect.y + rect.height),
    }),
    {
      minX: Number.POSITIVE_INFINITY,
      minY: Number.POSITIVE_INFINITY,
      maxX: Number.NEGATIVE_INFINITY,
      maxY: Number.NEGATIVE_INFINITY,
    },
  );
}

export function fitMapVerticalBounds(
  bounds: MapWorldBounds | null,
  viewport: MapViewportSize,
  horizontalCenter = 0,
): MapCamera {
  if (!bounds || viewport.width <= 0 || viewport.height <= 0) {
    return LEGACY_MAP_CAMERA;
  }
  const padding = Math.min(
    48,
    Math.max(16, Math.min(viewport.width, viewport.height) * 0.05),
  );
  const usableHeight = Math.max(1, viewport.height - padding * 2);
  const worldHeight = Math.max(0.001, bounds.maxY - bounds.minY);
  return {
    centerX: horizontalCenter,
    centerY: (bounds.minY + bounds.maxY) / 2,
    zoom: clampMapZoom(usableHeight / viewport.height * 100 / worldHeight),
  };
}

export function mapCameraTransform(camera: MapCamera): string {
  return `scale(${camera.zoom}) translate(${-camera.centerX}%, ${-camera.centerY}%)`;
}

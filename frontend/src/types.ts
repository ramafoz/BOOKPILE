export type BookStatus = "PENDING" | "READ";
export type ContainerType = "ROW" | "PILE";
export type Layer = "BACKGROUND" | "FOREGROUND";

export interface Container {
  id: number;
  shelf_id: number;
  container_type: ContainerType;
  layer: Layer;
  container_number: number;
}

export interface Shelf {
  id: number;
  bookcase_id: number;
  shelf_number: number;
  containers: Container[];
}

export interface Bookcase {
  id: number;
  name: string;
  description: string | null;
  shelves: Shelf[];
}

export interface Book {
  id: number;
  title: string;
  author: string;
  status: BookStatus;
  goodreads_url: string | null;
  notes: string | null;
  container_id: number | null;
  position: number | null;
  created_at: string;
  updated_at: string;
  location_label: string | null;
}

export interface Stats {
  total: number;
  pending: number;
  read: number;
}

export interface BookPayload {
  title: string;
  author: string;
  status: BookStatus;
  goodreads_url: string | null;
  notes: string | null;
  container_id: number | null;
  position: number | null;
}


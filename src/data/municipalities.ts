/**
 * Typed access to the Metro Vancouver municipal boundary data.
 *
 * The geometry lives in `metro-vancouver.municipalities.json` (generated from
 * an authoritative public GIS source — see `src/data/README.md`). This module
 * only adds types and small helpers; it does no rendering, so each
 * municipality can be consumed individually later (selection, labels, routing).
 */
import data from './metro-vancouver.municipalities.json'

/** A single [x, y] vertex in scene units. +x = East, +y = North. */
export type Point = [number, number]

/** One polygon: an outer ring plus zero or more holes. */
export interface Polygon {
  outer: Point[]
  holes: Point[][]
}

export interface Municipality {
  /** Stable kebab-case identifier, e.g. `"north-vancouver-district"`. */
  id: string
  /** Human-readable name for UI, e.g. `"District of North Vancouver"`. */
  name: string
  /** Original name from the source dataset. */
  source_name: string
  /** One or more polygons (islands / detached parts) making up the area. */
  polygons: Polygon[]
}

export interface MunicipalitiesMeta {
  description: string
  source: string
  source_url: string
  source_licence: string
  access: string
  retrieved: string
  projection: {
    type: string
    origin_lon: number
    origin_lat: number
    note: string
  }
  simplify_tolerance_m: number
  units_per_metre: number
  bounds: { width: number; height: number }
}

export const municipalitiesMeta = data.meta as MunicipalitiesMeta

export const municipalities = data.municipalities as Municipality[]

/** Look up a municipality by its `id`. */
export function getMunicipality(id: string): Municipality | undefined {
  return municipalities.find((m) => m.id === id)
}

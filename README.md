# Metro Mobile Plans

An interactive 3D map of Metro Vancouver, built with React + TypeScript and
[`@react-three/fiber`](https://r3f.docs.pmnd.rs/) / Three.js. The municipalities
will become individually selectable; this is the map foundation.

## Develop

```sh
npm install
npm run dev      # Vite dev server with HMR
npm run build    # type-check + production build
npm run lint
```

## Project layout

```
src/
  main.tsx                     React entry
  App.tsx                      mounts <Scene/>
  index.css                    full-window reset
  scene/                       everything that renders in 3D
    Scene.tsx                  the full-screen <Canvas>, camera, composition
    config.ts                  colors, camera framing, terrain height
    Lights.tsx                 hemisphere + ambient + one shadow-casting sun
    Water.tsx                  large blue ground plane
    Municipalities.tsx         extrudes the boundary data into green land
  data/                        geographic data, kept separate from rendering
    metro-vancouver.municipalities.json   generated boundary polygons
    municipalities.ts          typed access + helpers
    README.md                  data source, licence, processing details
scripts/
  fetch-municipalities.py      regenerates the boundary JSON from source
```

## Geographic data

Municipal boundaries come from the **Province of British Columbia**'s authoritative
GIS dataset *"Municipalities – Legally Defined Administrative Areas of BC"* (BC Data
Catalogue, Open Government Licence – British Columbia), retrieved from the province's
public WFS endpoint. Shapes are real legal boundaries, not approximations. Full
details and regeneration instructions: [`src/data/README.md`](src/data/README.md).

import { Bridge } from '../Bridge'
import { Road } from '../Road'
import { BRIDGES, ROAD_NETWORK, ROAD_WIDTH } from './network'

/**
 * Draws the decorative playmat road network + its bridges from the data in
 * `network.ts`. Rendering only — no routing or movement logic here.
 */
export function Roads() {
  return (
    <group>
      {ROAD_NETWORK.map((road) => (
        <Road
          key={road.id}
          points={road.points}
          width={ROAD_WIDTH[road.kind]}
          markings={road.kind === 'arterial'}
        />
      ))}
      {BRIDGES.map((bridge) => (
        <Bridge
          key={bridge.id}
          from={bridge.from}
          to={bridge.to}
          width={bridge.width}
        />
      ))}
    </group>
  )
}

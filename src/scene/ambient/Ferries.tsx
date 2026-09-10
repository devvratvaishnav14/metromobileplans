import { Ferry } from './Ferry'
import { FERRY_ROUTES } from './ferryRoutes'

/** Every ambient ferry, one per route. */
export function Ferries() {
  return (
    <group>
      {FERRY_ROUTES.map((route) => (
        <Ferry key={route.id} route={route} />
      ))}
    </group>
  )
}

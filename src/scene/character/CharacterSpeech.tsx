import { Html } from '@react-three/drei'
import { CHARACTER_HEIGHT } from './characterConfig'

interface Props {
  /** Line to speak (e.g. "Burnaby it is."), or null for no bubble. */
  text: string | null
}

/**
 * A small speech bubble anchored just above the boy's head. Rendered inside
 * the character's wrapper group, so it tracks his position and the map's
 * rotation/zoom automatically. Billboards to face the screen; a downward tail
 * points back at him.
 */
export function CharacterSpeech({ text }: Props) {
  if (!text) return null

  return (
    <Html
      position={[0, CHARACTER_HEIGHT + 1.05, 0]}
      center
      wrapperClass="speech-wrap"
      style={{ pointerEvents: 'none' }}
      zIndexRange={[30, 10]}
    >
      <div className="speech-bubble">{text}</div>
    </Html>
  )
}

import { useState } from 'react'
import './overlay.css'
import { OnboardingNotifications } from './OnboardingNotifications'
import { ConfirmationNotification } from './ConfirmationNotification'
import { InfoButton } from './InfoButton'
import { InfoPanel } from './InfoPanel'

export interface ConfirmationProps {
  /** Stable key per arrival so a fresh card mounts each time. */
  instanceKey: string
  placeName: string
  onConfirm: () => void
  onReject: () => void
}

interface Props {
  /** True once the user has selected a municipality and the boy sets off. */
  journeyStarted: boolean
  /** Present while the boy has arrived and we're asking the user to confirm. */
  confirmation: ConfirmationProps | null
}

/**
 * The whole DOM interface layer that sits on top of the 3D canvas: the opening
 * onboarding notifications, the arrival confirmation notification, and the
 * permanent info button / panel. Kept entirely separate from the Three.js scene.
 */
export function Overlay({ journeyStarted, confirmation }: Props) {
  const [infoOpen, setInfoOpen] = useState(false)
  const [manuallyClosed, setManuallyClosed] = useState(false)

  return (
    <div className="overlay-root">
      <OnboardingNotifications
        dismissed={journeyStarted || manuallyClosed}
        onClose={() => setManuallyClosed(true)}
      />
      {confirmation && (
        <ConfirmationNotification
          key={confirmation.instanceKey}
          placeName={confirmation.placeName}
          onConfirm={confirmation.onConfirm}
          onReject={confirmation.onReject}
        />
      )}
      <InfoButton onClick={() => setInfoOpen(true)} />
      {infoOpen && <InfoPanel onClose={() => setInfoOpen(false)} />}
    </div>
  )
}

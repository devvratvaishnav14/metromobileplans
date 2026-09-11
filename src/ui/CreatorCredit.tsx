import './creator-credit.css'

interface Props {
  /**
   * `overlay` — floating in the bottom-left corner over the miniature map.
   * `footer`  — in normal flow at the foot of the results page (dark surface).
   */
  variant: 'overlay' | 'footer'
}

/**
 * The site author's signature. One shared component so the map screen and the
 * results screen never drift apart.
 */
export function CreatorCredit({ variant }: Props) {
  return (
    <div className={`creator-credit creator-credit--${variant}`}>
      <span className="creator-credit__name">Devvrat Vaishnav</span>
      <span className="creator-credit__role">BSc in Data Science, SFU</span>
    </div>
  )
}

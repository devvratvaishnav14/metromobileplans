interface Props {
  onClick: () => void
}

/** Small, always-available control that opens the "How to use the map" panel. */
export function InfoButton({ onClick }: Props) {
  return (
    <button
      type="button"
      className="info-btn"
      onClick={onClick}
      aria-haspopup="dialog"
      aria-label="How to use the map"
    >
      <span aria-hidden="true">i</span>
    </button>
  )
}

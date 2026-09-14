import { useState } from 'react'
import {
  BUDGET_CHOICES,
  DATA_CHOICES,
  customizationEquals,
  customizationIsActive,
  type Customization,
  type PlanTypeChoice,
} from './customization'

interface Props {
  /** The working copy being edited. Draft edits do not affect results until Apply. */
  draft: Customization
  /** The currently applied customization — Apply is disabled while draft === committed. */
  committed: Customization
  onChange: (patch: Partial<Customization>) => void
  onApply: () => void
  onResetAll: () => void
  onClose: () => void
}

function Segmented<T extends string | number>({
  label,
  value,
  options,
  onSelect,
}: {
  label: string
  value: T
  options: { value: T; label: string }[]
  onSelect: (v: T) => void
}) {
  return (
    <div className="cz-seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          className={`cz-seg__opt${o.value === value ? ' cz-seg__opt--on' : ''}`}
          aria-pressed={o.value === value}
          onClick={() => onSelect(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function CheckRow({
  checked,
  onChange,
  label,
  help,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  help?: string
}) {
  return (
    <label className="cz-check">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="cz-check__body">
        <span className="cz-check__label">{label}</span>
        {help && <span className="cz-check__help">{help}</span>}
      </span>
    </label>
  )
}

const isChoice = (n: number | null, choices: readonly number[]) =>
  n != null && choices.includes(n)

/**
 * The Customize drawer. Draft-edit model: it edits a working copy and the
 * parent applies it on "Apply filters". Purely a preference collector — it
 * builds `/api/rank` parameters and never filters or ranks anything itself.
 */
export function CustomizePanel({
  draft,
  committed,
  onChange,
  onApply,
  onResetAll,
  onClose,
}: Props) {
  const [customBudget, setCustomBudget] = useState(
    draft.maxMonthlyPriceCad != null && !isChoice(draft.maxMonthlyPriceCad, BUDGET_CHOICES),
  )
  const [customData, setCustomData] = useState(
    draft.minDataGb != null && !isChoice(draft.minDataGb, DATA_CHOICES),
  )

  const dirty = !customizationEquals(draft, committed)
  const active = customizationIsActive(draft)

  const budgetValue: number | 'any' | 'custom' = customBudget
    ? 'custom'
    : draft.maxMonthlyPriceCad == null
      ? 'any'
      : isChoice(draft.maxMonthlyPriceCad, BUDGET_CHOICES)
        ? draft.maxMonthlyPriceCad
        : 'custom'

  const dataValue: number | 'any' | 'custom' = customData
    ? 'custom'
    : draft.minDataGb == null
      ? 'any'
      : isChoice(draft.minDataGb, DATA_CHOICES)
        ? draft.minDataGb
        : 'custom'

  return (
    <section className="cz-panel" aria-label="Customize results">
      <div className="cz-panel__head">
        <h3 className="cz-panel__title">Customize</h3>
        <button
          type="button"
          className="cz-panel__close"
          onClick={onClose}
          aria-label="Close customize panel"
        >
          &times;
        </button>
      </div>
      <p className="cz-panel__intro">
        Narrow the plans the ranking looks at. Your ranking mode still decides the
        order — these choices only decide which plans are in the running.
      </p>

      <div className="cz-grid">
        <fieldset className="cz-group">
          <legend>Monthly budget</legend>
          <Segmented
            label="Monthly budget"
            value={budgetValue}
            options={[
              { value: 'any', label: 'Any' },
              ...BUDGET_CHOICES.map((n) => ({ value: n, label: `$${n}` })),
              { value: 'custom', label: 'Custom' },
            ]}
            onSelect={(v) => {
              if (v === 'any') {
                setCustomBudget(false)
                onChange({ maxMonthlyPriceCad: null })
              } else if (v === 'custom') {
                setCustomBudget(true)
              } else {
                setCustomBudget(false)
                onChange({ maxMonthlyPriceCad: v })
              }
            }}
          />
          {customBudget && (
            <label className="cz-custom">
              <span aria-hidden>$</span>
              <input
                type="number"
                min={1}
                step={1}
                inputMode="decimal"
                placeholder="e.g. 45"
                aria-label="Custom maximum monthly budget in Canadian dollars"
                value={draft.maxMonthlyPriceCad ?? ''}
                onChange={(e) => {
                  const n = Number(e.target.value)
                  onChange({
                    maxMonthlyPriceCad: e.target.value !== '' && n > 0 ? n : null,
                  })
                }}
              />
              <span className="cz-custom__unit">/mo</span>
            </label>
          )}
          <p className="cz-help">
            Annual plans are compared using their monthly-equivalent cost. The
            upfront payment is still shown on the plan card.
          </p>
        </fieldset>

        <fieldset className="cz-group">
          <legend>Minimum data</legend>
          <Segmented
            label="Minimum data"
            value={dataValue}
            options={[
              { value: 'any', label: 'Any' },
              ...DATA_CHOICES.map((n) => ({ value: n, label: `${n} GB` })),
              { value: 'custom', label: 'Custom' },
            ]}
            onSelect={(v) => {
              if (v === 'any') {
                setCustomData(false)
                onChange({ minDataGb: null })
              } else if (v === 'custom') {
                setCustomData(true)
              } else {
                setCustomData(false)
                onChange({ minDataGb: v })
              }
            }}
          />
          {customData && (
            <label className="cz-custom">
              <input
                type="number"
                min={1}
                step={1}
                inputMode="decimal"
                placeholder="e.g. 30"
                aria-label="Custom minimum full-speed data in GB"
                value={draft.minDataGb ?? ''}
                onChange={(e) => {
                  const n = Number(e.target.value)
                  onChange({ minDataGb: e.target.value !== '' && n > 0 ? n : null })
                }}
              />
              <span className="cz-custom__unit">GB+</span>
            </label>
          )}
          <p className="cz-help">
            Domestic full-speed data only. Roam Beyond / international roaming data
            is not counted here.
          </p>
        </fieldset>

        <fieldset className="cz-group">
          <legend>Plan type</legend>
          <Segmented
            label="Plan type"
            value={draft.planType}
            options={[
              { value: 'any' as PlanTypeChoice, label: 'Any' },
              { value: 'prepaid' as PlanTypeChoice, label: 'Prepaid' },
              { value: 'postpaid' as PlanTypeChoice, label: 'Postpaid' },
            ]}
            onSelect={(v) => onChange({ planType: v })}
          />
        </fieldset>

        <fieldset className="cz-group">
          <legend>Technology &amp; roaming</legend>
          <CheckRow
            checked={draft.require5g}
            onChange={(v) => onChange({ require5g: v })}
            label="Require 5G"
            help="Only plans explicitly verified as 5G or 5G+"
          />
          <CheckRow
            checked={draft.requireCanUsMex}
            onChange={(v) => onChange({ requireCanUsMex: v })}
            label="Need Canada–U.S.–Mexico usage"
          />
          <CheckRow
            checked={draft.requireInternationalRoaming}
            onChange={(v) => onChange({ requireInternationalRoaming: v })}
            label="Need international roaming"
          />
        </fieldset>

        <fieldset className="cz-group">
          <legend>Eligibility &amp; payment</legend>
          <CheckRow
            checked={draft.studentEligible}
            onChange={(v) => onChange({ studentEligible: v })}
            label="I'm eligible for post-secondary student offers"
            help="Requires proof of enrollment at a recognized post-secondary institution."
          />
          <CheckRow
            checked={draft.autopayWilling}
            onChange={(v) => onChange({ autopayWilling: v })}
            label="Use AutoPay / Digital Discount pricing"
            help="On by default: shows the carrier's advertised AutoPay / Digital Discount price where one is separately identified. Not every carrier has one. Uncheck to rank and display regular prices only."
          />
        </fieldset>
      </div>

      <div className="cz-panel__foot">
        <button
          type="button"
          className="cz-btn cz-btn--primary"
          disabled={!dirty}
          onClick={onApply}
        >
          Apply filters
        </button>
        <button
          type="button"
          className="cz-btn cz-btn--ghost"
          disabled={!active}
          onClick={onResetAll}
        >
          Reset all
        </button>
      </div>
    </section>
  )
}

import { useEffect, useId, useRef, useState } from 'react'
import { CalendarBlankIcon as CalendarBlank } from '@phosphor-icons/react'
import { displayToIso, isoToDisplay, maskDateInput } from './dateInput'

const dateError = 'Дата в формате дд.мм.гггг'

export default function DateField({ id, value, onChange, disabled = false, required = false, ariaLabel }: {
  id?: string
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  required?: boolean
  ariaLabel?: string
}) {
  const [text, setText] = useState(() => isoToDisplay(value))
  const [invalid, setInvalid] = useState(false)
  const errorId = useId()
  const input = useRef<HTMLInputElement>(null)
  const picker = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (displayToIso(text) !== value.slice(0, 10)) {
      setText(isoToDisplay(value))
      setInvalid(false)
      input.current?.setCustomValidity('')
    }
  }, [value]) // eslint-disable-line react-hooks/exhaustive-deps

  const change = (field: HTMLInputElement) => {
    const next = maskDateInput(field.value)
    const iso = displayToIso(next)
    field.setCustomValidity(next && !iso ? dateError : '')
    setText(next)
    setInvalid(false)
    if (!next) { onChange(''); return }
    if (iso) onChange(iso)
  }
  const openPicker = () => {
    const input = picker.current
    if (!input) return
    try { input.showPicker() } catch { input.click() }
  }

  return <span className={`date-field ${invalid ? 'is-invalid' : ''}`}>
    <input
      ref={input} id={id} type="text" inputMode="numeric" autoComplete="off" placeholder="дд.мм.гггг" aria-label={ariaLabel}
      aria-invalid={invalid || undefined} required={required} disabled={disabled} value={text}
      aria-describedby={invalid ? errorId : undefined}
      onChange={event => change(event.currentTarget)}
      onBlur={event => setInvalid(event.currentTarget.validity.customError)}
      onInvalid={event => setInvalid(event.currentTarget.validity.customError)}
    />
    <button type="button" className="date-field-picker" aria-label="Выбрать дату в календаре" disabled={disabled} onClick={openPicker}><CalendarBlank size={18}/></button>
    <input ref={picker} className="date-field-native" type="date" tabIndex={-1} aria-hidden="true" value={value.slice(0, 10)} onChange={event => { input.current?.setCustomValidity(''); setText(isoToDisplay(event.target.value)); setInvalid(false); onChange(event.target.value) }}/>
    {invalid && <small id={errorId} className="date-field-error" role="alert">{dateError}</small>}
  </span>
}

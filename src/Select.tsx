import { Children, isValidElement, useId } from 'react'
import type { ChangeEvent, ReactNode, SelectHTMLAttributes } from 'react'
import * as RadixSelect from '@radix-ui/react-select'
import { CaretDownIcon, CheckIcon } from '@phosphor-icons/react'

type Props = Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size' | 'multiple'> & { children: ReactNode }
const EMPTY = '__curatorskaya_empty_option__'

function optionText(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(optionText).join('')
  if (isValidElement<{ children?: ReactNode }>(node)) return optionText(node.props.children)
  return ''
}

/** Keeps existing form handlers while replacing the browser control with one accessible Radix Select. */
export default function Select({ children, className = '', value, defaultValue, onChange, disabled, name, required, title, id, 'aria-label': ariaLabel, 'aria-labelledby': ariaLabelledBy }: Props) {
  const fallbackId = useId()
  const options = Children.toArray(children).filter(isValidElement<{ value?: string; disabled?: boolean; children?: ReactNode }>).map(child => ({
    value: String(child.props.value ?? optionText(child.props.children)),
    label: child.props.children,
    text: optionText(child.props.children),
    disabled: child.props.disabled ?? false,
  }))
  const current = value === undefined ? undefined : String(value)
  const initial = defaultValue === undefined ? undefined : String(defaultValue)
  const selected = options.find(option => option.value === (current ?? initial))
  const status = className.includes('study-status') ? current : undefined
  const change = (next: string) => {
    onChange?.({ target: { value: next === EMPTY ? '' : next } } as ChangeEvent<HTMLSelectElement>)
  }

  return <RadixSelect.Root value={current === '' ? EMPTY : current} defaultValue={initial === '' ? EMPTY : initial} onValueChange={change} disabled={disabled} name={name} required={required}>
    <RadixSelect.Trigger id={id ?? fallbackId} title={title} aria-label={ariaLabel} aria-labelledby={ariaLabelledBy} className={`ui-select-trigger ${className}`.trim()} data-status={status}>
      <RadixSelect.Value>{selected?.label}</RadixSelect.Value>
      <RadixSelect.Icon className="ui-select-chevron"><CaretDownIcon size={14} weight="fill" aria-hidden="true" /></RadixSelect.Icon>
    </RadixSelect.Trigger>
    <RadixSelect.Portal>
      <RadixSelect.Content className="ui-select-content" position="popper" sideOffset={6} collisionPadding={12} align="start">
        <RadixSelect.Viewport className="ui-select-viewport">
          {options.map(option => <RadixSelect.Item key={option.value} value={option.value === '' ? EMPTY : option.value} disabled={option.disabled} textValue={option.text} className="ui-select-item" data-status={className.includes('study-status') ? option.value : undefined}>
            <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
            <RadixSelect.ItemIndicator className="ui-select-check"><CheckIcon size={14} weight="fill" aria-hidden="true" /></RadixSelect.ItemIndicator>
          </RadixSelect.Item>)}
        </RadixSelect.Viewport>
      </RadixSelect.Content>
    </RadixSelect.Portal>
  </RadixSelect.Root>
}

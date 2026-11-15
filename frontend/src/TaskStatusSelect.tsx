import Select from './Select'
import { STUDY_STATUS } from './data'
import type { StudyStatus } from './types'

type Props = {
  value: StudyStatus
  onChange: (status: StudyStatus) => void
  ariaLabel: string
  disabled?: boolean
  title?: string
  options?: StudyStatus[]
}

export default function TaskStatusSelect({ value, onChange, ariaLabel, disabled = false, title, options }: Props) {
  return <Select
    className="study-status task-status"
    aria-label={ariaLabel}
    title={title}
    disabled={disabled}
    value={value}
    onChange={event => onChange(event.target.value as StudyStatus)}
  >
    {Object.entries(STUDY_STATUS).filter(([status])=>!options||options.includes(status as StudyStatus)).map(([status, label]) => <option key={status} value={status}>{label}</option>)}
  </Select>
}

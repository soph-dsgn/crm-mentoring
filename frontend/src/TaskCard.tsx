import type { ReactNode } from 'react'
import { ArrowSquareOutIcon as ExternalLink } from '@phosphor-icons/react'
import TaskStatusSelect from './TaskStatusSelect'
import { hasTechnicalUntitledTitle } from './taskPresentation'
import { safeExternalUrl } from './safeExternalUrl'
import type { StrategyTask, StudyStatus } from './types'

type Props = {
  task: StrategyTask
  selected?: boolean
  onSelect?: () => void
  onOpen: () => void
  onStatus: (status: StudyStatus) => void
  statusDisabled?: boolean
  statusTitle?: string
  badge?: ReactNode
  actions?: ReactNode
}

export default function TaskCard({ task, selected, onSelect, onOpen, onStatus, statusDisabled = false, statusTitle, badge, actions }: Props) {
  const hideTitle = hasTechnicalUntitledTitle(task)
  const values=[task.url,...task.materials].filter(Boolean)
  const links=values.map(safeExternalUrl).filter((value):value is string=>Boolean(value))
    .filter((value,index,items)=>items.indexOf(value)===index)
  const notes=values.filter(value=>!safeExternalUrl(value))
  const openLabel = hideTitle ? 'Открыть задачу без названия' : `Открыть задачу: ${task.title}`

  return <article className={`task-card ${hideTitle ? 'task-card-technical' : ''} ${onSelect ? '' : 'task-card-no-check'}`}>
    {onSelect && <label className="task-card-check">
      <input type="checkbox" checked={Boolean(selected)} onChange={onSelect} aria-label={hideTitle ? 'Выбрать задачу для ДЗ' : `Выбрать для ДЗ: ${task.title}`}/>
    </label>}
    <div className="task-card-content">
      <button className="task-card-open" onClick={onOpen} aria-label={openLabel}>
        {!hideTitle && <strong>{task.title}</strong>}
        {task.description && <span className="task-card-description">{task.description}</span>}
        {hideTitle && !task.description && <span className="task-card-untitled-action">Открыть задачу</span>}
      </button>
      {task.comments && <p className="task-card-comments"><span>Комментарий</span>{task.comments}</p>}
      {(links.length > 0 || notes.length > 0) && <div className="task-card-materials">
        {links.map((url, index) => <a key={url} href={url} target="_blank" rel="noopener noreferrer">
          {index === 0 ? 'Открыть материал' : `Материал ${index + 1}`} <ExternalLink size={14} weight="regular"/>
        </a>)}
        {notes.map((note, index) => <span key={`${note}-${index}`}>{note}</span>)}
      </div>}
    </div>
    <div className="task-card-status">{badge}<TaskStatusSelect value={task.studyStatus} onChange={onStatus} ariaLabel={hideTitle ? 'Статус задачи без названия' : `Статус задачи: ${task.title}`} disabled={statusDisabled} title={statusTitle}/></div>
    {actions && <div className="task-card-actions">{actions}</div>}
  </article>
}

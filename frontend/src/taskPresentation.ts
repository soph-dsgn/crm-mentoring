import type { StrategyTask } from './types'

export const hasTechnicalUntitledTitle = (task: StrategyTask) => (
  task.title.trim().toLocaleLowerCase('en-US') === 'untitled'
  && !task.description.trim()
  && !task.comments.trim()
)

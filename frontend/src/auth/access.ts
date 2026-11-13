import type { CurrentUser } from '../api/contracts'

export type AccessProfile = {
  kind: 'owner' | 'curator' | 'student'
  canUseCrm: boolean
  canManageUsers: boolean
}

export function getAccessProfile(user: CurrentUser): AccessProfile {
  if (user.role === 'student') {
    return { kind: 'student', canUseCrm: false, canManageUsers: false }
  }
  if (user.is_owner) {
    return { kind: 'owner', canUseCrm: true, canManageUsers: true }
  }
  return { kind: 'curator', canUseCrm: true, canManageUsers: false }
}

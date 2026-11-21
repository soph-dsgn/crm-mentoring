import type { LegacyImportRequest, LegacyImportResult, LegacyValidationReport } from './contracts'
import { apiRequest } from './http'

export const legacyApi = {
  validate(payload: LegacyImportRequest, signal?: AbortSignal) {
    return apiRequest<LegacyValidationReport>('/api/v1/imports/legacy/validate', {
      method: 'POST', body: payload, signal,
    })
  },
  importLegacy(payload: LegacyImportRequest, signal?: AbortSignal) {
    return apiRequest<LegacyImportResult>('/api/v1/imports/legacy', {
      method: 'POST', body: payload, signal,
    })
  },
  exportBackup(signal?: AbortSignal) {
    return apiRequest<Record<string, unknown>>('/api/v1/exports/backup', { signal })
  },
}

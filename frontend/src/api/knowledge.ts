import type {
  KnowledgeDocumentCreate,
  KnowledgeDocumentList,
  KnowledgeDocumentRead,
  KnowledgeDocumentUpdate,
  KnowledgeImportRequest,
  KnowledgeImportResult,
  KnowledgeImportValidation,
  KnowledgeKind,
  KnowledgeLibraryState,
} from './contracts'
import { apiRequest } from './http'

type ListOptions = {
  kind?: KnowledgeKind
  category?: string
  q?: string
  favorite?: boolean
  includeArchived?: boolean
  cursor?: string
  limit?: number
}

const encoded = (value: string) => encodeURIComponent(value)

export const knowledgeApi = {
  libraryState(signal?: AbortSignal) {
    return apiRequest<KnowledgeLibraryState>('/api/v1/knowledge/library-state', { signal })
  },
  list(options: ListOptions = {}, signal?: AbortSignal) {
    const params = new URLSearchParams()
    if (options.kind) params.set('kind', options.kind)
    if (options.category) params.set('category', options.category)
    if (options.q) params.set('q', options.q)
    if (options.favorite !== undefined) params.set('favorite', String(options.favorite))
    if (options.includeArchived) params.set('include_archived', 'true')
    if (options.cursor) params.set('cursor', options.cursor)
    params.set('limit', String(options.limit ?? 50))
    return apiRequest<KnowledgeDocumentList>(`/api/v1/knowledge/documents?${params}`, { signal })
  },
  get(documentId: string, signal?: AbortSignal) {
    return apiRequest<KnowledgeDocumentRead>(`/api/v1/knowledge/documents/${encoded(documentId)}`, { signal })
  },
  create(payload: KnowledgeDocumentCreate, signal?: AbortSignal) {
    return apiRequest<KnowledgeDocumentRead>('/api/v1/knowledge/documents', { method: 'POST', body: payload, signal })
  },
  update(documentId: string, payload: KnowledgeDocumentUpdate, signal?: AbortSignal) {
    return apiRequest<KnowledgeDocumentRead>(`/api/v1/knowledge/documents/${encoded(documentId)}`, { method: 'PATCH', body: payload, signal })
  },
  archive(documentId: string, expectedVersion: number, signal?: AbortSignal) {
    return apiRequest<KnowledgeDocumentRead>(`/api/v1/knowledge/documents/${encoded(documentId)}/archive`, { method: 'POST', body: { expected_version: expectedVersion }, signal })
  },
  restore(documentId: string, expectedVersion: number, signal?: AbortSignal) {
    return apiRequest<KnowledgeDocumentRead>(`/api/v1/knowledge/documents/${encoded(documentId)}/restore`, { method: 'POST', body: { expected_version: expectedVersion }, signal })
  },
  setFavorite(documentId: string, favorite: boolean, signal?: AbortSignal) {
    return apiRequest<void>(`/api/v1/knowledge/documents/${encoded(documentId)}/${favorite ? 'favorite' : 'unfavorite'}`, { method: 'POST', body: {}, signal })
  },
  validateImport(payload: KnowledgeImportRequest, signal?: AbortSignal) {
    return apiRequest<KnowledgeImportValidation>('/api/v1/knowledge/imports/validate', { method: 'POST', body: payload, signal })
  },
  confirmImport(payload: KnowledgeImportRequest, signal?: AbortSignal) {
    return apiRequest<KnowledgeImportResult>('/api/v1/knowledge/imports', { method: 'POST', body: payload, signal })
  },
  exportLibrary(signal?: AbortSignal) {
    return apiRequest<Record<string, unknown>>('/api/v1/knowledge/export', { signal })
  },
}

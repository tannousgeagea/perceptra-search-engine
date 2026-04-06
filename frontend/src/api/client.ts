import axios, { type AxiosProgressEvent } from 'axios'
import type {
  SearchResponse, TextSearchRequest, HybridSearchRequest,
  SimilaritySearchRequest, SearchStatsResponse, SearchHistoryItem,
  ImageMedia, VideoMedia, DetectionMedia, MediaStats, TagResponse,
  PaginatedResponse, ApiKey, CreateApiKeyRequest, CreateApiKeyResponse,
  ApiKeyUsage, VideoUploadResponse, ImageUploadResponse,
  SessionInfo, SearchVolumeDay, ActivityItem,
  HazardConfig, CreateHazardConfigRequest, UpdateHazardConfigRequest,
  DetectionJob, RunDetectionRequest, RunDetectionResponse,
  AgentSearchRequest, AgentSearchResponse,
  DetectionCreateRequest,
  AlertResponse, AlertRule, CreateAlertRuleRequest, UpdateAlertRuleRequest,
  AlertUnreadCount,
  ShiftSummaryResponse, AvailableShift,
  TrendResponse, AnomalyResponse, HeatmapResponse,
  ChecklistTemplate, ChecklistInstance, CreateChecklistTemplateRequest,
  CreateChecklistInstanceRequest, SubmitChecklistItemRequest, ComplianceStats,
  CommentResponse, AssignmentResponse, ActivityEventResponse, TenantUser,
  CreateCommentRequest, CreateAssignmentRequest, UpdateAssignmentRequest,
  WasteCamera, WasteCameraCreate, WasteCameraUpdate,
  WasteInspection, WasteAlert, WasteStats,
  InspectFrameRequest, WastePaginatedResponse,
} from '../types/api'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

// Attach auth headers
api.interceptors.request.use((config) => {
  try {
    const raw = localStorage.getItem('auth')
    if (!raw) return config
    const auth = JSON.parse(raw)
    if (auth.mode === 'apikey' && auth.apiKey) {
      config.headers['X-API-Key'] = auth.apiKey
    } else if (auth.mode === 'jwt' && auth.token) {
      config.headers['Authorization'] = `Bearer ${auth.token}`
      if (auth.tenantId) config.headers['X-Tenant-ID'] = auth.tenantId
      if (auth.tenantDomain) config.headers['X-Tenant-Domain'] = auth.tenantDomain
    }
  } catch { /* ignore */ }
  return config
})

// Global 401 handler — attempt token refresh before redirecting
let _refreshing: Promise<string> | null = null

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config as (typeof err.config) & { _retry?: boolean }
    if (err.response?.status !== 401 || original._retry || window.location.pathname === '/login') {
      return Promise.reject(err)
    }

    try {
      const raw = localStorage.getItem('auth')
      if (!raw) throw new Error('no auth')
      const auth = JSON.parse(raw)
      if (auth.mode !== 'jwt' || !auth.refreshToken) throw new Error('no refresh token')

      if (!_refreshing) {
        _refreshing = api
          .post<{ access: string }>('/v1/auth/token/refresh', { refresh: auth.refreshToken })
          .then((r) => r.data.access)
          .finally(() => { _refreshing = null })
      }

      const newAccess = await _refreshing
      const updated = { ...auth, token: newAccess }
      localStorage.setItem('auth', JSON.stringify(updated))

      original._retry = true
      original.headers = { ...original.headers, Authorization: `Bearer ${newAccess}` }
      return api(original)
    } catch {
      localStorage.removeItem('auth')
      window.location.href = '/login'
      return Promise.reject(err)
    }
  }
)

// ── Auth ──────────────────────────────────────────────────────
export const registerUser = (data: { email: string; password: string; name?: string }) =>
  api.post('/v1/auth/register', data)

export const loginWithCredentials = (data: { email: string; password: string }) =>
  api.post<{ access: string; refresh: string }>('/v1/auth/token', data)

export const refreshToken = (data: { refresh: string }) =>
  api.post<{ access: string; token_type: string }>('/v1/auth/token/refresh', data)

export const logoutUser = (data: { refresh: string }) =>
  api.post('/v1/auth/logout', data)

export const getCurrentUser = () =>
  api.get('/v1/auth/me')

export const requestPasswordReset = (data: { email: string }) =>
  api.post('/v1/auth/password/reset', data)

export const confirmPasswordReset = (data: { token: string; new_password: string }) =>
  api.post('/v1/auth/password/reset/confirm', data)

export const changePassword = (data: { current_password: string; new_password: string }) =>
  api.post('/v1/auth/password/change', data)

export const getSession = () =>
  api.get<SessionInfo>('/v1/auth/session')

export const validateAuth = () => getSession()

// ── Search ────────────────────────────────────────────────────
export const searchByImage = (formData: FormData, params?: Record<string, string | number>) =>
  api.post<SearchResponse>('/v1/search/image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params,
  })

export const searchByText = (data: TextSearchRequest) =>
  api.post<SearchResponse>('/v1/search/text', data)

export const searchHybrid = (formData: FormData, params?: Record<string, string | number>) =>
  api.post<SearchResponse>('/v1/search/hybrid', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params,
  })

export const searchSimilar = (data: SimilaritySearchRequest) =>
  api.post<SearchResponse>('/v1/search/similar', data)

export const getSearchHistory = (params?: { page?: number; page_size?: number }) =>
  api.get<PaginatedResponse<SearchHistoryItem>>('/v1/search/history', { params })

export const agentSearch = (data: AgentSearchRequest) =>
  api.post<AgentSearchResponse>('/v1/agent/search', data)

export const getSearchStats = () =>
  api.get<SearchStatsResponse>('/v1/search/stats')

export const getSearchVolume = (days?: number) =>
  api.get<SearchVolumeDay[]>('/v1/search/stats/volume', { params: days ? { days } : {} })

export const getRecentActivity = (limit?: number) =>
  api.get<ActivityItem[]>('/v1/search/stats/activity', { params: limit ? { limit } : {} })

// ── Media ─────────────────────────────────────────────────────
export interface MediaParams {
  plant_site?: string
  shift?: string
  status?: string
  date_from?: string
  date_to?: string
  tags?: string
  page?: number
  page_size?: number
}

export const getImages = (params?: MediaParams) =>
  api.get<PaginatedResponse<ImageMedia>>('/v1/media/images', { params })

export const getVideos = (params?: MediaParams) =>
  api.get<PaginatedResponse<VideoMedia>>('/v1/media/videos', { params })

export const getDetections = (params?: { label?: string; min_confidence?: number; page?: number; page_size?: number }) =>
  api.get<PaginatedResponse<DetectionMedia>>('/v1/media/detections', { params })

export const getImage = (id: number) =>
  api.get<ImageMedia>(`/v1/media/images/${id}`)

export const getVideo = (id: number) =>
  api.get<VideoMedia>(`/v1/media/videos/${id}`)

export const getDetection = (id: number) =>
  api.get<DetectionMedia>(`/v1/media/detections/${id}`)

export const getMediaStats = () =>
  api.get<MediaStats>('/v1/media/stats')

export const getTags = () =>
  api.get<TagResponse[]>('/v1/media/tags')

export const deleteVideo = (id: number) =>
  api.delete(`/v1/media/videos/${id}`)

export const deleteImage = (id: number) =>
  api.delete(`/v1/media/images/${id}`)

export const createDetection = (data: DetectionCreateRequest) =>
  api.post<DetectionMedia>('/v1/upload/detection', data)

// ── Bulk Operations ──────────────────────────────────────────
export const bulkDeleteImages = (ids: number[]) =>
  api.post<{ deleted: number }>('/v1/media/images/bulk-delete', { ids })

export const bulkDeleteVideos = (ids: number[]) =>
  api.post<{ deleted: number }>('/v1/media/videos/bulk-delete', { ids })

export const bulkDeleteDetections = (ids: number[]) =>
  api.post<{ deleted: number }>('/v1/media/detections/bulk-delete', { ids })

export const bulkTagImages = (ids: number[], tag_names: string[], action: 'add' | 'remove') =>
  api.post('/v1/media/images/bulk-tag', { ids, tag_names, action })

export const bulkTagVideos = (ids: number[], tag_names: string[], action: 'add' | 'remove') =>
  api.post('/v1/media/videos/bulk-tag', { ids, tag_names, action })

export const bulkTagDetections = (ids: number[], tag_names: string[], action: 'add' | 'remove') =>
  api.post('/v1/media/detections/bulk-tag', { ids, tag_names, action })

// ── Upload ────────────────────────────────────────────────────
export const uploadImage = (
  formData: FormData,
  onProgress?: (pct: number) => void
) =>
  api.post<ImageUploadResponse>('/v1/upload/image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e: AxiosProgressEvent) =>
      onProgress?.(Math.round(((e.loaded ?? 0) / (e.total ?? 1)) * 100)),
  })

export const uploadVideo = (
  formData: FormData,
  onProgress?: (pct: number) => void
) =>
  api.post<VideoUploadResponse>('/v1/upload/video', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e: AxiosProgressEvent) =>
      onProgress?.(Math.round(((e.loaded ?? 0) / (e.total ?? 1)) * 100)),
  })

// ── API Keys ──────────────────────────────────────────────────
export const getApiKeys = () =>
  api.get<ApiKey[]>('/v1/api-keys/')

export const createApiKey = (data: CreateApiKeyRequest) =>
  api.post<CreateApiKeyResponse>('/v1/api-keys/', data)

export const updateApiKey = (id: string, data: Partial<ApiKey>) =>
  api.patch<ApiKey>(`/v1/api-keys/${id}`, data)

export const deleteApiKey = (id: string) =>
  api.delete(`/v1/api-keys/${id}`)

export const getApiKeyUsage = (id: string) =>
  api.get<ApiKeyUsage>(`/v1/api-keys/${id}/usage`)

// ── Hazard Config ────────────────────────────────────────────
export const getHazardConfigs = (params?: { page?: number; page_size?: number; is_active?: boolean }) =>
  api.get<PaginatedResponse<HazardConfig>>('/v1/hazard-configs/', { params })

export const getHazardConfig = (id: number) =>
  api.get<HazardConfig>(`/v1/hazard-configs/${id}`)

export const createHazardConfig = (data: CreateHazardConfigRequest) =>
  api.post<HazardConfig>('/v1/hazard-configs/', data)

export const updateHazardConfig = (id: number, data: UpdateHazardConfigRequest) =>
  api.put<HazardConfig>(`/v1/hazard-configs/${id}`, data)

export const deleteHazardConfig = (id: number) =>
  api.delete(`/v1/hazard-configs/${id}`)

export const getDetectionJobs = (params?: { page?: number; page_size?: number; status?: string; image_id?: number; config_id?: number }) =>
  api.get<PaginatedResponse<DetectionJob>>('/v1/hazard-configs/detection-jobs/', { params })

export const runDetection = (configId: number, data: RunDetectionRequest) =>
  api.post<RunDetectionResponse>(`/v1/hazard-configs/${configId}/run`, data)

// ── Alerts ───────────────────────────────────────────────────
export const getAlerts = (params?: {
  page?: number; page_size?: number; severity?: string;
  is_acknowledged?: boolean; plant_site?: string;
  date_from?: string; date_to?: string
}) =>
  api.get<PaginatedResponse<AlertResponse>>('/v1/alerts/', { params })

export const getAlertUnreadCount = () =>
  api.get<AlertUnreadCount>('/v1/alerts/unread-count')

export const acknowledgeAlert = (id: number) =>
  api.post<AlertResponse>(`/v1/alerts/${id}/acknowledge`)

export const acknowledgeAllAlerts = () =>
  api.post<{ acknowledged: number }>('/v1/alerts/acknowledge-all')

export const getAlertRules = (params?: { page?: number; page_size?: number; is_active?: boolean }) =>
  api.get<PaginatedResponse<AlertRule>>('/v1/alerts/rules/', { params })

export const createAlertRule = (data: CreateAlertRuleRequest) =>
  api.post<AlertRule>('/v1/alerts/rules/', data)

export const updateAlertRule = (id: number, data: UpdateAlertRuleRequest) =>
  api.put<AlertRule>(`/v1/alerts/rules/${id}`, data)

export const deleteAlertRule = (id: number) =>
  api.delete(`/v1/alerts/rules/${id}`)

// ── Reports ──────────────────────────────────────────────────
export const getShiftSummary = (params: { shift: string; date: string; plant_site?: string }) =>
  api.get<ShiftSummaryResponse>('/v1/reports/shift-summary', { params })

export const downloadShiftPdf = (params: { shift: string; date: string; plant_site?: string }) =>
  api.get('/v1/reports/shift-summary/pdf', { params, responseType: 'blob' })

export const getAvailableShifts = (params?: { date_from?: string; date_to?: string }) =>
  api.get<AvailableShift[]>('/v1/reports/available-shifts', { params })

// ── Trends & Anomalies ───────────────────────────────────────
export const getDetectionTrends = (params?: { labels?: string; plant_site?: string; granularity?: string; days?: number }) =>
  api.get<TrendResponse>('/v1/search/stats/trends', { params })

export const getAnomalies = (params?: { window?: number; threshold?: number }) =>
  api.get<AnomalyResponse>('/v1/search/stats/anomalies', { params })

export const getHeatmap = (params?: { days?: number }) =>
  api.get<HeatmapResponse>('/v1/search/stats/heatmap', { params })

// ── Checklists ───────────────────────────────────────────────
export const getChecklistTemplates = (params?: { page?: number; page_size?: number; is_active?: boolean; plant_site?: string }) =>
  api.get<PaginatedResponse<ChecklistTemplate>>('/v1/checklists/templates/', { params })

export const createChecklistTemplate = (data: CreateChecklistTemplateRequest) =>
  api.post<ChecklistTemplate>('/v1/checklists/templates/', data)

export const updateChecklistTemplate = (id: number, data: Partial<CreateChecklistTemplateRequest>) =>
  api.put<ChecklistTemplate>(`/v1/checklists/templates/${id}`, data)

export const deleteChecklistTemplate = (id: number) =>
  api.delete(`/v1/checklists/templates/${id}`)

export const getChecklistInstances = (params?: { page?: number; page_size?: number; date?: string; shift?: string; status?: string }) =>
  api.get<PaginatedResponse<ChecklistInstance>>('/v1/checklists/', { params })

export const createChecklistInstance = (data: CreateChecklistInstanceRequest) =>
  api.post<ChecklistInstance>('/v1/checklists/', data)

export const getChecklistInstance = (id: number) =>
  api.get<ChecklistInstance>(`/v1/checklists/${id}`)

export const submitChecklistItem = (instanceId: number, itemIndex: number, data: SubmitChecklistItemRequest) =>
  api.post<ChecklistInstance>(`/v1/checklists/${instanceId}/items/${itemIndex}/submit`, data)

export const completeChecklist = (id: number) =>
  api.post<ChecklistInstance>(`/v1/checklists/${id}/complete`)

export const getComplianceStats = (params?: { days?: number }) =>
  api.get<ComplianceStats>('/v1/checklists/compliance', { params })

// ── Exports ──────────────────────────────────────────────────
export const exportMedia = (params?: { format?: string; plant_site?: string; date_from?: string; date_to?: string }) =>
  api.post('/v1/exports/media', null, { params, responseType: 'blob' })

export const exportDetections = (params?: { format?: string; label?: string; plant_site?: string; min_confidence?: number; date_from?: string; date_to?: string }) =>
  api.post('/v1/exports/detections', null, { params, responseType: 'blob' })

export const exportAnalytics = (params?: { days?: number }) =>
  api.post('/v1/exports/analytics', null, { params, responseType: 'blob' })

// ── Collaboration ────────────────────────────────────────────
export const getComments = (params: { content_type: string; object_id: number; page?: number }) =>
  api.get<PaginatedResponse<CommentResponse>>('/v1/collaboration/comments', { params })

export const createComment = (data: CreateCommentRequest) =>
  api.post<CommentResponse>('/v1/collaboration/comments', data)

export const deleteComment = (id: number) =>
  api.delete(`/v1/collaboration/comments/${id}`)

export const getAssignments = (params?: { page?: number; page_size?: number; assigned_to?: number; status?: string; priority?: string }) =>
  api.get<PaginatedResponse<AssignmentResponse>>('/v1/collaboration/assignments/', { params })

export const getMyAssignments = (params?: { page?: number; page_size?: number }) =>
  api.get<PaginatedResponse<AssignmentResponse>>('/v1/collaboration/assignments/mine', { params })

export const createAssignment = (data: CreateAssignmentRequest) =>
  api.post<AssignmentResponse>('/v1/collaboration/assignments/', data)

export const updateAssignment = (id: number, data: UpdateAssignmentRequest) =>
  api.patch<AssignmentResponse>(`/v1/collaboration/assignments/${id}`, data)

export const getActivityFeed = (params?: { page?: number; page_size?: number; action?: string }) =>
  api.get<PaginatedResponse<ActivityEventResponse>>('/v1/collaboration/activity/', { params })

export const getTenantUsers = () =>
  api.get<TenantUser[]>('/v1/collaboration/users/')

// ── WasteVision ──────────────────────────────────────────────

// Cameras
export const listWasteCameras = (params?: { is_active?: boolean; plant_site?: string; page?: number; page_size?: number }) =>
  api.get<WastePaginatedResponse<WasteCamera>>('/v1/wastevision/cameras', { params })

export const createWasteCamera = (data: WasteCameraCreate) =>
  api.post<WasteCamera>('/v1/wastevision/cameras', data)

export const updateWasteCamera = (cameraUuid: string, data: WasteCameraUpdate) =>
  api.put<WasteCamera>(`/v1/wastevision/cameras/${cameraUuid}`, data)

export const deleteWasteCamera = (cameraUuid: string) =>
  api.delete(`/v1/wastevision/cameras/${cameraUuid}`)

export const startWasteCamera = (cameraUuid: string) =>
  api.post<WasteCamera>(`/v1/wastevision/cameras/${cameraUuid}/start`)

export const stopWasteCamera = (cameraUuid: string) =>
  api.post<WasteCamera>(`/v1/wastevision/cameras/${cameraUuid}/stop`)

// Inspections
export const inspectWasteFrame = (data: InspectFrameRequest) =>
  api.post<WasteInspection>('/v1/wastevision/inspect', data)

export const listWasteInspections = (params?: { camera_uuid?: string; overall_risk?: string; date_from?: string; date_to?: string; page?: number; page_size?: number }) =>
  api.get<WastePaginatedResponse<WasteInspection>>('/v1/wastevision/inspections', { params })

export const getWasteInspection = (inspectionUuid: string) =>
  api.get<WasteInspection>(`/v1/wastevision/inspections/${inspectionUuid}`)

export const getWasteCameraTrend = (cameraUuid: string, n = 50) =>
  api.get<WasteInspection[]>(`/v1/wastevision/cameras/${cameraUuid}/trend`, { params: { n } })

export const getWasteStats = () =>
  api.get<WasteStats>('/v1/wastevision/stats')

export const exportWasteInspections = (params?: { camera_uuid?: string; overall_risk?: string; date_from?: string; date_to?: string }) =>
  api.get('/v1/wastevision/inspections/export', { params, responseType: 'blob' })

// Alerts
export const listWasteAlerts = (params?: { camera_uuid?: string; severity?: string; is_acknowledged?: boolean; page?: number; page_size?: number }) =>
  api.get<WastePaginatedResponse<WasteAlert>>('/v1/wastevision/alerts', { params })

export const acknowledgeWasteAlert = (alertUuid: string) =>
  api.post<WasteAlert>(`/v1/wastevision/alerts/${alertUuid}/acknowledge`)

export default api

// ── Auth ─────────────────────────────────────────────────────
export interface TenantInfo {
  id: string
  name: string
  slug: string
  domain: string
  location: string
  timezone: string
}

export interface ApiKeySessionInfo {
  name: string
  key_prefix: string
  permissions: string
  expires_at: string | null
}

export interface SessionInfo {
  auth_method: 'jwt' | 'api_key'
  role: string
  user: {
    id: number
    email: string
    name: string | null
    is_active: boolean
    is_staff: boolean
    date_joined: string
  } | null
  tenant: TenantInfo
  api_key: ApiKeySessionInfo | null
}

export interface AuthState {
  mode: 'apikey' | 'jwt'
  apiKey?: string
  apiKeyLabel?: string
  token?: string
  refreshToken?: string
  email?: string
  tenantId?: string
  tenantDomain?: string
  session?: SessionInfo
}

// ── Filters ──────────────────────────────────────────────────
export interface SearchFilterParams {
  plant_site?: string
  shift?: string
  inspection_line?: string
  labels?: string[]
  tags?: string[]
  date_from?: string
  date_to?: string
  min_confidence?: number
  max_confidence?: number
  video_id?: number
}

// ── Search requests ──────────────────────────────────────────
export type SearchType = 'images' | 'detections' | 'both'

export interface TextSearchRequest {
  query: string
  top_k?: number
  score_threshold?: number
  search_type?: SearchType
  filters?: SearchFilterParams
  return_vectors?: boolean
}

export interface HybridSearchRequest extends TextSearchRequest {
  text_weight?: number
}

export interface SimilaritySearchRequest {
  item_id: number
  item_type: 'image' | 'detection'
  top_k?: number
  score_threshold?: number
  filters?: SearchFilterParams
}

// ── Search results ───────────────────────────────────────────
export interface BoundingBox {
  x: number
  y: number
  width: number
  height: number
  format: string
}

export interface ImageSearchResult {
  id: number
  image_id: string
  filename: string
  storage_key: string
  similarity_score: number
  width: number
  height: number
  plant_site: string
  shift?: string
  inspection_line?: string
  captured_at: string
  video_id?: number
  video_uuid?: string
  frame_number?: number
  timestamp_in_video?: number
  download_url?: string
}

export interface DetectionSearchResult {
  id: number
  detection_id: string
  similarity_score: number
  label: string
  confidence: number
  bbox: BoundingBox
  image_id: number
  image_uuid: string
  image_filename: string
  image_storage_key: string
  plant_site: string
  shift?: string
  inspection_line?: string
  captured_at: string
  video_id?: number
  video_uuid?: string
  frame_number?: number
  timestamp_in_video?: number
  tags: string[]
  image_url?: string
  crop_url?: string
}

export interface SearchResponse {
  query_id: string
  search_type: string
  results_type: string
  image_results?: ImageSearchResult[]
  detection_results?: DetectionSearchResult[]
  total_results: number
  execution_time_ms: number
  filters_applied: Record<string, unknown>
  model_version: string
}

export interface SearchHistoryItem {
  id: string
  query_type: string
  query_text?: string
  search_type: string
  results_count: number
  execution_time_ms: number
  created_at: string
}

export interface SearchStatsResponse {
  total_searches: number
  searches_today: number
  searches_yesterday: number
  avg_execution_time_ms: number
  most_searched_labels: Array<{ label: string; count: number }>
  search_type_distribution: Record<string, number>
}

export interface SearchVolumeDay {
  date: string
  day: string
  searches: number
  detections: number
}

export interface ActivityItem {
  type: 'search' | 'upload' | 'detect'
  msg: string
  time: string
  tag: string
}

// ── Media ─────────────────────────────────────────────────────
export interface TagResponse {
  id: number
  name: string
  description?: string
  color: string
}

export interface VideoMedia {
  id: number
  video_id: string
  filename: string
  storage_key: string
  storage_backend: string
  file_size_bytes: number
  duration_seconds?: number
  plant_site: string
  shift?: string
  inspection_line?: string
  recorded_at: string
  status: string
  frame_count?: number
  tags: TagResponse[]
  created_at: string
  download_url?: string
}

export interface ImageMedia {
  id: number
  image_id: string
  filename: string
  storage_key: string
  storage_backend: string
  file_size_bytes: number
  width: number
  height: number
  plant_site: string
  shift?: string
  inspection_line?: string
  captured_at: string
  video_id?: string
  frame_number?: number
  checksum?: string
  tags: TagResponse[]
  status: string
  created_at: string
  download_url?: string
}

export interface DetectionMedia {
  id: number
  detection_id: string
  image_id: number
  image_uuid?: string
  image_filename?: string
  image_width?: number
  image_height?: number
  bbox_x: number
  bbox_y: number
  bbox_width: number
  bbox_height: number
  bbox_format: string
  label: string
  confidence: number
  storage_key?: string
  plant_site?: string
  shift?: string
  inspection_line?: string
  captured_at?: string
  video_id?: number
  video_uuid?: string
  embedding_generated: boolean
  embedding_model_version?: string
  tags: TagResponse[]
  created_at: string
  updated_at?: string
  image_url?: string
  crop_url?: string
}

export interface MediaStats {
  total_images: number
  total_videos: number
  total_detections: number
  total_storage_bytes: number
  status_breakdown: Record<string, number>
  top_labels: Array<{ label: string; count: number }>
  plant_breakdown: Array<{ plant_site: string; total: number; detections: number }>
  media_trend_pct: number
}

export interface PaginationMeta {
  page: number
  page_size: number
  total_items: number
  total_pages: number
  has_next: boolean
  has_previous: boolean
}

export interface PaginatedResponse<T> {
  items: T[]
  pagination: PaginationMeta
  filters_applied: Record<string, unknown>
}

// ── API Keys ──────────────────────────────────────────────────
export type ApiKeyPermission = 'read' | 'write' | 'admin'

export interface ApiKey {
  id: string
  name: string
  key_prefix: string
  permissions: ApiKeyPermission
  is_active: boolean
  rate_limit_per_minute?: number
  rate_limit_per_hour?: number
  expires_at?: string
  last_used_at?: string
  created_at: string
  usage_count: number
}

export interface CreateApiKeyRequest {
  name: string
  permissions: ApiKeyPermission
  rate_limit_per_minute?: number
  rate_limit_per_hour?: number
  expires_at?: string
}

export interface CreateApiKeyResponse extends ApiKey {
  secret: string // only shown once
}

export interface ApiKeyUsage {
  total_calls: number
  calls_today: number
  calls_this_week: number
  endpoints: Array<{ endpoint: string; count: number }>
}

// ── Hazard Config ────────────────────────────────────────────
export interface HazardConfig {
  id: number
  name: string
  prompts: string[]
  detection_backend: string
  confidence_threshold: number
  is_active: boolean
  is_default: boolean
  config: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface CreateHazardConfigRequest {
  name: string
  prompts: string[]
  detection_backend?: string
  confidence_threshold?: number
  is_active?: boolean
  is_default?: boolean
  config?: Record<string, unknown>
}

export interface UpdateHazardConfigRequest {
  name?: string
  prompts?: string[]
  detection_backend?: string
  confidence_threshold?: number
  is_active?: boolean
  is_default?: boolean
  config?: Record<string, unknown>
}

export interface DetectionJob {
  id: number
  detection_job_id: string
  image_id: number
  image_filename: string
  hazard_config_name: string | null
  detection_backend: string
  status: string
  total_detections: number
  inference_time_ms: number | null
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  created_at: string
}

// ── Agent Search ─────────────────────────────────────────────
export interface AgentSearchRequest {
  query: string
  top_k?: number
  search_type?: SearchType
  enable_reasoning?: boolean
}

export interface SearchPlan {
  search_method: string
  query_text?: string
  item_id?: number
  item_type?: string
  filters?: SearchFilterParams
  top_k: number
  reasoning: string
}

export interface AgentSearchResponse {
  query_id: string
  original_query: string
  search_plan: SearchPlan
  image_results?: ImageSearchResult[]
  detection_results?: DetectionSearchResult[]
  total_results: number
  execution_time_ms: number
  llm_time_ms: number
  llm_provider: string
  model_version: string
  agent_summary?: string
  fallback_used: boolean
}

export interface RunDetectionRequest {
  image_ids: number[]
}

export interface RunDetectionResponse {
  queued: number
  image_ids: number[]
}

// ── Detection Creation ───────────────────────────────────────
export interface DetectionCreateRequest {
  image_id: number
  bbox_x: number
  bbox_y: number
  bbox_width: number
  bbox_height: number
  bbox_format: 'normalized' | 'absolute'
  label: string
  confidence: number
  tags?: Array<{ name: string; description?: string; color?: string }>
}

// ── Upload ───────────────────────────────────────────────────
export interface VideoUploadResponse {
  id: number
  video_id: string
  filename: string
  plant_site: string
  status: string
  created_at: string
}

export interface ImageUploadResponse {
  id: number
  image_id: string
  filename: string
  plant_site: string
  status: string
  created_at: string
}

// ── Alerts ──────────────────────────────────────────────────
export type AlertSeverity = 'critical' | 'warning' | 'info'

export interface AlertResponse {
  id: number
  alert_rule_id: number | null
  alert_rule_name: string | null
  detection_id: number
  image_id: number
  severity: AlertSeverity
  label: string
  confidence: number
  plant_site: string | null
  is_acknowledged: boolean
  acknowledged_by_email: string | null
  acknowledged_at: string | null
  webhook_sent: boolean
  crop_url: string | null
  created_at: string
}

export interface AlertRule {
  id: number
  name: string
  label_pattern: string
  min_confidence: number
  plant_site: string | null
  is_active: boolean
  webhook_url: string | null
  notify_websocket: boolean
  cooldown_minutes: number
  created_at: string
  updated_at: string
}

export interface CreateAlertRuleRequest {
  name: string
  label_pattern: string
  min_confidence?: number
  plant_site?: string | null
  is_active?: boolean
  webhook_url?: string | null
  notify_websocket?: boolean
  cooldown_minutes?: number
}

export interface UpdateAlertRuleRequest {
  name?: string
  label_pattern?: string
  min_confidence?: number
  plant_site?: string | null
  is_active?: boolean
  webhook_url?: string | null
  notify_websocket?: boolean
  cooldown_minutes?: number
}

export interface AlertUnreadCount {
  count: number
}

// ── Reports ─────────────────────────────────────────────────
export interface ShiftUploads {
  total: number
  images: number
  videos: number
}

export interface HighSeverityItem {
  detection_id: number
  label: string
  confidence: number
  image_id: number
  image_filename: string
  crop_url: string | null
}

export interface LabelCount {
  label: string
  count: number
}

export interface ShiftDetections {
  total: number
  by_label: LabelCount[]
  high_severity: HighSeverityItem[]
}

export interface ShiftAlerts {
  total: number
  unacknowledged: number
  critical: number
}

export interface ShiftComparison {
  prev_uploads: number
  prev_detections: number
  upload_delta_pct: number
  detection_delta_pct: number
}

export interface ShiftSummaryResponse {
  shift: string
  date: string
  plant_site: string | null
  period_start: string
  period_end: string
  uploads: ShiftUploads
  detections: ShiftDetections
  alerts: ShiftAlerts
  comparison: ShiftComparison
}

export interface AvailableShift {
  date: string
  shift: string
  image_count: number
}

// ── Trends & Anomalies ──────────────────────────────────────
export interface TrendPoint {
  date: string
  count: number
}

export interface TrendSeries {
  label: string
  data: TrendPoint[]
}

export interface TrendResponse {
  series: TrendSeries[]
  granularity: string
  days: number
}

export interface AnomalyItem {
  label: string
  plant_site: string | null
  current_count: number
  avg_count: number
  z_score: number
  pct_change: number
  severity: string
  period: string
}

export interface AnomalyResponse {
  anomalies: AnomalyItem[]
  checked_at: string
}

export interface HeatmapCell {
  label: string
  plant_site: string
  count: number
}

export interface HeatmapResponse {
  cells: HeatmapCell[]
  labels: string[]
  plant_sites: string[]
}

// ── Checklists ──────────────────────────────────────────────
export interface ChecklistItemSchema {
  description: string
  required_photo: boolean
  auto_detect: boolean
}

export interface ChecklistTemplate {
  id: number
  name: string
  plant_site: string
  inspection_line: string | null
  shift: string | null
  items: ChecklistItemSchema[]
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ChecklistItemResult {
  item_index: number
  description: string
  required_photo: boolean
  auto_detect: boolean
  status: string
  image_id: number | null
  notes: string | null
  detection_count: number
  completed_at: string | null
}

export interface ChecklistInstance {
  id: number
  template_id: number
  template_name: string
  plant_site: string
  shift: string
  date: string
  operator_email: string | null
  status: string
  started_at: string | null
  completed_at: string | null
  notes: string | null
  items: ChecklistItemResult[]
  progress: number
  created_at: string
}

export interface CreateChecklistTemplateRequest {
  name: string
  plant_site: string
  inspection_line?: string | null
  shift?: string | null
  items: ChecklistItemSchema[]
  is_active?: boolean
}

export interface CreateChecklistInstanceRequest {
  template_id: number
  shift: string
  date: string
  notes?: string | null
}

export interface SubmitChecklistItemRequest {
  image_id?: number | null
  status: string
  notes?: string | null
}

export interface ComplianceStats {
  total_instances: number
  completed: number
  completion_rate: number
  overdue: number
  by_plant: Array<{ plant_site: string; total: number; completed: number }>
  by_shift: Array<{ shift: string; total: number; completed: number }>
}

// ── Collaboration ───────────────────────────────────────────
export interface CommentResponse {
  id: number
  content_type: string
  object_id: number
  author_id: number
  author_email: string
  author_name: string | null
  text: string
  mentions: number[]
  created_at: string
  updated_at: string
}

export interface AssignmentResponse {
  id: number
  detection_id: number
  detection_label: string | null
  detection_crop_url: string | null
  assigned_to_id: number
  assigned_to_email: string
  assigned_by_email: string
  status: string
  priority: string
  due_date: string | null
  notes: string | null
  resolved_at: string | null
  created_at: string
}

export interface ActivityEventResponse {
  id: number
  user_email: string
  user_name: string | null
  action: string
  target_type: string
  target_id: number
  metadata: Record<string, unknown>
  created_at: string
}

export interface TenantUser {
  id: number
  email: string
  name: string | null
}

export interface CreateCommentRequest {
  content_type: string
  object_id: number
  text: string
  mentions?: number[]
}

export interface CreateAssignmentRequest {
  detection_id: number
  assigned_to_id: number
  priority?: string
  due_date?: string | null
  notes?: string | null
}

export interface UpdateAssignmentRequest {
  status?: string
  priority?: string
  notes?: string | null
}

// ── WasteVision ─────────────────────────────────────────────
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface WasteCamera {
  id: number
  camera_uuid: string
  name: string
  location: string
  plant_site: string
  stream_type: 'rtsp' | 'mjpeg' | 'upload'
  stream_url: string
  target_fps: number
  is_active: boolean
  status: 'idle' | 'streaming' | 'error'
  consecutive_high: number
  last_frame_at: string | null
  last_risk_level: string
  created_at: string
}

export interface WasteComposition {
  plastic: number
  paper: number
  glass: number
  metal: number
  organic: number
  e_waste: number
  hazardous: number
  other: number
}

export interface WasteContaminationItem {
  item: string
  severity: RiskLevel
  location_in_frame: string
  action: string
}

export interface WasteInspection {
  id: number
  inspection_uuid: string
  camera_uuid: string
  sequence_no: number
  frame_timestamp: string
  waste_composition: WasteComposition
  contamination_alerts: WasteContaminationItem[]
  line_blockage: boolean
  overall_risk: RiskLevel
  confidence: number
  inspector_note: string
  vlm_provider: string
  vlm_model: string
  processing_time_ms: number | null
  created_at: string
}

export interface WasteAlert {
  id: number
  alert_uuid: string
  camera_uuid: string
  alert_type: 'contamination' | 'blockage' | 'escalation' | 'drift'
  severity: RiskLevel
  details: Record<string, unknown>
  is_acknowledged: boolean
  acknowledged_at: string | null
  created_at: string
}

export interface WasteStats {
  total_inspections: number
  risk_breakdown: { low: number; medium: number; high: number; critical: number }
  top_contamination_labels: Array<{ label: string; count: number }>
  avg_confidence_by_camera: Array<{ camera_uuid: string; camera_name: string; avg_confidence: number }>
  active_cameras: number
  alerts_last_24h: number
}

export interface WasteCameraCreate {
  name: string
  location: string
  plant_site?: string
  stream_type: 'rtsp' | 'mjpeg' | 'upload'
  stream_url?: string
  target_fps?: number
}

export interface WasteCameraUpdate {
  name?: string
  location?: string
  plant_site?: string
  stream_type?: 'rtsp' | 'mjpeg' | 'upload'
  stream_url?: string
  target_fps?: number
  is_active?: boolean
}

export interface InspectFrameRequest {
  camera_uuid: string
  image_b64: string
  async_mode?: boolean
}

export interface WastePaginatedResponse<T> {
  items: T[]
  pagination: {
    page: number
    page_size: number
    total_items: number
    total_pages: number
    has_next: boolean
    has_previous: boolean
  }
}

/** API service for communicating with the backend. */

const API_BASE = '/api/v1';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) {
    if (res.status === 502 || res.statusText === 'Bad Gateway') {
      throw new Error(
        'Backend server is not running on port 8000 (Bad Gateway). Please start the backend service using run.bat or run: cd backend && python -m uvicorn app.main:app --port 8000 --reload'
      );
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join(', ')
        : `Request failed: ${res.status}`;
    throw new Error(message || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return {} as T;
  return res.json();
}

// --- Venues ---
export const venueApi = {
  list: () => request<any[]>('/venues'),
  get: (id: string) => request<any>(`/venues/${id}`),
  create: (data: any) => request<any>('/venues', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: any) => request<any>(`/venues/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id: string) => request<void>(`/venues/${id}`, { method: 'DELETE' }),
  setBaseline: (id: string, data: any) => request<any>(`/venues/${id}/baseline`, { method: 'POST', body: JSON.stringify(data) }),
  reconcile: (id: string, data: any) => request<any>(`/venues/${id}/reconcile`, { method: 'POST', body: JSON.stringify(data) }),
  quickSetup: (data: any) => request<any>('/venues/quick-setup', { method: 'POST', body: JSON.stringify(data) }),
  startProcess: (venueId: string) => request<any>(`/venues/${venueId}/start-process`, { method: 'POST' }),
  pauseProcess: (venueId: string) => request<any>(`/venues/${venueId}/pause-process`, { method: 'POST' }),
  resetProcess: (venueId: string) => request<any>(`/venues/${venueId}/reset-process`, { method: 'POST' }),
};

// --- Gates ---
export const gateApi = {
  list: (venueId: string) => request<any[]>(`/venues/${venueId}/gates`),
  create: (venueId: string, data: any) => request<any>(`/venues/${venueId}/gates`, { method: 'POST', body: JSON.stringify(data) }),
  update: (gateId: string, data: any) => request<any>(`/gates/${gateId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (gateId: string) => request<void>(`/gates/${gateId}`, { method: 'DELETE' }),
  testConnection: (gateId: string) => request<any>(`/gates/${gateId}/test-connection`, { method: 'POST' }),
  start: (gateId: string) => request<any>(`/gates/${gateId}/start`, { method: 'POST' }),
  stop: (gateId: string) => request<any>(`/gates/${gateId}/stop`, { method: 'POST' }),
  updateLineConfig: (
    gateId: string,
    data: { start_x?: number; start_y?: number; end_x?: number; end_y?: number; counting_direction?: string; reset_anti_passback?: boolean }
  ) => request<any>(`/gates/${gateId}/line-config`, { method: 'PATCH', body: JSON.stringify(data) }),
  uploadVideo: (
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<{ success: boolean; filename: string; file_path: string; size_bytes: number }> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      const formData = new FormData()
      formData.append('file', file)

      xhr.timeout = 180000 // 3 minutes timeout

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) {
          const percent = Math.round((event.loaded / event.total) * 100)
          onProgress(percent)
        }
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText)
            resolve(data)
          } catch {
            reject(new Error('Invalid response from server'))
          }
        } else {
          if (xhr.status === 502) {
            reject(new Error('Backend server is offline on port 8000 (Bad Gateway). Start it using run.bat or uvicorn.'))
          } else {
            try {
              const err = JSON.parse(xhr.responseText)
              reject(new Error(err.detail || `Upload failed with status ${xhr.status}`))
            } catch {
              reject(new Error(`Upload failed with status ${xhr.status}`))
            }
          }
        }
      }

      xhr.onerror = () => {
        reject(new Error('Network error uploading video. Check that the backend server is running on port 8000.'))
      }

      xhr.ontimeout = () => {
        reject(new Error('Upload timed out after 3 minutes. Please check server or file size.'))
      }

      xhr.open('POST', '/api/v1/gates/upload-video')
      xhr.send(formData)
    })
  },
};

// --- Monitoring ---
export const monitorApi = {
  dashboard: (venueId: string) => request<any>(`/venues/${venueId}/dashboard`),
  occupancy: (venueId: string) => request<any>(`/venues/${venueId}/occupancy`),
  flow: (venueId: string, window = 60) => request<any>(`/venues/${venueId}/flow?window=${window}`),
  forecast: (venueId: string) => request<any>(`/venues/${venueId}/forecast`),
  alerts: (venueId: string, includeResolved = false) =>
    request<any[]>(`/venues/${venueId}/alerts?include_resolved=${includeResolved}`),
  acknowledgeAlert: (alertId: string, by = 'admin') =>
    request<any>(`/alerts/${alertId}/acknowledge`, { method: 'POST', body: JSON.stringify({ acknowledged_by: by }) }),
  resolveAlert: (alertId: string, by = 'admin', note = '') =>
    request<any>(`/alerts/${alertId}/resolve`, { method: 'POST', body: JSON.stringify({ resolved_by: by, resolution_note: note }) }),
  events: (venueId: string, limit = 100) => request<any[]>(`/venues/${venueId}/events?limit=${limit}`),
  gateCounts: (venueId: string) => request<any[]>(`/venues/${venueId}/gate-counts`),
  snapshots: (venueId: string, minutes = 60) => request<any[]>(`/venues/${venueId}/snapshots?minutes=${minutes}`),
  cameraHealth: () => request<any[]>('/cameras/health'),
  health: () => request<any>('/health'),
};

// --- WebSocket ---
export function connectWebSocket(venueId: string, onMessage: (data: any) => void): () => void {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/dashboard/${venueId}`;
  let active = true;
  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

  const connect = () => {
    if (!active) return;
    socket = new WebSocket(wsUrl);
    socket.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data));
      } catch (e) {
        console.error('WebSocket message error:', e);
      }
    };
    socket.onclose = () => {
      if (active) reconnectTimer = setTimeout(connect, 3000);
    };
    socket.onerror = () => socket?.close();
  };

  connect();
  return () => {
    active = false;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    socket?.close();
  };
}

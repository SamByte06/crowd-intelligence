/** API service for communicating with the backend. */



export function getBackendBaseUrl(): string {

  if (typeof window === 'undefined') return '';

  const stored = localStorage.getItem('crowd_backend_url');

  if (stored) return stored.trim().replace(/\/+$/, '');

  const envUrl = (import.meta as any).env?.VITE_API_BASE_URL;

  if (envUrl) return envUrl.trim().replace(/\/+$/, '');

  return '';

}



export function setBackendBaseUrl(url: string): void {

  if (typeof window === 'undefined') return;

  const clean = url.trim().replace(/\/+$/, '');

  if (!clean) {

    localStorage.removeItem('crowd_backend_url');

  } else {

    localStorage.setItem('crowd_backend_url', clean);

  }

}



export function getApiUrl(endpoint: string): string {

  const base = getBackendBaseUrl();

  const cleanEp = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;

  return `${base}/api/v1${cleanEp}`;

}



async function request<T>(url: string, options?: RequestInit): Promise<T> {

  const fullUrl = getApiUrl(url);

  let res: Response;

  try {

    res = await fetch(fullUrl, {

      ...options,

      headers: { 'Content-Type': 'application/json', ...options?.headers },

    });

  } catch (netErr: any) {

    throw new Error('Could not reach backend. Verify Cloudflare tunnel is running or check server connection.');

  }



  const contentType = res.headers.get('content-type') || '';

  if (contentType.includes('text/html')) {

    throw new Error('Host AI Server is on standby. Click the STANDBY button to connect your Cloudflare tunnel.');

  }



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



  const text = await res.text();

  try {

    return JSON.parse(text) as T;

  } catch {

    throw new Error('Host AI Server is on standby. Click the STANDBY button to connect your Cloudflare tunnel.');

  }

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

  updateCampaign: (venueId: string, data: { notification_campaign_active?: boolean; reminder_interval_seconds?: number; moderate_threshold?: number; warning_threshold?: number; critical_threshold?: number }) =>

    request<any>(`/venues/${venueId}/campaign`, { method: 'POST', body: JSON.stringify(data) }),

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

  pickLocalFile: () =>
    request<{ success?: boolean; cancelled?: boolean; file_path?: string; filename?: string }>(
      '/gates/pick-local-file',
      { method: 'POST' }
    ),
  listServerVideos: () =>

    request<

      {

        filename: string

        display_name: string

        file_path: string

        size_bytes: number

        size_mb: number

        modified_at: number

      }[]

    >('/gates/server-videos'),



  checkVideoExists: async (

    filename: string,

    sizeBytes: number

  ): Promise<{ exists: boolean; filename?: string; file_path?: string; size_bytes?: number }> => {

    try {

      const res = await fetch(

        getApiUrl(`/gates/check-video-exists?filename=${encodeURIComponent(filename)}&size_bytes=${sizeBytes}`)

      )

      if (res.ok) {

        return await res.json()

      }

    } catch {

      // fallback

    }

    return { exists: false }

  },



  uploadVideo: async (

    file: File,

    onProgress?: (percent: number) => void

  ): Promise<{ success: boolean; filename: string; file_path: string; size_bytes: number }> => {

    // 1. Instant Deduplication Check:

    // If this video already exists on the server, complete in 0ms!

    try {

      const existing = await gateApi.checkVideoExists(file.name, file.size)

      if (existing.exists && existing.file_path) {

        if (onProgress) onProgress(100)

        return {

          success: true,

          filename: existing.filename || file.name,

          file_path: existing.file_path,

          size_bytes: existing.size_bytes || file.size,

        }

      }

    } catch {

      // ignore and continue

    }



    // 2. High-Speed Resilient Chunked Upload:

    // Slices file into 2MB chunks. Bypasses Cloudflare 100MB body limit and 100s timeouts.

    const CHUNK_SIZE = 2 * 1024 * 1024 // 2MB chunks

    const totalChunks = Math.ceil(file.size / CHUNK_SIZE)

    const uploadId =

      typeof crypto !== 'undefined' && crypto.randomUUID

        ? crypto.randomUUID().replace(/-/g, '')

        : Math.random().toString(36).substring(2) + Date.now().toString(36)



    try {

      for (let i = 0; i < totalChunks; i++) {

        const start = i * CHUNK_SIZE

        const end = Math.min(file.size, start + CHUNK_SIZE)

        const chunkBlob = file.slice(start, end)



        let attempts = 3

        let chunkOk = false

        let lastErr: any = null



        while (attempts > 0 && !chunkOk) {

          try {

            const formData = new FormData()

            formData.append('upload_id', uploadId)

            formData.append('chunk_index', String(i))

            formData.append('total_chunks', String(totalChunks))

            formData.append('filename', file.name)

            formData.append('chunk', chunkBlob, `chunk_${i}.part`)



            const res = await fetch(getApiUrl('/gates/upload-video-chunk'), {

              method: 'POST',

              body: formData,

            })



            if (!res.ok) {

              const errText = await res.text().catch(() => '')

              throw new Error(`Chunk ${i + 1}/${totalChunks} upload failed: HTTP ${res.status} ${errText}`)

            }

            chunkOk = true

          } catch (err: any) {

            lastErr = err

            attempts--

            if (attempts > 0) {

              await new Promise((r) => setTimeout(r, 600))

            }

          }

        }



        if (!chunkOk) {

          throw lastErr || new Error(`Upload failed at chunk ${i + 1}/${totalChunks}`)

        }



        if (onProgress) {

          const percent = Math.min(99, Math.round(((i + 1) / totalChunks) * 100))

          onProgress(percent)

        }

      }



      // Finalize all chunks into completed file

      const finishData = new FormData()

      finishData.append('upload_id', uploadId)

      finishData.append('total_chunks', String(totalChunks))

      finishData.append('filename', file.name)



      const finishRes = await fetch(getApiUrl('/gates/finish-video-chunk'), {

        method: 'POST',

        body: finishData,

      })



      if (!finishRes.ok) {

        throw new Error(`Failed to finalize uploaded video on server (${finishRes.status})`)

      }



      const result = await finishRes.json()

      if (onProgress) onProgress(100)

      return result

    } catch (chunkError: any) {

      console.warn('Chunked upload failed, trying fallback direct upload:', chunkError)

      return new Promise((resolve, reject) => {

        const xhr = new XMLHttpRequest()

        const formData = new FormData()

        formData.append('file', file)

        xhr.timeout = 180000



        xhr.upload.onprogress = (event) => {

          if (event.lengthComputable && onProgress) {

            const percent = Math.round((event.loaded / event.total) * 100)

            onProgress(percent)

          }

        }



        xhr.onload = () => {

          if (xhr.status >= 200 && xhr.status < 300) {

            try {

              resolve(JSON.parse(xhr.responseText))

            } catch {

              reject(new Error('Invalid response from server'))

            }

          } else {

            reject(new Error(`Upload failed with status ${xhr.status}: ${xhr.statusText}`))

          }

        }



        xhr.onerror = () => reject(new Error('Network error uploading video. Check server and tunnel status.'))

        xhr.ontimeout = () => reject(new Error('Upload timed out. Check connection speed or file size.'))



        xhr.open('POST', getApiUrl('/gates/upload-video'))

        xhr.send(formData)

      })

    }

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

  pushStats: (venueId: string) => request<any>(`/push/stats/${venueId}`),

  pushHistory: (venueId: string, limit = 30) => request<any[]>(`/push/history/${venueId}?limit=${limit}`),

  togglePush: (data: { venue_id: string; endpoint: string; notifications_enabled?: boolean; is_following?: boolean }) =>

    request<any>('/push/toggle', { method: 'POST', body: JSON.stringify(data) }),

};



// WebSocket connection helper

export type ConnectionStatus = 'CONNECTED' | 'RECONNECTING' | 'OFFLINE';



export function connectWebSocket(

  venueId: string,

  onMessage: (data: any) => void,

  onStatusChange?: (status: ConnectionStatus) => void

): () => void {

  const base = getBackendBaseUrl();

  let wsUrl: string;

  if (base) {

    const wsHost = base.replace(/^http:\/\//i, 'ws://').replace(/^https:\/\//i, 'wss://');

    wsUrl = `${wsHost}/api/v1/ws/dashboard/${venueId}`;

  } else {

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

    wsUrl = `${protocol}//${window.location.host}/api/v1/ws/dashboard/${venueId}`;

  }

  let active = true;

  let socket: WebSocket | null = null;

  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

  let heartbeatTimer: ReturnType<typeof setInterval> | undefined;

  let retryCount = 0;



  const setStatus = (s: ConnectionStatus) => {

    if (onStatusChange) onStatusChange(s);

  };



  const clearTimers = () => {

    if (reconnectTimer) clearTimeout(reconnectTimer);

    if (heartbeatTimer) clearInterval(heartbeatTimer);

    reconnectTimer = undefined;

    heartbeatTimer = undefined;

  };



  const connect = () => {

    if (!active) return;

    clearTimers();

    setStatus(retryCount === 0 ? 'RECONNECTING' : 'RECONNECTING');



    try {

      socket = new WebSocket(wsUrl);



      socket.onopen = () => {

        if (!active) return;

        retryCount = 0;

        setStatus('CONNECTED');



        // Ping server every 20s to keep connection alive

        heartbeatTimer = setInterval(() => {

          if (socket && socket.readyState === WebSocket.OPEN) {

            socket.send(JSON.stringify({ type: 'ping', time: Date.now() }));

          }

        }, 20000);

      };



      socket.onmessage = (event) => {

        try {

          const parsed = JSON.parse(event.data);

          if (parsed.type === 'pong') return; // Heartbeat reply

          onMessage(parsed);

        } catch (e) {

          console.debug('WebSocket parse note:', e);

        }

      };



      socket.onclose = () => {

        if (!active) return;

        clearTimers();

        setStatus('RECONNECTING');

        // Reconnect with backoff

        const delay = Math.min(12000, 1000 * Math.pow(1.5, retryCount));

        retryCount++;

        reconnectTimer = setTimeout(connect, delay);

      };



      socket.onerror = () => {

        if (socket && socket.readyState === WebSocket.OPEN) {

          socket.close();

        }

      };

    } catch (err) {

      if (active) {

        setStatus('OFFLINE');

        reconnectTimer = setTimeout(connect, 3000);

      }

    }

  };



  // Reconnect when tab becomes active again

  const handleVisibilityChange = () => {

    if (!active) return;

    if (document.visibilityState === 'visible') {

      if (!socket || socket.readyState !== WebSocket.OPEN) {

        retryCount = 0;

        connect();

      }

    }

  };



  document.addEventListener('visibilitychange', handleVisibilityChange);

  window.addEventListener('focus', handleVisibilityChange);



  connect();



  return () => {

    active = false;

    clearTimers();

    document.removeEventListener('visibilitychange', handleVisibilityChange);

    window.removeEventListener('focus', handleVisibilityChange);

    if (socket) {

      socket.onopen = null;

      socket.onclose = null;

      socket.onerror = null;

      socket.onmessage = null;

      socket.close();

      socket = null;

    }

    setStatus('OFFLINE');

  };

}


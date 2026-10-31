import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { gateApi, venueApi } from '../services/api'
import type { Gate, Venue } from '../types'
import {
  Plus,
  Trash2,
  Play,
  Square,
  Wifi,
  ArrowLeft,
  DoorOpen,
  DoorClosed,
  Check,
  AlertCircle,
  Video,
  ExternalLink,
  Loader2,
  Sliders,
  FolderOpen,
  Film,
} from 'lucide-react'

export default function GateManagement() {
  const { venueId } = useParams<{ venueId: string }>()
  const [venue, setVenue] = useState<Venue | null>(null)
  const [gates, setGates] = useState<Gate[]>([])
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState('')
  const [testResult, setTestResult] = useState<{ id: string; success: boolean; message: string } | null>(null)
  const [gateToDelete, setGateToDelete] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionInProgress, setActionInProgress] = useState<string | null>(null)

  const refresh = async () => {
    if (!venueId) return
    try {
      const [v, g] = await Promise.all([venueApi.get(venueId), gateApi.list(venueId)])
      setVenue(v)
      setGates(g)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [venueId])

  const handleDelete = async (gateId: string) => {
    try {
      await gateApi.delete(gateId)
      setGateToDelete(null)
      refresh()
    } catch (e: any) {
      setError(e.message)
    }
  }

  const handleStart = async (gateId: string) => {
    setActionInProgress(gateId)
    try {
      await gateApi.start(gateId)
      refresh()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionInProgress(null)
    }
  }

  const handleStop = async (gateId: string) => {
    setActionInProgress(gateId)
    try {
      await gateApi.stop(gateId)
      refresh()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionInProgress(null)
    }
  }

  const handleTestConnection = async (gateId: string) => {
    setActionInProgress(gateId)
    setTestResult(null)
    try {
      const result = await gateApi.testConnection(gateId)
      setTestResult({
        id: gateId,
        success: result.success,
        message: result.message + (result.resolution ? ` (Resolution: ${result.resolution})` : ''),
      })
    } catch (e: any) {
      setTestResult({
        id: gateId,
        success: false,
        message: e.message || 'Connection test failed',
      })
    } finally {
      setActionInProgress(null)
    }
  }

  if (loading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center gap-3">
        <div className="w-8 h-8 border-3 border-slate-900 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-medium text-slate-500">Loading facility gates...</p>
      </div>
    )
  }

  const entryGates = gates.filter(g => g.gate_type === 'ENTRY')
  const exitGates = gates.filter(g => g.gate_type === 'EXIT')

  return (
    <div className="w-full max-w-full space-y-6">
      {/* Top Header */}
      <div>
        <Link
          to={`/venues/${venueId}/dashboard`}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-600 hover:text-blue-800 mb-3 transition-colors no-underline"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Live Dashboard</span>
        </Link>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-slate-900 leading-tight">
                Gate Installations
              </h1>
              <span className="text-xs px-2.5 py-0.5 rounded bg-slate-100 text-slate-700 font-medium border border-slate-200">
                {venue?.name}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Configure camera inputs, counting lines, and track individual gate in/out totals.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Link
              to={`/venues/${venueId}/dashboard`}
              className="btn-secondary text-xs py-2 px-3"
            >
              <ExternalLink className="w-3.5 h-3.5 text-slate-500" />
              <span>Live Dashboard</span>
            </Link>
            <button
              onClick={() => setShowForm(!showForm)}
              className="btn-primary text-xs py-2 px-3"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>{showForm ? 'Hide Form' : 'Add Gate'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Global Alerts */}
      {error && (
        <div className="p-3.5 rounded-lg bg-red-50 border border-red-200 text-red-800 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Connection Test Result Feedback */}
      {testResult && (
        <div className={`p-3.5 rounded-lg text-xs flex items-center justify-between gap-2 border ${
          testResult.success
            ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
            : 'bg-red-50 border-red-200 text-red-900'
        }`}>
          <div className="flex items-center gap-2">
            {testResult.success ? (
              <Check className="w-4 h-4 text-emerald-600 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            )}
            <span><strong>Connection Test:</strong> {testResult.message}</span>
          </div>
          <button
            onClick={() => setTestResult(null)}
            className="text-xs font-semibold hover:underline cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Add Gate Form Container */}
      {showForm && (
        <AddGateForm
          venueId={venueId!}
          onCreated={() => {
            setShowForm(false)
            refresh()
          }}
          onCancel={() => setShowForm(false)}
        />
      )}

      {/* Gate Directory Summary Bar */}
      <div className="grid grid-cols-3 gap-4">
        <div className="classic-card p-3.5 text-center">
          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">Total Gates</span>
          <span className="text-xl font-bold font-mono text-slate-900">{gates.length}</span>
        </div>
        <div className="classic-card p-3.5 text-center">
          <span className="text-[11px] font-semibold text-emerald-700 uppercase tracking-wider block">Entry Gates</span>
          <span className="text-xl font-bold font-mono text-emerald-700">{entryGates.length}</span>
        </div>
        <div className="classic-card p-3.5 text-center">
          <span className="text-[11px] font-semibold text-red-700 uppercase tracking-wider block">Exit Gates</span>
          <span className="text-xl font-bold font-mono text-red-700">{exitGates.length}</span>
        </div>
      </div>

      {/* Gates List */}
      {gates.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center shadow-xs">
          <Video className="w-10 h-10 text-slate-400 mx-auto mb-3" />
          <h2 className="text-base font-bold text-slate-900 mb-1">No Gates Registered</h2>
          <p className="text-xs text-slate-500 mb-4 max-w-sm mx-auto">
            Add at least one entry and one exit gate camera to enable automatic counting and crowd analysis.
          </p>
          <button
            onClick={() => setShowForm(true)}
            className="btn-primary text-xs py-2 px-4"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add First Gate</span>
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {gates.map((gate) => {
            const isEntry = gate.gate_type === 'ENTRY'
            const isBusy = actionInProgress === gate.id

            return (
              <div
                key={gate.id}
                className="classic-card p-4 flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                {/* Gate Left Info */}
                <div className="flex items-center gap-3.5">
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 border ${
                    isEntry ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-red-50 text-red-700 border-red-200'
                  }`}>
                    {isEntry ? <DoorOpen className="w-5 h-5" /> : <DoorClosed className="w-5 h-5" />}
                  </div>

                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-bold text-slate-900">{gate.display_name}</h3>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border uppercase tracking-wider ${
                        isEntry ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-red-50 text-red-800 border-red-200'
                      }`}>
                        {gate.gate_type}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-xs text-slate-500 font-mono mt-1 flex-wrap">
                      <span>Source: <strong className="text-slate-700 font-semibold">{gate.camera_source}</strong></span>
                      <span>•</span>
                      <span>Type: {gate.camera_source_type}</span>
                      <span>•</span>
                      <span className="flex items-center gap-1">
                        <span className={`w-2 h-2 rounded-full ${
                          gate.status === 'ACTIVE' ? 'bg-emerald-500' :
                          gate.status === 'CONNECTING' ? 'bg-amber-500' :
                          gate.status === 'ERROR' ? 'bg-red-500' : 'bg-slate-400'
                        }`} />
                        <span>{gate.status}</span>
                      </span>
                    </div>
                  </div>
                </div>

                {/* Gate Metrics & Controls */}
                <div className="flex items-center justify-between md:justify-end gap-5 border-t md:border-t-0 pt-3 md:pt-0 border-slate-100">
                  {/* Counts */}
                  <div className="text-right">
                    <span className="text-[10px] uppercase font-semibold text-slate-400 block tracking-wider">
                      Cumulative
                    </span>
                    <span className="text-sm font-mono font-bold text-slate-800">
                      <span className="text-emerald-700">{gate.entry_count} In</span>
                      <span className="text-slate-300 mx-1">/</span>
                      <span className="text-red-700">{gate.exit_count} Out</span>
                    </span>
                  </div>

                  {/* Actions (Available & Functional Only) */}
                  <div className="flex items-center gap-1.5">
                    {/* Test Connection Button */}
                    <button
                      onClick={() => handleTestConnection(gate.id)}
                      disabled={isBusy}
                      title="Test camera connection"
                      className="p-2 rounded-md bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 transition-colors cursor-pointer disabled:opacity-50"
                    >
                      {isBusy ? <Loader2 className="w-4 h-4 animate-spin text-slate-500" /> : <Wifi className="w-4 h-4" />}
                    </button>

                    {/* Start / Stop Button */}
                    {gate.status === 'ACTIVE' || gate.status === 'CONNECTING' ? (
                      <button
                        onClick={() => handleStop(gate.id)}
                        disabled={isBusy}
                        title="Stop camera processing"
                        className="px-2.5 py-1.5 rounded-md bg-red-50 border border-red-200 text-red-700 hover:bg-red-100 text-xs font-semibold flex items-center gap-1 transition-colors cursor-pointer disabled:opacity-50"
                      >
                        <Square className="w-3.5 h-3.5 fill-current" />
                        <span>Stop</span>
                      </button>
                    ) : (
                      <button
                        onClick={() => handleStart(gate.id)}
                        disabled={isBusy}
                        title="Start camera processing"
                        className="px-2.5 py-1.5 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-700 hover:bg-emerald-100 text-xs font-semibold flex items-center gap-1 transition-colors cursor-pointer disabled:opacity-50"
                      >
                        <Play className="w-3.5 h-3.5 fill-current" />
                        <span>Start</span>
                      </button>
                    )}

                    {/* Delete Gate Button */}
                    {gateToDelete === gate.id ? (
                      <div className="flex items-center gap-1 bg-red-50 p-1 rounded border border-red-200">
                        <span className="text-[11px] text-red-800 px-1 font-semibold">Delete?</span>
                        <button
                          onClick={() => handleDelete(gate.id)}
                          className="px-2 py-0.5 bg-red-600 text-white rounded text-xs font-bold hover:bg-red-700"
                        >
                          Yes
                        </button>
                        <button
                          onClick={() => setGateToDelete(null)}
                          className="px-2 py-0.5 bg-slate-200 text-slate-700 rounded text-xs hover:bg-slate-300"
                        >
                          No
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setGateToDelete(gate.id)}
                        title="Remove gate"
                        className="p-2 rounded-md bg-white border border-slate-300 hover:bg-red-50 hover:border-red-200 hover:text-red-700 text-slate-500 transition-colors cursor-pointer"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function AddGateForm({
  venueId,
  onCreated,
  onCancel,
}: {
  venueId: string
  onCreated: () => void
  onCancel: () => void
}) {
  const [form, setForm] = useState({
    display_name: '',
    gate_type: 'ENTRY',
    camera_source_type: 'WEBCAM',
    camera_source: '0',
    counting_direction: 'down',
    line_start_x: 0.05,
    line_start_y: 0.55,
    line_end_x: 0.95,
    line_end_y: 0.55,
    confidence_threshold: 0.25,
    frame_skip: 1,
  })
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [serverVideos, setServerVideos] = useState<any[]>([])
  const [loadingVideos, setLoadingVideos] = useState(false)
  const [showLibraryModal, setShowLibraryModal] = useState(false)

  const openLibraryModal = async () => {
    setShowLibraryModal(true)
    setLoadingVideos(true)
    try {
      const vids = await gateApi.listServerVideos()
      setServerVideos(vids || [])
    } catch (e) {
      console.error('Failed to load server videos', e)
    } finally {
      setLoadingVideos(false)
    }
  }
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await gateApi.create(venueId, form)
      onCreated()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs space-y-4">
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
          Configure New Gate Camera
        </h3>
        <button
          type="button"
          onClick={onCancel}
          className="text-xs text-slate-500 hover:text-slate-800"
        >
          Cancel
        </button>
      </div>

      {error && <p className="text-red-600 text-xs font-semibold">{error}</p>}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">
            Gate Display Name <span className="text-red-500">*</span>
          </label>
          <input
            required
            type="text"
            value={form.display_name}
            onChange={e => setForm({ ...form, display_name: e.target.value })}
            placeholder="e.g. West Main Gate"
            className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">
            Gate Function <span className="text-red-500">*</span>
          </label>
          <select
            value={form.gate_type}
            onChange={e => setForm({ ...form, gate_type: e.target.value })}
            className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
          >
            <option value="ENTRY">ENTRY (Increments Occupancy)</option>
            <option value="EXIT">EXIT (Decrements Occupancy)</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">
            Camera Type
          </label>
          <select
            value={form.camera_source_type}
            onChange={e => setForm({ ...form, camera_source_type: e.target.value })}
            className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
          >
            <option value="WEBCAM">Local Webcam (0, 1)</option>
            <option value="RTSP">RTSP Camera Stream</option>
            <option value="HTTP">HTTP Video Stream</option>
            <option value="VIDEO_FILE">Pre-recorded Video File</option>
          </select>
        </div>

        <div className="md:col-span-2">
          <label className="block text-xs font-semibold text-slate-700 mb-1">
            Source URL, Device Index, or Local Video File <span className="text-red-500">*</span>
          </label>
          <div className="flex gap-2">
            <input
              required
              type="text"
              value={form.camera_source}
              onChange={e => setForm({ ...form, camera_source: e.target.value.replace(/^["']|["']$/g, '') })}
              placeholder="0, 1, C:\path\video.mp4, or rtsp://..."
              className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
            />
            <input
              ref={fileInputRef}
              type="file"
              accept="video/*,.mp4,.avi,.mov,.mkv,.webm"
              style={{ display: 'none' }}
              disabled={uploading}
              onChange={async (e) => {
                const file = e.target.files?.[0]
                if (!file) return
                setUploading(true)
                setUploadProgress(0)
                try {
                  const res = await gateApi.uploadVideo(file, setUploadProgress)
                  setForm({ ...form, camera_source: res.file_path, camera_source_type: 'VIDEO_FILE' })
                } catch (err: any) {
                  setError(err.message || 'Failed to upload video')
                } finally {
                  setUploading(false)
                  setUploadProgress(0)
                  e.target.value = ''
                }
              }}
            />
            <button
              type="button"
              onClick={openLibraryModal}
              disabled={uploading}
              className="flex items-center gap-1.5 px-2.5 py-2 rounded-lg border border-indigo-200 bg-indigo-50/70 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold cursor-pointer shrink-0 transition select-none disabled:opacity-60"
              title="Select video already on server (Instant 0s)"
            >
              <Film className="w-3.5 h-3.5 text-indigo-600" />
              <span className="hidden sm:inline">Library</span>
            </button>

            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-semibold cursor-pointer shrink-0 transition select-none disabled:opacity-60"
              title="Browse video file (Chunked + Auto-dedup)"
            >
              {uploading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-600" />
              ) : (
                <FolderOpen className="w-3.5 h-3.5 text-slate-600" />
              )}
              <span className="hidden sm:inline">
                {uploadProgress && uploadProgress > 0 && uploadProgress < 100
                  ? `${uploadProgress}%`
                  : uploadProgress === 100
                  ? 'Ready!'
                  : 'Browse'}
              </span>
            </button>
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">
            Crossing Direction
          </label>
          <select
            value={form.counting_direction}
            onChange={e => setForm({ ...form, counting_direction: e.target.value })}
            className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
          >
            <option value="down">Downward (Top → Bottom = IN)</option>
            <option value="up">Upward (Bottom → Top = IN)</option>
            <option value="right">Rightward (Left → Right = IN)</option>
            <option value="left">Leftward (Right → Left = IN)</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">
            Detection Confidence Threshold
          </label>
          <input
            type="number"
            step="0.05"
            min="0.1"
            max="1.0"
            value={form.confidence_threshold}
            onChange={e => setForm({ ...form, confidence_threshold: parseFloat(e.target.value) })}
            className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
          />
        </div>
      </div>

      <div className="pt-2 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="btn-secondary text-xs py-2 px-3"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving}
          className="btn-primary text-xs py-2 px-4"
        >
          {saving ? 'Registering Gate...' : 'Save & Register Gate'}
        </button>
      </div>

      {/* Server Video Library Modal */}
      {showLibraryModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full shadow-2xl border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600">
                  <Film className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Server Video Library</h3>
                  <p className="text-xs text-slate-500">Pick any video already on server — 0ms instant loading</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowLibraryModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg hover:bg-slate-100 transition cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="p-5 max-h-80 overflow-y-auto space-y-2">
              {loadingVideos ? (
                <div className="flex items-center justify-center py-8 text-slate-400 gap-2 text-xs">
                  <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
                  Scanning server media_uploads...
                </div>
              ) : serverVideos.length === 0 ? (
                <div className="text-center py-8 text-slate-500 text-xs">
                  No video files found on server. Click <strong>Browse</strong> to upload.
                </div>
              ) : (
                serverVideos.map((v) => (
                  <div
                    key={v.file_path}
                    className="flex items-center justify-between p-3 rounded-xl border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/40 transition gap-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-semibold text-slate-800 truncate" title={v.display_name}>
                        {v.display_name}
                      </div>
                      <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                        {v.size_mb} MB · {v.filename.substring(0, 8)}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setForm({ ...form, camera_source: v.file_path, camera_source_type: 'VIDEO_FILE' })
                        setShowLibraryModal(false)
                      }}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shrink-0 cursor-pointer transition shadow-xs"
                    >
                      Select (0s)
                    </button>
                  </div>
                ))
              )}
            </div>

            <div className="p-4 bg-slate-50 border-t border-slate-100 flex justify-between items-center text-xs text-slate-500">
              <span>Files in <code className="font-mono text-[11px] bg-slate-200 px-1 py-0.5 rounded">backend/media_uploads</code></span>
              <button
                type="button"
                onClick={() => setShowLibraryModal(false)}
                className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 font-medium cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </form>
  )
}

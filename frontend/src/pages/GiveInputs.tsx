import { useState, useEffect, useRef } from 'react'



import { useNavigate, Link } from 'react-router-dom'



import {



  AlertCircle,



  Building2,



  CheckCircle2,



  DoorClosed,



  DoorOpen,



  Map,



  Plus,



  RefreshCw,



  Trash2,



  Users,



  Video,



  Loader2,



  ArrowRight,



  Sparkles,



  FolderOpen,



  FileVideo,



  Film,



  Server,
} from 'lucide-react'
import ServerConfigModal from '../components/ServerConfigModal'



import { venueApi, monitorApi, gateApi } from '../services/api'







function isValidSource(value: string) {



  const source = value.trim().replace(/^["']|["']$/g, '')



  if (!source) return false



  // Webcam index (e.g. 0, 1, 2)



  if (/^\d+$/.test(source)) return true



  // YouTube link



  if (/^https?:\/\/(www\.)?(youtube\.com|youtu\.be)\/.+$/i.test(source)) return true



  // RTSP, RTMP, HTTP, HTTPS streams



  if (/^(rtsp|rtmp|https?):\/\/\S+$/i.test(source)) return true



  // Common video files (local paths or bare filenames)



  if (/\.(mp4|avi|mov|mkv|webm|m4v)$/i.test(source)) return true



  return false



}







export default function GiveInputs() {



  const navigate = useNavigate()



  const [venueName, setVenueName] = useState('')



  const [entryStreams, setEntryStreams] = useState<string[]>(['', ''])



  const [exitStreams, setExitStreams] = useState<string[]>(['', ''])



  const [area, setArea] = useState('')



  const [capacity, setCapacity] = useState('')



  const [submitted, setSubmitted] = useState(false)



  const [saving, setSaving] = useState(false)



  const [error, setError] = useState('')



  const [uploadError, setUploadError] = useState<string | null>(null)



  const [uploadingRow, setUploadingRow] = useState<string | null>(null)



  const [uploadProgress, setUploadProgress] = useState<number>(0)



  const [backendOnline, setBackendOnline] = useState<boolean | null>(null)



  const [checkingBackend, setCheckingBackend] = useState(false)



  const [serverVideos, setServerVideos] = useState<any[]>([])



  const [loadingVideos, setLoadingVideos] = useState(false)



  const [isServerModalOpen, setIsServerModalOpen] = useState(false)
  const [showLibraryModal, setShowLibraryModal] = useState<{ type: 'entry' | 'exit'; index: number } | null>(null)







  const openLibraryModal = async (type: 'entry' | 'exit', index: number) => {



    setShowLibraryModal({ type, index })



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







  // Verify backend status on mount



  const checkBackendHealth = async () => {



    setCheckingBackend(true)



    try {



      const res = await monitorApi.health()



      if (res && (res.status === 'healthy' || res.status === 'ok')) {



        setBackendOnline(true)



      } else {



        setBackendOnline(false)



      }



    } catch {



      setBackendOnline(false)



    } finally {



      setCheckingBackend(false)



    }



  }







  useEffect(() => {



    checkBackendHealth()



  }, [])







  const areaNumber = Number(area)



  const capacityNumber = Number(capacity)







  const cleanSource = (s: string) => s.trim().replace(/^["']|["']$/g, '')







  const validEntries = entryStreams.filter((s) => isValidSource(s))



  const validExits = exitStreams.filter((s) => isValidSource(s))



  const invalidSources = [...entryStreams, ...exitStreams].some(



    (s) => s.trim() && !isValidSource(s)



  )







  const areaInvalid = !area || !Number.isFinite(areaNumber) || areaNumber <= 0



  const capacityInvalid = !!capacity && (!Number.isInteger(capacityNumber) || capacityNumber <= 0)



  const canSubmit =



    !areaInvalid &&



    !capacityInvalid &&



    !invalidSources &&



    validEntries.length > 0 &&



    validExits.length > 0







  const updateStream = (type: 'entry' | 'exit', index: number, value: string) => {



    const cleaned = value.replace(/^["']|["']$/g, '')



    const update = type === 'entry' ? setEntryStreams : setExitStreams



    update((current) => current.map((s, i) => (i === index ? cleaned : s)))



  }







  const removeStream = (type: 'entry' | 'exit', index: number) => {



    const update = type === 'entry' ? setEntryStreams : setExitStreams



    update((current) => (current.length === 1 ? [''] : current.filter((_, i) => i !== index)))



  }







  const handleFileUpload = async (type: 'entry' | 'exit', index: number, file: File) => {



    const rowKey = `${type}-${index}`



    setUploadingRow(rowKey)



    setUploadProgress(0)



    setUploadError(null)







    try {



      const res = await gateApi.uploadVideo(file, (percent) => {



        setUploadProgress(percent)



      })



      updateStream(type, index, res.file_path)



    } catch (e: any) {



      setUploadError(e.message || 'Failed to upload video file')



    } finally {



      setUploadingRow(null)



      setUploadProgress(0)



    }



  }







  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {



    event.preventDefault()



    setSubmitted(true)



    if (!canSubmit || saving) return







    setSaving(true)



    setError('')



    try {



      const result = await venueApi.quickSetup({



        name: venueName.trim() || 'AI Crowd Intelligence Zone',



        area_sqm: areaNumber,



        max_capacity: capacity ? capacityNumber : Math.round(areaNumber * 2),



        entry_streams: validEntries.map((s) => cleanSource(s)),



        exit_streams: validExits.map((s) => cleanSource(s)),



      })







      if (!result?.venue_id) {



        throw new Error('The server did not return a valid facility ID.')



      }



      localStorage.setItem('activeVenueId', result.venue_id)



      navigate(`/venues/${result.venue_id}/dashboard`)



    } catch (reason: any) {



      const msg = reason instanceof Error ? reason.message : 'Could not start crowd monitoring.'



      setError(msg)



      setSaving(false)



    }



  }







  return (



    <div className="w-full max-w-[1440px] mx-auto space-y-6 pb-12">



      {/* Page Title & Status Banner */}



      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">



        <div>



          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">



            Setup Monitoring Streams



          </h1>



          <p className="mt-1 text-sm text-slate-500">



            Configure camera sources (webcam, local video file, or stream) and facility capacity.



          </p>



        </div>







        {/* Engine status indicator */}



        <div className="flex items-center gap-2 self-start sm:self-auto px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-700 shadow-2xs">



          <Sparkles className="w-4 h-4 text-blue-600 shrink-0" />



          <span>YOLOv11 Person Tracking Engine</span>



          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 ml-1" />



        </div>



      </div>







      {/* Backend Offline / Bad Gateway Alert */}



      {backendOnline === false && (



        <div



          role="alert"



          className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900 shadow-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"



        >



          <div className="flex items-start gap-3">



            <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />



            <div className="text-sm">



              <span className="font-semibold text-amber-900">Backend Server Offline (Port 8000)</span>



              <p className="mt-0.5 text-xs text-amber-800">



                The Python API service is not reachable on port 8000. Start it by running{' '}



                <code className="bg-amber-100 px-1 py-0.5 rounded text-amber-950 font-mono">run.bat</code>{' '}



                or in a terminal:{' '}



                <code className="bg-amber-100 px-1 py-0.5 rounded text-amber-950 font-mono">



                  python -m uvicorn app.main:app --port 8000 --reload



                </code>



              </p>



            </div>



          </div>



          <button



            type="button"



            onClick={checkBackendHealth}



            disabled={checkingBackend}



            className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-white border border-amber-300 text-xs font-semibold text-amber-900 hover:bg-amber-100 transition disabled:opacity-50"



          >



            <RefreshCw className={`w-3.5 h-3.5 ${checkingBackend ? 'animate-spin' : ''}`} />



            {checkingBackend ? 'Checking...' : 'Check Connection'}



          </button>



        </div>



      )}







      {/* Upload Error Alert */}



      {uploadError && (



        <div



          role="alert"



          className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900 shadow-xs"



        >



          <AlertCircle className="w-5 h-5 shrink-0 text-red-600 mt-0.5" />



          <div className="flex-1">



            <div className="font-semibold text-red-800">Video Upload Error</div>



            <div className="text-xs text-red-700 mt-0.5">{uploadError}</div>



          </div>



          <button



            type="button"



            onClick={() => setUploadError(null)}



            className="text-xs font-semibold text-red-800 hover:text-red-950"



          >



            Dismiss



          </button>



        </div>



      )}







      {/* General Form Error Alert */}



      {error && (



        <div



          role="alert"



          className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900 shadow-xs"



        >



          <AlertCircle className="w-5 h-5 shrink-0 text-red-600 mt-0.5" />



          <div className="flex-1">



            <div className="font-semibold text-red-800">Setup Error</div>



            <div className="text-xs text-red-700 mt-0.5">{error}</div>



          </div>



        </div>



      )}







      {/* Active Facility Notification Banner */}



      {typeof window !== 'undefined' && localStorage.getItem('activeVenueId') && (



        <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 bg-blue-50/90 border border-blue-200 rounded-xl text-xs text-blue-900 shadow-2xs">



          <div className="flex items-center gap-2">



            <CheckCircle2 className="w-4 h-4 text-blue-600 shrink-0" />



            <span>You have an active crowd monitoring facility in progress. You can return directly to your live stream or configure a new facility below.</span>



          </div>



          <Link



            to={`/venues/${localStorage.getItem('activeVenueId')}/dashboard`}



            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 transition shrink-0 no-underline shadow-xs"



          >



            <span>Return to Live Dashboard</span>



            <ArrowRight className="w-3.5 h-3.5" />



          </Link>



        </div>



      )}







      {/* Main Setup Form */}



      <form id="setup-monitoring-form" onSubmit={handleSubmit} noValidate className="space-y-6">



        {/* 1. Facility Parameters Card */}



        <section className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs">



          <div className="flex items-center gap-2.5 pb-4 border-b border-slate-100">



            <Building2 className="w-5 h-5 text-blue-600" />



            <h2 className="text-base font-bold text-slate-900">1. Facility Parameters</h2>



          </div>







          <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-5">



            {/* Facility Name */}



            <div>



              <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1.5">



                Facility / Venue Name <span className="text-slate-400 font-normal lowercase">(optional)</span>



              </label>



              <div className="flex h-10 w-full items-center rounded-lg border border-slate-300 bg-white overflow-hidden focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 transition-all">



                <span className="flex h-full w-10 shrink-0 items-center justify-center border-r border-slate-200 bg-slate-50 text-slate-500">



                  <Building2 className="w-4 h-4" />



                </span>



                <input



                  type="text"



                  value={venueName}



                  onChange={(e) => setVenueName(e.target.value)}



                  placeholder="e.g. Main Facility / Terminal 1"



                  className="w-full bg-transparent px-3 text-sm text-slate-900 outline-none placeholder:text-slate-400"



                />



              </div>



              <p className="mt-1 text-[11px] text-slate-400">Descriptive name for reports &amp; logs.</p>



            </div>







            {/* Usable Area */}



            <div>



              <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1.5">



                Usable Area (m²) <span className="text-red-500">*</span>



              </label>



              <div



                className={`flex h-10 w-full items-center rounded-lg border bg-white overflow-hidden transition-all focus-within:ring-2 ${



                  submitted && areaInvalid



                    ? 'border-red-400 focus-within:border-red-500 focus-within:ring-red-100'



                    : 'border-slate-300 focus-within:border-blue-500 focus-within:ring-blue-100'



                }`}



              >



                <span className="flex h-full w-10 shrink-0 items-center justify-center border-r border-slate-200 bg-slate-50 text-slate-500">



                  <Map className="w-4 h-4" />



                </span>



                <input



                  type="number"



                  min="0.1"



                  step="any"



                  value={area}



                  onChange={(e) => setArea(e.target.value)}



                  placeholder="e.g. 500"



                  className="w-full bg-transparent px-3 text-sm text-slate-900 outline-none placeholder:text-slate-400"



                />



                <span className="flex h-full px-2.5 items-center justify-center border-l border-slate-200 bg-slate-50 text-xs font-mono text-slate-500 select-none">



                  m²



                </span>



              </div>



              {submitted && areaInvalid ? (



                <p className="mt-1 text-xs text-red-600 font-medium">Enter a usable area greater than 0.</p>



              ) : (



                <p className="mt-1 text-[11px] text-slate-400">Total operational footprint.</p>



              )}



            </div>







            {/* Max Capacity */}



            <div>



              <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1.5">



                Max Capacity <span className="text-slate-400 font-normal lowercase">(optional)</span>



              </label>



              <div



                className={`flex h-10 w-full items-center rounded-lg border bg-white overflow-hidden transition-all focus-within:ring-2 ${



                  submitted && capacityInvalid



                    ? 'border-red-400 focus-within:border-red-500 focus-within:ring-red-100'



                    : 'border-slate-300 focus-within:border-blue-500 focus-within:ring-blue-100'



                }`}



              >



                <span className="flex h-full w-10 shrink-0 items-center justify-center border-r border-slate-200 bg-slate-50 text-slate-500">



                  <Users className="w-4 h-4" />



                </span>



                <input



                  type="number"



                  min="1"



                  step="1"



                  value={capacity}



                  onChange={(e) => setCapacity(e.target.value)}



                  placeholder={areaNumber > 0 ? String(Math.round(areaNumber * 2)) : 'e.g. 1000'}



                  className="w-full bg-transparent px-3 text-sm text-slate-900 outline-none placeholder:text-slate-400"



                />



                <span className="flex h-full px-2.5 items-center justify-center border-l border-slate-200 bg-slate-50 text-xs font-mono text-slate-500 select-none">



                  persons



                </span>



              </div>



              {submitted && capacityInvalid ? (



                <p className="mt-1 text-xs text-red-600 font-medium">Capacity must be a positive whole number.</p>



              ) : (



                <p className="mt-1 text-[11px] text-slate-400">



                  Safety threshold guidelines recommend 2.0 persons per m² when left blank.



                </p>



              )}



            </div>



          </div>



        </section>







        {/* 2 & 3. Two Side-by-Side Camera Source Cards */}



        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">



          {/* Entry Gate Video Sources */}



          <CameraPanel



            title="Entry Gate Video Sources"



            badgeNumber="2"



            type="entry"



            subtitle="Used to detect and count people entering the facility."



            accentColor="emerald"



            streams={entryStreams}



            validCount={validEntries.length}



            submitted={submitted}



            uploadingRow={uploadingRow}



            uploadProgress={uploadProgress}



            onAdd={() => setEntryStreams((c) => [...c, ''])}



            onChange={updateStream}



            onRemove={removeStream}



            onUpload={handleFileUpload}



            onOpenLibrary={openLibraryModal}



          />







          {/* Exit Gate Video Sources */}



          <CameraPanel



            title="Exit Gate Video Sources"



            badgeNumber="3"



            type="exit"



            subtitle="Used to detect and count people exiting the facility."



            accentColor="rose"



            streams={exitStreams}



            validCount={validExits.length}



            submitted={submitted}



            uploadingRow={uploadingRow}



            uploadProgress={uploadProgress}



            onAdd={() => setExitStreams((c) => [...c, ''])}



            onChange={updateStream}



            onRemove={removeStream}



            onUpload={handleFileUpload}



            onOpenLibrary={openLibraryModal}



          />



        </div>







        {/* Bottom Action Area */}



        <div className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs flex flex-col md:flex-row items-center justify-between gap-4">



          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">



            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-100 border border-slate-200 font-medium text-slate-700">



              <DoorOpen className="w-3.5 h-3.5 text-emerald-600" />



              {validEntries.length} Entry {validEntries.length === 1 ? 'Gate' : 'Gates'}



            </span>



            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-100 border border-slate-200 font-medium text-slate-700">



              <DoorClosed className="w-3.5 h-3.5 text-rose-600" />



              {validExits.length} Exit {validExits.length === 1 ? 'Gate' : 'Gates'}



            </span>



            {areaNumber > 0 && (



              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-slate-100 border border-slate-200 font-medium text-slate-700">



                {areaNumber} m² · Cap: {capacity ? capacityNumber : Math.round(areaNumber * 2)}



              </span>



            )}



          </div>







          <div className="w-full md:w-auto flex justify-end">



            <button



              type="submit"



              disabled={saving}



              className="w-full md:w-auto min-w-[240px] h-11 px-8 rounded-lg bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-semibold text-sm shadow-xs flex items-center justify-center gap-2 transition-all disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"



            >



              {saving ? (



                <>



                  <Loader2 className="w-4 h-4 animate-spin" />



                  <span>Initializing Monitoring Streams...</span>



                </>



              ) : (



                <>



                  <span>Initialize Monitoring</span>



                  <ArrowRight className="w-4 h-4" />



                </>



              )}



            </button>



          </div>



        </div>



      </form>







      {/* Server Video Library Modal (Instant 0s Selection) */}



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



                onClick={() => setShowLibraryModal(null)}



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



                  No video files in server library yet. Click <strong>Browse</strong> to upload.



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



                        updateStream(showLibraryModal.type, showLibraryModal.index, v.file_path)



                        setShowLibraryModal(null)



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



                onClick={() => setShowLibraryModal(null)}



                className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 font-medium cursor-pointer"



              >



                Close



              </button>



            </div>



          </div>



        </div>



      )}



    </div>



  )



}







interface CameraPanelProps {



  title: string



  badgeNumber: string



  type: 'entry' | 'exit'



  subtitle: string



  accentColor: 'emerald' | 'rose'



  streams: string[]



  validCount: number



  submitted: boolean



  uploadingRow: string | null



  uploadProgress: number



  onAdd: () => void



  onChange: (type: 'entry' | 'exit', index: number, value: string) => void



  onRemove: (type: 'entry' | 'exit', index: number) => void



  onUpload: (type: 'entry' | 'exit', index: number, file: File) => void



  onOpenLibrary: (type: 'entry' | 'exit', index: number) => void



}







function CameraPanel({



  title,



  badgeNumber,



  type,



  subtitle,



  accentColor,



  streams,



  validCount,



  submitted,



  uploadingRow,



  uploadProgress,



  onAdd,



  onChange,



  onRemove,



  onUpload,



  onOpenLibrary,



}: CameraPanelProps) {



  const isEntry = type === 'entry'



  const singular = isEntry ? 'Entry' : 'Exit'



  const hasNoValid = submitted && validCount === 0







  return (



    <section className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs flex flex-col justify-between">



      <div>



        {/* Header with dot and count badge */}



        <div className="flex items-start justify-between gap-3 pb-3 border-b border-slate-100">



          <div className="flex items-start gap-2.5">



            <span



              className={`w-2.5 h-2.5 rounded-full mt-1.5 shrink-0 ${



                isEntry ? 'bg-emerald-500 ring-4 ring-emerald-50' : 'bg-rose-500 ring-4 ring-rose-50'



              }`}



            />



            <div>



              <h2 className="text-base font-bold text-slate-900">



                {badgeNumber}. {title} <span className="text-red-500">*</span>



              </h2>



              <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>



            </div>



          </div>







          <span



            className={`shrink-0 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${



              validCount > 0



                ? isEntry



                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'



                  : 'bg-rose-50 text-rose-700 border-rose-200'



                : 'bg-slate-100 text-slate-500 border-slate-200'



            }`}



          >



            {validCount} valid configured



          </span>



        </div>







        <p className="text-xs text-slate-500 mt-3 mb-2">



          Click <strong>Browse</strong> to select a video file (.mp4, .avi, .mov), or paste a local path / stream URL.



        </p>







        {/* Input rows */}



        <div className="space-y-3">



          {streams.map((source, index) => (



            <StreamInputRow



              key={`${type}-${index}`}



              type={type}



              index={index}



              source={source}



              submitted={submitted}



              isUploading={uploadingRow === `${type}-${index}`}



              uploadProgress={uploadProgress}



              onChange={onChange}



              onRemove={onRemove}



              onUploadFile={onUpload}



              onOpenLibrary={onOpenLibrary}



            />



          ))}



        </div>







        {hasNoValid && (



          <p className="mt-2 text-xs text-red-600 font-medium">



            At least one valid {singular.toLowerCase()} video stream is required.



          </p>



        )}



      </div>







      {/* Add stream button */}



      <div className="mt-4 pt-3 border-t border-slate-100">



        <button



          type="button"



          onClick={onAdd}



          className="w-full flex h-9 items-center justify-center gap-1.5 rounded-lg border border-dashed border-slate-300 hover:border-blue-500 hover:bg-blue-50/50 text-xs font-semibold text-slate-700 hover:text-blue-600 transition cursor-pointer"



        >



          <Plus className="w-3.5 h-3.5" />



          <span>Add Additional {singular} Gate Source</span>



        </button>



      </div>



    </section>



  )



}







function StreamInputRow({



  type,



  index,



  source,



  submitted,



  isUploading,



  uploadProgress,



  onChange,



  onRemove,



  onUploadFile,



  onOpenLibrary,



}: {



  type: 'entry' | 'exit'



  index: number



  source: string



  submitted: boolean



  isUploading: boolean



  uploadProgress?: number



  onChange: (type: 'entry' | 'exit', index: number, value: string) => void



  onRemove: (type: 'entry' | 'exit', index: number) => void



  onUploadFile: (type: 'entry' | 'exit', index: number, file: File) => void



  onOpenLibrary: (type: 'entry' | 'exit', index: number) => void



}) {



  const fileInputRef = useRef<HTMLInputElement>(null)



  const [isDragging, setIsDragging] = useState(false)



  const isEntry = type === 'entry'



  const singular = isEntry ? 'Entry' : 'Exit'



  const hasText = !!source.trim()



  const isRowValid = isValidSource(source)



  const isRowInvalid = submitted && hasText && !isRowValid



  const isLocalFile = /\.(mp4|avi|mov|mkv|webm|m4v)$/i.test(source.trim())







  return (



    <div className="group">



      <div className="flex items-center gap-2">



        <span className="w-16 shrink-0 text-[11px] font-mono font-bold uppercase tracking-wider text-slate-500">



          {isEntry ? 'ENTRY' : 'EXIT'} {index + 1}



        </span>







        {/* Hidden native input element, triggered safely via ref */}



        <input



          ref={fileInputRef}



          type="file"



          accept="video/*,.mp4,.avi,.mov,.mkv,.webm,.m4v"



          style={{ display: 'none' }}



          onChange={(e) => {



            const file = e.target.files?.[0]



            if (file) {



              onUploadFile(type, index, file)



            }



            e.target.value = ''



          }}



        />







        {/* Input box with Drag & Drop */}



        <div



          onDragOver={(e) => {



            e.preventDefault()



            e.stopPropagation()



            setIsDragging(true)



          }}



          onDragLeave={(e) => {



            e.preventDefault()



            e.stopPropagation()



            setIsDragging(false)



          }}



          onDrop={(e) => {



            e.preventDefault()



            e.stopPropagation()



            setIsDragging(false)



            const file = e.dataTransfer.files?.[0]



            if (file) {



              onUploadFile(type, index, file)



            }



          }}



          className={`flex h-10 min-w-0 flex-1 items-center rounded-lg border bg-white overflow-hidden transition-all focus-within:ring-2 ${



            isDragging



              ? 'border-blue-500 ring-2 ring-blue-100 bg-blue-50/40'



              : isRowInvalid



              ? 'border-red-400 focus-within:border-red-500 focus-within:ring-red-100'



              : isRowValid



              ? 'border-slate-300 focus-within:border-blue-500 focus-within:ring-blue-100'



              : 'border-slate-300 focus-within:border-blue-500 focus-within:ring-blue-100'



          }`}



        >



          <span className="flex h-full w-10 shrink-0 items-center justify-center border-r border-slate-200 bg-slate-50 text-slate-500">



            {isLocalFile ? (



              <FileVideo className="w-4 h-4 text-blue-600" />



            ) : (



              <Video className="w-4 h-4" />



            )}



          </span>



          <input



            type="text"



            value={source}



            onChange={(e) => onChange(type, index, e.target.value)}



            placeholder={



              isEntry



                ? 'Click Browse, drag video here, or paste path'



                : 'Click Browse, drag video here, or paste path'



            }



            className="w-full min-w-0 bg-transparent px-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 font-mono text-xs"



          />



          {isRowValid && (



            <span className="pr-2.5 text-emerald-600 shrink-0" title="Valid video format">



              <CheckCircle2 className="w-4 h-4" />



            </span>



          )}



        </div>







        {/* Direct Local File Link (0s Instant Connection, Skips Upload Completely) */}

        <button

          type="button"

          onClick={async () => {

            try {

              const res = await gateApi.pickLocalFile()

              if (res && res.file_path) {

                onChange(type, index, res.file_path)

              }

            } catch (err: any) {

              console.warn('Native picker error:', err)

              fileInputRef.current?.click()

            }

          }}

          disabled={isUploading}

          className="flex h-10 px-2.5 items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50/70 hover:bg-emerald-100 active:bg-emerald-200 text-emerald-800 text-xs font-semibold cursor-pointer shrink-0 transition select-none disabled:opacity-60"

          title="Direct Local File Link (0s instant connection, skips upload completely!)"

        >

          <Sparkles className="w-3.5 h-3.5 text-emerald-600" />

          <span className="hidden sm:inline font-bold">Direct File</span>

        </button>



        {/* Server Library Fast Picker (0ms) */}



        <button



          type="button"



          onClick={() => onOpenLibrary(type, index)}



          disabled={isUploading}



          className="flex h-10 px-2.5 items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50/60 hover:bg-indigo-100 active:bg-indigo-200 text-indigo-700 text-xs font-semibold cursor-pointer shrink-0 transition select-none disabled:opacity-60"



          title="Select video already on server (0-second instant loading)"



        >



          <Film className="w-3.5 h-3.5 text-indigo-600" />



          <span className="hidden xl:inline">Library</span>



        </button>







        {/* Real Button to open File Picker (Chunked + Auto-dedup) */}



        <button



          type="button"



          onClick={() => fileInputRef.current?.click()}



          disabled={isUploading}



          className="flex h-10 px-3 items-center gap-1.5 rounded-lg border border-slate-300 bg-slate-50 hover:bg-slate-100 active:bg-slate-200 text-slate-700 text-xs font-semibold cursor-pointer shrink-0 transition select-none disabled:opacity-60"



          title="Browse video file (Auto-deduplicated & chunked for Cloudflare speed)"



        >



          {isUploading ? (



            <>



              <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-600" />



              <span className="text-blue-600 font-medium">



                {uploadProgress && uploadProgress > 0 && uploadProgress < 100



                  ? `${uploadProgress}%`



                  : uploadProgress === 100



                  ? 'Ready!'



                  : 'Uploading...'}



              </span>



            </>



          ) : (



            <>



              <FolderOpen className="w-3.5 h-3.5 text-slate-600" />



              <span className="hidden sm:inline">Browse</span>



            </>



          )}



        </button>







        {/* Delete Row Button */}



        <button



          type="button"



          onClick={() => onRemove(type, index)}



          title={`Remove ${singular} source ${index + 1}`}



          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-400 hover:text-red-600 hover:border-red-200 hover:bg-red-50 transition cursor-pointer"



        >



          <Trash2 className="w-4 h-4" />



        </button>



      </div>







      {isLocalFile && (



        <p className="mt-1 ml-18 text-[11px] text-blue-600 font-mono flex items-center gap-1">



          <FileVideo className="w-3 h-3" />



          Local video file configured (loops continuously)



        </p>



      )}







      {isRowInvalid && (



        <p className="mt-1 ml-18 text-xs text-red-600 font-medium">



          Please provide a valid webcam index (e.g. 0), local video file path, or stream URL.



        </p>



      )}



    </div>



  )



}




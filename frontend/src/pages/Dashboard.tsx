import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Calendar,
  CheckCircle2,
  Clock,
  DoorClosed,
  DoorOpen,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Trash2,
  Users,
  VideoOff,
  X,
} from 'lucide-react'
import { connectWebSocket, gateApi, monitorApi, venueApi } from '../services/api'
import { useVideoStreams } from '../services/useVideoStream'
import type { Alert, DashboardState, Gate, Venue } from '../types'

export default function Dashboard() {
  const { venueId: routeVenueId } = useParams<{ venueId?: string }>()
  const navigate = useNavigate()
  const savedVenueId = typeof window !== 'undefined' ? localStorage.getItem('activeVenueId') : null
  const [venueId, setVenueId] = useState<string | null>(routeVenueId || savedVenueId || null)
  const [venue, setVenue] = useState<Venue | null>(null)
  const [venues, setVenues] = useState<Venue[]>([])
  const [gates, setGates] = useState<Gate[]>([])
  const [state, setState] = useState<DashboardState | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [streamErrors, setStreamErrors] = useState<Record<string, boolean>>({})
  const [actionPending, setActionPending] = useState<string | null>(null)
  const [processPending, setProcessPending] = useState(false)
  const [fullscreenGate, setFullscreenGate] = useState<Gate | null>(null)
  const [gridMode, setGridMode] = useState<'large' | 'compact'>('large')

  // High-performance multiplexed video streams over a single WebSocket connection
  const liveFrames = useVideoStreams(venueId)

  // Keep fullscreenGate synchronized with latest live data
  useEffect(() => {
    if (fullscreenGate) {
      const updated = gates.find((g) => g.id === fullscreenGate.id)
      if (updated) {
        setFullscreenGate(updated)
      }
    }
  }, [gates])

  const handleUpdateLineConfig = async (
    gateId: string,
    lineY: number,
    direction: string,
    resetPassback = false
  ) => {
    try {
      await gateApi.updateLineConfig(gateId, {
        start_y: lineY,
        end_y: lineY,
        counting_direction: direction,
        reset_anti_passback: resetPassback,
      })
      setGates((current) =>
        current.map((g) =>
          g.id === gateId
            ? {
                ...g,
                line_start_y: lineY,
                line_end_y: lineY,
                counting_direction: direction,
              }
            : g
        )
      )
      if (fullscreenGate && fullscreenGate.id === gateId) {
        setFullscreenGate((prev) =>
          prev
            ? {
                ...prev,
                line_start_y: lineY,
                line_end_y: lineY,
                counting_direction: direction,
              }
            : null
        )
      }
    } catch (err) {
      console.error('Failed to update line configuration:', err)
    }
  }

  const handleStartProcess = async () => {
    if (!venueId) return
    setProcessPending(true)
    setError('')
    try {
      await venueApi.startProcess(venueId)
      await fetchData(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start live monitoring process.')
    } finally {
      setProcessPending(false)
    }
  }

  const handlePauseProcess = async () => {
    if (!venueId) return
    setProcessPending(true)
    setError('')
    try {
      await venueApi.pauseProcess(venueId)
      await fetchData(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not pause counting process.')
    } finally {
      setProcessPending(false)
    }
  }

  const handleResetProcess = async () => {
    if (!venueId) return
    if (!confirm('Neutralize all current counts and reset back to 0 in calibration mode?')) return
    setProcessPending(true)
    setError('')
    try {
      await venueApi.resetProcess(venueId)
      await fetchData(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reset counts.')
    } finally {
      setProcessPending(false)
    }
  }

  const handleDeleteVenue = async () => {
    if (!venue) return
    if (!confirm(`Are you sure you want to permanently delete "${venue.name}"? This will stop all camera streams and remove all gate and crowd data.`)) {
      return
    }
    try {
      await venueApi.delete(venue.id)
      localStorage.removeItem('activeVenueId')
      navigate('/venues', { replace: true })
    } catch (err: any) {
      alert(err.message || 'Failed to delete facility.')
    }
  }

  useEffect(() => {
    if (routeVenueId) {
      setVenueId(routeVenueId)
      localStorage.setItem('activeVenueId', routeVenueId)
    }
  }, [routeVenueId])

  useEffect(() => {
    let cancelled = false
    venueApi.list().then((items: Venue[]) => {
      if (cancelled) return
      setVenues(items)
      if (!items.length) {
        setLoading(false)
        return
      }

      const stored = localStorage.getItem('activeVenueId')
      const target = (routeVenueId && items.find((v) => v.id === routeVenueId))
        || (stored && items.find((v) => v.id === stored))
        || items[items.length - 1]

      if (target) {
        setVenueId(target.id)
        localStorage.setItem('activeVenueId', target.id)
        if (!routeVenueId) {
          navigate(`/venues/${target.id}/dashboard`, { replace: true })
        }
      }
    }).catch((reason) => {
      if (cancelled) return
      setError(reason instanceof Error ? reason.message : 'Could not load facilities.')
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [routeVenueId, navigate])

  const fetchData = useCallback(async (silent = false) => {
    const targetId = venueId || (typeof window !== 'undefined' ? localStorage.getItem('activeVenueId') : null)
    if (!targetId) {
      return
    }
    if (!silent) setRefreshing(true)
    setError('')
    try {
      // Use single aggregated dashboard endpoint to eliminate socket starvation
      const data = await monitorApi.dashboard(targetId)
      if (data) {
        if (data.venue) setVenue(data.venue)
        if (Array.isArray(data.gates)) setGates(data.gates)
        setState(data)
        setStreamErrors({})
      }
    } catch (reason) {
      try {
        const [currentVenue, currentGates] = await Promise.all([
          venueApi.get(targetId),
          gateApi.list(targetId),
        ])
        setVenue(currentVenue)
        setGates(currentGates)
      } catch {
        setError(reason instanceof Error ? reason.message : 'Could not load monitoring data.')
      }
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [venueId])

  useEffect(() => {
    fetchData()
    // 4-second poll as lightweight backup; WebSocket handles real-time pushes
    const pollInterval = setInterval(() => {
      fetchData(true)
    }, 4000)
    return () => clearInterval(pollInterval)
  }, [fetchData])

  useEffect(() => {
    if (!venueId) return
    return connectWebSocket(venueId, (message) => {
      if (message.type !== 'initial_state' && message.type !== 'update') return
      const next = message.data as DashboardState
      setState((previous) => ({ ...previous, ...next, gates: next.gates || previous?.gates || [] } as DashboardState))
      if (Array.isArray(next.gates)) {
        setGates((current) => next.gates.map((incoming) => ({
          ...(current.find((gate) => gate.id === incoming.id) || {} as Gate),
          ...incoming,
        })))
      }
      if (next.venue) {
        setVenue((prev) => (prev ? { ...prev, ...next.venue } : next.venue!))
      }
    })
  }, [venueId])

  const handleRestartGate = async (gateId: string) => {
    setActionPending(gateId)
    setError('')
    try {
      await gateApi.start(gateId)
      setStreamErrors((current) => ({ ...current, [gateId]: false }))
      await fetchData(true)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not restart camera gate.')
    } finally {
      setActionPending(null)
    }
  }

  const handleAlert = async (alert: any, action: 'acknowledge' | 'resolve') => {
    if (alert.isClientOnly) {
      setClientSurgeAlert(null)
      return
    }
    setActionPending(alert.id)
    setError('')
    try {
      if (action === 'acknowledge') await monitorApi.acknowledgeAlert(alert.id, 'Operator')
      else await monitorApi.resolveAlert(alert.id, 'Operator', 'Resolved from the live dashboard')
      await fetchData(true)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not update this alert.')
    } finally {
      setActionPending(null)
    }
  }

  const entryGates = gates.filter((g) => g.gate_type?.toUpperCase().includes('ENTRY'))
  const exitGates = gates.filter((g) => g.gate_type?.toUpperCase().includes('EXIT'))

  const totalEntriesSum = entryGates.reduce((acc, g) => acc + (g.entry_count || 0), 0)
  const totalExitsSum = exitGates.reduce((acc, g) => acc + (g.exit_count || 0), 0)

  // Strictly synchronized global counts derived directly from individual gate cameras
  const entries = gates.length > 0 ? totalEntriesSum : (state?.occupancy?.total_entries ?? venue?.total_entries ?? 0)
  const exits = gates.length > 0 ? totalExitsSum : (state?.occupancy?.total_exits ?? venue?.total_exits ?? 0)
  const occupancy = Math.max(0, entries - exits)
  const capacity = state?.occupancy?.effective_capacity ?? venue?.effective_capacity ?? venue?.max_capacity ?? 0
  const capacityPercent = capacity > 0 ? Number(((occupancy / capacity) * 100).toFixed(1)) : 0
  const isBaselineEstablished = state?.occupancy?.baseline_established ?? venue?.baseline_established ?? false
  const isUncertain = state?.occupancy?.occupancy_is_uncertain ?? (!isBaselineEstablished)
  const entryRate = Number((state?.flow?.entry_rate_per_min ?? 0).toFixed(1))
  const exitRate = Number((state?.flow?.exit_rate_per_min ?? 0).toFixed(1))
  const netInflow = Number((state?.flow?.net_inflow_per_min ?? entryRate - exitRate).toFixed(1))
  const timeToFull = state?.forecast?.time_to_capacity_minutes
  const remainingSpots = Math.max(0, capacity - occupancy)

  // Determine in how much time occupancy will be fully filled
  let timeToFullText = ''
  let timeToFullDetail = ''
  let timeToFullColor = 'text-blue-600'

  if (capacity > 0 && occupancy >= capacity) {
    timeToFullText = 'Fully Filled'
    timeToFullDetail = `At 100% capacity (${occupancy.toLocaleString()}/${capacity.toLocaleString()} people)`
    timeToFullColor = 'text-red-600'
  } else if (capacity > 0) {
    const forecastMinutes = timeToFull != null ? Math.round(timeToFull) : null
    const computedMinutes = netInflow > 0 ? Math.max(1, Math.round(remainingSpots / netInflow)) : null
    const minutes = forecastMinutes ?? computedMinutes

    if (minutes !== null && minutes > 0) {
      timeToFullText = formatDuration(minutes)
      const targetTime = new Date(Date.now() + minutes * 60000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      timeToFullDetail = `Full at ~${targetTime} · ${remainingSpots.toLocaleString()} spots left (+${netInflow}/min)`
      timeToFullColor = minutes <= 15 ? 'text-red-600' : minutes <= 45 ? 'text-orange-600' : 'text-blue-600'
    } else if (netInflow <= 0 && entryRate > 0) {
      timeToFullText = 'Steady (No Inflow)'
      timeToFullDetail = `${remainingSpots.toLocaleString()} spots open · Exits match entries (${entryRate}/min)`
      timeToFullColor = 'text-emerald-600'
    } else if (occupancy === 0 && entries === 0) {
      timeToFullText = 'Awaiting Inflow'
      timeToFullDetail = `${capacity.toLocaleString()} spots open until 100% full`
      timeToFullColor = 'text-slate-500'
    } else {
      timeToFullText = 'No Inflow'
      timeToFullDetail = `${remainingSpots.toLocaleString()} spots open · 0 net inflow/min`
      timeToFullColor = 'text-slate-500'
    }
  } else {
    timeToFullText = 'No Capacity Set'
    timeToFullDetail = 'Configure venue capacity to project time'
    timeToFullColor = 'text-slate-400'
  }

  const isCountingActive = Boolean(state?.monitoring_active ?? venue?.monitoring_active)

  const crowd = capacityPercent >= 90
    ? { label: 'Critical', detail: capacityPercent > 100 ? `${capacityPercent}% Over capacity` : 'Capacity limit approaching', color: 'text-red-600', surface: 'bg-red-50 border-red-100' }
    : capacityPercent >= 75
      ? { label: 'High', detail: 'Approaching capacity', color: 'text-orange-600', surface: 'bg-orange-50 border-orange-100' }
      : capacityPercent >= 50
        ? { label: 'Moderate', detail: 'Normal flow', color: 'text-orange-500', surface: 'bg-orange-50 border-orange-100' }
        : { label: 'Low', detail: 'Smooth movement', color: 'text-emerald-600', surface: 'bg-emerald-50 border-emerald-100' }

  // Track previous crowd level to detect rapid transitions: Moderate -> High and High -> Critical
  const prevCrowdLevelRef = useRef<string | null>(null)
  const [clientSurgeAlert, setClientSurgeAlert] = useState<{
    id: string
    title: string
    message: string
    recommended_action: string
    severity: 'WARNING' | 'CRITICAL'
  } | null>(null)

  useEffect(() => {
    const prevLevel = prevCrowdLevelRef.current
    const currLevel = crowd.label // 'Low' | 'Moderate' | 'High' | 'Critical'

    if (prevLevel && prevLevel !== currLevel) {
      // Rapid change from Moderate to High
      if (prevLevel === 'Moderate' && currLevel === 'High') {
        setClientSurgeAlert({
          id: `surge-mod-to-high-${Date.now()}`,
          title: 'Rapid Crowd Surge: Moderate to High',
          message: `Crowd density escalated rapidly from Moderate to High (${capacityPercent}% capacity, ${occupancy.toLocaleString()} people inside). Inflow rate is approaching safe capacity limits.`,
          recommended_action: 'Monitor entry gate influx closely. Prepare queue management barriers and divert incoming pedestrian flow.',
          severity: 'WARNING',
        })
      }
      // Rapid change to Critical (from High or Moderate)
      else if ((prevLevel === 'High' || prevLevel === 'Moderate') && currLevel === 'Critical') {
        setClientSurgeAlert({
          id: `surge-high-to-crit-${Date.now()}`,
          title: 'Critical Occupancy Surge: High to Critical',
          message: `CRITICAL ALERT: Occupancy escalated rapidly into Critical state (${capacityPercent}% capacity, ${occupancy.toLocaleString()} people inside). Imminent crush and bottleneck risk!`,
          recommended_action: 'Immediately restrict incoming flow. Verify all emergency and auxiliary exits are open. Deploy marshals to prevent bottlenecking.',
          severity: 'CRITICAL',
        })
      }
      // Auto-clear surge alert if crowd recedes safely to Low
      else if (currLevel === 'Low') {
        setClientSurgeAlert(null)
      }
    }

    prevCrowdLevelRef.current = currLevel
  }, [crowd.label, capacityPercent, occupancy])

  // Filter backend active alerts: ONLY show when data changes rapidly from Moderate to High or High to Critical
  const serverEscalationAlerts = useMemo(() => {
    return (state?.alerts || []).filter((alert) => {
      if (alert.status !== 'ACTIVE') return false
      const key = (alert.alert_type_key || '').toLowerCase()
      const title = (alert.title || '').toLowerCase()

      // Suppress noisy alerts (data reliability, entry-to-exit ratio)
      if (key.includes('data_quality') || title.includes('data reliability')) return false
      if (key.includes('flow_imbalance') || title.includes('ratio')) return false

      // Only allow High to Critical (critical threshold) and Moderate to High (warning threshold / surge)
      const isCriticalSurge = alert.severity === 'CRITICAL' || key.includes('occupancy_critical') || title.includes('critical') || title.includes('high to critical')
      const isHighSurge = key.includes('occupancy_warning') || title.includes('moderate to high') || title.includes('surge')
      return isCriticalSurge || isHighSurge
    })
  }, [state?.alerts])

  // Combined active alerts for display
  const displayAlerts = useMemo(() => {
    const list: Array<{
      id: string
      title: string
      message: string
      recommended_action?: string
      severity?: string
      isClientOnly?: boolean
    }> = [...serverEscalationAlerts]

    if (clientSurgeAlert && !list.some(a => a.title.toLowerCase().includes(clientSurgeAlert.severity === 'CRITICAL' ? 'critical' : 'moderate to high'))) {
      list.unshift({ ...clientSurgeAlert, isClientOnly: true })
    }
    return list
  }, [serverEscalationAlerts, clientSurgeAlert])

  if (loading) return <div className="py-24 text-center text-sm text-slate-500">Loading crowd monitoring…</div>

  if (!venueId || !venue) {
    return (
      <div className="mx-auto max-w-xl py-20 text-center">
        <Activity className="mx-auto mb-4 h-10 w-10 text-blue-600" />
        <h1 className="text-2xl font-bold text-slate-900">{error ? 'Dashboard unavailable' : 'No facility configured'}</h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">{error || 'Add camera streams and venue details to begin live crowd monitoring.'}</p>
        <div className="mt-5 flex justify-center gap-3">
          {error && <button onClick={() => { setLoading(true); setError(''); venueApi.list().then((items: Venue[]) => { setVenues(items); const next = routeVenueId || items[items.length - 1]?.id; if (next) setVenueId(next); else setLoading(false) }).catch((reason) => { setError(reason.message); setLoading(false) }) }} className="btn-secondary"><RefreshCw className="h-4 w-4" />Retry</button>}
          <Link to="/inputs" className="btn-primary">Set up monitoring <ArrowRight className="h-4 w-4" /></Link>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-5 pb-8">
      {error && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <span>{error} Showing the last available readings.</span>
          <button onClick={() => fetchData()} disabled={refreshing} className="btn-secondary text-xs">
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />Retry
          </button>
        </div>
      )}

      {/* Top Header & Facility Selector */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          {venues.length > 1 ? (
            <select
              aria-label="Select venue"
              value={venue.id}
              onChange={(event) => {
                setVenueId(event.target.value)
                localStorage.setItem('activeVenueId', event.target.value)
                navigate(`/venues/${event.target.value}/dashboard`)
              }}
              className="max-w-full border-0 bg-transparent p-0 text-xl font-bold text-slate-900 focus:ring-0"
            >
              {venues.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          ) : <h1 className="text-xl font-bold text-slate-900">{venue.name}</h1>}
          {venue.location && <span className="text-sm text-slate-500">{venue.location}</span>}
          <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2.5 py-1 text-xs font-mono font-medium text-slate-600 border border-slate-200">
            <Calendar className="w-3.5 h-3.5 text-blue-600" />
            {new Date().toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => fetchData()} disabled={refreshing} className="btn-secondary text-xs">
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />Refresh
          </button>
          <Link to={`/venues/${venue.id}/gates`} className="btn-secondary text-xs">
            <Settings className="h-4 w-4" />Gate settings
          </Link>
          <button
            type="button"
            onClick={handleDeleteVenue}
            className="btn-secondary text-xs text-rose-600 hover:bg-rose-50 hover:text-rose-700 hover:border-rose-300"
            title="Delete this facility"
          >
            <Trash2 className="h-4 w-4" />
            <span className="hidden sm:inline">Delete</span>
          </button>
        </div>
      </div>

      {/* CRITICAL PROCESS CONTROL & CALIBRATION BANNER */}
      {!isCountingActive ? (
        <div className="rounded-xl border-2 border-amber-400 bg-gradient-to-r from-amber-50 via-orange-50 to-amber-50 p-4 sm:p-5 shadow-xs">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500 text-white shadow-sm ring-4 ring-amber-100">
                <Sliders className="h-5 w-5" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-md bg-amber-200/80 px-2.5 py-0.5 text-xs font-extrabold text-amber-950 uppercase tracking-wider border border-amber-300">
                    <span className="h-2 w-2 rounded-full bg-amber-600 animate-pulse" />
                    Line Calibration &amp; Setup Mode
                  </span>
                  <span className="text-xs text-amber-800 font-semibold">Live Streams Active · Live Counting Paused</span>
                </div>
                <p className="mt-1 text-xs sm:text-sm text-amber-950 font-normal leading-relaxed">
                  Use the sliders <strong>directly below each video feed</strong> to align the counting lines with your physical doorways.
                  When ready, press <strong>Start Monitoring Process</strong> to neutralize initial setup data and activate synchronized counting.
                </p>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-3">
              <button
                type="button"
                onClick={handleStartProcess}
                disabled={processPending}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-bold text-white shadow-md hover:bg-emerald-700 transition cursor-pointer disabled:opacity-50 ring-2 ring-emerald-500/30"
              >
                <Play className={`h-4 w-4 fill-white ${processPending ? 'animate-spin' : ''}`} />
                {processPending ? 'Starting Process…' : 'Start Monitoring Process'}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-emerald-300 bg-emerald-50/80 p-3.5 sm:p-4 shadow-xs">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-white shadow-xs">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-bold text-emerald-800 border border-emerald-300">
                    <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                    SYNCHRONIZED LIVE COUNTING ACTIVE
                  </span>
                  <span className="text-xs text-emerald-700 font-medium hidden sm:inline">Single-Pass Anti-Passback Enforced</span>
                </div>
                <p className="text-xs text-emerald-800 mt-0.5">
                  Real-time detection and line crossing are synchronized across all gate cameras.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handlePauseProcess}
                disabled={processPending}
                className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-100 transition cursor-pointer disabled:opacity-50"
                title="Pause live counting to recalibrate gate lines without stopping streams"
              >
                <Pause className="h-3.5 w-3.5" />
                Pause / Recalibrate
              </button>
              <button
                type="button"
                onClick={handleResetProcess}
                disabled={processPending}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition cursor-pointer disabled:opacity-50"
                title="Reset all counts to 0 and re-enter calibration mode"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Reset &amp; Neutralize
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Summary KPI Cards */}
      <section aria-label="Crowd summary" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard title="Total Entry" value={entries.toLocaleString()} detail="People" color="text-emerald-600" surface="bg-emerald-50/70 border-emerald-100" />
        <SummaryCard title="Total Exit" value={exits.toLocaleString()} detail="People" color="text-rose-600" surface="bg-rose-50/70 border-rose-100" />
        <SummaryCard
          title="Current Crowd"
          value={occupancy.toLocaleString()}
          detail={
            capacity
              ? `${capacityPercent}% of ${capacity.toLocaleString()} cap${isUncertain ? ' (Estimated)' : ''}`
              : isUncertain ? 'Estimated delta' : 'People inside'
          }
          color="text-blue-600"
          surface="bg-blue-50/70 border-blue-100"
        />
        <SummaryCard title="Crowd Level" value={crowd.label} detail={crowd.detail} color={crowd.color} surface={crowd.surface} />
      </section>

      {/* Flow & Capacity Metrics (First Image: positioned directly below Total Entry/Exit and above Cameras) */}
      <section aria-label="Current flow metrics" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="Entry Rate" value={`${entryRate} / min`} detail="People per minute" color="text-emerald-600" icon={<DoorOpen className="h-5 w-5" />} />
        <MetricCard title="Exit Rate" value={`${exitRate} / min`} detail="People per minute" color="text-rose-600" icon={<DoorClosed className="h-5 w-5" />} />
        <MetricCard title="Current Occupancy" value={capacity ? `${occupancy.toLocaleString()} / ${capacity.toLocaleString()}` : occupancy.toLocaleString()} detail={capacity ? `People (${capacityPercent}% capacity)` : 'People inside'} color="text-blue-600" icon={<Users className="h-5 w-5" />} />
        <MetricCard
          title="Time to Full Capacity"
          value={timeToFullText}
          detail={timeToFullDetail}
          color={timeToFullColor}
          icon={<Clock className="h-5 w-5" />}
        />
      </section>

      {/* Live Gate Cameras Grid */}
      <section aria-label="Live gate cameras">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-slate-900">Live Gate Cameras</h2>
            <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600 border border-slate-200">
              {gates.filter((gate) => gate.status === 'ACTIVE').length} live · {gates.length} total
            </span>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center rounded-lg border border-slate-200 bg-white p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setGridMode('large')}
                className={`rounded-md px-2.5 py-1 font-medium transition ${
                  gridMode === 'large'
                    ? 'bg-slate-900 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
                title="Theater view with 2 large camera cards side-by-side"
              >
                Wide (2 Col)
              </button>
              <button
                type="button"
                onClick={() => setGridMode('compact')}
                className={`rounded-md px-2.5 py-1 font-medium transition ${
                  gridMode === 'compact'
                    ? 'bg-slate-900 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
                title="Compact view with up to 4 camera cards"
              >
                Compact (4 Col)
              </button>
            </div>
          </div>
        </div>

        {gates.length === 0 ? (
          <div className="rounded-lg border border-slate-200 bg-white px-5 py-12 text-center">
            <VideoOff className="mx-auto mb-3 h-8 w-8 text-slate-400" />
            <p className="font-medium text-slate-800">No camera gates have been added yet.</p>
            <Link to={`/venues/${venue.id}/gates`} className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-blue-700 hover:underline">
              Add gate cameras <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        ) : (
          <div className={`grid gap-4 ${gridMode === 'large' ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-4'}`}>
            {gates.map((gate) => (
              <CameraCard
                key={gate.id}
                gate={gate}
                liveFrameUrl={liveFrames[gate.id]}
                isCountingActive={isCountingActive}
                error={streamErrors[gate.id]}
                isCurrentlyFullscreen={fullscreenGate?.id === gate.id}
                onError={() => setStreamErrors((current) => ({ ...current, [gate.id]: true }))}
                onRestart={() => handleRestartGate(gate.id)}
                onOpenFullscreen={() => setFullscreenGate(gate)}
                onUpdateLine={handleUpdateLineConfig}
              />
            ))}
          </div>
        )}
      </section>

      {fullscreenGate && (
        <FullscreenStreamModal
          gate={fullscreenGate}
          liveFrameUrl={liveFrames[fullscreenGate.id]}
          isCountingActive={isCountingActive}
          venueName={venue.name}
          occupancy={occupancy}
          capacity={capacity}
          onClose={() => setFullscreenGate(null)}
          onUpdateLine={handleUpdateLineConfig}
          onRestart={() => handleRestartGate(fullscreenGate.id)}
        />
      )}

      {/* Safety Alerts (Third Image: rectangular cards below the camera streams) */}
      {displayAlerts.length > 0 && (
        <section aria-label="Safety alerts" className="space-y-3 pt-2">
          {displayAlerts.map((alert) => (
            <div
              key={alert.id}
              className="flex flex-col gap-4 rounded-xl border border-rose-200 bg-rose-50/70 p-4 sm:p-5 sm:flex-row sm:items-center sm:justify-between shadow-xs transition"
            >
              <div className="flex items-start gap-3.5">
                <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-rose-100 text-rose-600">
                  <AlertCircle className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-rose-800">{alert.title}</h2>
                  <p className="mt-0.5 text-sm text-slate-800 leading-relaxed">{alert.message}</p>
                  {alert.recommended_action && (
                    <p className="mt-1 text-sm font-semibold text-rose-900">{alert.recommended_action}</p>
                  )}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2 pl-10 sm:pl-0">
                <button
                  type="button"
                  disabled={actionPending === alert.id}
                  onClick={() => handleAlert(alert, 'acknowledge')}
                  className="rounded-md border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition shadow-xs cursor-pointer disabled:opacity-50"
                >
                  Acknowledge
                </button>
                <button
                  type="button"
                  disabled={actionPending === alert.id}
                  onClick={() => handleAlert(alert, 'resolve')}
                  className="rounded-md bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-700 transition shadow-xs cursor-pointer disabled:opacity-50"
                >
                  Resolve
                </button>
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}

function SummaryCard({ title, value, detail, color, surface }: { title: string; value: string; detail: string; color: string; surface: string }) {
  return <div className={`flex min-h-36 flex-col items-center justify-center rounded-lg border px-4 py-5 text-center ${surface}`}><h2 className="text-base font-medium text-slate-700">{title}</h2><p className={`mt-2 text-4xl font-bold tracking-tight ${color}`}>{value}</p><p className="mt-1 text-sm text-slate-600">{detail}</p></div>
}

function MetricCard({ title, value, detail, color, icon }: { title: string; value: string; detail: string; color: string; icon: React.ReactNode }) {
  return <div className="rounded-lg border border-slate-200 bg-white p-5"><div className="flex items-center justify-between"><h2 className="font-semibold text-slate-800">{title}</h2><span className={color}>{icon}</span></div><p className={`mt-3 text-3xl font-bold tracking-tight ${color}`}>{value}</p><p className="mt-1 text-sm text-slate-500">{detail}</p></div>
}

function CameraCard({
  gate,
  liveFrameUrl,
  isCountingActive,
  error,
  onError,
  onRestart,
  onOpenFullscreen,
  onUpdateLine,
  isCurrentlyFullscreen,
}: {
  gate: Gate
  liveFrameUrl?: string
  isCountingActive: boolean
  error: boolean
  onError: () => void
  onRestart: () => void
  onOpenFullscreen: () => void
  onUpdateLine: (gateId: string, lineY: number, direction: string, resetPassback?: boolean) => Promise<void>
  isCurrentlyFullscreen?: boolean
}) {
  const isEntry = gate.gate_type === 'ENTRY'
  const isConnecting = gate.status === 'CONNECTING'
  const isLive = gate.status === 'ACTIVE'
  const isError = gate.status === 'ERROR' || error
  const statusLabel = isLive ? 'Live' : isConnecting ? 'Connecting' : isError ? 'Error' : 'Offline'

  const [lineY, setLineY] = useState(gate.line_start_y ?? (isEntry ? 0.65 : 0.78))
  const [direction, setDirection] = useState(gate.counting_direction || 'any')
  const [isSaving, setIsSaving] = useState(false)
  const [resetSuccess, setResetSuccess] = useState(false)

  // Sync state if props change from outside
  useEffect(() => {
    if (gate.line_start_y !== undefined) setLineY(gate.line_start_y)
    if (gate.counting_direction) setDirection(gate.counting_direction)
  }, [gate.line_start_y, gate.counting_direction])

  const handleSliderChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value) / 100
    setLineY(val)
    setIsSaving(true)
    await onUpdateLine(gate.id, val, direction)
    setIsSaving(false)
  }

  const handleDirectLineSet = async (val: number) => {
    setLineY(val)
    setIsSaving(true)
    await onUpdateLine(gate.id, val, direction)
    setIsSaving(false)
  }

  const handleDirectionChange = async (newDir: string) => {
    setDirection(newDir)
    setIsSaving(true)
    await onUpdateLine(gate.id, lineY, newDir)
    setIsSaving(false)
  }

  const handleResetPassback = async () => {
    setIsSaving(true)
    await onUpdateLine(gate.id, lineY, direction, true)
    setIsSaving(false)
    setResetSuccess(true)
    setTimeout(() => setResetSuccess(false), 2000)
  }

  // Use multiplexed WebSocket blob URL if available; otherwise fallback to direct stream
  const frameSrc = liveFrameUrl || `/api/v1/gates/${gate.id}/stream`

  return (
    <article className="group overflow-hidden rounded-xl border border-slate-200 bg-white p-3 shadow-xs transition hover:shadow-md flex flex-col justify-between">
      <div>
        {/* Card Header */}
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span
              className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                isEntry ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
              }`}
            >
              {isEntry ? 'Entry' : 'Exit'}
            </span>
            <h3 className="truncate text-sm font-bold text-slate-900" title={gate.display_name}>
              {gate.display_name}
            </h3>
          </div>

          <div className="flex items-center gap-1.5">
            <span
              className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium border ${
                isLive
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : isConnecting
                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                  : isError
                  ? 'bg-rose-50 text-rose-700 border-rose-200'
                  : 'bg-slate-100 text-slate-600 border-slate-200'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isLive
                    ? 'bg-emerald-500 animate-pulse'
                    : isConnecting
                    ? 'bg-amber-500 animate-pulse'
                    : isError
                    ? 'bg-rose-500'
                    : 'bg-slate-400'
                }`}
              />
              {statusLabel}
            </span>

            <button
              type="button"
              onClick={onOpenFullscreen}
              className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-800 transition cursor-pointer"
              title="Open Fullscreen Surveillance View"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Video Screen Container */}
        <div
          onClick={onOpenFullscreen}
          className="relative flex aspect-[16/10] items-center justify-center overflow-hidden rounded-t-lg bg-slate-950 border border-slate-900 cursor-pointer group-hover:border-slate-700 transition"
        >
          {isCurrentlyFullscreen ? (
            <div className="h-full w-full bg-slate-950 flex flex-col items-center justify-center text-xs text-slate-400 gap-1.5 p-4 text-center">
              <Maximize2 className="h-6 w-6 text-blue-400 animate-pulse" />
              <span className="font-semibold text-slate-200">Active in Fullscreen Modal</span>
              <span className="text-[11px] text-slate-500">Stream active above</span>
            </div>
          ) : !error && gate.status !== 'INACTIVE' ? (
            <>
              <img
                src={frameSrc}
                alt={`${gate.display_name} live camera`}
                className="h-full w-full object-cover transition duration-200"
                onError={onError}
              />
              {/* Fullscreen Hover Hint */}
              <div className="absolute inset-0 bg-slate-950/0 group-hover:bg-slate-950/20 transition flex items-center justify-center opacity-0 group-hover:opacity-100 pointer-events-none">
                <span className="flex items-center gap-1.5 rounded-full bg-slate-900/80 px-3 py-1.5 text-xs font-medium text-white shadow-lg backdrop-blur-xs border border-white/10">
                  <Maximize2 className="h-3.5 w-3.5" /> Click to Expand Full Screen
                </span>
              </div>
            </>
          ) : (
            <div
              onClick={(e) => e.stopPropagation()}
              className="px-4 text-center text-xs text-slate-400 flex flex-col items-center justify-center gap-2"
            >
              <VideoOff className="h-7 w-7 text-slate-600" />
              <p className="font-semibold text-slate-300">{error ? 'Camera feed unavailable' : statusLabel}</p>
              {gate.error_message && (
                <p className="text-[11px] text-rose-400 max-w-[200px] truncate" title={gate.error_message}>
                  {gate.error_message}
                </p>
              )}
              <button
                onClick={onRestart}
                className="mt-1 flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-white text-[11px] font-medium transition cursor-pointer"
              >
                <RefreshCw className="w-3 h-3" />
                Reconnect
              </button>
            </div>
          )}

          {/* Real-time Count Badge on Video */}
          <span
            className={`absolute bottom-2 left-2 rounded-md px-2.5 py-1 text-xs font-mono font-bold text-white shadow-md backdrop-blur-xs border ${
              isCountingActive
                ? isEntry
                  ? 'bg-emerald-950/90 border-emerald-500/50 text-emerald-300'
                  : 'bg-rose-950/90 border-rose-500/50 text-rose-300'
                : 'bg-amber-950/90 border-amber-500/50 text-amber-300'
            }`}
          >
            {isCountingActive
              ? isEntry
                ? `IN: ${gate.entry_count || 0}`
                : `OUT: ${gate.exit_count || 0}`
              : 'CALIBRATING'}
          </span>

          <span className="absolute bottom-2 right-2 rounded-md bg-slate-950/80 px-2 py-1 text-[10px] font-medium text-slate-300 border border-white/10">
            {isCountingActive ? 'Single-Pass Active' : 'Setup Mode'}
          </span>
        </div>

        {/* ZERO-SPACING DIRECT LINE CALIBRATION CONTROL BAR (Directly below video) */}
        <div className="rounded-b-lg border-x border-b border-slate-300 bg-slate-50 p-2.5 text-xs shadow-inner">
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <span className="font-semibold text-slate-800 flex items-center gap-1.5 text-xs">
              <Sliders className="h-3.5 w-3.5 text-blue-600" />
              Counting Line Height: <span className="font-mono font-bold text-blue-700 text-sm">{Math.round(lineY * 100)}%</span>
            </span>
            <span className="text-[11px] text-slate-500 font-medium">
              {isSaving ? 'Updating line…' : 'Drag to adjust line position'}
            </span>
          </div>

          {/* Slider directly below video */}
          <input
            type="range"
            min="15"
            max="85"
            step="1"
            value={Math.round(lineY * 100)}
            onChange={handleSliderChange}
            className="w-full accent-blue-600 h-2 bg-slate-200 rounded-lg cursor-pointer"
            title="Adjust counting line height"
          />

          {/* Optimal Pedestrian Corridor Alignment Status & Quick-Fix */}
          {lineY < 0.44 ? (
            <div className="mt-1.5 flex items-center justify-between gap-1 text-[11px] text-amber-900 bg-amber-100/90 px-2 py-1 rounded border border-amber-300">
              <span className="truncate">⚠️ Line at {Math.round(lineY * 100)}% is above crowd!</span>
              <button
                type="button"
                onClick={() => handleDirectLineSet(0.55)}
                className="font-bold underline text-blue-700 hover:text-blue-900 cursor-pointer shrink-0"
                title="Snap line to optimal 55% pedestrian crossing corridor"
              >
                Auto-Align (55%)
              </button>
            </div>
          ) : lineY > 0.75 ? (
            <div className="mt-1.5 flex items-center justify-between gap-1 text-[11px] text-amber-900 bg-amber-100/90 px-2 py-1 rounded border border-amber-300">
              <span className="truncate">⚠️ Line near bottom edge.</span>
              <button
                type="button"
                onClick={() => handleDirectLineSet(0.55)}
                className="font-bold underline text-blue-700 hover:text-blue-900 cursor-pointer shrink-0"
              >
                Set Optimal (55%)
              </button>
            </div>
          ) : (
            <div className="mt-1.5 flex items-center justify-between gap-1 text-[11px] text-emerald-800 bg-emerald-50 px-2 py-1 rounded border border-emerald-200">
              <span className="flex items-center gap-1 font-medium truncate">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0" />
                Optimal Pedestrian Corridor ({Math.round(lineY * 100)}%)
              </span>
              <button
                type="button"
                onClick={() => handleDirectLineSet(0.55)}
                className="text-[10px] text-slate-500 hover:text-slate-800 underline cursor-pointer shrink-0"
              >
                Snap 55%
              </button>
            </div>
          )}

          {/* Flow Direction & Reset Pass Controls */}
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-semibold text-slate-600">Direction:</span>
              <div className="inline-flex rounded border border-slate-300 bg-white p-0.5 text-[11px]">
                <button
                  type="button"
                  onClick={() => handleDirectionChange('any')}
                  className={`rounded px-2 py-0.5 font-medium transition cursor-pointer ${
                    direction === 'any' ? 'bg-blue-600 text-white font-bold' : 'text-slate-600 hover:text-slate-900'
                  }`}
                  title="Count all verified crossings"
                >
                  ⬍ Any
                </button>
                <button
                  type="button"
                  onClick={() => handleDirectionChange('up')}
                  className={`rounded px-2 py-0.5 font-medium transition cursor-pointer ${
                    direction === 'up' ? 'bg-blue-600 text-white font-bold' : 'text-slate-600 hover:text-slate-900'
                  }`}
                  title="Count upward movement"
                >
                  ⬆ Up
                </button>
                <button
                  type="button"
                  onClick={() => handleDirectionChange('down')}
                  className={`rounded px-2 py-0.5 font-medium transition cursor-pointer ${
                    direction === 'down' ? 'bg-blue-600 text-white font-bold' : 'text-slate-600 hover:text-slate-900'
                  }`}
                  title="Count downward movement"
                >
                  ⬇ Down
                </button>
              </div>
            </div>

            <button
              type="button"
              onClick={handleResetPassback}
              disabled={isSaving}
              className={`text-[11px] transition flex items-center gap-1 font-semibold px-2 py-1 rounded border cursor-pointer ${
                resetSuccess
                  ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
                  : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-100 hover:text-slate-900'
              }`}
              title="Allow registered tracks to re-enter"
            >
              <RotateCcw className={`h-3 w-3 ${isSaving ? 'animate-spin' : ''}`} />
              {resetSuccess ? 'Reset!' : 'Reset Passes'}
            </button>
          </div>
        </div>
      </div>
    </article>
  )
}

function FullscreenStreamModal({
  gate,
  liveFrameUrl,
  isCountingActive,
  venueName,
  occupancy,
  capacity,
  onClose,
  onUpdateLine,
  onRestart,
}: {
  gate: Gate
  liveFrameUrl?: string
  isCountingActive: boolean
  venueName: string
  occupancy: number
  capacity: number
  onClose: () => void
  onUpdateLine: (gateId: string, lineY: number, direction: string, resetPassback?: boolean) => Promise<void>
  onRestart: () => void
}) {
  const isEntry = gate.gate_type === 'ENTRY'
  const [lineY, setLineY] = useState(gate.line_start_y ?? (isEntry ? 0.65 : 0.78))
  const [direction, setDirection] = useState(gate.counting_direction || 'any')
  const [isSaving, setIsSaving] = useState(false)
  const [resetSuccess, setResetSuccess] = useState(false)
  const [isNativeFullscreen, setIsNativeFullscreen] = useState(false)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const toggleNativeFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().then(() => setIsNativeFullscreen(true)).catch(() => {})
    } else {
      document.exitFullscreen().then(() => setIsNativeFullscreen(false)).catch(() => {})
    }
  }

  const handleSliderChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value) / 100
    setLineY(val)
    setIsSaving(true)
    await onUpdateLine(gate.id, val, direction)
    setIsSaving(false)
  }

  const handleDirectLineSet = async (val: number) => {
    setLineY(val)
    setIsSaving(true)
    await onUpdateLine(gate.id, val, direction)
    setIsSaving(false)
  }

  const handleDirectionChange = async (newDir: string) => {
    setDirection(newDir)
    setIsSaving(true)
    await onUpdateLine(gate.id, lineY, newDir)
    setIsSaving(false)
  }

  const handleResetAntiPassback = async () => {
    setIsSaving(true)
    await onUpdateLine(gate.id, lineY, direction, true)
    setIsSaving(false)
    setResetSuccess(true)
    setTimeout(() => setResetSuccess(false), 2500)
  }

  const frameSrc = liveFrameUrl || `/api/v1/gates/${gate.id}/stream`

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-slate-950 text-white select-none overflow-hidden animate-fadeIn">
      {/* Top Header Bar */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/90 px-4 py-2.5 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span
              className={`rounded px-2 py-0.5 text-xs font-bold uppercase tracking-wider ${
                isEntry ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40' : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
              }`}
            >
              {isEntry ? 'Entry Gate' : 'Exit Gate'}
            </span>
            <h2 className="text-base font-bold text-white tracking-tight">{gate.display_name}</h2>
            <span className="text-xs text-slate-400 hidden sm:inline">({venueName})</span>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-400 border border-emerald-500/30">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              LIVE AI SURVEILLANCE
            </span>
            <span className="hidden md:inline-flex items-center gap-1 rounded bg-slate-800 px-2 py-0.5 text-[11px] font-mono text-slate-300 border border-slate-700">
              {isCountingActive ? 'LIVE COUNTING' : 'CALIBRATION MODE'}
            </span>
          </div>
        </div>

        {/* Live Counters Readout */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3 border-x border-slate-800 px-4">
            <div className="text-right">
              <span className="block text-[10px] uppercase tracking-wider text-slate-400 font-medium">
                {isEntry ? 'Total Entered' : 'Total Exited'}
              </span>
              <span className={`text-lg font-mono font-bold ${isEntry ? 'text-emerald-400' : 'text-rose-400'}`}>
                {isEntry ? gate.entry_count : gate.exit_count}
              </span>
            </div>
            <div className="text-right">
              <span className="block text-[10px] uppercase tracking-wider text-slate-400 font-medium">Facility Crowd</span>
              <span className="text-lg font-mono font-bold text-blue-400">
                {occupancy} {capacity ? `/ ${capacity}` : ''}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              onClick={toggleNativeFullscreen}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white transition cursor-pointer"
              title={isNativeFullscreen ? 'Exit Native Fullscreen' : 'Native Browser Fullscreen'}
            >
              {isNativeFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </button>
            <button
              onClick={onClose}
              className="rounded-lg p-2 text-slate-400 hover:bg-rose-500/20 hover:text-rose-400 transition cursor-pointer"
              title="Close Fullscreen (Esc)"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Video Screen with ZERO SPACING TO CONTROLS */}
      <main className="relative flex-1 flex flex-col items-center justify-center p-2 sm:p-4 bg-slate-950 overflow-hidden">
        <div className="relative flex flex-col items-center justify-center w-full max-w-6xl h-full max-h-[85vh]">
          {/* Video Feed */}
          <div className="relative flex-1 flex items-center justify-center w-full overflow-hidden rounded-t-xl bg-black border border-slate-800">
            <img
              src={frameSrc}
              alt={`${gate.display_name} Fullscreen Stream`}
              className="max-h-full max-w-full object-contain"
            />

            {/* Real-Time Rule Overlay Notice */}
            <div className="absolute top-4 left-4 flex flex-col gap-1.5 pointer-events-none">
              <div className="inline-flex items-center gap-1.5 rounded-md bg-slate-900/85 px-3 py-1.5 text-xs font-medium text-emerald-300 border border-emerald-500/30 backdrop-blur-xs shadow-lg">
                <ShieldCheck className="h-4 w-4 text-emerald-400" />
                <span>{isCountingActive ? 'SINGLE-PASS PASSBACK ENFORCEMENT ACTIVE' : 'CALIBRATION MODE: COUNTING PAUSED'}</span>
              </div>
            </div>
          </div>

          {/* Integrated Control Bar directly below video frame */}
          <div className="w-full rounded-b-xl border border-t-0 border-slate-800 bg-slate-900 px-4 py-3 shadow-2xl">
            <div className="flex flex-wrap items-center justify-between gap-4">
              {/* Virtual Line Position Slider */}
              <div className="flex min-w-[280px] flex-1 items-center gap-3">
                <Sliders className="h-4 w-4 text-blue-400 shrink-0" />
                <div className="flex-1">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-semibold text-slate-200">
                      Counting Line Height: <span className="font-mono text-blue-400">{Math.round(lineY * 100)}%</span>
                    </span>
                    <span className="text-[11px] text-slate-400">
                      {isSaving ? 'Updating line in stream…' : 'Drag slider to adjust crossing threshold'}
                    </span>
                  </div>
                  <input
                    type="range"
                    min="15"
                    max="85"
                    step="1"
                    value={Math.round(lineY * 100)}
                    onChange={handleSliderChange}
                    className="w-full accent-blue-500 h-2 bg-slate-700 rounded-lg cursor-pointer"
                  />
                  {lineY < 0.44 ? (
                    <div className="mt-1 flex items-center justify-between gap-1 text-[11px] text-amber-300 bg-amber-950/60 px-2 py-0.5 rounded border border-amber-500/30">
                      <span>⚠️ Line at {Math.round(lineY * 100)}% is above crowd flow!</span>
                      <button
                        type="button"
                        onClick={() => handleDirectLineSet(0.55)}
                        className="font-bold underline text-amber-400 hover:text-white cursor-pointer"
                      >
                        Auto-Align (55%)
                      </button>
                    </div>
                  ) : lineY > 0.75 ? (
                    <div className="mt-1 flex items-center justify-between gap-1 text-[11px] text-amber-300 bg-amber-950/60 px-2 py-0.5 rounded border border-amber-500/30">
                      <span>⚠️ Line near bottom edge.</span>
                      <button
                        type="button"
                        onClick={() => handleDirectLineSet(0.55)}
                        className="font-bold underline text-amber-400 hover:text-white cursor-pointer"
                      >
                        Set Optimal (55%)
                      </button>
                    </div>
                  ) : (
                    <div className="mt-1 flex items-center justify-between gap-1 text-[11px] text-emerald-300 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-500/30">
                      <span className="flex items-center gap-1">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                        Optimal Pedestrian Crossing Corridor ({Math.round(lineY * 100)}%)
                      </span>
                      <button
                        type="button"
                        onClick={() => handleDirectLineSet(0.55)}
                        className="text-[10px] text-slate-400 hover:text-white underline cursor-pointer"
                      >
                        Snap 55%
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Counting Direction Toggle */}
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-slate-300">Flow:</span>
                <div className="inline-flex rounded-lg border border-slate-700 bg-slate-800 p-0.5 text-xs">
                  <button
                    type="button"
                    onClick={() => handleDirectionChange('any')}
                    className={`rounded px-2.5 py-1 font-medium transition cursor-pointer ${
                      direction === 'any' ? 'bg-blue-600 text-white font-bold' : 'text-slate-300 hover:text-white'
                    }`}
                  >
                    ⬍ Any
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDirectionChange('up')}
                    className={`rounded px-2.5 py-1 font-medium transition cursor-pointer ${
                      direction === 'up' ? 'bg-blue-600 text-white font-bold' : 'text-slate-300 hover:text-white'
                    }`}
                  >
                    ⬆ Up
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDirectionChange('down')}
                    className={`rounded px-2.5 py-1 font-medium transition cursor-pointer ${
                      direction === 'down' ? 'bg-blue-600 text-white font-bold' : 'text-slate-300 hover:text-white'
                    }`}
                  >
                    ⬇ Down
                  </button>
                </div>
              </div>

              {/* Anti-Passback Clear & Reconnect */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleResetAntiPassback}
                  disabled={isSaving}
                  className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition cursor-pointer border ${
                    resetSuccess
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : 'bg-slate-800 text-slate-200 border-slate-700 hover:bg-slate-700 hover:text-white'
                  }`}
                >
                  <RotateCcw className={`h-3.5 w-3.5 ${isSaving ? 'animate-spin' : ''}`} />
                  {resetSuccess ? 'Passes Reset!' : 'Reset Passes'}
                </button>

                <button
                  type="button"
                  onClick={onRestart}
                  className="flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 border border-slate-700 hover:bg-slate-700 hover:text-white transition cursor-pointer"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Reconnect
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

function formatDuration(minutes: number) {
  if (minutes <= 0) return 'Fully Filled'
  if (minutes < 2) return 'in < 2 mins'
  if (minutes < 60) return `in ${minutes} mins`
  const hours = Math.floor(minutes / 60)
  const remaining = minutes % 60
  if (remaining === 0) return `in ${hours} hr${hours > 1 ? 's' : ''}`
  return `in ${hours} hr ${remaining} min`
}

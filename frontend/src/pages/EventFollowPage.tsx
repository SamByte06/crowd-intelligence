import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Bell,
  BellRing,
  ShieldCheck,
  ShieldAlert,
  Clock,
  TrendingUp,
  TrendingDown,
  Users,
  Compass,
  ArrowRight,
  Share2,
  Check,
  ChevronLeft,
  Volume2,
  VolumeX,
  Activity,
  Layers,
  Smartphone,
  Laptop,
  CheckCircle2
} from 'lucide-react'
import { venueApi, gateApi, monitorApi, connectWebSocket } from '../services/api'
import {
  registerServiceWorker,
  getSystemNotificationPermission,
  requestSystemNotificationPermission,
  sendSystemNotification,
  updateLiveTimelineNotification,
  sendUrgentAlertNotification,
  sendTestNotification
} from '../services/systemNotification'

// Gentle synthesized audio chime using Web Audio API (Zero external mp3 needed)
function playAlertChime(severity: 'warning' | 'critical' | 'info') {
  try {
    const AudioContext = window.AudioContext || (window as any).webkitAudioContext
    if (!AudioContext) return
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()

    osc.type = severity === 'critical' ? 'sawtooth' : 'sine'
    osc.frequency.setValueAtTime(severity === 'critical' ? 587.33 : 440, ctx.currentTime)
    osc.frequency.exponentialRampToValueAtTime(severity === 'critical' ? 880 : 659.25, ctx.currentTime + 0.15)

    gain.gain.setValueAtTime(0.18, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4)

    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + 0.45)
  } catch (e) {
    console.debug('Audio chime error:', e)
  }
}

export default function EventFollowPage() {
  const { venueId } = useParams<{ venueId: string }>()

  // Data states
  const [venue, setVenue] = useState<any>(null)
  const [occupancy, setOccupancy] = useState<any>(null)
  const [flow, setFlow] = useState<any>(null)
  const [forecast, setForecast] = useState<any>(null)
  const [gates, setGates] = useState<any[]>([])
  const [alerts, setAlerts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  // User notification & follow states
  const [isFollowing, setIsFollowing] = useState<boolean>(() => {
    return localStorage.getItem(`follow_${venueId}`) === 'true'
  })
  const [systemPermission, setSystemPermission] = useState<NotificationPermission>('default')
  const [testSent, setTestSent] = useState(false)
  const [soundEnabled, setSoundEnabled] = useState(true)
  const [copiedLink, setCopiedLink] = useState(false)
  const [lastNotificationAlert, setLastNotificationAlert] = useState<string>('')

  const lastStateRef = useRef<string>('')

  // 1. Initial Load & Service Worker Registration
  useEffect(() => {
    registerServiceWorker()
    setSystemPermission(getSystemNotificationPermission())
  }, [])

  const fetchData = async () => {
    if (!venueId) return
    try {
      const [venueRes, occRes, flowRes, fcRes, gatesRes, alertsRes] = await Promise.all([
        venueApi.get(venueId),
        monitorApi.occupancy(venueId),
        monitorApi.flow(venueId, 60),
        monitorApi.forecast(venueId),
        gateApi.list(venueId),
        monitorApi.alerts(venueId, false),
      ])
      setVenue(venueRes)
      setOccupancy(occRes)
      setFlow(flowRes)
      setForecast(fcRes)
      setGates(gatesRes)
      setAlerts(alertsRes)
    } catch (err) {
      console.error('Failed to fetch event data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 4000)
    return () => clearInterval(interval)
  }, [venueId])

  // 2. WebSocket Real-time Listener
  useEffect(() => {
    if (!venueId) return
    return connectWebSocket(venueId, (message) => {
      if (message.type === 'state_update') {
        if (message.occupancy) setOccupancy((prev: any) => ({ ...prev, ...message.occupancy }))
        if (message.flow) setFlow((prev: any) => ({ ...prev, ...message.flow }))
        if (message.forecast) setForecast((prev: any) => ({ ...prev, ...message.forecast }))
      } else if (message.type === 'alert' && message.data) {
        setAlerts((prev) => [message.data, ...prev.filter((a) => a.id !== message.data.id)])
      }
    })
  }, [venueId])

  // Tracking refs for silent timeline vs urgent alarm separation
  const lastTimelineTimeRef = useRef<number>(0)
  const lastTimelinePercentRef = useRef<number>(-1)
  const lastAlertLevelRef = useRef<'NORMAL' | 'WARNING' | 'CRITICAL'>('NORMAL')
  const lastAlertTimeRef = useRef<number>(0)

  // 3A. Persistent Silent Live Timeline Notification (Flipkart / Delivery-Tracker Style)
  // Updates smoothly in-place in the notification drawer WITHOUT buzzing, ringing, or creating multiple cards
  useEffect(() => {
    if (!venue || !occupancy || !isFollowing) return

    const now = Date.now()
    const percent = occupancy.percentage || 0
    const currentCount = occupancy.current_occupancy || 0
    const cap = venue.effective_capacity || occupancy.effective_capacity || 1000
    const timeToCap = forecast?.time_to_capacity_minutes ?? null
    const netInflow = flow?.net_inflow_per_min ?? (forecast?.net_inflow_rate || 0)

    // Update timeline if at least 10 seconds have passed OR percent changed by >= 1%
    const timeElapsed = now - lastTimelineTimeRef.current >= 10000
    const percentChanged = Math.abs(percent - lastTimelinePercentRef.current) >= 1

    if (timeElapsed || percentChanged) {
      lastTimelineTimeRef.current = now
      lastTimelinePercentRef.current = percent

      updateLiveTimelineNotification(
        venue.name,
        percent,
        currentCount,
        cap,
        timeToCap,
        netInflow
      )
    }
  }, [
    occupancy?.percentage,
    occupancy?.current_occupancy,
    forecast?.time_to_capacity_minutes,
    flow?.net_inflow_per_min,
    isFollowing,
    venue?.name
  ])

  // 3B. Separate Urgent Alarms (Moderate / Warning & Critical)
  // Only fires when crossing a threshold boundary (e.g. crossing 75% or 90%) with 5-min cooldown
  useEffect(() => {
    if (!venue || !occupancy || !isFollowing) return

    const now = Date.now()
    const percent = occupancy.percentage || 0
    const timeToCap = forecast?.time_to_capacity_minutes ?? null
    const inflow = forecast?.net_inflow_rate ?? 0

    let currentLevel: 'NORMAL' | 'WARNING' | 'CRITICAL' = 'NORMAL'
    if (percent >= 90) {
      currentLevel = 'CRITICAL'
    } else if (percent >= 75 || (timeToCap !== null && timeToCap <= 15 && inflow > 10)) {
      currentLevel = 'WARNING'
    }

    const prevLevel = lastAlertLevelRef.current
    const cooldownPassed = now - lastAlertTimeRef.current >= 300000 // 5 minutes cooldown

    if (currentLevel !== 'NORMAL' && (currentLevel !== prevLevel || cooldownPassed)) {
      lastAlertLevelRef.current = currentLevel
      lastAlertTimeRef.current = now

      if (currentLevel === 'CRITICAL') {
        const msg = `🚨 Critical Capacity Alarm: ${venue.name} has reached ${percent}% occupancy! Area expected to reach max limit in ~${Math.round(timeToCap || 5)} minutes. Expect gate holds.`
        if (soundEnabled) playAlertChime('critical')
        sendUrgentAlertNotification(venue.name, 'CRITICAL', msg)
      } else if (currentLevel === 'WARNING') {
        const msg = `⚠️ Moderate Rush Warning: ${venue.name} is now ${percent}% full. High inflow speed detected (+${inflow}/min). Queues forming at entry gates.`
        if (soundEnabled) playAlertChime('warning')
        sendUrgentAlertNotification(venue.name, 'WARNING', msg)
      }
    } else if (currentLevel === 'NORMAL' && prevLevel !== 'NORMAL') {
      lastAlertLevelRef.current = 'NORMAL'
    }
  }, [
    occupancy?.percentage,
    forecast?.time_to_capacity_minutes,
    forecast?.net_inflow_rate,
    isFollowing,
    soundEnabled,
    venue?.name
  ])

  // 4. Toggle Follow Handler
  const handleToggleFollow = async () => {
    const nextState = !isFollowing
    setIsFollowing(nextState)
    localStorage.setItem(`follow_${venueId}`, String(nextState))

    if (nextState) {
      const granted = await requestSystemNotificationPermission()
      setSystemPermission(getSystemNotificationPermission())
      if (granted && venue && occupancy) {
        const percent = occupancy.percentage || 0
        const currentCount = occupancy.current_occupancy || 0
        const cap = venue.effective_capacity || occupancy.effective_capacity || 1000
        const timeToCap = forecast?.time_to_capacity_minutes ?? null
        const netInflow = flow?.net_inflow_per_min ?? (forecast?.net_inflow_rate || 0)

        await updateLiveTimelineNotification(
          venue.name,
          percent,
          currentCount,
          cap,
          timeToCap,
          netInflow
        )
      }
      if (soundEnabled) playAlertChime('info')
    }
  }

  // 5. Test Notification Trigger
  const handleSendTestNotification = async () => {
    let granted = systemPermission === 'granted'
    if (!granted) {
      granted = await requestSystemNotificationPermission()
      setSystemPermission(getSystemNotificationPermission())
    }
    if (granted) {
      await sendTestNotification(venue?.name || 'Current Venue')
      if (soundEnabled) playAlertChime('info')
      setTestSent(true)
      setTimeout(() => setTestSent(false), 3500)
    }
  }

  // 5. Copy Event Link
  const handleCopyLink = () => {
    if (typeof window !== 'undefined') {
      navigator.clipboard.writeText(window.location.href)
      setCopiedLink(true)
      setTimeout(() => setCopiedLink(false), 2500)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col items-center justify-center p-4">
        <div className="w-10 h-10 border-3 border-blue-600 border-t-transparent rounded-full animate-spin mb-3" />
        <p className="text-slate-500 text-sm font-medium">Connecting to live crowd intelligence feed...</p>
      </div>
    )
  }

  if (!venue) {
    return (
      <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col items-center justify-center p-4">
        <h2 className="text-xl font-bold text-slate-900 mb-2">Event Not Found</h2>
        <p className="text-slate-500 text-sm mb-6">The requested event feed is unavailable or has ended.</p>
        <Link to="/" className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white font-semibold text-xs">
          Browse All Events
        </Link>
      </div>
    )
  }

  const currentCount = occupancy?.current_occupancy ?? 0
  const capacity = venue.effective_capacity ?? (occupancy?.effective_capacity || 1000)
  const percent = Math.min(100, Math.round((currentCount / (capacity || 1)) * 100))
  const netInflow = flow?.net_inflow_per_min ?? (forecast?.net_inflow_rate || 0)
  const timeToCapacity = forecast?.time_to_capacity_minutes ?? null

  // Status colors & text — Using Admin style badges
  let statusBadge = {
    bg: 'bg-emerald-50 border-emerald-200 text-emerald-800',
    dot: 'bg-emerald-500',
    label: '🟢 Safe Entry — Smooth Flow',
    desc: 'Lines are moving steadily. No significant delays at entry gates.',
  }

  if (percent >= 90) {
    statusBadge = {
      bg: 'bg-rose-50 border-rose-200 text-rose-800',
      dot: 'bg-rose-600',
      label: '🔴 Critical Capacity Reached',
      desc: 'Venue is near maximum capacity. Entrance gates may be metering or holding arrivals.',
    }
  } else if (percent >= 75) {
    statusBadge = {
      bg: 'bg-amber-50 border-amber-200 text-amber-900',
      dot: 'bg-amber-600',
      label: '🟡 High Rush — Heavy Inflow',
      desc: 'Rapidly filling up. Expect moderate queues at main gates.',
    }
  } else if (timeToCapacity && timeToCapacity <= 20 && netInflow > 5) {
    statusBadge = {
      bg: 'bg-orange-50 border-orange-200 text-orange-900',
      dot: 'bg-orange-600',
      label: '🟠 Surge Incoming',
      desc: `High net crowd velocity! Projected to be full in approximately ${Math.round(timeToCapacity)} minutes.`,
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans w-full max-w-full overflow-x-hidden antialiased">
      {/* Top Floating Live Banner for Active Followers */}
      {isFollowing && (
        <div className="bg-blue-600 text-white px-4 py-2 text-xs font-semibold flex items-center justify-between sticky top-0 z-50 shadow-xs">
          <div className="flex items-center gap-2 max-w-[80%] truncate">
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-300 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400"></span>
            </span>
            <span className="truncate">
              <strong>LIVE FOLLOWING:</strong> Continuous crowd updates and time-to-full alerts are active.
            </span>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={() => setSoundEnabled(!soundEnabled)}
              className="p-1 rounded hover:bg-white/10 transition-colors"
              title={soundEnabled ? 'Mute Chime' : 'Enable Chime'}
            >
              {soundEnabled ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5 text-white/60" />}
            </button>
            <button
              onClick={handleToggleFollow}
              className="text-[11px] underline text-blue-100 hover:text-white shrink-0"
            >
              Unfollow
            </button>
          </div>
        </div>
      )}

      {/* Top Header — Matching Admin Look */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40 w-full shadow-xs">
        <div className="w-full max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <Link
              to="/"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors"
            >
              <ChevronLeft className="w-4 h-4 text-slate-400" />
              <span>All Events</span>
            </Link>

            <div className="h-4 w-px bg-slate-200 hidden sm:block" />

            <div className="hidden sm:flex items-center gap-2">
              <div className="w-6 h-6 rounded bg-blue-600 text-white flex items-center justify-center font-bold text-xs">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <span className="text-xs font-bold text-slate-900 tracking-tight">AI CROWD INTELLIGENCE</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyLink}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-200 text-xs font-medium text-slate-700 transition-colors"
              title="Share Event Link"
            >
              {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Share2 className="w-3.5 h-3.5" />}
              <span>{copiedLink ? 'Copied' : 'Share'}</span>
            </button>

            <Link
              to={`/venues/${venueId}/dashboard`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-50 hover:bg-blue-100 border border-blue-200 text-xs font-semibold text-blue-700 transition-colors"
            >
              <Layers className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Admin Panel</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Main Body */}
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6 w-full flex-1 flex flex-col gap-5">
        {/* Event Hero Card */}
        <div className="rounded-xl bg-white border border-slate-200 p-6 sm:p-7 shadow-xs">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
            <div>
              <div className="inline-flex items-center gap-1.5 text-xs font-bold text-blue-600 uppercase tracking-wider mb-1">
                <Activity className="w-3.5 h-3.5" />
                <span>Live Event Stream</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">{venue.name}</h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
                {venue.location || 'Monitored Venue'} • Area: {venue.area_sqm} m² • Real-Time AI Tracking Active
              </p>
            </div>

            {/* Follow / Notification Action Button */}
            <button
              onClick={handleToggleFollow}
              className={`inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg font-bold text-xs sm:text-sm transition-all shadow-xs shrink-0 ${
                isFollowing
                  ? 'bg-emerald-600 hover:bg-emerald-700 text-white ring-2 ring-emerald-300'
                  : 'bg-blue-600 hover:bg-blue-700 text-white'
              }`}
            >
              {isFollowing ? (
                <>
                  <BellRing className="w-4 h-4 animate-bounce" />
                  <span>Following Live Alerts</span>
                </>
              ) : (
                <>
                  <Bell className="w-4 h-4" />
                  <span>Follow &amp; Get Rush Alerts</span>
                </>
              )}
            </button>
          </div>

          {/* Current Status Pill */}
          <div className={`rounded-lg border p-3.5 flex items-start gap-3 ${statusBadge.bg}`}>
            <span className={`w-2.5 h-2.5 rounded-full mt-1 shrink-0 ${statusBadge.dot}`} />
            <div>
              <div className="font-bold text-sm leading-tight">{statusBadge.label}</div>
              <p className="text-xs mt-0.5 opacity-90">{statusBadge.desc}</p>
            </div>
          </div>
        </div>

        {/* Device System Notifications Panel (Windows Action Center & Android Notification Drawer) */}
        <div className="rounded-xl bg-white border border-slate-200 p-4 sm:p-5 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div
              className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                systemPermission === 'granted' ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'
              }`}
            >
              {systemPermission === 'granted' ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              ) : (
                <Smartphone className="w-5 h-5 text-blue-600" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm text-slate-900">
                  {systemPermission === 'granted'
                    ? 'Device System Notifications: Active'
                    : 'Enable Device System Notifications'}
                </span>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full font-bold border ${
                    systemPermission === 'granted'
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : 'bg-amber-50 text-amber-800 border-amber-200'
                  }`}
                >
                  {systemPermission === 'granted' ? 'NOTIFICATION SHADE ACTIVE' : 'SETUP REQUIRED'}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5 max-w-xl">
                {systemPermission === 'granted'
                  ? 'Active: Live timeline quietly updates crowd status in-place in your notification drawer (zero buzz spam). Separate audible alarms ring only when crowd crosses 75% or 90% capacity.'
                  : 'Receive real-time push alerts in your phone notification shade or Windows action center even when using other apps or when the browser is minimized.'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {systemPermission !== 'granted' ? (
              <button
                type="button"
                onClick={handleSendTestNotification}
                className="px-3.5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition-all shadow-xs"
              >
                Enable System Alerts
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSendTestNotification}
                disabled={testSent}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 rounded-lg text-xs font-semibold transition-all"
              >
                {testSent ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Bell className="w-3.5 h-3.5 text-blue-600" />}
                <span>{testSent ? 'Alert Sent to OS!' : 'Send Test Notification'}</span>
              </button>
            )}
          </div>
        </div>

        {/* TIME TO FULL & KEY PREDICTIONS */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Card 1: Estimated Time to Full (Hero Metric) */}
          <div className="rounded-xl bg-white border border-slate-200 p-5 flex flex-col justify-between shadow-xs">
            <div className="flex items-center justify-between text-xs font-bold text-slate-500 mb-2">
              <span className="flex items-center gap-1.5">
                <Clock className="w-4 h-4 text-blue-600" />
                ESTIMATED TIME TO FULL
              </span>
              <span className="text-[10px] bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded-full font-bold">
                AI PREDICTED
              </span>
            </div>

            <div className="my-2">
              {percent >= 100 ? (
                <div className="text-2xl sm:text-3xl font-extrabold text-rose-600">100% CAPACITY</div>
              ) : timeToCapacity !== null && timeToCapacity > 0 ? (
                <div className="flex items-baseline gap-1.5">
                  <span className="text-3xl sm:text-4xl font-extrabold text-amber-600 tracking-tight">
                    ~{Math.round(timeToCapacity)}
                  </span>
                  <span className="text-sm font-semibold text-slate-500">Minutes</span>
                </div>
              ) : netInflow <= 0 ? (
                <div className="text-xl sm:text-2xl font-bold text-emerald-700">NO RUSH EXPECTED</div>
              ) : (
                <div className="text-xl font-bold text-slate-500">Calculating...</div>
              )}

              <p className="text-xs text-slate-500 mt-1">
                {percent >= 100
                  ? 'Area is already at capacity. Entry queues may be held.'
                  : timeToCapacity !== null && timeToCapacity > 0
                  ? `At current velocity (${netInflow > 0 ? '+' + netInflow : netInflow}/min), area reaches capacity soon.`
                  : 'Outflow matches or exceeds inflow. Capacity is stable.'}
              </p>
            </div>

            {/* Micro visual progress */}
            <div className="w-full bg-slate-100 rounded-full h-1.5 mt-2 overflow-hidden border border-slate-200">
              <div
                className={`h-full transition-all duration-500 ${
                  percent >= 90 ? 'bg-rose-500' : percent >= 75 ? 'bg-amber-500' : 'bg-emerald-500'
                }`}
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>

          {/* Card 2: Current Headcount & Capacity */}
          <div className="rounded-xl bg-white border border-slate-200 p-5 flex flex-col justify-between shadow-xs">
            <div className="flex items-center justify-between text-xs font-bold text-slate-500 mb-2">
              <span className="flex items-center gap-1.5">
                <Users className="w-4 h-4 text-emerald-600" />
                CURRENT OCCUPANCY
              </span>
              <span className="text-xs font-bold text-slate-900">{percent}% FILLED</span>
            </div>

            <div className="my-2">
              <div className="flex items-baseline gap-2">
                <span className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight font-mono">
                  {currentCount.toLocaleString()}
                </span>
                <span className="text-sm font-medium text-slate-500">/ {capacity.toLocaleString()} Max</span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                {Math.max(0, capacity - currentCount).toLocaleString()} more people can enter before reaching limit.
              </p>
            </div>

            <div className="flex items-center justify-between text-[11px] text-slate-500 pt-2 border-t border-slate-100 font-mono">
              <span>Warning Limit: {Math.round(capacity * (venue.warning_threshold || 0.75))}</span>
              <span>Total Entries: {venue.total_entries || currentCount}</span>
            </div>
          </div>

          {/* Card 3: Live Flow Velocity */}
          <div className="rounded-xl bg-white border border-slate-200 p-5 flex flex-col justify-between shadow-xs">
            <div className="flex items-center justify-between text-xs font-bold text-slate-500 mb-2">
              <span className="flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-blue-600" />
                NET FLOW SPEED
              </span>
              <span className="text-[10px] text-slate-500 font-semibold bg-slate-100 px-2 py-0.5 rounded">60s WINDOW</span>
            </div>

            <div className="my-2">
              <div className="flex items-baseline gap-1.5">
                <span
                  className={`text-3xl sm:text-4xl font-extrabold tracking-tight font-mono ${
                    netInflow > 0 ? 'text-amber-600' : 'text-emerald-600'
                  }`}
                >
                  {netInflow > 0 ? `+${netInflow}` : netInflow}
                </span>
                <span className="text-sm font-medium text-slate-500">persons / min</span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Inflow: <span className="text-emerald-700 font-bold">+{flow?.entry_rate_per_min || 0}/min</span> •
                Outflow: <span className="text-blue-700 font-bold">-{flow?.exit_rate_per_min || 0}/min</span>
              </p>
            </div>

            <div className="text-[11px] text-slate-500 pt-2 border-t border-slate-100 flex items-center gap-1">
              {netInflow > 0 ? (
                <>
                  <TrendingUp className="w-3.5 h-3.5 text-amber-600" />
                  <span>Area is steadily filling</span>
                </>
              ) : (
                <>
                  <TrendingDown className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Crowd is dispersing or steady</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Gate Status & Recommendations */}
        <div className="rounded-xl bg-white border border-slate-200 p-5 sm:p-6 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-bold text-slate-900">Gate Check-Points &amp; Queue Status</h2>
              <p className="text-xs text-slate-500">Live AI tracking across entrance and exit lines</p>
            </div>
            <span className="text-xs bg-slate-100 text-slate-700 border border-slate-200 px-2.5 py-1 rounded-full font-bold">
              {gates.length} Gates Active
            </span>
          </div>

          {gates.length === 0 ? (
            <div className="text-center py-6 text-slate-400 text-xs">No gates registered yet.</div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {gates.map((g) => {
                const isEntry = g.gate_type?.includes('ENTRY')
                return (
                  <div
                    key={g.id}
                    className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-8 h-8 rounded-md flex items-center justify-center font-bold text-xs ${
                          isEntry ? 'bg-emerald-100 text-emerald-800' : 'bg-blue-100 text-blue-800'
                        }`}
                      >
                        {isEntry ? 'IN' : 'OUT'}
                      </div>
                      <div>
                        <div className="font-bold text-xs sm:text-sm text-slate-900">{g.name}</div>
                        <div className="text-[11px] text-slate-500 font-mono">
                          {isEntry ? `Total In: ${g.entry_count || 0}` : `Total Out: ${g.exit_count || 0}`}
                        </div>
                      </div>
                    </div>

                    <div className="text-right">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold border ${
                          g.status === 'ACTIVE'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : 'bg-slate-200 text-slate-600 border-slate-300'
                        }`}
                      >
                        {g.status === 'ACTIVE' ? 'ONLINE' : 'STANDBY'}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Live Active Official Announcements */}
        <div className="rounded-xl bg-white border border-slate-200 p-5 sm:p-6 shadow-xs">
          <h2 className="text-base font-bold text-slate-900 mb-0.5 flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-amber-600" />
            <span>Official Advisories &amp; Live Alerts</span>
          </h2>
          <p className="text-xs text-slate-500 mb-3.5">Real-time alerts broadcasted to all followers</p>

          {alerts.length === 0 ? (
            <div className="p-3.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2 font-medium">
              <Check className="w-4 h-4 text-emerald-600" />
              <span>All clear. Normal pedestrian flow. No active bottlenecks or gate closures reported.</span>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {alerts.map((a) => (
                <div
                  key={a.id}
                  className={`p-3 rounded-lg border flex items-start gap-2.5 text-xs ${
                    a.severity === 'CRITICAL'
                      ? 'bg-rose-50 border-rose-200 text-rose-900'
                      : 'bg-amber-50 border-amber-200 text-amber-950'
                  }`}
                >
                  <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold leading-tight">{a.message}</div>
                    <div className="text-[10px] text-slate-500 mt-1 font-mono">
                      Reported: {new Date(a.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-5 text-center text-xs text-slate-500">
        AI Crowd Intelligence • Real-time Safety &amp; Inflow Monitoring Platform
      </footer>
    </div>
  )
}

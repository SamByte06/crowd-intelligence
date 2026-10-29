import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Bell,
  BellRing,
  BellOff,
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
  Sparkles,
  Info
} from 'lucide-react'
import { venueApi, gateApi, monitorApi, connectWebSocket } from '../services/api'

// Gentle synthesized audio chime using Web Audio API (Zero external mp3 needed)
function playAlertChime(severity: 'warning' | 'critical' | 'info') {
  try {
    const AudioContext = window.AudioContext || (window as any).webkitAudioContext
    if (!AudioContext) return
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()

    osc.type = severity === 'critical' ? 'sawtooth' : 'sine'
    osc.frequency.setValueAtTime(severity === 'critical' ? 587.33 : 440, ctx.currentTime) // D5 or A4
    osc.frequency.exponentialRampToValueAtTime(severity === 'critical' ? 880 : 659.25, ctx.currentTime + 0.15)

    gain.gain.setValueAtTime(0.2, ctx.currentTime)
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
  const [notificationsGranted, setNotificationsGranted] = useState<boolean>(() => {
    return typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'granted'
  })
  const [soundEnabled, setSoundEnabled] = useState(true)
  const [copiedLink, setCopiedLink] = useState(false)
  const [lastNotificationAlert, setLastNotificationAlert] = useState<string>('')

  // Poll timer ref
  const lastStateRef = useRef<string>('')

  // 1. Initial Load
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

  // 3. Trigger Continuous Notifications when user is following
  useEffect(() => {
    if (!venue || !occupancy || !forecast || !isFollowing) return

    const percent = occupancy.percentage || 0
    let alertMsg = ''
    let severity: 'warning' | 'critical' | 'info' = 'info'

    if (percent >= 90) {
      alertMsg = `🚨 CRITICAL ALERT: ${venue.name} is ${percent}% FULL! Expected to reach capacity in ${forecast.time_to_capacity_minutes || 5} mins. Entry severely restricted!`
      severity = 'critical'
    } else if (percent >= 75) {
      alertMsg = `⚠️ RUSH WARNING: ${venue.name} is now ${percent}% full. High inflow detected. Expect delays at entry gates.`
      severity = 'warning'
    } else if (forecast.time_to_capacity_minutes && forecast.time_to_capacity_minutes <= 15 && forecast.net_inflow_rate > 10) {
      alertMsg = `⏱️ SURGE ALERT: ${venue.name} is filling up quickly. Projected to reach 100% capacity in ~${forecast.time_to_capacity_minutes} minutes!`
      severity = 'warning'
    }

    if (alertMsg && alertMsg !== lastNotificationAlert && alertMsg !== lastStateRef.current) {
      lastStateRef.current = alertMsg
      setLastNotificationAlert(alertMsg)

      // Sound chime
      if (soundEnabled) {
        playAlertChime(severity)
      }

      // Native Web Browser Notification (even if user is in background or phone screen)
      if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'granted') {
        try {
          new Notification(`Live Alert: ${venue.name}`, {
            body: alertMsg,
            icon: '/favicon.ico',
            tag: 'crowd-status-alert',
          })
        } catch (e) {
          console.debug('Notification push error:', e)
        }
      }
    }
  }, [occupancy?.percentage, forecast?.time_to_capacity_minutes, isFollowing, soundEnabled, venue?.name])

  // 4. Toggle Follow Handler
  const handleToggleFollow = async () => {
    const nextState = !isFollowing
    setIsFollowing(nextState)
    localStorage.setItem(`follow_${venueId}`, String(nextState))

    if (nextState) {
      // Request native browser permission
      if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission !== 'granted') {
        try {
          const perm = await Notification.requestPermission()
          setNotificationsGranted(perm === 'granted')
        } catch (e) {
          console.debug('Permission request error:', e)
        }
      }
      if (soundEnabled) playAlertChime('info')
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
      <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col items-center justify-center p-4">
        <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-slate-400 font-medium">Connecting to live crowd intelligence feed...</p>
      </div>
    )
  }

  if (!venue) {
    return (
      <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col items-center justify-center p-4">
        <h2 className="text-2xl font-bold text-white mb-2">Event Not Found</h2>
        <p className="text-slate-400 mb-6">The requested event feed is unavailable or has ended.</p>
        <Link to="/events" className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-white font-semibold">
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
  const timeToWarning = forecast?.time_to_warning_minutes ?? null

  // Status colors & text
  let statusBadge = {
    bg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
    dot: 'bg-emerald-400',
    label: '🟢 Normal Flow — Safe Entry',
    desc: 'Lines are moving swiftly. No significant delay expected at entrance.',
  }

  if (percent >= 90) {
    statusBadge = {
      bg: 'bg-rose-500/15 border-rose-500/40 text-rose-400 animate-pulse',
      dot: 'bg-rose-500',
      label: '🔴 Critical Capacity Reached',
      desc: 'Venue is near maximum limit! Gates may temporarily hold arrivals.',
    }
  } else if (percent >= 75) {
    statusBadge = {
      bg: 'bg-amber-500/15 border-amber-500/40 text-amber-400',
      dot: 'bg-amber-400',
      label: '🟡 High Rush — Heavy Inflow',
      desc: 'Rapidly filling up. Moderate queues formed at major entry gates.',
    }
  } else if (timeToCapacity && timeToCapacity <= 20 && netInflow > 5) {
    statusBadge = {
      bg: 'bg-orange-500/15 border-orange-500/40 text-orange-400',
      dot: 'bg-orange-400',
      label: '🟠 Surge Incoming',
      desc: `High net crowd velocity! Projected to be full in approximately ${timeToCapacity} mins.`,
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-blue-600 selection:text-white">
      {/* Top Floating Live Banner for Followers */}
      {isFollowing && (
        <div className="bg-gradient-to-r from-blue-700 via-indigo-700 to-purple-800 text-white px-4 py-2.5 text-xs sm:text-sm font-semibold flex items-center justify-between sticky top-0 z-50 shadow-md">
          <div className="flex items-center gap-2 max-w-[80%] truncate">
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
            <span className="truncate">
              <strong>LIVE FOLLOWING:</strong> Real-time crowd updates and time-to-full alerts are active on this device.
            </span>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={() => setSoundEnabled(!soundEnabled)}
              className="p-1 rounded hover:bg-white/10 transition-colors"
              title={soundEnabled ? 'Mute Chime' : 'Enable Chime'}
            >
              {soundEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4 text-white/50" />}
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

      {/* Header Navigation */}
      <header className="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-4xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link
            to="/events"
            className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-white transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
            <span>All Monitored Events</span>
          </Link>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyLink}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-xs font-medium text-slate-300 transition-colors"
              title="Share Event Link"
            >
              {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Share2 className="w-3.5 h-3.5" />}
              <span>{copiedLink ? 'Copied!' : 'Share'}</span>
            </button>

            <Link
              to={`/venues/${venueId}/dashboard`}
              className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/30 text-xs font-medium text-blue-300 transition-colors"
            >
              <span>Admin Panel</span>
              <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
        </div>
      </header>

      {/* Main Body */}
      <main className="max-w-4xl mx-auto px-4 py-6 w-full flex-1 flex flex-col gap-6">
        {/* Event Hero Card */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-b from-slate-900 to-slate-900/70 border border-slate-800 p-6 sm:p-8 shadow-xl">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-blue-400 uppercase tracking-wider mb-1">
                <Compass className="w-3.5 h-3.5" />
                <span>Live Event Crowd Intelligence</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">{venue.name}</h1>
              <p className="text-sm text-slate-400 mt-1">
                Area: {venue.area_sqm} m² • Real-Time AI Camera Ingestion Active
              </p>
            </div>

            {/* Follow / Notification Action Button */}
            <button
              onClick={handleToggleFollow}
              className={`flex items-center justify-center gap-2 px-5 py-3 rounded-xl font-bold text-sm transition-all shadow-lg shrink-0 ${
                isFollowing
                  ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-900/30 ring-2 ring-emerald-400/30'
                  : 'bg-blue-600 hover:bg-blue-500 text-white shadow-blue-900/40 hover:scale-[1.02]'
              }`}
            >
              {isFollowing ? (
                <>
                  <BellRing className="w-4 h-4 animate-bounce" />
                  <span>Following Live Updates</span>
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
          <div className={`rounded-xl border p-3.5 flex items-start gap-3 ${statusBadge.bg}`}>
            <span className={`w-3 h-3 rounded-full mt-0.5 shrink-0 ${statusBadge.dot}`} />
            <div>
              <div className="font-bold text-sm sm:text-base leading-tight">{statusBadge.label}</div>
              <p className="text-xs sm:text-sm text-slate-300 mt-0.5 opacity-90">{statusBadge.desc}</p>
            </div>
          </div>
        </div>

        {/* TIME TO FULL & KEY PREDICTIONS */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Card 1: Estimated Time to Full (Hero Metric) */}
          <div className="rounded-2xl bg-slate-900/80 border border-slate-800 p-5 flex flex-col justify-between relative overflow-hidden group hover:border-slate-700 transition-all shadow-md">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-400 mb-2">
              <span className="flex items-center gap-1.5">
                <Clock className="w-4 h-4 text-blue-400" />
                ESTIMATED TIME TO FULL
              </span>
              <span className="text-[10px] bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded-full border border-blue-500/20 font-bold">
                AI PREDICTED
              </span>
            </div>

            <div className="my-2">
              {percent >= 100 ? (
                <div className="text-2xl sm:text-3xl font-extrabold text-rose-400">100% CAPACITY</div>
              ) : timeToCapacity !== null && timeToCapacity > 0 ? (
                <div className="flex items-baseline gap-1.5">
                  <span className="text-3xl sm:text-4xl font-extrabold text-amber-400 tracking-tight">
                    ~{Math.round(timeToCapacity)}
                  </span>
                  <span className="text-sm font-semibold text-slate-400">Minutes</span>
                </div>
              ) : netInflow <= 0 ? (
                <div className="text-2xl font-bold text-emerald-400">NO RUSH EXPECTED</div>
              ) : (
                <div className="text-2xl font-bold text-slate-300">Calculating...</div>
              )}

              <p className="text-xs text-slate-400 mt-1">
                {percent >= 100
                  ? 'Area is already full. Please wait outside.'
                  : timeToCapacity !== null && timeToCapacity > 0
                  ? `At current velocity (${netInflow > 0 ? '+' + netInflow : netInflow}/min), area reaches capacity soon.`
                  : 'Outflow exceeds or matches inflow. Capacity is stable.'}
              </p>
            </div>

            {/* Micro visual progress */}
            <div className="w-full bg-slate-800 rounded-full h-1.5 mt-2 overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${
                  percent >= 90 ? 'bg-rose-500' : percent >= 75 ? 'bg-amber-500' : 'bg-emerald-500'
                }`}
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>

          {/* Card 2: Current Headcount & Capacity */}
          <div className="rounded-2xl bg-slate-900/80 border border-slate-800 p-5 flex flex-col justify-between shadow-md">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-400 mb-2">
              <span className="flex items-center gap-1.5">
                <Users className="w-4 h-4 text-emerald-400" />
                CURRENT CAPACITY
              </span>
              <span className="text-xs font-bold text-slate-300">{percent}% FILLED</span>
            </div>

            <div className="my-2">
              <div className="flex items-baseline gap-2">
                <span className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
                  {currentCount.toLocaleString()}
                </span>
                <span className="text-sm font-medium text-slate-400">/ {capacity.toLocaleString()} Max</span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                {Math.max(0, capacity - currentCount).toLocaleString()} more people can comfortably enter before capacity.
              </p>
            </div>

            <div className="flex items-center justify-between text-[11px] text-slate-400 pt-2 border-t border-slate-800">
              <span>Warning Threshold: {Math.round(capacity * (venue.warning_threshold || 0.75))}</span>
              <span>Total Entries: {venue.total_entries || currentCount}</span>
            </div>
          </div>

          {/* Card 3: Live Flow Velocity */}
          <div className="rounded-2xl bg-slate-900/80 border border-slate-800 p-5 flex flex-col justify-between shadow-md">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-400 mb-2">
              <span className="flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-indigo-400" />
                LIVE FLOW SPEED
              </span>
              <span className="text-[10px] text-slate-400 font-semibold">60s WINDOW</span>
            </div>

            <div className="my-2">
              <div className="flex items-baseline gap-2">
                <span
                  className={`text-3xl sm:text-4xl font-extrabold tracking-tight ${
                    netInflow > 0 ? 'text-amber-400' : 'text-emerald-400'
                  }`}
                >
                  {netInflow > 0 ? `+${netInflow}` : netInflow}
                </span>
                <span className="text-sm font-medium text-slate-400">persons / min</span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Inflow: <span className="text-emerald-400 font-semibold">+{flow?.entry_rate_per_min || 0}/min</span> •
                Outflow: <span className="text-blue-400 font-semibold">-{flow?.exit_rate_per_min || 0}/min</span>
              </p>
            </div>

            <div className="text-[11px] text-slate-400 pt-2 border-t border-slate-800 flex items-center gap-1">
              {netInflow > 0 ? (
                <>
                  <TrendingUp className="w-3.5 h-3.5 text-amber-400" />
                  <span>Area is filling up steadily</span>
                </>
              ) : (
                <>
                  <TrendingDown className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Crowd is dispersing or steady</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Gate Status & Best Recommendations */}
        <div className="rounded-2xl bg-slate-900/80 border border-slate-800 p-6 shadow-md">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
                <span>Gate Status &amp; Recommendations</span>
              </h2>
              <p className="text-xs text-slate-400">Live camera headcount at entrance and exit check-points</p>
            </div>
            <span className="text-xs bg-slate-800 text-slate-300 px-2.5 py-1 rounded-full font-semibold">
              {gates.length} Gates Monitored
            </span>
          </div>

          {gates.length === 0 ? (
            <div className="text-center py-6 text-slate-500 text-sm">No gate streams registered yet.</div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {gates.map((g) => {
                const isEntry = g.gate_type?.includes('ENTRY')
                return (
                  <div
                    key={g.id}
                    className="p-4 rounded-xl bg-slate-950/70 border border-slate-800/80 flex items-center justify-between hover:border-slate-700 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-9 h-9 rounded-lg flex items-center justify-center font-bold text-xs ${
                          isEntry ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                        }`}
                      >
                        {isEntry ? 'IN' : 'OUT'}
                      </div>
                      <div>
                        <div className="font-semibold text-sm text-white">{g.name}</div>
                        <div className="text-xs text-slate-400">
                          {isEntry ? `Total Entered: ${g.entry_count || 0}` : `Total Exited: ${g.exit_count || 0}`}
                        </div>
                      </div>
                    </div>

                    <div className="text-right">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[11px] font-bold ${
                          g.status === 'ACTIVE'
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                            : 'bg-slate-800 text-slate-400'
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

        {/* Live Active Incident & Rush Alerts */}
        <div className="rounded-2xl bg-slate-900/80 border border-slate-800 p-6 shadow-md">
          <h2 className="text-base sm:text-lg font-bold text-white mb-1 flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-amber-400" />
            <span>Active Official Announcements &amp; Advisories</span>
          </h2>
          <p className="text-xs text-slate-400 mb-4">Real-time alerts broadcasted to all followers</p>

          {alerts.length === 0 ? (
            <div className="p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20 text-emerald-300 text-sm flex items-center gap-2">
              <Check className="w-4 h-4 text-emerald-400" />
              <span>All clear. No active bottlenecks, congestion alarms, or gate closures reported.</span>
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {alerts.map((a) => (
                <div
                  key={a.id}
                  className={`p-3.5 rounded-xl border flex items-start gap-3 ${
                    a.severity === 'CRITICAL'
                      ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                      : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                  }`}
                >
                  <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-sm leading-tight">{a.message}</div>
                    <div className="text-[11px] text-slate-400 mt-1">
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
      <footer className="border-t border-slate-800/80 bg-slate-950 py-6 text-center text-xs text-slate-500">
        AI Crowd Intelligence &amp; Live Event Management • Real-time Safety Broadcast
      </footer>
    </div>
  )
}

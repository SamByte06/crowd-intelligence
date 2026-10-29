import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ShieldCheck,
  Users,
  Clock,
  ArrowRight,
  TrendingUp,
  SlidersHorizontal,
  ChevronRight,
  Sparkles,
  Activity,
  Layers
} from 'lucide-react'
import { venueApi, monitorApi } from '../services/api'

interface VenueWithStats {
  id: string
  name: string
  area_sqm: number
  location?: string
  effective_capacity: number
  current_occupancy: number
  percentage: number
  net_inflow_rate: number
  time_to_capacity_minutes: number | null
}

export default function PublicEventsList() {
  const [venues, setVenues] = useState<VenueWithStats[]>([])
  const [loading, setLoading] = useState(true)

  const fetchVenuesAndStats = async () => {
    try {
      const list = await venueApi.list()
      const enriched = await Promise.all(
        list.map(async (v: any) => {
          try {
            const [occ, fc] = await Promise.all([
              monitorApi.occupancy(v.id).catch(() => null),
              monitorApi.forecast(v.id).catch(() => null),
            ])
            const current = occ?.current_occupancy ?? v.current_occupancy ?? 0
            const cap = v.effective_capacity || occ?.effective_capacity || 1000
            const pct = Math.min(100, Math.round((current / (cap || 1)) * 100))

            return {
              id: v.id,
              name: v.name,
              location: v.location || 'Monitored Venue',
              area_sqm: v.area_sqm,
              effective_capacity: cap,
              current_occupancy: current,
              percentage: pct,
              net_inflow_rate: fc?.net_inflow_rate ?? 0,
              time_to_capacity_minutes: fc?.time_to_capacity_minutes ?? null,
            }
          } catch {
            return {
              id: v.id,
              name: v.name,
              location: v.location || 'Monitored Venue',
              area_sqm: v.area_sqm,
              effective_capacity: v.effective_capacity || 1000,
              current_occupancy: v.current_occupancy || 0,
              percentage: 0,
              net_inflow_rate: 0,
              time_to_capacity_minutes: null,
            }
          }
        })
      )
      setVenues(enriched)
    } catch (err) {
      console.error('Failed to load public venues:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchVenuesAndStats()
    const interval = setInterval(fetchVenuesAndStats, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans w-full max-w-full overflow-x-hidden antialiased">
      {/* Top Header — Matching Admin Style */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50 w-full shrink-0 shadow-xs">
        <div className="w-full max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between gap-4">
          {/* Brand & Subtitle */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center shadow-xs">
              <ShieldCheck className="w-5 h-5 text-white" />
            </div>
            <div className="flex flex-col leading-none">
              <span className="text-base font-extrabold tracking-tight text-slate-900">
                AI CROWD INTELLIGENCE
              </span>
              <span className="text-[9px] font-semibold tracking-wider text-slate-400 uppercase mt-0.5">
                PUBLIC ATTENDEE &amp; EVENT PORTAL
              </span>
            </div>
          </div>

          {/* Right Action: Admin Dashboard Switch */}
          <div className="flex items-center gap-2.5">
            <Link
              to="/dashboard"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 text-xs font-semibold transition-colors"
            >
              <Layers className="w-3.5 h-3.5 text-slate-600" />
              <span>Admin Dashboard</span>
              <ArrowRight className="w-3 h-3 text-slate-400" />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Banner Section */}
      <section className="bg-white border-b border-slate-200 py-10 px-4 sm:px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-50 border border-blue-200 text-blue-700 text-xs font-bold uppercase tracking-wider mb-3">
            <Activity className="w-3.5 h-3.5 text-blue-600" />
            <span>Real-Time Headcount &amp; Predictive Inflow</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight leading-tight">
            Follow Live Events &amp; Beat The Rush
          </h1>
          <p className="text-slate-600 text-sm sm:text-base mt-2 max-w-2xl mx-auto">
            Select an event below to follow live occupancy, monitor entry gate queues, and receive continuous alerts
            predicting exactly when the venue will reach full capacity.
          </p>
        </div>
      </section>

      {/* Main Events List */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 flex-1 w-full">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <span>Active Gatherings &amp; Monitored Venues</span>
            </h2>
            <p className="text-xs text-slate-500">Live AI camera tracking active across entry and exit portals</p>
          </div>
          <span className="text-xs bg-slate-100 text-slate-700 border border-slate-200 px-3 py-1 rounded-full font-bold">
            {venues.length} Active Events
          </span>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-9 h-9 border-3 border-blue-600 border-t-transparent rounded-full animate-spin mb-3" />
            <p className="text-slate-500 text-sm font-medium">Fetching real-time crowd metrics...</p>
          </div>
        ) : venues.length === 0 ? (
          <div className="rounded-xl border border-slate-200 bg-white p-12 text-center shadow-xs">
            <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto mb-3">
              <Users className="w-6 h-6" />
            </div>
            <h3 className="text-base font-bold text-slate-900">No Active Events Registered</h3>
            <p className="text-slate-500 text-xs sm:text-sm mt-1 mb-5">
              There are currently no monitored venues in the system.
            </p>
            <Link
              to="/inputs"
              className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold text-xs shadow-xs"
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>Create First Event</span>
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {venues.map((v) => {
              const isFull = v.percentage >= 90
              const isWarning = v.percentage >= 75 && !isFull
              const timeToFull = v.time_to_capacity_minutes

              return (
                <Link
                  key={v.id}
                  to={`/events/${v.id}`}
                  className="group rounded-xl bg-white border border-slate-200 hover:border-blue-400 p-5 flex flex-col justify-between transition-all shadow-xs hover:shadow-md"
                >
                  <div>
                    {/* Header line: Name & Status Tag */}
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div>
                        <h3 className="text-base font-bold text-slate-900 group-hover:text-blue-600 transition-colors">
                          {v.name}
                        </h3>
                        <p className="text-xs text-slate-500 mt-0.5">{v.location} • {v.area_sqm} m²</p>
                      </div>

                      <span
                        className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold border shrink-0 ${
                          isFull
                            ? 'bg-rose-50 border-rose-200 text-rose-700'
                            : isWarning
                            ? 'bg-amber-50 border-amber-200 text-amber-800'
                            : 'bg-emerald-50 border-emerald-200 text-emerald-700'
                        }`}
                      >
                        {isFull ? 'CRITICAL' : isWarning ? 'HIGH RUSH' : 'SAFE FLOW'}
                      </span>
                    </div>

                    {/* Capacity Progress Bar */}
                    <div className="my-3">
                      <div className="flex items-center justify-between text-xs mb-1.5 font-semibold">
                        <span className="text-slate-600">Occupancy</span>
                        <span className="text-slate-900 font-bold">{v.percentage}% Capacity</span>
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden border border-slate-200">
                        <div
                          className={`h-full transition-all duration-500 ${
                            isFull ? 'bg-rose-500' : isWarning ? 'bg-amber-500' : 'bg-emerald-500'
                          }`}
                          style={{ width: `${v.percentage}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-slate-500 mt-1 font-mono">
                        <span>{v.current_occupancy.toLocaleString()} inside</span>
                        <span>{v.effective_capacity.toLocaleString()} Max</span>
                      </div>
                    </div>

                    {/* Time To Full Pill */}
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 my-3 flex items-center justify-between">
                      <div className="flex items-center gap-2 text-xs text-slate-600">
                        <Clock className="w-3.5 h-3.5 text-blue-600 shrink-0" />
                        <span>Estimated Full In:</span>
                      </div>
                      <div className="font-bold text-xs">
                        {isFull ? (
                          <span className="text-rose-600 font-extrabold">AT CAPACITY</span>
                        ) : timeToFull !== null && timeToFull > 0 ? (
                          <span className="text-amber-700 font-extrabold">~{Math.round(timeToFull)} Minutes</span>
                        ) : v.net_inflow_rate <= 0 ? (
                          <span className="text-emerald-700 font-semibold">No Rush Expected</span>
                        ) : (
                          <span className="text-slate-500 font-medium">Calculating...</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Card Bottom CTA */}
                  <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs font-semibold text-blue-600 group-hover:text-blue-700 transition-colors">
                    <span>Follow Live Event &amp; Alerts</span>
                    <ChevronRight className="w-4 h-4 transform group-hover:translate-x-1 transition-transform" />
                  </div>
                </Link>
              )
            })}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-500">
        AI Crowd Intelligence • Real-Time Safety &amp; Inflow Monitoring Platform
      </footer>
    </div>
  )
}

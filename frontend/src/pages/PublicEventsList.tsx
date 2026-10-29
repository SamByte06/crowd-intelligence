import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  Compass,
  Users,
  Clock,
  ArrowRight,
  ShieldCheck,
  TrendingUp,
  MapPin,
  Sparkles,
  SlidersHorizontal,
  ChevronRight
} from 'lucide-react'
import { venueApi, monitorApi } from '../services/api'

interface VenueWithStats {
  id: string
  name: string
  area_sqm: number
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
    const interval = setInterval(fetchVenuesAndStats, 6000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-blue-600 selection:text-white">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold">
              <Compass className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="font-extrabold text-base tracking-tight text-white leading-none">
                EVENT CROWD INTELLIGENCE
              </div>
              <div className="text-[10px] font-semibold text-blue-400 uppercase tracking-wider mt-0.5">
                Public Live Attendee Portal
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Link
              to="/dashboard"
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300 transition-colors"
            >
              <span>Admin Dashboard</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="bg-gradient-to-b from-slate-900 via-slate-900/60 to-slate-950 border-b border-slate-800/80 py-12 px-4">
        <div className="max-w-3xl mx-auto text-center">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-bold uppercase tracking-wider mb-4">
            <Sparkles className="w-3.5 h-3.5" />
            Live Crowd Density &amp; Time-To-Full Forecasting
          </span>
          <h1 className="text-3xl sm:text-5xl font-black text-white tracking-tight leading-tight mb-4">
            Follow Live Events &amp; Beat The Rush
          </h1>
          <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
            Select an event to view real-time headcount, entry gate queues, and continuous predictive alerts on your
            device showing exactly when the venue is expected to reach capacity.
          </p>
        </div>
      </section>

      {/* Event Cards Grid */}
      <main className="max-w-6xl mx-auto px-4 py-8 flex-1 w-full">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <span>Currently Monitored Venues &amp; Gatherings</span>
          </h2>
          <span className="text-xs bg-slate-800 text-slate-300 px-3 py-1 rounded-full font-semibold">
            {venues.length} Active Events
          </span>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-16">
            <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-3" />
            <p className="text-slate-400 text-sm">Retrieving live venues and camera nodes...</p>
          </div>
        ) : venues.length === 0 ? (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-12 text-center">
            <Compass className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <h3 className="text-lg font-bold text-white">No Monitored Venues Found</h3>
            <p className="text-slate-400 text-sm mt-1 mb-6">
              There are currently no active venue streams configured in the system.
            </p>
            <Link
              to="/inputs"
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-bold text-sm"
            >
              <SlidersHorizontal className="w-4 h-4" />
              <span>Configure First Venue</span>
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
                  className="group rounded-2xl bg-slate-900/80 border border-slate-800 hover:border-blue-500/50 p-6 flex flex-col justify-between transition-all hover:shadow-xl hover:shadow-blue-950/20 hover:-translate-y-1 relative overflow-hidden"
                >
                  <div>
                    {/* Header line: Name & Status Tag */}
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div>
                        <h3 className="text-lg font-bold text-white group-hover:text-blue-400 transition-colors">
                          {v.name}
                        </h3>
                        <p className="text-xs text-slate-400 mt-0.5">Area: {v.area_sqm} m²</p>
                      </div>

                      <span
                        className={`px-2.5 py-1 rounded-full text-[11px] font-bold border shrink-0 ${
                          isFull
                            ? 'bg-rose-500/10 border-rose-500/30 text-rose-400'
                            : isWarning
                            ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                            : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                        }`}
                      >
                        {isFull ? '🔴 CRITICAL' : isWarning ? '🟡 HIGH RUSH' : '🟢 SAFE FLOW'}
                      </span>
                    </div>

                    {/* Capacity Progress Bar */}
                    <div className="my-4">
                      <div className="flex items-center justify-between text-xs mb-1.5 font-semibold">
                        <span className="text-slate-400">Current Occupancy</span>
                        <span className="text-white font-bold">{v.percentage}% Capacity</span>
                      </div>
                      <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                        <div
                          className={`h-full transition-all duration-500 ${
                            isFull ? 'bg-rose-500' : isWarning ? 'bg-amber-500' : 'bg-emerald-500'
                          }`}
                          style={{ width: `${v.percentage}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-slate-500 mt-1">
                        <span>{v.current_occupancy.toLocaleString()} inside</span>
                        <span>{v.effective_capacity.toLocaleString()} Max</span>
                      </div>
                    </div>

                    {/* Time To Full Pill */}
                    <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800/80 mb-4 flex items-center justify-between">
                      <div className="flex items-center gap-2 text-xs text-slate-300">
                        <Clock className="w-4 h-4 text-blue-400 shrink-0" />
                        <span>Estimated Full In:</span>
                      </div>
                      <div className="font-bold text-xs">
                        {isFull ? (
                          <span className="text-rose-400">NOW AT CAPACITY</span>
                        ) : timeToFull !== null && timeToFull > 0 ? (
                          <span className="text-amber-400">~{Math.round(timeToFull)} Minutes</span>
                        ) : v.net_inflow_rate <= 0 ? (
                          <span className="text-emerald-400">No Rush Expected</span>
                        ) : (
                          <span className="text-slate-400">Calculating...</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Card Bottom CTA */}
                  <div className="pt-3 border-t border-slate-800 flex items-center justify-between text-xs font-semibold text-blue-400 group-hover:text-blue-300 transition-colors">
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
      <footer className="border-t border-slate-800 py-6 text-center text-xs text-slate-500">
        AI Crowd Intelligence • Public Safety &amp; Inflow Monitoring Platform
      </footer>
    </div>
  )
}

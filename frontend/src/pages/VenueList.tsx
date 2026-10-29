import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { venueApi } from '../services/api'
import type { Venue } from '../types'
import { Plus, MapPin, Activity, Settings, DoorOpen, RefreshCw, Trash2 } from 'lucide-react'

export default function VenueList() {
  const [venues, setVenues] = useState<Venue[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadVenues = () => {
    setLoading(true)
    setError('')
    venueApi.list()
      .then(setVenues)
      .catch(e => setError(e.message || 'Could not load facilities.'))
      .finally(() => setLoading(false))
  }

  const handleDelete = async (venueId: string, venueName: string) => {
    if (!confirm(`Are you sure you want to permanently delete "${venueName}"? All gates, camera feeds, and counts will be removed.`)) {
      return
    }
    try {
      await venueApi.delete(venueId)
      setVenues((prev) => prev.filter((v) => v.id !== venueId))
      const stored = localStorage.getItem('activeVenueId')
      if (stored === venueId) {
        localStorage.removeItem('activeVenueId')
      }
    } catch (err: any) {
      alert(err.message || 'Failed to delete facility.')
    }
  }

  useEffect(() => { loadVenues() }, [])

  if (loading) return <LoadingSkeleton />

  return (
    <div className="w-full max-w-full space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Monitored Facilities
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Overview and configuration for all active crowd monitoring installations.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/inputs"
            className="btn-secondary text-xs"
          >
            Quick Setup Form
          </Link>
          <Link
            to="/venues/new"
            className="btn-primary text-xs"
          >
            <Plus className="w-4 h-4" />
            <span>Create Facility</span>
          </Link>
        </div>
      </div>

      {error && (
        <div role="alert" className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
          <span>{error}</span>
          <button onClick={loadVenues} className="btn-secondary text-xs self-start sm:self-auto">
            <RefreshCw className="w-3.5 h-3.5" /> Retry
          </button>
        </div>
      )}

      {error ? null : venues.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-16 text-center shadow-xs">
          <div className="w-14 h-14 mx-auto mb-4 rounded-xl bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-500">
            <MapPin className="w-7 h-7" />
          </div>
          <h2 className="text-lg font-bold text-slate-900 mb-1">No Facilities Configured</h2>
          <p className="text-sm text-slate-500 mb-6 max-w-sm mx-auto">
            Create your first monitored venue to establish camera gates and real-time occupancy counting.
          </p>
          <Link
            to="/inputs"
            className="btn-primary text-sm px-6 py-2.5"
          >
            <Plus className="w-4 h-4" />
            <span>Start Quick Setup</span>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {venues.map((venue) => (
            <VenueCard key={venue.id} venue={venue} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  )
}

function VenueCard({ venue, onDelete }: { venue: Venue; onDelete: (id: string, name: string) => void }) {
  const cap = venue.effective_capacity || 0
  const pct = cap > 0 ? Math.round((venue.current_occupancy / cap) * 100) : 0
  
  let barColor = 'bg-slate-900'
  let statusText = 'Nominal'
  let statusColor = 'text-emerald-700 bg-emerald-50 border-emerald-200'

  if (pct >= 90) {
    barColor = 'bg-red-600'
    statusText = 'Critical'
    statusColor = 'text-red-700 bg-red-50 border-red-200'
  } else if (pct >= 75) {
    barColor = 'bg-orange-500'
    statusText = 'High'
    statusColor = 'text-orange-700 bg-orange-50 border-orange-200'
  } else if (pct >= 50) {
    statusText = 'Moderate'
    statusColor = 'text-amber-700 bg-amber-50 border-amber-200'
  }

  return (
    <div className="classic-card classic-card-hover p-5 flex flex-col justify-between">
      <div>
        {/* Top Header */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <h2 className="text-base font-bold text-slate-900 leading-snug">
              {venue.name}
            </h2>
            {venue.location ? (
              <p className="text-xs text-slate-500 flex items-center gap-1 mt-1">
                <MapPin className="w-3 h-3 text-slate-400" />
                <span>{venue.location}</span>
              </p>
            ) : (
              <p className="text-xs text-slate-400 mt-1">
                {venue.usable_area_sqm ? `${venue.usable_area_sqm} m² facility` : 'Standard configuration'}
              </p>
            )}
          </div>
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase tracking-wider ${statusColor}`}>
            {statusText}
          </span>
        </div>

        {/* Headcount Capacity Gauge */}
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3.5 mb-4">
          <div className="flex items-baseline justify-between mb-1.5">
            <span className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
              Occupancy
            </span>
            <div className="text-right">
              <span className="text-lg font-bold font-mono text-slate-900">
                {venue.current_occupancy.toLocaleString()}
              </span>
              <span className="text-xs font-mono text-slate-500">
                {' '}/ {cap > 0 ? cap.toLocaleString() : '∞'}
              </span>
            </div>
          </div>
          <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
            <div className={`h-full ${barColor} transition-all duration-300`} style={{ width: `${Math.min(pct, 100)}%` }} />
          </div>
          <div className="flex justify-between items-center text-[11px] text-slate-500 mt-1.5 font-mono">
            <span>{pct}% utilized</span>
            <span>{cap > 0 ? `${Math.max(0, cap - venue.current_occupancy)} remaining` : ''}</span>
          </div>
        </div>

        {/* Cumulative Movement Stats */}
        <div className="grid grid-cols-2 gap-3 mb-5">
          <div className="bg-white border border-slate-200 rounded-lg p-2.5 text-center">
            <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Total In</p>
            <p className="text-base font-bold font-mono text-emerald-700 mt-0.5">{venue.total_entries.toLocaleString()}</p>
          </div>
          <div className="bg-white border border-slate-200 rounded-lg p-2.5 text-center">
            <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Total Out</p>
            <p className="text-base font-bold font-mono text-red-700 mt-0.5">{venue.total_exits.toLocaleString()}</p>
          </div>
        </div>
      </div>

      {/* Available & Working Actions */}
      <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
        <Link
          to={`/venues/${venue.id}/dashboard`}
          className="flex-1 btn-primary text-xs py-2"
        >
          <Activity className="w-3.5 h-3.5" />
          <span>Monitor</span>
        </Link>
        <Link
          to={`/venues/${venue.id}/gates`}
          className="btn-secondary text-xs py-2 px-3"
          title="Gate Cameras"
        >
          <DoorOpen className="w-3.5 h-3.5 text-slate-500" />
          <span>Gates</span>
        </Link>
        <Link
          to={`/venues/${venue.id}/edit`}
          className="btn-secondary text-xs py-2 px-2.5"
          title="Configure Facility Parameters"
        >
          <Settings className="w-3.5 h-3.5 text-slate-500" />
        </Link>
        <button
          type="button"
          onClick={() => onDelete(venue.id, venue.name)}
          className="btn-secondary text-xs py-2 px-2.5 text-rose-600 hover:bg-rose-50 hover:text-rose-700 hover:border-rose-300 flex items-center gap-1"
          title={`Delete ${venue.name}`}
        >
          <Trash2 className="w-3.5 h-3.5" />
          <span>Delete</span>
        </button>
      </div>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5 mt-6">
      {[1, 2, 3].map(i => (
        <div key={i} className="bg-white border border-slate-200 rounded-xl p-6 animate-pulse space-y-4">
          <div className="h-5 w-1/2 bg-slate-200 rounded" />
          <div className="h-4 w-1/3 bg-slate-100 rounded" />
          <div className="h-14 bg-slate-100 rounded-lg" />
          <div className="h-8 bg-slate-100 rounded" />
        </div>
      ))}
    </div>
  )
}

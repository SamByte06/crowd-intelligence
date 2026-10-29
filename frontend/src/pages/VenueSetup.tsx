import { useState, useEffect } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { venueApi } from '../services/api'
import type { Venue } from '../types'
import { Save, ArrowLeft, Building2, Check, AlertCircle, Users, Sliders } from 'lucide-react'

export default function VenueSetup() {
  const { venueId } = useParams()
  const navigate = useNavigate()
  const isEdit = !!venueId

  const [form, setForm] = useState({
    name: '',
    description: '',
    location: '',
    usable_area_sqm: '',
    max_capacity: '',
    density_per_sqm: '2.0',
    warning_threshold: '0.75',
    critical_threshold: '0.90',
    timezone: 'UTC',
  })

  const [baseline, setBaseline] = useState({ occupancy: '0', established_by: 'Operator', reason: 'Initial count calibration' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [venue, setVenue] = useState<Venue | null>(null)

  useEffect(() => {
    if (venueId) {
      venueApi.get(venueId).then(v => {
        setVenue(v)
        setForm({
          name: v.name || '',
          description: v.description || '',
          location: v.location || '',
          usable_area_sqm: v.usable_area_sqm?.toString() || '',
          max_capacity: v.max_capacity?.toString() || '',
          density_per_sqm: v.density_per_sqm?.toString() || '2.0',
          warning_threshold: v.warning_threshold?.toString() || '0.75',
          critical_threshold: v.critical_threshold?.toString() || '0.90',
          timezone: v.timezone || 'UTC',
        })
      }).catch(e => setError(e.message))
    }
  }, [venueId])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setSaving(true)

    try {
      const data: any = {
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        location: form.location.trim() || undefined,
        density_per_sqm: parseFloat(form.density_per_sqm),
        warning_threshold: parseFloat(form.warning_threshold),
        critical_threshold: parseFloat(form.critical_threshold),
        timezone: form.timezone,
      }
      if (form.usable_area_sqm) data.usable_area_sqm = parseFloat(form.usable_area_sqm)
      if (form.max_capacity) data.max_capacity = parseInt(form.max_capacity)

      let result: Venue
      if (isEdit) {
        result = await venueApi.update(venueId!, data)
        setSuccess('Facility configuration updated successfully.')
        setVenue(result)
      } else {
        result = await venueApi.create(data)
        navigate(`/venues/${result.id}/edit`)
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleSetBaseline = async () => {
    if (!venueId || !baseline.occupancy) return
    setError('')
    try {
      const result = await venueApi.setBaseline(venueId, {
        occupancy: parseInt(baseline.occupancy),
        established_by: baseline.established_by,
        reason: baseline.reason || 'Manual headcount reset',
      })
      setVenue(result)
      setSuccess('Headcount baseline calibrated successfully.')
    } catch (e: any) {
      setError(e.message)
    }
  }

  return (
    <div className="w-full max-w-5xl mx-auto space-y-6">
      {/* Top Breadcrumb & Title */}
      <div>
        <Link
          to="/venues"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-900 mb-3 transition-colors no-underline"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Facility Directory</span>
        </Link>
        <div className="flex items-center justify-between border-b border-slate-200 pb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-700">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-900 leading-tight">
                {isEdit ? `Configure: ${venue?.name || 'Facility'}` : 'New Monitored Facility'}
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">
                {isEdit ? 'Adjust physical dimensions, occupancy rules, and safety thresholds.' : 'Register a new venue for camera gate tracking.'}
              </p>
            </div>
          </div>
          {isEdit && (
            <Link
              to={`/venues/${venueId}/dashboard`}
              className="btn-primary text-xs"
            >
              Open Live Dashboard →
            </Link>
          )}
        </div>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-red-50 border border-red-200 text-red-800 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="p-3.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
          <Check className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{success}</span>
        </div>
      )}

      {/* Main Parameters Form */}
      <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs space-y-6">
        <div>
          <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-4">
            General Information
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Facility Name <span className="text-red-500">*</span>
              </label>
              <input
                required
                type="text"
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. South Exhibition Hall"
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Building / Location
              </label>
              <input
                type="text"
                value={form.location}
                onChange={e => setForm({ ...form, location: e.target.value })}
                placeholder="e.g. Terminal 2, Level 1"
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Description / Notes
              </label>
              <textarea
                rows={2}
                value={form.description}
                onChange={e => setForm({ ...form, description: e.target.value })}
                placeholder="Operational notes or facility restrictions..."
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900"
              />
            </div>
          </div>
        </div>

        <div className="border-t border-slate-200" />

        {/* Capacity & Safety Dimensions */}
        <div>
          <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-4">
            Dimensions & Safety Limits
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Usable Area (m²)
              </label>
              <input
                type="number"
                step="any"
                min="0.1"
                value={form.usable_area_sqm}
                onChange={e => setForm({ ...form, usable_area_sqm: e.target.value })}
                placeholder="e.g. 500"
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Max Safe Capacity
              </label>
              <input
                type="number"
                min="1"
                value={form.max_capacity}
                onChange={e => setForm({ ...form, max_capacity: e.target.value })}
                placeholder="Auto (Area × Density)"
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Persons / m²
              </label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="10"
                value={form.density_per_sqm}
                onChange={e => setForm({ ...form, density_per_sqm: e.target.value })}
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Warning Threshold
              </label>
              <input
                type="number"
                step="0.05"
                min="0.1"
                max="1.0"
                value={form.warning_threshold}
                onChange={e => setForm({ ...form, warning_threshold: e.target.value })}
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
              <span className="text-[11px] text-slate-500 font-mono">
                {Math.round(parseFloat(form.warning_threshold || '0.75') * 100)}% capacity
              </span>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Critical Threshold
              </label>
              <input
                type="number"
                step="0.05"
                min="0.1"
                max="1.0"
                value={form.critical_threshold}
                onChange={e => setForm({ ...form, critical_threshold: e.target.value })}
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
              <span className="text-[11px] text-slate-500 font-mono">
                {Math.round(parseFloat(form.critical_threshold || '0.90') * 100)}% capacity
              </span>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Timezone
              </label>
              <input
                type="text"
                value={form.timezone}
                onChange={e => setForm({ ...form, timezone: e.target.value })}
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
            </div>
          </div>
        </div>

        <div className="pt-2 flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="btn-primary text-xs py-2 px-5"
          >
            <Save className="w-4 h-4" />
            <span>{saving ? 'Saving Changes...' : isEdit ? 'Update Facility' : 'Create Facility'}</span>
          </button>
        </div>
      </form>

      {/* Baseline Calibration Card (Available when editing) */}
      {isEdit && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                Occupancy Calibration (Baseline)
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Calibrate or reset current inside headcount if monitoring begins while visitors are already present.
              </p>
            </div>
            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
              Current: {venue?.current_occupancy ?? 0}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-1">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Verified Headcount
              </label>
              <input
                type="number"
                min="0"
                value={baseline.occupancy}
                onChange={e => setBaseline({ ...baseline, occupancy: e.target.value })}
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Operator / Auditor
              </label>
              <input
                type="text"
                value={baseline.established_by}
                onChange={e => setBaseline({ ...baseline, established_by: e.target.value })}
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Calibration Reason
              </label>
              <input
                type="text"
                value={baseline.reason}
                onChange={e => setBaseline({ ...baseline, reason: e.target.value })}
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
            </div>
          </div>

          <div className="pt-2 flex justify-end">
            <button
              type="button"
              onClick={handleSetBaseline}
              className="btn-secondary text-xs py-2 px-4"
            >
              Set Baseline Count
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

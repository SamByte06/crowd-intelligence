import { useEffect, useState } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, SlidersHorizontal, Building2, ShieldCheck, RefreshCw, Calendar, Settings, Compass, Server } from 'lucide-react'
import { monitorApi } from '../services/api'
import ServerConfigModal from './ServerConfigModal'

export default function Layout() {
  const location = useLocation()
  const [currentTime, setCurrentTime] = useState<string>('')
  const [systemStatus, setSystemStatus] = useState<'checking' | 'online' | 'standby'>('checking')
  const [isServerModalOpen, setIsServerModalOpen] = useState(false)

  // Live formatted date and time
  useEffect(() => {
    const updateTime = () => {
      const now = new Date()
      const dateStr = new Intl.DateTimeFormat('en-GB', {
        weekday: 'short',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      }).format(now)
      const timeStr = new Intl.DateTimeFormat('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hourCycle: 'h23',
      }).format(now)
      setCurrentTime(`${dateStr} | ${timeStr}`)
    }
    updateTime()
    const timer = setInterval(updateTime, 1000)
    return () => clearInterval(timer)
  }, [])

  // Poll backend health to reflect true connection state
  const checkHealth = () => {
    monitorApi
      .health()
      .then((res) => {
        if (res && (res.status === 'healthy' || res.status === 'ok')) {
          setSystemStatus('online')
        } else {
          setSystemStatus('standby')
        }
      })
      .catch(() => {
        setSystemStatus('standby')
      })
  }

  useEffect(() => {
    checkHealth()
    const interval = setInterval(checkHealth, 25000)
    return () => clearInterval(interval)
  }, [])

  const activeVenueId = typeof window !== 'undefined' ? localStorage.getItem('activeVenueId') : null
  const dashboardPath = activeVenueId ? `/venues/${activeVenueId}/dashboard` : '/dashboard'
  const settingsPath = activeVenueId ? `/venues/${activeVenueId}/gates` : '/venues'

  const isDashboardActive = location.pathname.includes('/dashboard')
  const isInputsActive = location.pathname === '/' || location.pathname === '/inputs'
  const isSettingsActive = location.pathname.includes('/gates')
  const isVenuesActive = location.pathname.startsWith('/venues') && !isDashboardActive && !isSettingsActive

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans w-full max-w-full overflow-x-hidden antialiased">
      {/* Top Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50 w-full shrink-0 shadow-xs">
        <div className="w-full max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between gap-4">
          {/* Brand & Subtitle */}
          <div className="flex items-center gap-6 sm:gap-8 min-w-0">
            <Link to={dashboardPath} className="flex items-center gap-2.5 no-underline shrink-0 group">
              <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center shadow-xs transition-transform group-hover:scale-105">
                <ShieldCheck className="w-5 h-5 text-white" />
              </div>
              <div className="flex flex-col leading-none">
                <span className="text-base font-extrabold tracking-tight text-slate-900 group-hover:text-blue-600 transition-colors">
                  AI CROWD INTELLIGENCE
                </span>
                <span className="text-[9px] font-semibold tracking-wider text-slate-400 uppercase mt-0.5">
                  ENTRY &amp; EXIT MONITORING SYSTEM
                </span>
              </div>
            </Link>

            {/* Desktop Navigation Links */}
            <nav className="hidden md:flex items-center gap-1.5 border-l border-slate-200 pl-5">
              <NavLink to={dashboardPath} active={isDashboardActive}>
                <LayoutDashboard className="w-3.5 h-3.5" />
                <span>Dashboard</span>
              </NavLink>
              <NavLink to={settingsPath} active={isSettingsActive}>
                <Settings className="w-3.5 h-3.5" />
                <span>Gate Settings</span>
              </NavLink>
              <NavLink to="/inputs" active={isInputsActive}>
                <SlidersHorizontal className="w-3.5 h-3.5" />
                <span>New Facility</span>
              </NavLink>
              <NavLink to="/venues" active={isVenuesActive}>
                <Building2 className="w-3.5 h-3.5" />
                <span>Venues</span>
              </NavLink>
              <NavLink to="/events" active={location.pathname.startsWith('/events')}>
                <Compass className="w-3.5 h-3.5 text-blue-500" />
                <span className="text-blue-700 font-semibold">Attendee View</span>
              </NavLink>
            </nav>
          </div>

          {/* Right Status Indicator & Live Date/Time */}
          <div className="flex shrink-0 items-center gap-3 sm:gap-4">
            {/* Live System Status Indicator (Click to open Server Connection Modal) */}
            <button
              type="button"
              onClick={() => setIsServerModalOpen(true)}
              title="Click to connect or view AI Host Server status"
              className="flex items-center gap-2 px-2.5 py-1 rounded-md border text-xs font-mono cursor-pointer transition-colors select-none shadow-2xs hover:opacity-90"
              style={{
                backgroundColor: systemStatus === 'online' ? '#f0fdf4' : '#fffbeb',
                borderColor: systemStatus === 'online' ? '#bbf7d0' : '#fef08a',
              }}
            >
              {systemStatus === 'online' ? (
                <>
                  <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block animate-pulse" />
                  <span className="text-emerald-800 font-semibold tracking-tight">LIVE SYSTEM</span>
                </>
              ) : systemStatus === 'checking' ? (
                <>
                  <span className="w-2 h-2 rounded-full bg-slate-400 inline-block animate-pulse" />
                  <span className="text-slate-600 font-medium">CHECKING</span>
                </>
              ) : (
                <>
                  <span className="w-2 h-2 rounded-full bg-amber-500 inline-block" />
                  <span className="text-amber-800 font-semibold tracking-tight">STANDBY</span>
                  <Server className="w-3 h-3 text-amber-600 ml-0.5" />
                </>
              )}
            </button>

            {/* Live Formatted Date & Time Display */}
            <div className="flex items-center gap-1.5 text-xs font-mono text-slate-600 tracking-tight rounded-md bg-slate-50 border border-slate-200 px-2.5 py-1 shadow-2xs">
              <Calendar className="w-3.5 h-3.5 text-blue-600 shrink-0" />
              <span>{currentTime}</span>
            </div>
          </div>
        </div>

        {/* Global Host Standby Alert Banner */}
        {systemStatus === 'standby' && (
          <div className="bg-amber-50 border-t border-b border-amber-200 px-4 py-2 text-xs text-amber-900 flex flex-wrap items-center justify-between gap-3 shadow-2xs">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0 animate-pulse" />
              <span>
                <strong>AI Host Server is in Standby:</strong> Connect your Cloudflare Tunnel URL to stream real-time camera tracking and live gate analytics.
              </span>
            </div>
            <button
              onClick={() => setIsServerModalOpen(true)}
              className="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded-md font-bold text-xs transition shadow-xs cursor-pointer"
            >
              Connect Server URL
            </button>
          </div>
        )}

        {/* Mobile Navigation Tabs */}
        <div className="flex items-center justify-around border-t border-slate-200 bg-white px-2 py-1.5 md:hidden">
          <MobileNavLink to={dashboardPath} active={isDashboardActive}>
            <LayoutDashboard className="w-4 h-4" />
            <span>Dashboard</span>
          </MobileNavLink>
          <MobileNavLink to={settingsPath} active={isSettingsActive}>
            <Settings className="w-4 h-4" />
            <span>Settings</span>
          </MobileNavLink>
          <MobileNavLink to="/inputs" active={isInputsActive}>
            <SlidersHorizontal className="w-4 h-4" />
            <span>New Facility</span>
          </MobileNavLink>
          <MobileNavLink to="/venues" active={isVenuesActive}>
            <Building2 className="w-4 h-4" />
            <span>Venues</span>
          </MobileNavLink>
        </div>
      </header>

      {/* Main Page Area */}
      <main className="flex-1 w-full max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-6 fade-in min-w-0">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="w-full shrink-0 border-t border-slate-200 bg-white py-3 px-4 sm:px-6 lg:px-8">
        <div className="max-w-[1600px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-slate-500">
          <span>Facility Entrance &amp; Exit Intelligence Engine</span>
          <span className="font-mono text-slate-400">
            YOLOv11 Person Tracking &bull; Real-Time Line Crossing
          </span>
        </div>
      </footer>

      {/* Global AI Server Connection Modal */}
      <ServerConfigModal
        isOpen={isServerModalOpen}
        onClose={() => setIsServerModalOpen(false)}
        connectionStatus={systemStatus === 'online' ? 'CONNECTED' : 'STANDBY'}
      />
    </div>
  )
}

function NavLink({ to, active, children }: { to: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all no-underline whitespace-nowrap ${
        active
          ? 'bg-slate-900 text-white shadow-xs'
          : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
      }`}
    >
      {children}
    </Link>
  )
}

function MobileNavLink({ to, active, children }: { to: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-colors no-underline whitespace-nowrap ${
        active ? 'bg-slate-900 text-white font-semibold' : 'text-slate-600 hover:text-slate-900'
      }`}
    >
      {children}
    </Link>
  )
}

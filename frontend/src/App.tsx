import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import GiveInputs from './pages/GiveInputs'
import Dashboard from './pages/Dashboard'
import VenueList from './pages/VenueList'
import VenueSetup from './pages/VenueSetup'
import GateManagement from './pages/GateManagement'
import PublicEventsList from './pages/PublicEventsList'
import EventFollowPage from './pages/EventFollowPage'

export default function App() {
  return (
    <Routes>
      {/* Primary Public Attendee Landing Page & Event Follower Views */}
      <Route path="/" element={<PublicEventsList />} />
      <Route path="/events" element={<PublicEventsList />} />
      <Route path="/events/:venueId" element={<EventFollowPage />} />
      <Route path="/live/:venueId" element={<EventFollowPage />} />

      {/* Admin and Facility Operator Portal */}
      <Route element={<Layout />}>
        {/* Create New Facility / Event Input */}
        <Route path="/inputs" element={<GiveInputs />} />
        <Route path="/admin/new" element={<GiveInputs />} />

        {/* Live Operational Dashboard */}
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/admin" element={<Navigate to="/dashboard" replace />} />
        <Route path="/venues/:venueId/dashboard" element={<Dashboard />} />

        {/* Venue and Gate Management */}
        <Route path="/venues" element={<VenueList />} />
        <Route path="/venues/new" element={<VenueSetup />} />
        <Route path="/venues/:venueId/edit" element={<VenueSetup />} />
        <Route path="/venues/:venueId/gates" element={<GateManagement />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

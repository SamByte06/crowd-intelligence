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
      {/* Standalone Public Attendee & Event Follower Views */}
      <Route path="/events" element={<PublicEventsList />} />
      <Route path="/events/:venueId" element={<EventFollowPage />} />
      <Route path="/live/:venueId" element={<EventFollowPage />} />

      {/* Admin and Facility Operator Portal */}
      <Route element={<Layout />}>
        {/* Quick Setup and Primary Entry-Exit Input */}
        <Route path="/" element={<GiveInputs />} />
        <Route path="/inputs" element={<GiveInputs />} />

        {/* Live Operational Dashboard */}
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/venues/:venueId/dashboard" element={<Dashboard />} />

        {/* Venue and Gate Management */}
        <Route path="/venues" element={<VenueList />} />
        <Route path="/venues/new" element={<VenueSetup />} />
        <Route path="/venues/:venueId/edit" element={<VenueSetup />} />
        <Route path="/venues/:venueId/gates" element={<GateManagement />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

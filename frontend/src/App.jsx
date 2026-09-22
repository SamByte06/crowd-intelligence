import { BrowserRouter, Routes, Route } from "react-router-dom";

import Home from "./pages/Home";
import PlacePage from "./pages/PlacePage";
import EventPage from "./pages/EventPage";

import AdminLayout from "./pages/admin/AdminLayout";
import Dashboard from "./pages/admin/Dashboard";
import CreateEvent from "./pages/admin/CreateEvent";

function App() {
    return (
        <BrowserRouter>
            <Routes>
                {/* Public Website */}
                <Route path="/" element={<Home />} />
                <Route path="/place/:placeId" element={<PlacePage />} />
                <Route path="/event/:eventId" element={<EventPage />} />

                {/* Admin Panel (Only 2 Pages: Dashboard and Create Event) */}
                <Route path="/admin" element={<AdminLayout />}>
                    <Route index element={<Dashboard />} />
                    <Route path="create-event" element={<CreateEvent />} />
                </Route>
            </Routes>
        </BrowserRouter>
    );
}

export default App;
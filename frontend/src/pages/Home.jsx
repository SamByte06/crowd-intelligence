import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { fetchEvents, getStoredEvents } from "../services/api";

const places = [
    {
        id: "mahakaleshwar",
        name: "Mahakaleshwar Temple",
        location: "Ujjain, Madhya Pradesh",
        image: "/images/mahakaleshwar.jpg",
    },
    {
        id: "stadium",
        name: "City Stadium",
        location: "Bhopal, Madhya Pradesh",
        image: "/images/holkarstadium.jpg",
    },
    {
        id: "festival",
        name: "Festival Ground",
        location: "Bhopal, Madhya Pradesh",
        image: "/images/gwaliorfair.jpg",
    },
];

function HeroSearch() {
    const [search, setSearch] = useState("");

    const results = search.trim()
        ? places.filter((place) =>
              `${place.name} ${place.location}`
                  .toLowerCase()
                  .includes(search.toLowerCase())
          )
        : [];

    return (
        <section className="hero hero-centered">
            <div className="hero-content hero-content-centered">
                <p className="hero-label">AI-POWERED CROWD INTELLIGENCE</p>

                <h1>
                    Understand Crowds.
                    <span>Before They Become Risky.</span>
                </h1>

                <p className="hero-description">
                    Real-time crowd monitoring, movement analysis, risk
                    estimation and early-warning intelligence.
                </p>

                <div className="search-box">
                    <input
                        type="text"
                        placeholder="Search a monitored place..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />

                    <span>⌕</span>

                    {results.length > 0 && (
                        <div className="search-results">
                            {results.map((place) => (
                                <Link
                                    key={place.id}
                                    to={`/place/${place.id}`}
                                    className="search-result"
                                >
                                    <strong>{place.name}</strong>
                                    <small>{place.location} • Stay tuned, Coming Soon</small>
                                </Link>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </section>
    );
}

function ActiveEvents() {
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const loadEvents = async () => {
            const local = getStoredEvents();
            if (local && local.length > 0) {
                setEvents(local);
                setLoading(false);
                return;
            }

            try {
                const apiRes = await fetchEvents();
                if (apiRes.events && apiRes.events.length > 0) {
                    setEvents(apiRes.events);
                } else {
                    setEvents([]);
                }
            } catch (err) {
                console.error("Failed to load events:", err);
                setEvents([]);
            } finally {
                setLoading(false);
            }
        };

        loadEvents();
    }, []);

    return (
        <section className="section" id="events">
            <div className="section-heading">
                <p className="eyebrow">REAL-TIME MONITORING</p>
                <h2>Active Events</h2>
                <p>
                    Live crowd intelligence and monitoring for registered public
                    gatherings and events. Click to open full event dashboard.
                </p>
            </div>

            {loading ? (
                <div className="events-loading">
                    <p>Loading scheduled events...</p>
                </div>
            ) : events.length > 0 ? (
                <div className="events-grid">
                    {events.map((event, idx) => {
                        const targetId = event.id || idx;
                        return (
                            <Link
                                key={targetId}
                                to={`/event/${targetId}`}
                                className="event-item-card-link"
                            >
                                <div className="event-item-card">
                                    <div className="event-card-header">
                                        <span className="event-type-badge">
                                            {event.type || "Special Event"}
                                        </span>
                                        <span
                                            className={`event-status-pill ${String(
                                                event.status || "Active"
                                            ).toLowerCase()}`}
                                        >
                                            ● {event.status || "Active"}
                                        </span>
                                    </div>

                                    <h3 className="event-title">{event.name}</h3>

                                    <p className="event-location">
                                        📍 {event.location}
                                    </p>

                                    <div className="event-meta-grid">
                                        <div className="event-meta-item">
                                            <strong>Expected Crowd</strong>
                                            <span>
                                                {event.expected_crowd
                                                    ? `${Number(
                                                          event.expected_crowd
                                                      ).toLocaleString()} people`
                                                    : "Not specified"}
                                            </span>
                                        </div>

                                        <div className="event-meta-item">
                                            <strong>Schedule</strong>
                                            <span>
                                                {event.start_date || "Ongoing"}
                                                {event.start_time
                                                    ? ` • ${event.start_time}`
                                                    : ""}
                                            </span>
                                        </div>
                                    </div>

                                    {event.description && (
                                        <p className="event-desc">
                                            {event.description}
                                        </p>
                                    )}

                                    <div className="event-card-action">
                                        <span>View Live Intelligence →</span>
                                    </div>
                                </div>
                            </Link>
                        );
                    })}
                </div>
            ) : (
                <div className="events-empty-state">
                    <div className="empty-icon">📅</div>
                    <h3>No Active Events Currently Scheduled</h3>
                    <p>
                        There are currently no active public events registered
                        in the monitoring system. Events configured through the
                        admin portal will appear here automatically.
                    </p>
                </div>
            )}
        </section>
    );
}

function PopularPlaces() {
    return (
        <section className="section" id="places">
            <div className="section-heading">
                <p className="eyebrow">MONITORED LOCATIONS</p>
                <h2>Popular Places</h2>
                <p>
                    Explore crowd intelligence for monitored public locations.
                </p>
            </div>

            <div className="places-grid">
                {places.map((place) => (
                    <Link
                        key={place.id}
                        to={`/place/${place.id}`}
                        className="place-card"
                    >
                        <img src={place.image} alt={place.name} />

                        <div className="place-card-content">
                            <h3>{place.name}</h3>
                            <p>{place.location}</p>

                            <span className="view-place">
                                Stay Tuned • Coming Soon →
                            </span>
                        </div>
                    </Link>
                ))}
            </div>
        </section>
    );
}

function Footer() {
    return (
        <footer className="footer">
            <div>
                <strong>AI Crowd Intelligence</strong>
                <p>AI-powered crowd monitoring and early-warning system.</p>
            </div>

            <div>
                <p>© 2026 AI Crowd Intelligence</p>
            </div>
        </footer>
    );
}

function Home() {
    return (
        <>
            <nav className="navbar">
                <Link to="/" className="logo">
                    AI Crowd Intelligence
                </Link>

                <div className="nav-links">
                    <Link to="/">Home</Link>
                    <a href="#events">Active Events</a>
                    <a href="#places">Popular Places</a>

                    <Link to="/admin" className="nav-link-button">
                        Admin
                    </Link>
                </div>
            </nav>

            <main>
                <HeroSearch />
                <ActiveEvents />
                <PopularPlaces />
            </main>

            <Footer />
        </>
    );
}

export default Home;
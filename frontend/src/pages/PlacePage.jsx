import { useNavigate, useParams, Link } from "react-router-dom";

const places = {
    mahakaleshwar: {
        name: "Mahakaleshwar Temple",
        location: "Ujjain, Madhya Pradesh",
        description:
            "Ancient sacred shrine and primary pilgrimage center experiencing high-density pilgrim gatherings.",
        image: "/images/mahakaleshwar.jpg",
    },

    stadium: {
        name: "City Stadium",
        location: "Bhopal, Madhya Pradesh",
        description:
            "Large-capacity sports and public entertainment arena for major tournaments and mass public gatherings.",
        image: "/images/holkarstadium.jpg",
    },

    festival: {
        name: "Festival Ground",
        location: "Bhopal, Madhya Pradesh",
        description:
            "Open civic grounds for seasonal fairs, cultural festivals, and community celebrations.",
        image: "/images/gwaliorfair.jpg",
    },
};

function PlacePage() {
    const { placeId } = useParams();
    const navigate = useNavigate();

    const place = places[placeId];

    if (!place) {
        return (
            <>
                <nav className="navbar">
                    <Link to="/" className="logo">
                        AI Crowd Intelligence
                    </Link>
                    <div className="nav-links">
                        <Link to="/">Home</Link>
                        <Link to="/admin" className="nav-link-button">
                            Admin
                        </Link>
                    </div>
                </nav>

                <div className="section not-found">
                    <button className="back-button" onClick={() => navigate("/")}>
                        ← Back to Home
                    </button>
                    <h2>Place Not Found</h2>
                    <p style={{ marginTop: "10px", color: "#64748b" }}>
                        The requested location could not be found.
                    </p>
                </div>
            </>
        );
    }

    return (
        <>
            <nav className="navbar">
                <Link to="/" className="logo">
                    AI Crowd Intelligence
                </Link>

                <div className="nav-links">
                    <Link to="/">Home</Link>
                    <Link to="/admin" className="nav-link-button">
                        Admin
                    </Link>
                </div>
            </nav>

            <main>
                <section className="place-hero">
                    <img src={place.image} alt={place.name} />

                    <div className="place-hero-content">
                        <button className="back-button" onClick={() => navigate("/")}>
                            ← Back to Home
                        </button>

                        <p className="eyebrow">MONITORED LOCATION</p>
                        <h1>{place.name}</h1>
                        <p className="place-location">📍 {place.location}</p>
                        <p>{place.description}</p>
                    </div>
                </section>

                {/* Coming Soon / Stay Tuned Section */}
                <section className="section">
                    <div className="place-coming-soon-card">
                        <div className="place-coming-soon-badge">
                            STAY TUNED
                        </div>
                        <h2>Live Intelligence Coming Soon</h2>
                        <p>
                            Real-time AI camera streaming and crowd risk analysis for{" "}
                            <strong>{place.name}</strong> is currently being calibrated.
                            Stay tuned as we connect live CCTV nodes and forecasting models for this location.
                        </p>
                        <div className="place-coming-soon-features">
                            <div className="coming-soon-feat">
                                <span>📹</span>
                                <div>
                                    <strong>CCTV AI Integration</strong>
                                    <small>Configuring multi-camera edge nodes</small>
                                </div>
                            </div>
                            <div className="coming-soon-feat">
                                <span>📊</span>
                                <div>
                                    <strong>Density Estimation</strong>
                                    <small>Zone-based headcount algorithms</small>
                                </div>
                            </div>
                            <div className="coming-soon-feat">
                                <span>⚡</span>
                                <div>
                                    <strong>Early-Warning Alarms</strong>
                                    <small>Surge risk & movement anomaly detection</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>
            </main>

            <footer className="footer">
                <div>
                    <strong>AI Crowd Intelligence</strong>
                    <p>AI-powered crowd monitoring and early-warning system.</p>
                </div>

                <div>
                    <p>© 2026 AI Crowd Intelligence</p>
                </div>
            </footer>
        </>
    );
}

export default PlacePage;
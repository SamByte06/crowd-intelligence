import { useState } from "react";
import { Link } from "react-router-dom";

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
        <section className="hero">
            <div className="hero-content">
                <p className="hero-label">AI-POWERED CROWD INTELLIGENCE</p>

                <h1>
                    Understand Crowds.
                    <br />
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
                </div>

                {results.length > 0 && (
                    <div className="search-results">
                        {results.map((place) => (
                            <Link
                                key={place.id}
                                to={`/place/${place.id}`}
                                className="search-result"
                            >
                                <strong>{place.name}</strong>
                                <small>{place.location}</small>
                            </Link>
                        ))}
                    </div>
                )}
            </div>
        </section>
    );
}

function LiveCrowd() {
    return (
        <section className="section live-crowd">
            <div className="section-heading">
                <p className="eyebrow">LIVE INTELLIGENCE</p>
                <h2>Live Crowd Situation</h2>
                <p>
                    Monitor crowd conditions and understand changing risk in
                    real time.
                </p>
            </div>

            <div className="stats-grid">
                <div className="stat-card">
                    <span>👥</span>
                    <h3>Real-Time People</h3>
                    <p>AI-based person detection and tracking</p>
                </div>

                <div className="stat-card">
                    <span>📊</span>
                    <h3>Crowd Density</h3>
                    <p>Zone-wise crowd density analysis</p>
                </div>

                <div className="stat-card">
                    <span>↗</span>
                    <h3>Crowd Movement</h3>
                    <p>Movement and flow direction analysis</p>
                </div>

                <div className="stat-card">
                    <span>⚠</span>
                    <h3>Risk Intelligence</h3>
                    <p>Current risk and early-warning estimation</p>
                </div>
            </div>
        </section>
    );
}

function PopularPlaces() {
    return (
        <section className="section popular-places">
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
                                View Live Intelligence →
                            </span>
                        </div>
                    </Link>
                ))}
            </div>
        </section>
    );
}

function About() {
    return (
        <section className="section about-section">
            <div className="about-content">
                <p className="eyebrow">ABOUT THE SYSTEM</p>

                <h2>
                    From Crowd Observation
                    <br />
                    to Crowd Intelligence
                </h2>

                <p>
                    The system combines live crowd information with historical
                    crowd patterns to understand changing conditions, estimate
                    risk and provide early warnings.
                </p>

                <p>
                    It uses computer vision, object tracking, crowd-flow
                    analysis and temporal intelligence to support safer crowd
                    management.
                </p>
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
                    <a href="#live-crowd">Live Crowd</a>
                    <a href="#places">Places</a>
                    <a href="#about">About</a>

                    <Link to="/admin" className="nav-link-button">
                        Admin
                    </Link>
                </div>
            </nav>

            <main>
                <HeroSearch />

                <div id="live-crowd">
                    <LiveCrowd />
                </div>

                <div id="places">
                    <PopularPlaces />
                </div>

                <div id="about">
                    <About />
                </div>
            </main>

            <Footer />
        </>
    );
}

export default Home;
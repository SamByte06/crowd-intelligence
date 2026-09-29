import { useState, useEffect } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

function AdminLayout() {
    const location = useLocation();
    const isCreateEventPage = location.pathname === "/admin/create-event";

    // Dynamic ticking clock
    const [currentTime, setCurrentTime] = useState(new Date());
    const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);

    useEffect(() => {
        const timer = setInterval(() => {
            setCurrentTime(new Date());
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    // Close user menu on outside click or escape
    useEffect(() => {
        const handleDocClick = (e) => {
            if (!e.target.closest(".admin-user-profile-wrapper")) {
                setIsUserMenuOpen(false);
            }
        };
        const handleKeyDown = (e) => {
            if (e.key === "Escape") setIsUserMenuOpen(false);
        };
        document.addEventListener("click", handleDocClick);
        document.addEventListener("keydown", handleKeyDown);
        return () => {
            document.removeEventListener("click", handleDocClick);
            document.removeEventListener("keydown", handleKeyDown);
        };
    }, []);

    // Format: "Tue, 29 Sep 2026 11:03 AM"
    const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];

    const dayName = days[currentTime.getDay()];
    const dateNum = currentTime.getDate();
    const monthName = months[currentTime.getMonth()];
    const year = currentTime.getFullYear();

    let hours = currentTime.getHours();
    const minutes = currentTime.getMinutes().toString().padStart(2, "0");
    const seconds = currentTime.getSeconds().toString().padStart(2, "0");
    const ampm = hours >= 12 ? "PM" : "AM";
    hours = hours % 12 || 12;
    const formattedHours = hours.toString().padStart(2, "0");

    const formattedDateTime = `${dayName}, ${dateNum} ${monthName} ${year}   ${formattedHours}:${minutes} ${ampm}`;
    const liveCCTVTimestamp = `${year}-${(currentTime.getMonth() + 1)
        .toString()
        .padStart(2, "0")}-${dateNum
        .toString()
        .padStart(2, "0")} ${currentTime.getHours().toString().padStart(2, "0")}:${minutes}:${seconds}`;

    return (
        <div className="admin-app">
            {/* GLOBAL HEADER */}
            <header className="admin-header">
                <div className="admin-header-left">
                    <Link to="/admin" className="admin-brand-text" title="Go to Admin Dashboard">
                        Crowd Intelligence
                    </Link>
                    <NavLink
                        to="/admin"
                        end
                        className={({ isActive }) =>
                            `header-nav-pill ${isActive ? "active" : ""}`
                        }
                        title="Live Admin Dashboard"
                    >
                        <span className="header-nav-icon">
                            <svg
                                width="15"
                                height="15"
                                viewBox="0 0 24 24"
                                fill="currentColor"
                            >
                                <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z" />
                            </svg>
                        </span>
                        Dashboard
                    </NavLink>
                </div>

                <div className="admin-header-right">
                    {isCreateEventPage ? (
                        <Link to="/admin" className="btn-back-header" title="Return to Dashboard">
                            <span>←</span> Back to Dashboard
                        </Link>
                    ) : (
                        <Link to="/admin/create-event" className="btn-create-event-header" title="Register New Event">
                            <span>+</span> Create Event
                        </Link>
                    )}

                    <div className="admin-user-profile-wrapper" style={{ position: "relative" }}>
                        <div
                            className="admin-user-profile"
                            onClick={() => setIsUserMenuOpen((prev) => !prev)}
                            title="Administrator Menu"
                            role="button"
                            tabIndex={0}
                        >
                            <div className="admin-avatar-circle">
                                <svg
                                    width="16"
                                    height="16"
                                    viewBox="0 0 24 24"
                                    fill="currentColor"
                                >
                                    <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
                                </svg>
                            </div>
                            <span className="admin-user-name">Admin</span>
                            <span className="admin-user-chevron">▾</span>
                        </div>

                        {/* Interactive User Menu Dropdown */}
                        {isUserMenuOpen && (
                            <div className="admin-dropdown-menu">
                                <div className="dropdown-header">
                                    <div className="dropdown-user-title">Administrator</div>
                                    <div className="dropdown-user-email">admin@crowdintel.local</div>
                                </div>
                                <div className="dropdown-divider" />
                                <Link
                                    to="/admin"
                                    className="dropdown-item"
                                    onClick={() => setIsUserMenuOpen(false)}
                                >
                                    <span>📊</span> Live Dashboard
                                </Link>
                                <Link
                                    to="/admin/create-event"
                                    className="dropdown-item"
                                    onClick={() => setIsUserMenuOpen(false)}
                                >
                                    <span>➕</span> Create Event
                                </Link>
                                <Link
                                    to="/"
                                    className="dropdown-item"
                                    onClick={() => setIsUserMenuOpen(false)}
                                >
                                    <span>🌐</span> Public Crowd Portal
                                </Link>
                                <div className="dropdown-divider" />
                                <button
                                    className="dropdown-item dropdown-danger"
                                    onClick={() => {
                                        setIsUserMenuOpen(false);
                                        window.location.reload();
                                    }}
                                >
                                    <span>🔄</span> Refresh Session
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            </header>

            {/* MAIN CONTENT VIEWPORT */}
            <main className="admin-main-viewport">
                <Outlet context={{ formattedDateTime, liveCCTVTimestamp }} />
            </main>
        </div>
    );
}

export default AdminLayout;

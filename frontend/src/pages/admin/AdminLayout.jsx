import { useState, useEffect } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

function AdminLayout() {
    const location = useLocation();
    const isCreateEventPage = location.pathname === "/admin/create-event";

    // Dynamic ticking clock
    const [currentTime, setCurrentTime] = useState(new Date());

    useEffect(() => {
        const timer = setInterval(() => {
            setCurrentTime(new Date());
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    // Format: "Fri, 20 Jun 2025   02:14 PM" (or live date formatted identically)
    const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
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
                    <Link to="/admin" className="admin-brand-text">
                        Crowd Intelligence
                    </Link>
                </div>

                <div className="admin-header-right">
                    {isCreateEventPage ? (
                        <Link to="/admin" className="btn-back-header">
                            <span>←</span> Back to Dashboard
                        </Link>
                    ) : (
                        <Link to="/admin/create-event" className="btn-create-event-header">
                            <span>+</span> Create Event
                        </Link>
                    )}

                    <div className="header-divider" />

                    <div className="admin-user-profile" title="Admin Account">
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
                        <span className="admin-user-chevron">▼</span>
                    </div>
                </div>
            </header>

            {/* BODY CONTAINER */}
            <div className="admin-body-container">
                {/* MINIMAL SIDEBAR (Only Dashboard) */}
                <aside className="admin-sidebar-minimal">
                    <div className="sidebar-title">Crowd Intelligence</div>

                    <nav className="sidebar-nav-list">
                        <NavLink
                            to="/admin"
                            end
                            className={({ isActive }) =>
                                `sidebar-nav-item ${isActive ? "active" : ""}`
                            }
                        >
                            <span className="sidebar-icon">
                                <svg
                                    width="16"
                                    height="16"
                                    viewBox="0 0 24 24"
                                    fill="currentColor"
                                >
                                    <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z" />
                                </svg>
                            </span>
                            Dashboard
                        </NavLink>
                    </nav>
                </aside>

                {/* MAIN CONTENT VIEWPORT */}
                <main className="admin-main-viewport">
                    <Outlet context={{ formattedDateTime, liveCCTVTimestamp }} />
                </main>
            </div>
        </div>
    );
}

export default AdminLayout;

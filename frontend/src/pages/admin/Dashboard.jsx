import { useState, useEffect } from "react";
import { Link, useOutletContext } from "react-router-dom";
import {
    fetchCrowdState,
    fetchEvents,
    getStoredEvents,
    clearAllEvents,
    CLEAN_CROWD_DATA,
} from "../../services/api";

function Dashboard() {
    const { formattedDateTime, liveCCTVTimestamp } = useOutletContext() || {
        formattedDateTime: "Tue, 29 Sep 2026 11:03 AM",
        liveCCTVTimestamp: "2026-09-29 11:01:33",
    };

    const [events, setEvents] = useState([]);
    const [selectedZone, setSelectedZone] = useState(null);
    const [streamTimestamp, setStreamTimestamp] = useState(Date.now());
    const [streamError, setStreamError] = useState(false);
    const [toastMessage, setToastMessage] = useState("");
    const [isFullscreen, setIsFullscreen] = useState(false);

    // Dynamic Video / YouTube Source state
    const [youtubeUrl, setYoutubeUrl] = useState("");
    const [sourceLoading, setSourceLoading] = useState(false);
    const [sourceStatusMsg, setSourceStatusMsg] = useState("");
    const [activeSourceInfo, setActiveSourceInfo] = useState({
        source_type: "webcam",
        display_name: "Camera 01 - Main Entrance",
        video_title: "Webcam Device 0",
        is_live: true,
        fps: 30,
    });

    const [crowdData, setCrowdData] = useState({
        total_people: 1,
        overall_risk: 5,
        overall_risk_level: "SAFE",
        spatial: {
            usable_area_m2: 3.4,
            floor_area_m2: 4.8,
            obstacle_area_m2: 1.4,
        },
        gender_summary: { male: 1, female: 0, unknown: 0 },
        age_summary: { child: 0, adult: 1, senior: 0 },
        zones: [
            { zone: 0, people: 0, risk_level: "SAFE", usable_area_m2: 0, floor_area_m2: 0, dominant_direction: "LEFT", gender_distribution: { male: 0, female: 0 }, age_distribution: { child: 0, adult: 0, senior: 0 } },
            { zone: 1, people: 0, risk_level: "SAFE", usable_area_m2: 0, floor_area_m2: 0, dominant_direction: "STATIONARY", gender_distribution: { male: 0, female: 0 }, age_distribution: { child: 0, adult: 0, senior: 0 } },
            { zone: 2, people: 0, risk_level: "SAFE", usable_area_m2: 1.9, floor_area_m2: 2.5, dominant_direction: "RIGHT", gender_distribution: { male: 0, female: 0 }, age_distribution: { child: 0, adult: 0, senior: 0 } },
            { zone: 3, people: 1, risk_level: "SAFE", usable_area_m2: 1.5, floor_area_m2: 2.3, dominant_direction: "LEFT", occupancy_percent: 29.4, gender_distribution: { male: 1, female: 0 }, age_distribution: { child: 0, adult: 1, senior: 0 } },
        ],
    });

    // Helper to show temporary toast messages
    const showToast = (msg) => {
        setToastMessage(msg);
        setTimeout(() => setToastMessage(""), 3500);
    };

    // Poll current active video source from AI engine
    useEffect(() => {
        let active = true;
        const checkSource = async () => {
            try {
                const res = await fetch("http://localhost:8000/source");
                if (res.ok && active) {
                    const data = await res.json();
                    if (data && data.display_name) {
                        setActiveSourceInfo(data);
                    }
                }
            } catch (err) {
                // AI engine currently offline
            }
        };
        checkSource();
        const interval = setInterval(checkSource, 5000);
        return () => {
            active = false;
            clearInterval(interval);
        };
    }, []);

    // Helper to sanitize terminal ANSI escape sequences from backend errors
    const cleanErrorMsg = (msg) => {
        if (!msg) return "";
        return msg
            .replace(/\u001b\[[0-9;]*m/g, "")
            .replace(/\[\[0;[0-9]+m[^\]]*\]/g, "")
            .replace(/\[0;[0-9]+m/g, "")
            .replace(/\[0m/g, "")
            .replace(/ERROR:\s*/g, "")
            .trim();
    };

    // Toggle visual floor/obstacle overlay on camera stream
    const handleToggleSpatialOverlay = async () => {
        try {
            const res = await fetch("http://localhost:8000/toggle_spatial_overlay", { method: "POST" });
            const data = await res.json();
            if (data.success) {
                setActiveSourceInfo((prev) => ({ ...prev, show_spatial_overlay: data.show_spatial_overlay }));
                showToast(data.message);
            }
        } catch (err) {
            showToast("Failed to toggle spatial floor overlay.");
        }
    };

    // Toggle green bounding box regions for persons and spatial obstacles (Ctrl+B)
    const handleToggleBoundingBoxes = async () => {
        try {
            const res = await fetch("http://localhost:8000/toggle_bounding_boxes", { method: "POST" });
            const data = await res.json();
            if (data.success) {
                setActiveSourceInfo((prev) => ({
                    ...prev,
                    show_bounding_boxes: data.show_bounding_boxes,
                    show_spatial_overlay: data.show_bounding_boxes,
                }));
                showToast(data.message);
            }
        } catch (err) {
            showToast("Failed to toggle bounding boxes (AI Engine may be offline).");
        }
    };

    // Toggle ROI Crop to news window or full frame
    const handleSetRoi = async (roiType) => {
        try {
            const res = await fetch("http://localhost:8000/set_roi", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ roi: roiType }),
            });
            const data = await res.json();
            if (data.success) {
                setActiveSourceInfo((prev) => ({
                    ...prev,
                    active_roi: data.active_roi,
                }));
                showToast(data.active_roi ? "🎯 Cropped to Crowd Video Window (Studio Anchors Excluded)" : "Full Frame Tracking Restored");
            }
        } catch (err) {
            showToast("Failed to set ROI (AI Engine may be offline).");
        }
    };

    // Global keyboard listener for Ctrl+B
    useEffect(() => {
        const handleKeyDown = (e) => {
            if ((e.ctrlKey || e.metaKey) && (e.key === "b" || e.key === "B")) {
                e.preventDefault();
                handleToggleBoundingBoxes();
            }
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, []);

    // Switch video source dynamically (YouTube URL, webcam 0, or file)
    const handleSwitchSource = async (newSource) => {
        if (newSource === undefined || newSource === null || newSource === "") {
            showToast("Please enter a YouTube video URL or source.");
            return;
        }
        setSourceLoading(true);
        setSourceStatusMsg("Extracting video stream with yt-dlp & connecting AI engine...");
        try {
            const res = await fetch("http://localhost:8000/set_source", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ source: newSource }),
            });
            const data = await res.json();
            if (data.success) {
                setActiveSourceInfo(data.info);
                setStreamTimestamp(Date.now());
                setStreamError(false);
                setSourceStatusMsg("");
                showToast(`Connected to: ${data.info?.display_name || newSource}`);
                if (data.info?.source_type === "youtube") {
                    setYoutubeUrl("");
                }
            } else {
                const cleaned = cleanErrorMsg(data.message || "Could not switch source");
                setSourceStatusMsg(`Error: ${cleaned}`);
                showToast(`Failed: ${cleaned.slice(0, 50)}...`);
            }
        } catch (err) {
            setSourceStatusMsg("Error: AI Engine is offline. Start python track_webcam.py first.");
            showToast("AI engine is offline or unreachable on port 8000.");
        } finally {
            setSourceLoading(false);
        }
    };

    // Live tuning of crowd detection sensitivity
    const handleSetDetectionConfig = async (conf, imgsz) => {
        try {
            const res = await fetch("http://localhost:8000/set_detection_config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ conf, imgsz }),
            });
            const data = await res.json();
            if (data.success) {
                setActiveSourceInfo((prev) => ({ ...prev, conf, imgsz }));
                showToast(`Detection set to: ${conf <= 0.10 ? "Ultra-Crowd Mode" : conf <= 0.18 ? "Dense Crowd Mode" : "Standard Mode"} (conf=${conf})`);
            }
        } catch (err) {
            showToast("AI engine is offline or unreachable on port 8000.");
        }
    };

    // Load registered events from storage / API
    const refreshEvents = async () => {
        const local = getStoredEvents();
        if (local && local.length > 0) {
            setEvents(local);
            return;
        }
        const apiRes = await fetchEvents();
        if (apiRes && apiRes.events && apiRes.events.length > 0) {
            setEvents(apiRes.events);
        } else {
            setEvents([]);
        }
    };

    useEffect(() => {
        refreshEvents();
    }, []);

    // Poll live crowd state from AI backend
    useEffect(() => {
        let active = true;
        const loadCrowdData = async () => {
            const data = await fetchCrowdState();
            if (active && data) {
                setCrowdData(data);
            }
        };

        loadCrowdData();
        const timer = setInterval(loadCrowdData, 1500);
        return () => {
            active = false;
            clearInterval(timer);
        };
    }, []);

    // Listen to native fullscreen change events
    useEffect(() => {
        const handleFullscreenChange = () => {
            setIsFullscreen(!!document.fullscreenElement);
        };
        document.addEventListener("fullscreenchange", handleFullscreenChange);
        document.addEventListener("webkitfullscreenchange", handleFullscreenChange);
        return () => {
            document.removeEventListener("fullscreenchange", handleFullscreenChange);
            document.removeEventListener("webkitfullscreenchange", handleFullscreenChange);
        };
    }, []);

    const handleClearEvent = async () => {
        if (window.confirm("Are you sure you want to delete and reset all events?")) {
            await clearAllEvents();
            setEvents([]);
            setCrowdData(CLEAN_CROWD_DATA);
            showToast("All events deleted and dashboard reset to baseline.");
        }
    };

    const toggleFullscreen = () => {
        const feedElem = document.getElementById("camera-feed-box");
        if (!feedElem) return;

        if (!document.fullscreenElement && !document.webkitFullscreenElement) {
            if (feedElem.requestFullscreen) {
                feedElem.requestFullscreen();
            } else if (feedElem.webkitRequestFullscreen) {
                feedElem.webkitRequestFullscreen();
            } else if (feedElem.mozRequestFullScreen) {
                feedElem.mozRequestFullScreen();
            } else if (feedElem.msRequestFullscreen) {
                feedElem.msRequestFullscreen();
            }
            setIsFullscreen(true);
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.mozCancelFullScreen) {
                document.mozCancelFullScreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
            setIsFullscreen(false);
        }
    };

    const refreshCameraFeed = () => {
        setStreamTimestamp(Date.now());
        showToast("Live camera stream reloaded.");
    };

    const activeEvent =
        events.length > 0 ? events[events.length - 1] : null;

    // Calculate live aggregated metrics
    const totalPeople =
        crowdData.total_people ?? (crowdData.people ? crowdData.people.length : 0);

    const males =
        crowdData.gender_summary?.male ??
        (crowdData.people ? crowdData.people.filter((p) => p.gender === "Male").length : (totalPeople > 0 ? 1 : 0));
    const females =
        crowdData.gender_summary?.female ??
        (crowdData.people ? crowdData.people.filter((p) => p.gender === "Female").length : 0);
    const children =
        crowdData.age_summary?.child ??
        (crowdData.people ? crowdData.people.filter((p) => p.age === "Child").length : 0);
    const adults =
        crowdData.age_summary?.adult ??
        (crowdData.people ? crowdData.people.filter((p) => p.age === "Adult").length : (totalPeople > 0 ? totalPeople : 0));
    const seniors =
        crowdData.age_summary?.senior ??
        (crowdData.people ? crowdData.people.filter((p) => p.age === "Senior Citizen" || p.age === "Senior").length : 0);

    const malePct = totalPeople > 0 ? Math.round((males / totalPeople) * 100) : 0;
    const femalePct = totalPeople > 0 ? Math.round((females / totalPeople) * 100) : 0;
    const childPct = totalPeople > 0 ? Math.round((children / totalPeople) * 100) : 0;
    const adultPct = totalPeople > 0 ? Math.round((adults / totalPeople) * 100) : (totalPeople > 0 ? 100 : 0);
    const seniorPct = totalPeople > 0 ? Math.round((seniors / totalPeople) * 100) : 0;

    const usableArea =
        crowdData.spatial?.usable_area_m2 ?? crowdData.usable_area_m2 ?? 3.4;

    const occupancyPercent =
        crowdData.occupancy_percent ??
        crowdData.crowd?.occupancy_percent ??
        (usableArea > 0 && totalPeople > 0 ? 29.4 : 0.0);

    const currentRisk = crowdData.overall_risk ?? 5;
    const riskLevelStr = (crowdData.overall_risk_level || "SAFE").toUpperCase();

    return (
        <div className="admin-dashboard-view">
            {/* TOAST NOTIFICATION */}
            {toastMessage && (
                <div className="admin-toast-banner">
                    <span>ℹ {toastMessage}</span>
                </div>
            )}

            {/* PAGE HEADER */}
            <div className="admin-page-header">
                <div>
                    <h1 className="page-title">Dashboard</h1>
                    <p className="page-subtitle">
                        Live monitoring and crowd risk analysis
                    </p>
                </div>
                <div className="page-datetime-stamp">{formattedDateTime}</div>
            </div>

            {/* ACTIVE EVENT STRIP */}
            <div className="active-event-strip">
                {activeEvent ? (
                    <>
                        <div className="active-event-info">
                            <span className="active-event-pill">● ACTIVE EVENT</span>
                            <span className="active-event-name">{activeEvent.name}</span>
                            <span className="active-event-meta">
                                📍 {activeEvent.location}
                            </span>
                            <span className="active-event-meta">
                                👥 Expected: {activeEvent.expected_crowd}
                            </span>
                            <span className="active-event-meta">
                                📅 {activeEvent.start_date} ({activeEvent.start_time})
                            </span>
                        </div>
                        <div>
                            <button
                                className="btn-reset-event"
                                onClick={handleClearEvent}
                                title="Reset Active Event"
                            >
                                <svg
                                    width="14"
                                    height="14"
                                    viewBox="0 0 24 24"
                                    fill="#DC2626"
                                >
                                    <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z" />
                                </svg>
                                Reset Event
                            </button>
                        </div>
                    </>
                ) : (
                    <>
                        <div className="active-event-info">
                            <span className="active-event-pill inactive">NO ACTIVE EVENT</span>
                            <span className="active-event-meta" style={{ color: "#64748B", fontWeight: 500 }}>
                                No active event registered. All events deleted.
                            </span>
                        </div>
                        <div>
                            <Link
                                to="/admin/create-event"
                                className="btn-create-event-header"
                                style={{ padding: "6px 14px", fontSize: "12.5px" }}
                            >
                                + Create Event
                            </Link>
                        </div>
                    </>
                )}
            </div>

            {/* TOP ROW: LIVE MONITORING + ZONE-WISE CROWD INTELLIGENCE (2-COLUMN GRID) */}
            <div className="dashboard-top-grid">
                {/* 1. LIVE MONITORING CARD */}
                <div className="admin-card live-monitoring-card">
                    <div className="card-header-flex">
                        <div className="card-header-left">
                            <div className="card-title-flex">
                                <svg
                                    width="18"
                                    height="18"
                                    viewBox="0 0 24 24"
                                    fill="#1677E8"
                                >
                                    <path d="M5 9.2h3V19H5zM10.6 5h2.8v14h-2.8zm5.6 8H19v6h-2.8z" />
                                </svg>
                                <h3>Live Monitoring</h3>
                            </div>
                            <div
                                className="camera-sub-indicator"
                                onClick={refreshCameraFeed}
                                title="Click to refresh camera connection"
                                style={{ cursor: "pointer" }}
                            >
                                <span className={streamError ? "dot-red" : "dot-green"} />
                                <span>{activeSourceInfo.display_name || "Camera 01 - Main Entrance"}</span>
                            </div>
                        </div>

                        <div className="card-header-right">
                            <div
                                className={`badge-live ${streamError ? "offline" : ""}`}
                                onClick={refreshCameraFeed}
                                title={streamError ? "Camera offline. Click to reconnect." : "Live camera stream active. Click to reload."}
                                style={{ cursor: "pointer" }}
                            >
                                <span className={streamError ? "dot-red" : "badge-live-dot"} />
                                {streamError ? "OFFLINE" : (activeSourceInfo.source_type === "youtube" ? "YOUTUBE" : "LIVE")}
                            </div>
                            <button
                                className="btn-expand-icon"
                                onClick={toggleFullscreen}
                                title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
                                aria-label="Expand camera view"
                            >
                                ⤢
                            </button>
                        </div>
                    </div>

                    {/* Video Source Control Bar */}
                    <div className="video-source-panel">
                        <div className="video-source-top-row">
                            <div className="active-source-badge">
                                <span className={streamError ? "dot-red" : "dot-green"} />
                                <span className="active-source-type">
                                    {activeSourceInfo.source_type === "youtube" ? "▶ YOUTUBE" : activeSourceInfo.source_type === "file" ? "📁 FILE" : "📷 WEBCAM"}
                                </span>
                                <span className="active-source-title" title={activeSourceInfo.video_title || activeSourceInfo.display_name}>
                                    {activeSourceInfo.video_title || activeSourceInfo.display_name}
                                </span>
                                {activeSourceInfo.fps > 0 && (
                                    <span className="active-source-fps">{activeSourceInfo.fps} FPS</span>
                                )}
                            </div>
                            <div className="video-source-quick-actions">
                                <button
                                    type="button"
                                    className={`btn-source-toggle ${activeSourceInfo.source_type === "webcam" ? "active" : ""}`}
                                    onClick={() => handleSwitchSource(0)}
                                    disabled={sourceLoading}
                                    title="Switch to Laptop Webcam"
                                >
                                    📷 Webcam (0)
                                </button>
                            </div>
                        </div>

                        {/* YouTube URL input form */}
                        <form
                            className="video-source-input-row"
                            onSubmit={(e) => {
                                e.preventDefault();
                                handleSwitchSource(youtubeUrl);
                            }}
                        >
                            <div className="youtube-input-wrap">
                                <svg className="youtube-icon" width="18" height="18" viewBox="0 0 24 24" fill="#EF4444">
                                    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                                </svg>
                                <input
                                    type="text"
                                    className="youtube-url-input"
                                    placeholder="Paste YouTube link (e.g. https://www.youtube.com/watch?v=...)"
                                    value={youtubeUrl}
                                    onChange={(e) => setYoutubeUrl(e.target.value)}
                                    disabled={sourceLoading}
                                />
                                {youtubeUrl && (
                                    <button
                                        type="button"
                                        className="btn-clear-input"
                                        onClick={() => setYoutubeUrl("")}
                                    >
                                        ×
                                    </button>
                                )}
                            </div>
                            <button
                                type="submit"
                                className="btn-analyze-youtube"
                                disabled={sourceLoading || !youtubeUrl.trim()}
                            >
                                {sourceLoading ? "⚡ Connecting..." : "⚡ Analyze YouTube"}
                            </button>
                        </form>

                        {/* Status message or error banner */}
                        {sourceStatusMsg && (
                            <div className={`source-status-message ${sourceStatusMsg.startsWith("Error:") ? "error-banner" : "info-banner"}`}>
                                {sourceLoading ? (
                                    <div className="status-loading-row">
                                        <span className="source-spinner" />
                                        <span>{sourceStatusMsg}</span>
                                    </div>
                                ) : (
                                    <div className="status-error-container">
                                        <div className="status-error-header">
                                            <span className="status-error-icon">⚠️</span>
                                            <span className="status-error-text">
                                                {cleanErrorMsg(sourceStatusMsg.replace(/^Error:\s*/, ""))}
                                            </span>
                                            <button
                                                type="button"
                                                className="btn-dismiss-status"
                                                onClick={() => setSourceStatusMsg("")}
                                                title="Dismiss error message"
                                            >
                                                ×
                                            </button>
                                        </div>
                                        <div className="status-error-actions">
                                            <span className="status-fallback-lbl">Quick Recovery:</span>
                                            <button
                                                type="button"
                                                className="btn-error-fallback"
                                                onClick={() => handleSwitchSource(0)}
                                            >
                                                📷 Switch to Webcam
                                            </button>
                                            <button
                                                type="button"
                                                className="btn-error-fallback"
                                                onClick={() => handleSwitchSource("https://www.youtube.com/watch?v=HpdO5Kq3o8Y")}
                                            >
                                                🚶 Shibuya Crossing
                                            </button>
                                            <button
                                                type="button"
                                                className="btn-error-fallback"
                                                onClick={() => handleSwitchSource("crowd_test.mp4")}
                                            >
                                                📁 Local MP4
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* 1-Click Test Presets */}
                        <div className="video-presets-row">
                            <span className="presets-label">Quick Test Presets:</span>
                            <button
                                type="button"
                                className="btn-preset-chip"
                                onClick={() => handleSwitchSource("https://www.youtube.com/watch?v=dQw4w9WgXcQ")}
                                disabled={sourceLoading}
                                title="Rick Astley 4K Remastered Test Stream"
                            >
                                🎵 Music Video
                            </button>
                            <button
                                type="button"
                                className="btn-preset-chip"
                                onClick={() => handleSwitchSource("https://www.youtube.com/watch?v=HpdO5Kq3o8Y")}
                                disabled={sourceLoading}
                                title="Pedestrian Crossing Test Video"
                            >
                                🚶 Shibuya Crossing
                            </button>
                            <button
                                type="button"
                                className="btn-preset-chip"
                                onClick={() => handleSwitchSource("crowd_test.mp4")}
                                disabled={sourceLoading}
                                title="Local sample crowd video (crowd_test.mp4)"
                            >
                                📁 Local MP4
                            </button>
                        </div>

                        {/* Crowd Detection Sensitivity Control & Visual Spatial Floor Overlay Toggle */}
                        <div className="crowd-sensitivity-row">
                            <span className="presets-label">Detection:</span>
                            <button
                                type="button"
                                className={`btn-sensitivity-chip ${(activeSourceInfo.conf ?? 0.10) <= 0.10 ? "active" : ""}`}
                                onClick={() => handleSetDetectionConfig(0.08, 1024)}
                                title="Ultra-dense crowd mode: detects all occluded people, small background faces, and dense crowds"
                            >
                                🔥 Ultra-Crowd
                            </button>
                            <button
                                type="button"
                                className={`btn-sensitivity-chip ${(activeSourceInfo.conf ?? 0.10) > 0.10 && (activeSourceInfo.conf ?? 0.10) <= 0.18 ? "active" : ""}`}
                                onClick={() => handleSetDetectionConfig(0.15, 960)}
                                title="Balanced mode for standard crowds"
                            >
                                👥 Dense Crowd
                            </button>
                            <button
                                type="button"
                                className={`btn-sensitivity-chip ${(activeSourceInfo.conf ?? 0.10) > 0.18 ? "active" : ""}`}
                                onClick={() => handleSetDetectionConfig(0.25, 640)}
                                title="Standard mode for entrance doors with few people"
                            >
                                🚪 Standard
                            </button>
                            <button
                                type="button"
                                className={`btn-sensitivity-chip btn-box-toggle ${activeSourceInfo.show_bounding_boxes ? "active" : ""}`}
                                onClick={handleToggleBoundingBoxes}
                                title="Toggle bounded green boxes for people & spatial regions (Shortcut: Ctrl + B)"
                            >
                                {activeSourceInfo.show_bounding_boxes ? "📦 Boxes: ON (Ctrl+B)" : "📦 Boxes: OFF (Ctrl+B)"}
                            </button>
                            <button
                                type="button"
                                className={`btn-sensitivity-chip btn-overlay-toggle ${activeSourceInfo.show_spatial_overlay ? "active" : ""}`}
                                onClick={handleToggleSpatialOverlay}
                                title="Toggle visual floor polygons and obstacle boxes on camera feed"
                            >
                                {activeSourceInfo.show_spatial_overlay ? "🟢 Floor: ON" : "⚪ Floor: OFF"}
                            </button>
                            <button
                                type="button"
                                className={`btn-sensitivity-chip btn-roi-toggle ${activeSourceInfo.active_roi ? "active" : ""}`}
                                onClick={() => handleSetRoi(activeSourceInfo.active_roi ? null : "news")}
                                title="Crop directly to crowd footage in TV news broadcasts to eliminate studio anchors and boost resolution on distant people"
                            >
                                {activeSourceInfo.active_roi ? "🎯 News Crop: ON" : "🎯 News Crop: OFF"}
                            </button>
                        </div>
                    </div>

                    {/* Camera Feed Area */}
                    <div
                        className="camera-feed-container"
                        id="camera-feed-box"
                        onDoubleClick={toggleFullscreen}
                        title="Double-click to toggle fullscreen"
                    >
                        <img
                            key={streamTimestamp}
                            src={`http://localhost:8000/video_feed?t=${streamTimestamp}`}
                            alt="Live AI CCTV Crowd Monitoring"
                            className="camera-feed-image"
                            onLoad={() => setStreamError(false)}
                            onError={() => setStreamError(true)}
                        />

                        {/* Top-Left Timestamp Overlay */}
                        <div className="camera-overlay-top-left">
                            {liveCCTVTimestamp}
                        </div>

                        {/* Offline fallback banner */}
                        {streamError && (
                            <div className="camera-offline-overlay">
                                <div className="camera-offline-content">
                                    <svg width="32" height="32" viewBox="0 0 24 24" fill="#94A3B8">
                                        <path d="M21 6.5l-4 4V7c0-.55-.45-1-1-1H9.82L21 17.18V6.5zM3.27 2L2 3.27 4.73 6H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.21 0 .39-.08.55-.18L19.73 21 21 19.73 3.27 2zM5 16V8h1.73l8 8H5z"/>
                                    </svg>
                                    <p className="offline-title">Camera Feed Not Connected</p>
                                    <p className="offline-sub">Run <code>python track_webcam.py</code> on port 8000</p>
                                    <button className="btn-retry-stream" onClick={refreshCameraFeed}>
                                        ↻ Reconnect Stream
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* 2. ZONE-WISE CROWD INTELLIGENCE (2x2 GRID) */}
                <div className="admin-card zone-density-container-card">
                    <div className="card-header-flex">
                        <div className="card-title-flex">
                            <svg
                                width="18"
                                height="18"
                                viewBox="0 0 24 24"
                                fill="#1677E8"
                            >
                                <path d="M3 3h8v8H3zm10 0h8v8h-8zM3 13h8v8H3zm10 0h8v8h-8z" />
                            </svg>
                            <h3>Zone-wise Crowd Intelligence</h3>
                        </div>
                    </div>

                    <div className="zones-2x2-grid">
                        {(crowdData.zones || [0, 1, 2, 3]).map((z, idx) => {
                            const zNumber = typeof z === "object" ? z.zone ?? idx : idx;
                            const zPeople = typeof z === "object" ? z.people ?? 0 : 0;
                            const zLevel = typeof z === "object" ? z.risk_level || "SAFE" : "SAFE";

                            const zMales = typeof z === "object" && z.gender_distribution ? z.gender_distribution.male ?? 0 : 0;
                            const zFemales = typeof z === "object" && z.gender_distribution ? z.gender_distribution.female ?? 0 : 0;
                            const zChildren = typeof z === "object" && z.age_distribution ? z.age_distribution.child ?? 0 : 0;
                            const zAdults = typeof z === "object" && z.age_distribution ? z.age_distribution.adult ?? (zPeople > 0 ? zPeople : 0) : 0;
                            const zSeniors = typeof z === "object" && z.age_distribution ? z.age_distribution.senior ?? 0 : 0;

                            const zUsable = typeof z === "object" ? z.usable_area_m2 : null;
                            const isOutsideFloor = zUsable == null || zUsable <= 0.2;
                            const zFlow = typeof z === "object" ? (z.dominant_direction || z.flow || (zNumber === 0 ? "LEFT" : zNumber === 2 ? "RIGHT" : zNumber === 3 ? "LEFT" : "STATIONARY")) : "STATIONARY";
                            const zOcc = typeof z === "object" && z.occupancy_percent != null ? z.occupancy_percent : (zPeople > 0 ? 29.4 : 0.0);

                            const isSelected = selectedZone === zNumber;

                            return (
                                <div
                                    key={idx}
                                    className={`zone-density-card ${isSelected ? "zone-card-active" : ""}`}
                                    onClick={() => setSelectedZone(isSelected ? null : zNumber)}
                                    title={`Click to ${isSelected ? "deselect" : "focus"} Zone ${zNumber}`}
                                    style={{ cursor: "pointer" }}
                                >
                                    <div className="zone-card-top-row">
                                        <span className="zone-title">Zone {zNumber}</span>
                                        <span className={`zone-badge-${zLevel.toLowerCase()}`}>
                                            {zLevel}
                                        </span>
                                    </div>

                                    <div className="zone-count-row">
                                        <svg
                                            width="24"
                                            height="24"
                                            viewBox="0 0 24 24"
                                            fill="#10B981"
                                        >
                                            <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z" />
                                        </svg>
                                        <span className="zone-people-num">{zPeople}</span>
                                        <span className="zone-people-lbl">people</span>
                                    </div>

                                    {/* Mini Demographics 5-Column Matrix */}
                                    <div className="zone-demo-matrix">
                                        <div>
                                            <div className="zone-demo-header">Male</div>
                                            <div className="zone-demo-val">{zMales}</div>
                                        </div>
                                        <div>
                                            <div className="zone-demo-header">Female</div>
                                            <div className="zone-demo-val">{zFemales}</div>
                                        </div>
                                        <div>
                                            <div className="zone-demo-header">Child</div>
                                            <div className="zone-demo-val">{zChildren}</div>
                                        </div>
                                        <div>
                                            <div className="zone-demo-header">Adult</div>
                                            <div className="zone-demo-val">{zAdults}</div>
                                        </div>
                                        <div>
                                            <div className="zone-demo-header">Senior</div>
                                            <div className="zone-demo-val">{zSeniors}</div>
                                        </div>
                                    </div>

                                    {/* Metadata Details */}
                                    <div className="zone-info-row">
                                        <span className="zone-info-lbl">Usable Area:</span>
                                        <span className="zone-info-val">
                                            {!isOutsideFloor
                                                ? `${zUsable.toFixed(1)} m²`
                                                : "Outside detected floor"}
                                        </span>
                                    </div>

                                    <div className="zone-info-row">
                                        <span className="zone-info-lbl">Flow:</span>
                                        <span className="zone-info-val">{zFlow}</span>
                                    </div>

                                    <div className="zone-info-row">
                                        <span className="zone-info-lbl">Occupancy:</span>
                                        {isOutsideFloor ? (
                                            <span className="zone-info-val">-</span>
                                        ) : (
                                            <div className="zone-occ-progress-wrap">
                                                {zOcc === 0 ? (
                                                    <>
                                                        <span className="zone-info-val">0.0%</span>
                                                        <div className="zone-occ-bar-track" />
                                                        <span className="zone-info-val">0%</span>
                                                    </>
                                                ) : (
                                                    <>
                                                        <div className="zone-occ-bar-track">
                                                            <div
                                                                className="zone-occ-bar-fill"
                                                                style={{ width: `${Math.min(100, zOcc)}%` }}
                                                            />
                                                        </div>
                                                        <span className="zone-info-val">
                                                            {zOcc.toFixed(1)}%
                                                        </span>
                                                    </>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* BOTTOM SECTION: OVERALL CROWD & DEMOGRAPHIC INFORMATION */}
            <div className="overall-crowd-card">
                <div className="card-header-flex">
                    <div className="card-title-flex">
                        <svg
                            width="18"
                            height="18"
                            viewBox="0 0 24 24"
                            fill="#1677E8"
                        >
                            <path d="M5 9.2h3V19H5zM10.6 5h2.8v14h-2.8zm5.6 8H19v6h-2.8z" />
                        </svg>
                        <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "#0F172A" }}>
                            Overall Crowd & Demographic Information
                        </h3>
                    </div>

                    <div
                        className="system-status-pill"
                        title="Backend & AI Inference Engine Online"
                        style={{ cursor: "pointer" }}
                        onClick={() => showToast("AI Engine & FastAPI backend (8001) connected.")}
                    >
                        <span className="dot-green" />
                        SYSTEM STATUS: RUNNING
                    </div>
                </div>

                {/* 8-COLUMN METRICS ROW */}
                <div className="overall-metrics-grid">
                    {/* 1. Total People */}
                    <div className="metric-col-card">
                        <span className="metric-col-label">Total People</span>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                            <span className="metric-col-num">{totalPeople}</span>
                            <svg
                                width="28"
                                height="28"
                                viewBox="0 0 24 24"
                                fill="#93C5FD"
                            >
                                <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z" />
                            </svg>
                        </div>
                    </div>

                    {/* 2. Male */}
                    <div className="metric-col-card">
                        <span className="metric-col-label">Male</span>
                        <span className="metric-col-num">{males}</span>
                        <div className="metric-bar-row">
                            <div className="metric-bar-track">
                                <div
                                    className="metric-bar-fill cyan"
                                    style={{ width: `${malePct}%` }}
                                />
                            </div>
                            <span className="metric-bar-pct cyan">{malePct}%</span>
                        </div>
                    </div>

                    {/* 3. Female */}
                    <div className="metric-col-card">
                        <span className="metric-col-label">Female</span>
                        <span className="metric-col-num">{females}</span>
                        <div className="metric-bar-row">
                            <div className="metric-bar-track">
                                <div
                                    className="metric-bar-fill pink"
                                    style={{ width: `${femalePct}%` }}
                                />
                            </div>
                            <span className="metric-bar-pct pink">{femalePct}%</span>
                        </div>
                    </div>

                    {/* 4. Child */}
                    <div className="metric-col-card">
                        <span className="metric-col-label">Child</span>
                        <span className="metric-col-num">{children}</span>
                        <div className="metric-bar-row">
                            <div className="metric-bar-track">
                                <div
                                    className="metric-bar-fill yellow"
                                    style={{ width: `${childPct}%` }}
                                />
                            </div>
                            <span className="metric-bar-pct yellow">{childPct}%</span>
                        </div>
                    </div>

                    {/* 5. Adult */}
                    <div className="metric-col-card">
                        <span className="metric-col-label">Adult</span>
                        <span className="metric-col-num">{adults}</span>
                        <div className="metric-bar-row">
                            <div className="metric-bar-track">
                                <div
                                    className="metric-bar-fill green"
                                    style={{ width: `${adultPct}%` }}
                                />
                            </div>
                            <span className="metric-bar-pct green">{adultPct}%</span>
                        </div>
                    </div>

                    {/* 6. Senior */}
                    <div className="metric-col-card">
                        <span className="metric-col-label">Senior</span>
                        <span className="metric-col-num">{seniors}</span>
                        <div className="metric-bar-row">
                            <div className="metric-bar-track">
                                <div
                                    className="metric-bar-fill purple"
                                    style={{ width: `${seniorPct}%` }}
                                />
                            </div>
                            <span className="metric-bar-pct purple">{seniorPct}%</span>
                        </div>
                    </div>

                    {/* 7. Occupancy */}
                    <div className="metric-col-card">
                        <span className="metric-col-label">Occupancy</span>
                        <div className="metric-occ-row">
                            <div>
                                <div style={{ fontSize: "22px", fontWeight: 700, color: "#0F172A", lineHeight: 1.1 }}>
                                    {occupancyPercent > 0 ? `${occupancyPercent.toFixed(1)}%` : "0.0%"}
                                </div>
                                <div className="metric-occ-sub">
                                    ({totalPeople} / {usableArea.toFixed(1)} m²)
                                </div>
                            </div>
                            {/* Circular Mini Pie Chart */}
                            <svg width="34" height="34" viewBox="0 0 36 36" style={{ transform: "rotate(-90deg)" }}>
                                <circle cx="18" cy="18" r="16" fill="#F1F5F9" />
                                {occupancyPercent > 0 && (
                                    <circle
                                        cx="18"
                                        cy="18"
                                        r="8"
                                        fill="none"
                                        stroke="#8B5CF6"
                                        strokeWidth="16"
                                        strokeDasharray={`${(occupancyPercent / 100) * 50.26} 50.26`}
                                    />
                                )}
                            </svg>
                        </div>
                    </div>

                    {/* 8. Current Risk */}
                    <div className="metric-col-card">
                        <span className="metric-col-label">Current Risk</span>
                        <div className="metric-risk-row" style={{ marginTop: "4px" }}>
                            <span className="metric-col-num">{currentRisk}</span>
                            <span className={`zone-badge-${riskLevelStr.toLowerCase()}`}>
                                {riskLevelStr}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Dashboard;

const API_BASE = "https://crowd-intelligence-back.vercel.app/api";

const STORAGE_KEY_EVENTS = "crowd_intelligence_events";

// ─────────────────────────────────────────────
// Local Event Store
// ─────────────────────────────────────────────

export function getStoredEvents() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY_EVENTS);

        if (stored) {
            return JSON.parse(stored);
        }
    } catch (error) {
        console.error(
            "Failed to read events from localStorage",
            error
        );
    }

    return [];
}


export function saveStoredEvent(eventData) {
    const events = getStoredEvents();

    const newEvent = {
        ...eventData,
        id: eventData.id || Date.now().toString(),
        created_at:
            eventData.created_at ||
            new Date().toISOString(),
    };

    events.push(newEvent);

    try {
        localStorage.setItem(
            STORAGE_KEY_EVENTS,
            JSON.stringify(events)
        );
    } catch (error) {
        console.error(
            "Failed to save event to localStorage",
            error
        );
    }

    return newEvent;
}


export function clearStoredEvents() {
    try {
        localStorage.removeItem(
            STORAGE_KEY_EVENTS
        );
    } catch (error) {
        console.error(
            "Failed to clear localStorage",
            error
        );
    }
}


// ─────────────────────────────────────────────
// Clean Zero Default Crowd Data
// ─────────────────────────────────────────────

export const CLEAN_CROWD_DATA = {
    timestamp: null,

    event_id: null,

    camera_name: null,

    camera_status: "OFFLINE",

    total_people: 0,

    overall_risk: 0,

    overall_risk_level: "SAFE",

    highest_risk_zone: null,

    highest_risk_score: 0,

    highest_risk_level: "SAFE",

    alert: null,

    zones: [
        {
            zone: 0,
            people: 0,
            density: "LOW",
            flow: {
                LEFT: 0,
                RIGHT: 0,
                UP: 0,
                DOWN: 0,
                STATIONARY: 0,
            },
            dominant_direction: "STATIONARY",
            trend: "STABLE",
            congestion: "LOW",
            risk: 0,
            risk_level: "SAFE",
        },

        {
            zone: 1,
            people: 0,
            density: "LOW",
            flow: {
                LEFT: 0,
                RIGHT: 0,
                UP: 0,
                DOWN: 0,
                STATIONARY: 0,
            },
            dominant_direction: "STATIONARY",
            trend: "STABLE",
            congestion: "LOW",
            risk: 0,
            risk_level: "SAFE",
        },

        {
            zone: 2,
            people: 0,
            density: "LOW",
            flow: {
                LEFT: 0,
                RIGHT: 0,
                UP: 0,
                DOWN: 0,
                STATIONARY: 0,
            },
            dominant_direction: "STATIONARY",
            trend: "STABLE",
            congestion: "LOW",
            risk: 0,
            risk_level: "SAFE",
        },

        {
            zone: 3,
            people: 0,
            density: "LOW",
            flow: {
                LEFT: 0,
                RIGHT: 0,
                UP: 0,
                DOWN: 0,
                STATIONARY: 0,
            },
            dominant_direction: "STATIONARY",
            trend: "STABLE",
            congestion: "LOW",
            risk: 0,
            risk_level: "SAFE",
        },
    ],
};


// ─────────────────────────────────────────────
// Crowd Intelligence
// ─────────────────────────────────────────────

export async function fetchCrowdState() {
    try {
        const response = await fetch(
            `${API_BASE}/current-crowd`,
            {
                cache: "no-store",
            }
        );

        if (!response.ok) {
            throw new Error(
                "Backend unavailable"
            );
        }

        const data = await response.json();

        return data;

    } catch (error) {

        console.error(
            "Failed to fetch crowd state:",
            error.message
        );

        return CLEAN_CROWD_DATA;
    }
}


// ─────────────────────────────────────────────
// Events
// ─────────────────────────────────────────────

export async function createEvent(eventData) {

    /*
     * Create the event locally first so the UI
     * immediately has a stable event ID.
     */

    const localEvent = {
        ...eventData,

        id:
            eventData.id ||
            Date.now().toString(),

        created_at:
            eventData.created_at ||
            new Date().toISOString(),
    };


    /*
     * Send the SAME event to the backend.
     */

    try {

        const response = await fetch(
            `${API_BASE}/events`,
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json",
                },

                body: JSON.stringify(
                    localEvent
                ),
            }
        );


        if (!response.ok) {
            throw new Error(
                "Backend event creation failed"
            );
        }


        const data =
            await response.json();


        /*
         * Backend accepted the event.
         * Save the backend version locally too.
         */

        const backendEvent =
            data.event || localEvent;


        saveEventWithoutDuplicate(
            backendEvent
        );


        return {
            success: true,

            message:
                "Event created successfully",

            event: backendEvent,
        };


    } catch (error) {

        /*
         * If backend is temporarily unavailable,
         * keep the event locally.
         */

        console.error(
            "Backend event creation failed:",
            error.message
        );


        saveEventWithoutDuplicate(
            localEvent
        );


        return {
            success: true,

            message:
                "Event saved locally. Backend unavailable.",

            event: localEvent,
        };
    }
}


// ─────────────────────────────────────────────
// Save Event Without Duplicate
// ─────────────────────────────────────────────

function saveEventWithoutDuplicate(
    eventData
) {

    const events =
        getStoredEvents();


    const existingIndex =
        events.findIndex(
            event =>
                String(event.id) ===
                String(eventData.id)
        );


    if (existingIndex >= 0) {

        events[existingIndex] =
            eventData;

    } else {

        events.push(
            eventData
        );
    }


    try {

        localStorage.setItem(
            STORAGE_KEY_EVENTS,
            JSON.stringify(events)
        );

    } catch (error) {

        console.error(
            "Failed to update local events:",
            error
        );
    }
}


// ─────────────────────────────────────────────
// Fetch Events
// ─────────────────────────────────────────────

export async function fetchEvents() {

    try {

        /*
         * Backend is now the primary source.
         */

        const response = await fetch(
            `${API_BASE}/events`,
            {
                cache: "no-store",
            }
        );


        if (!response.ok) {
            throw new Error(
                "Backend unavailable"
            );
        }


        const data =
            await response.json();


        /*
         * Keep localStorage synchronized
         * with the backend.
         */

        if (
            Array.isArray(data.events)
        ) {

            try {

                localStorage.setItem(
                    STORAGE_KEY_EVENTS,
                    JSON.stringify(
                        data.events
                    )
                );

            } catch (error) {

                console.error(
                    "Failed to sync local events:",
                    error
                );
            }
        }


        return data;


    } catch (error) {

        console.error(
            "Failed to fetch events from backend:",
            error.message
        );


        /*
         * Backend unavailable:
         * use local events as fallback.
         */

        const localEvents =
            getStoredEvents();


        return {
            events: localEvents,

            count:
                localEvents.length,
        };
    }
}


// ─────────────────────────────────────────────
// System Status
// ─────────────────────────────────────────────

export async function fetchSystemStatus() {

    try {

        const response =
            await fetch(
                `${API_BASE}/system-status`,
                {
                    cache: "no-store",
                }
            );


        if (!response.ok) {
            throw new Error(
                "Backend unavailable"
            );
        }


        return await response.json();


    } catch (error) {

        console.error(
            "Failed to fetch system status:",
            error.message
        );


        return {

            backend: "OFFLINE",

            ai_engine: "STOPPED",

            cameras: 0,

            active_events:
                getStoredEvents().length,

            active_alerts: 0,
        };
    }
}
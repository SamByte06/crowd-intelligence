// ==============================================================================
// AI Crowd Intelligence — Dedicated Background Web Worker
// Runs in a background thread unaffected by browser tab visibility throttling
// ==============================================================================

let activeVenueId = null;
let pollInterval = 3000; // 3-second rapid background polling
let timerId = null;

self.onmessage = function (e) {
  const { type, venueId } = e.data;

  if (type === 'START') {
    activeVenueId = venueId;
    if (timerId) clearInterval(timerId);
    poll();
    timerId = setInterval(poll, pollInterval);
  } else if (type === 'STOP') {
    activeVenueId = null;
    if (timerId) {
      clearInterval(timerId);
      timerId = null;
    }
  }
};

async function poll() {
  if (!activeVenueId) return;

  try {
    const [occRes, fcRes] = await Promise.all([
      fetch(`/api/v1/venues/${activeVenueId}/occupancy`, { cache: 'no-store' }),
      fetch(`/api/v1/venues/${activeVenueId}/forecast`, { cache: 'no-store' }),
    ]);

    if (occRes.ok) {
      const occData = await occRes.json();
      const fcData = fcRes.ok ? await fcRes.json() : null;

      self.postMessage({
        type: 'STATE_UPDATE',
        occupancy: occData,
        forecast: fcData,
        timestamp: Date.now(),
      });
    }
  } catch (err) {
    // Network hiccup - silently continue
  }
}

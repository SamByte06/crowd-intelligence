// ==============================================================================
// AI Crowd Intelligence — Service Worker for System-Level Push Notifications
// Operates autonomously in background even when user moves to Instagram/other apps
// ==============================================================================

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// 1. Native Web Push Event: Receives real push from Google FCM / Backend
// Delivers notification straight to phone even if browser is closed / in Instagram!
self.addEventListener('push', (event) => {
  let data = {};
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data = { title: 'Crowd Intelligence Alert', options: { body: event.data.text() } };
    }
  }

  const title = data.title || '🚨 Live Crowd Alert';
  const options = {
    icon: '/favicon.svg',
    badge: '/favicon.svg',
    vibrate: [400, 150, 400, 150, 400],
    requireInteraction: true,
    ...data.options,
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// 2. Click on notification brings user directly back to the active event page
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const urlToOpen = event.notification.data?.url || '/';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if ('focus' in client) {
          if (client.url.includes(urlToOpen)) {
            return client.focus();
          }
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(urlToOpen);
      }
    })
  );
});

// Track monitored venues for autonomous background monitoring in service worker
const monitoredVenues = new Map();
let swPollIntervalId = null;

// 3. Handle commands from frontend tabs
self.addEventListener('message', (event) => {
  if (!event.data) return;

  const { type } = event.data;

  // Direct notification display request
  if (type === 'SHOW_NOTIFICATION') {
    const { title, options } = event.data;
    const isSilentTimeline = options?.tag === 'live-crowd-timeline' || options?.renotify === false;

    self.registration.showNotification(title, {
      icon: '/favicon.svg',
      badge: '/favicon.svg',
      vibrate: isSilentTimeline ? [] : [350, 120, 350],
      requireInteraction: !isSilentTimeline,
      renotify: !isSilentTimeline,
      silent: isSilentTimeline,
      ...options,
    });
  }

  // Start autonomous background monitoring for an event
  else if (type === 'START_BACKGROUND_MONITOR') {
    const { venueId, venueName } = event.data;
    if (venueId) {
      monitoredVenues.set(venueId, {
        name: venueName || 'Event Venue',
        lastLevel: 'NORMAL',
        lastAlertTime: 0,
        lastTimelineTime: 0,
        lastPercent: -1,
      });

      if (!swPollIntervalId) {
        checkAllMonitoredVenues();
        swPollIntervalId = setInterval(checkAllMonitoredVenues, 3500);
      }
    }
  }

  // Stop monitoring
  else if (type === 'STOP_BACKGROUND_MONITOR') {
    const { venueId } = event.data;
    if (venueId) {
      monitoredVenues.delete(venueId);
    }
    if (monitoredVenues.size === 0 && swPollIntervalId) {
      clearInterval(swPollIntervalId);
      swPollIntervalId = null;
    }
  }
});

// Autonomous background polling loop inside Service Worker
async function checkAllMonitoredVenues() {
  if (monitoredVenues.size === 0) return;

  for (const [venueId, state] of monitoredVenues.entries()) {
    try {
      const [occRes, fcRes] = await Promise.all([
        fetch(`/api/v1/venues/${venueId}/occupancy`, { cache: 'no-store' }),
        fetch(`/api/v1/venues/${venueId}/forecast`, { cache: 'no-store' }),
      ]);

      if (!occRes.ok) continue;

      const occ = await occRes.json();
      const fc = fcRes.ok ? await fcRes.json() : null;

      const percent = occ.percentage || 0;
      const count = occ.current_occupancy || 0;
      const cap = occ.effective_capacity || 1000;
      const timeToCap = fc?.time_to_capacity_minutes ?? null;
      const netInflow = fc?.net_inflow_rate ?? 0;
      const venueName = state.name || occ.venue_name || 'Event';
      const now = Date.now();

      // A. Silent In-Place Live Timeline Update (every 12 seconds or when % changes)
      const timeElapsed = now - state.lastTimelineTime >= 12000;
      const percentChanged = Math.abs(percent - state.lastPercent) >= 1;

      if (timeElapsed || percentChanged) {
        state.lastTimelineTime = now;
        state.lastPercent = percent;

        const statusEmoji = percent >= 90 ? '🔴' : percent >= 75 ? '🟡' : '🟢';
        const statusWord = percent >= 90 ? 'CRITICAL CAPACITY' : percent >= 75 ? 'HIGH RUSH' : 'SAFE FLOW';
        const timeText = percent >= 100
          ? 'Area is 100% FULL'
          : timeToCap !== null && timeToCap > 0
          ? `Full in ~${Math.round(timeToCap)}m`
          : 'Steady Flow';

        const flowText = netInflow > 0 ? `+${netInflow}/m` : `${netInflow}/m`;
        const title = `${statusEmoji} ${statusWord}: ${venueName}`;
        const body =
          `⏱️ ${timeText}  |  👥 ${percent}% (${count.toLocaleString()}/${cap.toLocaleString()})\n` +
          `⚡ Speed: ${flowText}  |  [Safe 🟢 ──> Rush 🟡 ──> Full 🔴]`;

        self.registration.showNotification(title, {
          body,
          icon: '/favicon.svg',
          badge: '/favicon.svg',
          tag: 'live-crowd-timeline',
          renotify: false,
          silent: true,
          requireInteraction: false,
          data: { url: `/events/${venueId}` },
        });
      }

      // B. Separate Urgent Alarms (Moderate / Critical)
      let currentLevel = 'NORMAL';
      if (percent >= 90) {
        currentLevel = 'CRITICAL';
      } else if (percent >= 75 || (timeToCap !== null && timeToCap <= 15 && netInflow > 10)) {
        currentLevel = 'WARNING';
      }

      const prevLevel = state.lastLevel;
      const cooldownPassed = now - state.lastAlertTime >= 300000; // 5 min cooldown

      if (currentLevel !== 'NORMAL' && (currentLevel !== prevLevel || cooldownPassed)) {
        state.lastLevel = currentLevel;
        state.lastAlertTime = now;

        const isCritical = currentLevel === 'CRITICAL';
        const title = isCritical
          ? `🚨 CRITICAL CROWD ALARM • ${venueName}`
          : `⚠️ MODERATE RUSH WARNING • ${venueName}`;

        const alertBody = isCritical
          ? `Area is ${percent}% FULL! Expected to reach capacity in ~${Math.round(timeToCap || 5)} minutes. Entrance holds in effect.`
          : `Venue reached ${percent}% capacity. High inflow (+${netInflow}/min). Main gate queues are forming.`;

        self.registration.showNotification(title, {
          body: alertBody,
          icon: '/favicon.svg',
          badge: '/favicon.svg',
          tag: `crowd-alert-${currentLevel.toLowerCase()}`,
          renotify: true,
          silent: false,
          vibrate: isCritical ? [400, 150, 400, 150, 400] : [300, 100, 300],
          requireInteraction: true,
          data: { url: `/events/${venueId}` },
        });
      } else if (currentLevel === 'NORMAL' && prevLevel !== 'NORMAL') {
        state.lastLevel = 'NORMAL';
      }
    } catch (err) {
      // Ignore background fetch network glitches
    }
  }
}

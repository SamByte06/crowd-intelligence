/**
 * System-Level Notification Service
 * Dispatches notifications directly into the operating system notification shade:
 * - Windows Action Center / Notification Tray
 * - Android Notification Drawer
 * - macOS Notification Center
 */

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
    return null
  }
  try {
    const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' })
    return reg
  } catch (err) {
    console.debug('Service Worker registration note:', err)
    return null
  }
}

export function getSystemNotificationPermission(): NotificationPermission {
  if (typeof window === 'undefined' || !('Notification' in window)) {
    return 'denied'
  }
  return Notification.permission
}

export async function requestSystemNotificationPermission(): Promise<boolean> {
  if (typeof window === 'undefined' || !('Notification' in window)) {
    return false
  }
  try {
    await registerServiceWorker()
    const result = await Notification.requestPermission()
    return result === 'granted'
  } catch (err) {
    console.debug('Permission request error:', err)
    return false
  }
}

export interface SystemNotificationOptions {
  body: string
  tag?: string
  data?: any
  requireInteraction?: boolean
  silent?: boolean
  renotify?: boolean
  vibrate?: number[]
}

/**
 * Dispatches a native OS system notification.
 * Uses ServiceWorker registration (mandatory for Android & backgrounded Windows desktop tabs).
 */
export async function sendSystemNotification(
  title: string,
  options: SystemNotificationOptions
): Promise<boolean> {
  if (typeof window === 'undefined' || !('Notification' in window)) {
    return false
  }

  if (Notification.permission !== 'granted') {
    return false
  }

  const isTimeline = options.tag === 'live-crowd-timeline' || options.renotify === false
  const notificationPayload = {
    body: options.body,
    icon: '/favicon.svg',
    badge: '/favicon.svg',
    tag: options.tag || 'crowd-status-alert',
    renotify: options.renotify ?? !isTimeline,
    silent: options.silent ?? isTimeline,
    requireInteraction: options.requireInteraction ?? !isTimeline,
    vibrate: options.vibrate ?? (isTimeline ? [] : [300, 100, 300]),
    data: options.data || { url: window.location.pathname },
  }

  // 1. Primary: Service Worker Registration (Required for Android & Background Tabs)
  if ('serviceWorker' in navigator) {
    try {
      const reg = await navigator.serviceWorker.ready
      if (reg && reg.showNotification) {
        await reg.showNotification(title, notificationPayload)
        return true
      }
    } catch (e) {
      console.debug('Service worker showNotification fallback:', e)
    }
  }

  // 2. Secondary Fallback: Direct DOM Notification
  try {
    new Notification(title, notificationPayload)
    return true
  } catch (e) {
    console.debug('Direct Notification fallback error:', e)
    return false
  }
}

/**
 * Updates the persistent silent live timeline notification (Flipkart/Zomato style).
 * Updates in-place without buzzing, ringing, or creating multiple cards.
 */
export async function updateLiveTimelineNotification(
  venueName: string,
  percent: number,
  currentCount: number,
  capacity: number,
  timeToCapacity: number | null,
  netInflow: number
): Promise<boolean> {
  const statusEmoji = percent >= 90 ? '🔴' : percent >= 75 ? '🟡' : '🟢'
  const statusWord = percent >= 90 ? 'CRITICAL CAPACITY' : percent >= 75 ? 'HIGH RUSH' : 'SAFE FLOW'

  const timeText =
    percent >= 100
      ? 'Area is 100% FULL'
      : timeToCapacity !== null && timeToCapacity > 0
      ? `Full in ~${Math.round(timeToCapacity)}m`
      : 'Steady Flow'

  const flowText = netInflow > 0 ? `+${netInflow}/m` : `${netInflow}/m`
  const title = `${statusEmoji} ${statusWord}: ${venueName}`
  
  // Clean delivery-tracker / timeline layout
  const body =
    `⏱️ ${timeText}  |  👥 ${percent}% (${currentCount.toLocaleString()}/${capacity.toLocaleString()})\n` +
    `⚡ Speed: ${flowText}  |  [Safe 🟢 ──> Rush 🟡 ──> Full 🔴]`

  return sendSystemNotification(title, {
    body,
    tag: 'live-crowd-timeline', // Fixed tag ensures in-place update!
    renotify: false,            // Zero buzz / zero re-ring!
    silent: true,               // Completely silent background update!
    requireInteraction: false,
  })
}

/**
 * Dispatches an urgent threshold alarm (Moderate/Warning or Critical).
 * Sends separately with ring & vibrate only when a threshold boundary is breached.
 */
export async function sendUrgentAlertNotification(
  venueName: string,
  severity: 'WARNING' | 'CRITICAL',
  message: string
): Promise<boolean> {
  const iconEmoji = severity === 'CRITICAL' ? '🚨' : '⚠️'
  const title = `${iconEmoji} ${severity === 'CRITICAL' ? 'CRITICAL CROWD ALERT' : 'RUSH WARNING'} • ${venueName}`

  return sendSystemNotification(title, {
    body: message,
    tag: `crowd-alert-${severity.toLowerCase()}`, // Distinct tag from timeline
    renotify: true,                               // Buzzes and rings for real danger!
    silent: false,
    requireInteraction: true,                     // Remains in action center
    vibrate: severity === 'CRITICAL' ? [400, 150, 400, 150, 400] : [300, 100, 300],
  })
}

/**
 * Triggers a test system notification so user can verify it pops up in their OS tray.
 */
export async function sendTestNotification(venueName: string = 'Current Venue'): Promise<boolean> {
  return sendSystemNotification(`🔔 Notification Test: ${venueName}`, {
    body: 'System notifications are active! Live timeline updates quietly in place, and urgent alerts buzz separately.',
    tag: 'test-notification',
    requireInteraction: false,
  })
}

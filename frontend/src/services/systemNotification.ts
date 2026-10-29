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

  const notificationPayload = {
    body: options.body,
    icon: '/favicon.svg',
    badge: '/favicon.svg',
    tag: options.tag || 'crowd-status-alert',
    renotify: true,
    requireInteraction: options.requireInteraction ?? true, // Stays in Action Center
    vibrate: [300, 100, 300, 100, 300],
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
 * Triggers a test system notification so user can verify it pops up in their OS tray.
 */
export async function sendTestNotification(venueName: string = 'Current Venue'): Promise<boolean> {
  return sendSystemNotification(`🔔 Notification Test: ${venueName}`, {
    body: 'System notifications are active! You will receive live alerts here even if you switch apps or minimize this tab.',
    tag: 'test-notification',
    requireInteraction: false,
  })
}

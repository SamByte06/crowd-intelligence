/**
 * System-Level Notification & Background Keep-Alive Service
 * Dispatches notifications directly into the operating system notification shade:
 * - Windows Action Center / Notification Tray
 * - Android Notification Drawer
 * - macOS Notification Center
 */

let keepAliveAudioCtx: AudioContext | null = null
let keepAliveOsc: OscillatorNode | null = null
let keepAliveAudioElement: HTMLAudioElement | null = null

// Standard 44-byte silent WAV data URI
const SILENT_WAV_URI = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA'

function urlB64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

/**
 * Subscribes the device to server-side Web Push (VAPID / Google FCM).
 * Pushes alerts from the server directly to the phone even if Chrome is closed or inside Instagram!
 */
export async function subscribeToBackendWebPush(venueId: string): Promise<boolean> {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator) || !('PushManager' in window)) {
    return false
  }

  try {
    const reg = await registerServiceWorker()
    if (!reg) return false

    // Fetch VAPID public key from backend
    const keyRes = await fetch('/api/v1/push/vapid-public-key')
    if (!keyRes.ok) return false
    const { publicKey } = await keyRes.json()
    if (!publicKey) return false

    // Subscribe via browser PushManager with active VAPID key
    const appKey = urlB64ToUint8Array(publicKey)
    let sub = await reg.pushManager.getSubscription()
    if (sub) {
      try {
        await sub.unsubscribe()
      } catch (e) {
        console.debug('Subscription cleanup note:', e)
      }
    }

    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: appKey as unknown as BufferSource,
    })

    // Register subscription with backend
    const regRes = await fetch('/api/v1/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        venue_id: venueId,
        subscription: sub.toJSON(),
      }),
    })

    return regRes.ok
  } catch (err) {
    console.warn('Backend Web Push subscription note:', err)
    return false
  }
}

/**
 * Triggers a real server-side push test to verify delivery to mobile notification tray.
 * If delaySeconds > 0, the server waits that long before dispatching, allowing user to switch to Instagram!
 */
export async function triggerBackendTestPush(venueId: string, delaySeconds: number = 0): Promise<boolean> {
  try {
    const res = await fetch('/api/v1/push/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ venue_id: venueId, delay_seconds: delaySeconds }),
    })
    return res.ok
  } catch (e) {
    console.debug('Trigger test push error:', e)
    return false
  }
}

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
 * Informs the Service Worker to autonomously monitor the venue in background.
 * Works even if tab is frozen or user switched to Instagram / WhatsApp!
 */
export async function startBackgroundServiceWorkerMonitoring(
  venueId: string,
  venueName: string
): Promise<void> {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return
  try {
    const reg = await navigator.serviceWorker.ready
    if (reg && reg.active) {
      reg.active.postMessage({
        type: 'START_BACKGROUND_MONITOR',
        venueId,
        venueName,
      })
    }
  } catch (e) {
    console.debug('SW background monitor init note:', e)
  }
}

export async function stopBackgroundServiceWorkerMonitoring(venueId: string): Promise<void> {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return
  try {
    const reg = await navigator.serviceWorker.ready
    if (reg && reg.active) {
      reg.active.postMessage({
        type: 'STOP_BACKGROUND_MONITOR',
        venueId,
      })
    }
  } catch (e) {
    console.debug('SW background monitor stop note:', e)
  }
}

/**
 * Starts an inaudible, silent HTML5 Audio loop and MediaSession registration.
 * This instructs the OS / mobile browser NOT to suspend or kill the background tab
 * when the user switches to Instagram, WhatsApp, or locks the phone.
 */
export function startAudioKeepAlive(venueName: string = 'Crowd Intelligence'): void {
  try {
    // 1. HTML5 Audio Element Loop (Primary Android Background Keep-Alive)
    if (!keepAliveAudioElement) {
      keepAliveAudioElement = new Audio(SILENT_WAV_URI)
      keepAliveAudioElement.loop = true
      keepAliveAudioElement.volume = 0.01 // Minimal non-zero volume allows MediaSession on Android
      keepAliveAudioElement.play().catch(() => {
        // User gesture may be required on some strict browsers
      })
    }

    // 2. MediaSession Registration (tells Android OS this is an active foreground task)
    if ('mediaSession' in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: 'Crowd Intelligence Live Monitoring',
        artist: venueName,
        album: 'Active Background Guard',
      })
      navigator.mediaSession.playbackState = 'playing'
    }

    // 3. AudioContext Oscillator (Desktop fallback)
    if (!keepAliveAudioCtx) {
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext
      if (AudioContextClass) {
        keepAliveAudioCtx = new AudioContextClass()
        const gainNode = keepAliveAudioCtx.createGain()
        gainNode.gain.setValueAtTime(0.00001, keepAliveAudioCtx.currentTime)

        keepAliveOsc = keepAliveAudioCtx.createOscillator()
        keepAliveOsc.frequency.setValueAtTime(1, keepAliveAudioCtx.currentTime)
        keepAliveOsc.connect(gainNode)
        gainNode.connect(keepAliveAudioCtx.destination)
        keepAliveOsc.start()
      }
    }
  } catch (e) {
    console.debug('Audio keep-alive initialization note:', e)
  }
}

export function stopAudioKeepAlive(): void {
  try {
    if (keepAliveAudioElement) {
      keepAliveAudioElement.pause()
      keepAliveAudioElement.src = ''
      keepAliveAudioElement = null
    }
    if ('mediaSession' in navigator) {
      navigator.mediaSession.playbackState = 'none'
    }
    if (keepAliveOsc) {
      keepAliveOsc.stop()
      keepAliveOsc.disconnect()
      keepAliveOsc = null
    }
    if (keepAliveAudioCtx) {
      keepAliveAudioCtx.close()
      keepAliveAudioCtx = null
    }
  } catch (e) {
    console.debug('Audio keep-alive cleanup note:', e)
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
  const body =
    `⏱️ ${timeText}  |  👥 ${percent}% (${currentCount.toLocaleString()}/${capacity.toLocaleString()})\n` +
    `⚡ Speed: ${flowText}  |  [Safe 🟢 ──> Rush 🟡 ──> Full 🔴]`

  return sendSystemNotification(title, {
    body,
    tag: 'live-crowd-timeline',
    renotify: false,
    silent: true,
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
  const title = `${iconEmoji} ${severity === 'CRITICAL' ? 'CRITICAL CROWD ALARM' : 'RUSH WARNING'} • ${venueName}`

  return sendSystemNotification(title, {
    body: message,
    tag: `crowd-alert-${severity.toLowerCase()}`,
    renotify: true,
    silent: false,
    requireInteraction: true,
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

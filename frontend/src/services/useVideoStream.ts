import { useEffect, useRef, useState } from 'react';

/**
 * Hook to receive multiplexed live camera JPEG frames over a single WebSocket connection.
 * Multiplexes frames for all gates in a venue over 1 single socket, bypassing the browser's
 * 6-concurrent HTTP connection pool limit entirely.
 */
export function useVideoStreams(venueId: string | null) {
  const [frames, setFrames] = useState<Record<string, string>>({});
  const activeUrlsRef = useRef<Record<string, string>>({});

  useEffect(() => {
    if (!venueId) return;

    let active = true;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      if (!active) return;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/streams/${venueId}`;
      ws = new WebSocket(wsUrl);
      ws.binaryType = 'arraybuffer';

      ws.onmessage = (event) => {
        if (!active || !(event.data instanceof ArrayBuffer)) return;
        const buffer = event.data;
        if (buffer.byteLength <= 36) return;

        // Gate ID is exactly the first 36 ASCII bytes
        const gateId = new TextDecoder().decode(new Uint8Array(buffer, 0, 36)).trim();
        const jpegBytes = new Uint8Array(buffer, 36);
        const blob = new Blob([jpegBytes], { type: 'image/jpeg' });
        const newUrl = URL.createObjectURL(blob);

        // Revoke the old ObjectURL for this gate to prevent memory leaks
        if (activeUrlsRef.current[gateId]) {
          URL.revokeObjectURL(activeUrlsRef.current[gateId]);
        }
        activeUrlsRef.current[gateId] = newUrl;

        setFrames((prev) => ({ ...prev, [gateId]: newUrl }));
      };

      ws.onclose = () => {
        if (active) {
          reconnectTimer = setTimeout(connect, 2000);
        }
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();

    return () => {
      active = false;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) ws.close();
      // Revoke all created URLs on unmount
      Object.values(activeUrlsRef.current).forEach((url) => URL.revokeObjectURL(url));
      activeUrlsRef.current = {};
    };
  }, [venueId]);

  return frames;
}


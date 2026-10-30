import { useState, useEffect } from 'react';
import { Server, Check, X, ExternalLink, RefreshCw } from 'lucide-react';
import { getBackendBaseUrl, setBackendBaseUrl } from '../services/api';

interface ServerConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  connectionStatus?: string;
}

export default function ServerConfigModal({ isOpen, onClose, connectionStatus }: ServerConfigModalProps) {
  const [url, setUrl] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setUrl(getBackendBaseUrl());
      setSaved(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = () => {
    setBackendBaseUrl(url);
    setSaved(true);
    setTimeout(() => {
      onClose();
      window.location.reload();
    }, 600);
  };

  const handleReset = () => {
    setUrl('');
    setBackendBaseUrl('');
    setSaved(true);
    setTimeout(() => {
      onClose();
      window.location.reload();
    }, 600);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs animate-fadeIn">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-200">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
              <Server className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">AI Host Server Connection</h3>
              <p className="text-[11px] text-slate-500">Configure Cloudflare Tunnel or local server URL</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="my-4 space-y-3">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Backend Cloudflare / Host URL
            </label>
            <input
              type="url"
              placeholder="e.g. https://xxxx.trycloudflare.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs font-mono text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-hidden focus:ring-1 focus:ring-blue-500"
            />
            <p className="mt-1 text-[11px] text-slate-500">
              Paste your active Cloudflare tunnel URL when frontend is hosted on Vercel. Leave blank if running on the same server.
            </p>
          </div>

          <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-xs flex items-center justify-between">
            <span className="text-slate-600">Current Status:</span>
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full font-bold text-[10px] ${
                connectionStatus === 'CONNECTED'
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-amber-100 text-amber-800'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  connectionStatus === 'CONNECTED' ? 'bg-emerald-500' : 'bg-amber-500'
                }`}
              />
              {connectionStatus === 'CONNECTED' ? 'CONNECTED' : 'STANDBY / OFFLINE'}
            </span>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-3">
          <button
            type="button"
            onClick={handleReset}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
          >
            Reset (Same Host)
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-blue-700 transition shadow-xs"
          >
            {saved ? <Check className="h-3.5 w-3.5" /> : <RefreshCw className="h-3.5 w-3.5" />}
            <span>{saved ? 'Saved!' : 'Save & Connect'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

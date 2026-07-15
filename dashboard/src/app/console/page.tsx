"use client";

import React, { useEffect, useState, useRef } from "react";
import { useDashboard } from "@/context/DashboardContext";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import { Terminal, Trash2, ArrowDown, Search, Cpu, HardDrive } from "lucide-react";

export default function LiveConsole() {
  const { wsUrl, token } = useDashboard();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [filter, setFilter] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  
  const terminalEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!token) return;

    const connectWS = () => {
      setStatus("connecting");
      try {
        const ws = new WebSocket(`${wsUrl}/api/ws/console`);
        wsRef.current = ws;

        ws.onopen = () => {
          setStatus("connected");
          setLogs((prev) => [...prev, `[SYSTEM] Terminal socket connection established.`]);
        };

        ws.onmessage = (event) => {
          setLogs((prev) => [...prev, event.data].slice(-499)); // Keep last 500 lines
        };

        ws.onclose = () => {
          setStatus("disconnected");
          setLogs((prev) => [...prev, `[SYSTEM] Terminal socket connection lost. Reconnecting in 5s...`]);
          setTimeout(connectWS, 5000);
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch (err) {
        console.error("WebSocket connection error:", err);
        setStatus("disconnected");
      }
    };

    connectWS();

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, [token, wsUrl]);

  // Handle Autoscrolling
  useEffect(() => {
    if (autoScroll && terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll]);

  const filteredLogs = logs.filter((log) =>
    log.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="min-h-screen flex bg-[#030305] text-zinc-100 font-['Plus_Jakarta_Sans']">
      <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />

      <div className="flex-1 lg:pl-64 flex flex-col min-w-0">
        <Header onMenuClick={() => setMobileOpen(true)} />

        <main className="flex-grow p-6 space-y-6 max-w-[1280px] mx-auto w-full flex flex-col h-[calc(100vh-4rem)]">
          {/* Header Panel */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 bg-zinc-950/40 rounded-2xl border border-zinc-800/40">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-indigo-500/10 rounded-xl border border-indigo-500/25 text-indigo-400">
                <Terminal className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-zinc-100">Live Bot Console</h2>
                <p className="text-xs text-zinc-500">
                  Real-time broadcast streams of python logger events and AutoMod checks
                </p>
              </div>
            </div>

            {/* Terminal Actions */}
            <div className="flex flex-wrap items-center gap-3">
              {/* Search filter */}
              <div className="relative">
                <input
                  type="text"
                  placeholder="Filter logs..."
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="pl-8 pr-3 py-1.5 bg-zinc-900/60 rounded-xl border border-zinc-800/50 text-zinc-300 text-xs font-semibold focus:outline-none focus:border-indigo-500/50 w-44"
                />
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500" />
              </div>

              {/* Status Indicator */}
              <span
                className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase border ${
                  status === "connected"
                    ? "bg-green-500/5 border-green-500/20 text-green-400"
                    : status === "connecting"
                    ? "bg-yellow-500/5 border-yellow-500/20 text-yellow-400"
                    : "bg-red-500/5 border-red-500/20 text-red-400"
                }`}
              >
                {status}
              </span>

              {/* Clear button */}
              <button
                onClick={() => setLogs([])}
                className="p-1.5 text-zinc-400 hover:text-zinc-200 bg-zinc-900/60 rounded-lg border border-zinc-800/50 hover:bg-zinc-800/60 transition cursor-pointer"
                title="Clear console"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Terminal Screen (Grows to fill) */}
          <div className="flex-1 min-h-0 rounded-2xl bg-[#010103] border border-zinc-800/50 p-5 font-mono text-[12px] leading-relaxed flex flex-col relative">
            <div className="flex-1 overflow-y-auto space-y-1.5 scrollbar-thin pr-2 select-text selection:bg-indigo-500/25">
              {filteredLogs.length === 0 ? (
                <div className="h-full flex items-center justify-center text-zinc-600 text-xs italic">
                  -- Terminal output buffer clean --
                </div>
              ) : (
                filteredLogs.map((log, idx) => {
                  let logColor = "text-zinc-400";
                  if (log.includes("[ERROR]")) logColor = "text-red-400";
                  else if (log.includes("[WARNING]")) logColor = "text-yellow-400";
                  else if (log.includes("[INFO]")) logColor = "text-zinc-300";
                  else if (log.includes("[SYSTEM]")) logColor = "text-indigo-400 font-bold";
                  
                  return (
                    <div key={idx} className={`${logColor} whitespace-pre-wrap break-all hover:bg-zinc-900/20 px-1 py-0.5 rounded transition`}>
                      {log}
                    </div>
                  );
                })
              )}
              <div ref={terminalEndRef} />
            </div>

            {/* Scroll Indicator button */}
            {!autoScroll && (
              <button
                onClick={() => setAutoScroll(true)}
                className="absolute bottom-5 right-8 p-2 bg-indigo-600 hover:bg-indigo-500 border border-indigo-500/30 rounded-full text-zinc-100 flex items-center gap-1 shadow-lg shadow-indigo-600/30 text-[10px] font-bold uppercase transition"
              >
                <ArrowDown className="h-3.5 w-3.5" />
                <span>Scroll Lock</span>
              </button>
            )}

            {/* Scroll Lock status control */}
            <div className="absolute top-3 right-5 flex items-center gap-2">
              <label className="flex items-center gap-1.5 text-[10px] text-zinc-500 select-none cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoScroll}
                  onChange={(e) => setAutoScroll(e.target.checked)}
                  className="rounded border-zinc-800 bg-zinc-950 text-indigo-600 focus:ring-0 focus:ring-offset-0 h-3.5 w-3.5 cursor-pointer"
                />
                <span>Auto Scroll</span>
              </label>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

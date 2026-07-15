"use client";

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useDashboard } from "@/context/DashboardContext";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import { Shield, ShieldAlert, Ban, Clock, AlertTriangle, Loader2 } from "lucide-react";

export default function GuildModeration() {
  const { guild_id } = useParams();
  const { backendUrl, token } = useDashboard();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [modData, setModData] = useState<any>({ warnings: [], timeouts: [], bans: [] });

  useEffect(() => {
    if (!token || !guild_id) return;

    const fetchModLogs = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${backendUrl}/api/guilds/${guild_id}/moderation`, {
          headers: {
            "Authorization": `Bearer ${token}`
          }
        });
        if (res.ok) {
          const data = await res.json();
          setModData(data);
        }
      } catch (err) {
        console.error("Error fetching moderation data:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchModLogs();
  }, [guild_id, token]);

  if (loading) {
    return (
      <div className="min-h-screen flex bg-[#030305] text-zinc-100 font-['Plus_Jakarta_Sans']">
        <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />
        <div className="flex-1 lg:pl-64 flex flex-col min-w-0">
          <Header onMenuClick={() => setMobileOpen(true)} />
          <div className="flex-grow flex flex-col items-center justify-center gap-3">
            <Loader2 className="h-8 w-8 text-indigo-400 animate-spin" />
            <span className="text-xs text-zinc-500">Querying Server Security Feeds...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex bg-[#030305] text-zinc-100 font-['Plus_Jakarta_Sans']">
      <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />

      <div className="flex-1 lg:pl-64 flex flex-col min-w-0">
        <Header onMenuClick={() => setMobileOpen(true)} />

        <main className="flex-grow p-6 space-y-6 max-w-[1280px] mx-auto w-full">
          {/* Header Panel */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 bg-zinc-950/40 rounded-2xl border border-zinc-800/40">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-indigo-500/10 rounded-xl border border-indigo-500/25 text-indigo-400">
                <Shield className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-zinc-100">Moderation Incident Registry</h2>
                <p className="text-xs text-zinc-500 font-medium">
                  Review warnings, active timeouts, and ban actions logged in the database database
                </p>
              </div>
            </div>
          </div>

          {/* Incidents Split Panels */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            {/* Warnings Log Panel */}
            <div className="p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl space-y-4">
              <div className="flex items-center gap-2 text-yellow-400">
                <AlertTriangle className="h-4 w-4" />
                <h3 className="text-xs font-bold uppercase tracking-wider">Warnings Issued</h3>
              </div>
              <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
                {modData.warnings.length === 0 ? (
                  <p className="text-xs text-zinc-500 italic text-center py-6">No warnings issued yet.</p>
                ) : (
                  modData.warnings.map((w: any) => (
                    <div key={w.id} className="p-4 bg-zinc-900/40 rounded-xl border border-zinc-800/30 text-xs space-y-1.5">
                      <div className="flex justify-between items-center text-[10px] text-zinc-500 font-bold uppercase">
                        <span>Target ID: {w.user_id}</span>
                        <span>{new Date(w.timestamp).toLocaleDateString()}</span>
                      </div>
                      <p className="text-zinc-200 font-medium leading-relaxed">
                        <span className="font-bold text-yellow-500">Reason:</span> {w.reason || "No reason provided"}
                      </p>
                      <span className="text-[10px] text-zinc-500 block border-t border-zinc-800/20 pt-1.5 mt-1.5">
                        Moderator: {w.moderator_id}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Timeouts Log Panel */}
            <div className="p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl space-y-4">
              <div className="flex items-center gap-2 text-indigo-400">
                <Clock className="h-4 w-4" />
                <h3 className="text-xs font-bold uppercase tracking-wider">Active Timeouts</h3>
              </div>
              <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
                {modData.timeouts.length === 0 ? (
                  <p className="text-xs text-zinc-500 italic text-center py-6">No active timeouts/mutes.</p>
                ) : (
                  modData.timeouts.map((t: any) => (
                    <div key={t.id} className="p-4 bg-zinc-900/40 rounded-xl border border-zinc-800/30 text-xs space-y-1.5">
                      <div className="flex justify-between items-center text-[10px] text-zinc-500 font-bold uppercase">
                        <span>Duration: {t.duration_seconds}s</span>
                        <span>{new Date(t.timestamp).toLocaleDateString()}</span>
                      </div>
                      <p className="text-zinc-200 font-medium leading-relaxed">
                        <span className="font-bold text-indigo-400">Reason:</span> {t.reason || "No reason provided"}
                      </p>
                      <span className="text-[10px] text-zinc-500 block border-t border-zinc-800/20 pt-1.5 mt-1.5">
                        Moderator: {t.moderator_id} | Target: {t.user_id}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Ban Registry Panel */}
            <div className="p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl space-y-4">
              <div className="flex items-center gap-2 text-red-400">
                <Ban className="h-4 w-4" />
                <h3 className="text-xs font-bold uppercase tracking-wider">Banned Users</h3>
              </div>
              <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
                {modData.bans.length === 0 ? (
                  <p className="text-xs text-zinc-500 italic text-center py-6">No bans recorded.</p>
                ) : (
                  modData.bans.map((b: any) => (
                    <div key={b.id} className="p-4 bg-zinc-900/40 rounded-xl border border-zinc-800/30 text-xs space-y-1.5">
                      <div className="flex justify-between items-center text-[10px] text-zinc-500 font-bold uppercase">
                        <span>Banned ID: {b.user_id}</span>
                        <span>{new Date(b.timestamp).toLocaleDateString()}</span>
                      </div>
                      <p className="text-zinc-200 font-medium leading-relaxed">
                        <span className="font-bold text-red-500">Reason:</span> {b.reason || "No reason provided"}
                      </p>
                      <span className="text-[10px] text-zinc-500 block border-t border-zinc-800/20 pt-1.5 mt-1.5">
                        Moderator: {b.moderator_id}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

"use client";

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useDashboard } from "@/context/DashboardContext";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import { Database, Trash2, Download, CloudLightning, Loader2, AlertCircle } from "lucide-react";

export default function GuildBackups() {
  const { guild_id } = useParams();
  const { backendUrl, token } = useDashboard();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [backups, setBackups] = useState<any[]>([]);

  const fetchBackups = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${backendUrl}/api/guilds/${guild_id}/backups`, {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      if (res.ok) {
        const data = await res.json();
        setBackups(data);
      }
    } catch (err) {
      console.error("Error fetching backups:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token && guild_id) {
      fetchBackups();
    }
  }, [guild_id, token]);

  const handleDelete = async (backupId: number) => {
    if (!confirm("Are you sure you want to permanently delete this server layout backup?")) return;
    
    try {
      const res = await fetch(`${backendUrl}/api/guilds/${guild_id}/backups/${backupId}`, {
        method: "DELETE",
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      if (res.ok) {
        // Refresh
        fetchBackups();
      }
    } catch (err) {
      console.error("Failed to delete backup:", err);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex bg-[#030305] text-zinc-100 font-['Plus_Jakarta_Sans']">
        <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />
        <div className="flex-1 lg:pl-64 flex flex-col min-w-0">
          <Header onMenuClick={() => setMobileOpen(true)} />
          <div className="flex-grow flex flex-col items-center justify-center gap-3">
            <Loader2 className="h-8 w-8 text-indigo-400 animate-spin" />
            <span className="text-xs text-zinc-500">Querying Server Backups...</span>
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
                <Database className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-zinc-100">Server Layout Backups</h2>
                <p className="text-xs text-zinc-500 font-medium">
                  Review and manage historical layout snapshots captured via `/backup` command
                </p>
              </div>
            </div>
          </div>

          {/* Warning Banner */}
          <div className="p-4 bg-yellow-500/5 border border-yellow-500/20 rounded-2xl flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-yellow-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <h4 className="text-xs font-bold text-yellow-400 uppercase tracking-wider">Production Disclaimer</h4>
              <p className="text-xs text-zinc-400 leading-relaxed">
                Backups store channels structure, role configs, and name styling. To **create** a new backup or **restore** one, please use the Discord bot slash commands (`/backup` and `/restore`) directly.
              </p>
            </div>
          </div>

          {/* Backups List */}
          <div className="p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
              Archived Backups ({backups.length})
            </h3>
            
            <div className="space-y-3">
              {backups.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-8 space-y-2">
                  <CloudLightning className="h-6 w-6 text-zinc-600 animate-bounce" />
                  <p className="text-xs text-zinc-500 italic">No layout backups created yet.</p>
                </div>
              ) : (
                backups.map((b) => (
                  <div
                    key={b.id}
                    className="p-4 bg-zinc-900/40 rounded-xl border border-zinc-800/30 flex items-center justify-between gap-4 text-xs hover:border-zinc-800/60 transition"
                  >
                    <div className="flex items-center gap-4">
                      <div className="p-2 bg-indigo-500/5 rounded-lg border border-indigo-500/20 text-indigo-400">
                        <Database className="h-4 w-4" />
                      </div>
                      <div>
                        <h4 className="font-semibold text-zinc-200">{b.filename}</h4>
                        <span className="text-[10px] text-zinc-500">
                          Created at: {new Date(b.timestamp).toLocaleString()}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => handleDelete(b.id)}
                        className="p-2 text-zinc-500 hover:text-red-400 bg-zinc-950 rounded-lg border border-zinc-800 hover:border-red-500/20 transition cursor-pointer"
                        title="Delete backup"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

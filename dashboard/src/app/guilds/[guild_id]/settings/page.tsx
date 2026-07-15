"use client";

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useDashboard } from "@/context/DashboardContext";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import { Settings, Save, Loader2, RefreshCw } from "lucide-react";

export default function GuildSettings() {
  const { guild_id } = useParams();
  const { backendUrl, token } = useDashboard();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");

  // Config settings state
  const [prefix, setPrefix] = useState("!");
  const [automod, setAutomod] = useState("off");
  const [automodAI, setAutomodAI] = useState(false);
  const [logChannel, setLogChannel] = useState("");
  const [autoroleStatus, setAutoroleStatus] = useState("off");
  const [autorole, setAutorole] = useState("");

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${backendUrl}/api/guilds/${guild_id}/config`, {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      if (res.ok) {
        const data = await res.json();
        setPrefix(data.prefix);
        setAutomod(data.automod);
        setAutomodAI(data.automod_ai);
        setLogChannel(data.log_channel);
        setAutoroleStatus(data.autorole_status);
        setAutorole(data.autorole);
      }
    } catch (err) {
      console.error("Error fetching config:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token && guild_id) {
      fetchConfig();
    }
  }, [guild_id, token]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSuccessMsg("");
    
    try {
      const updates = [
        { key: "prefix", value: prefix },
        { key: "automod", value: automod },
        { key: "automod_ai", value: automodAI ? "True" : "False" },
        { key: "mod_log_channel", value: logChannel },
        { key: "autorole", value: autoroleStatus },
        { key: "autorole_role", value: autorole }
      ];

      for (const item of updates) {
        await fetch(`${backendUrl}/api/guilds/${guild_id}/config`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify(item)
        });
      }

      setSuccessMsg("Configuration settings saved successfully.");
      setTimeout(() => setSuccessMsg(""), 3000);
    } catch (err) {
      console.error("Error saving configs:", err);
    } finally {
      setSaving(false);
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
            <span className="text-xs text-zinc-500">Retrieving Settings Parameters...</span>
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

        <main className="flex-grow p-6 space-y-6 max-w-[1000px] mx-auto w-full">
          {/* Header Panel */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 bg-zinc-950/40 rounded-2xl border border-zinc-800/40">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-indigo-500/10 rounded-xl border border-indigo-500/25 text-indigo-400">
                <Settings className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-zinc-100">Bot Configurations</h2>
                <p className="text-xs text-zinc-500 font-medium">
                  Modify local prefix settings, toggling Auto-Mod capabilities, and event logging
                </p>
              </div>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSave} className="space-y-6">
            {/* General Configurations */}
            <div className="p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl space-y-5">
              <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400 border-b border-zinc-800/20 pb-3">
                General Settings
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Prefix */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-zinc-300">Bot Commands Prefix</label>
                  <input
                    type="text"
                    maxLength={3}
                    value={prefix}
                    onChange={(e) => setPrefix(e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-900/60 rounded-xl border border-zinc-800/50 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500/50"
                  />
                  <span className="text-[10px] text-zinc-500 block">
                    Trigger prefix for standard text commands (e.g. !help)
                  </span>
                </div>

                {/* Mod Logs Channel */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-zinc-300">Logging Channel ID</label>
                  <input
                    type="text"
                    placeholder="e.g. 123456789012345678"
                    value={logChannel}
                    onChange={(e) => setLogChannel(e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-900/60 rounded-xl border border-zinc-800/50 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500/50"
                  />
                  <span className="text-[10px] text-zinc-500 block">
                    Discord text channel ID to post Auto-Mod audit logs
                  </span>
                </div>
              </div>
            </div>

            {/* Moderation Settings */}
            <div className="p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl space-y-5">
              <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400 border-b border-zinc-800/20 pb-3">
                AutoMod Filters
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* AutoMod Mode */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-zinc-300">AutoMod Activation</label>
                  <select
                    value={automod}
                    onChange={(e) => setAutomod(e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-900/60 rounded-xl border border-zinc-800/50 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500/50"
                  >
                    <option value="off">Disabled (Off)</option>
                    <option value="on">Enabled (On)</option>
                  </select>
                </div>

                {/* AutoMod AI toggle */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-zinc-300">AI Deep Moderation (Gemini)</label>
                  <div className="flex items-center gap-3 py-1">
                    <input
                      type="checkbox"
                      checked={automodAI}
                      onChange={(e) => setAutomodAI(e.target.checked)}
                      className="rounded border-zinc-800 bg-zinc-950 text-indigo-600 focus:ring-0 focus:ring-offset-0 h-4 w-4 cursor-pointer"
                    />
                    <span className="text-xs text-zinc-400">
                      Enable AI toxicity scans on doubtful posts
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* AutoRole Configurations */}
            <div className="p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl space-y-5">
              <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400 border-b border-zinc-800/20 pb-3">
                AutoRole Management
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* AutoRole Status */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-zinc-300">AutoRole Activation</label>
                  <select
                    value={autoroleStatus}
                    onChange={(e) => setAutoroleStatus(e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-900/60 rounded-xl border border-zinc-800/50 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500/50"
                  >
                    <option value="off">Disabled (Off)</option>
                    <option value="on">Enabled (On)</option>
                  </select>
                </div>

                {/* AutoRole Role */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-zinc-300">AutoAssign Role ID</label>
                  <input
                    type="text"
                    placeholder="e.g. 123456789012345678"
                    value={autorole}
                    onChange={(e) => setAutorole(e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-900/60 rounded-xl border border-zinc-800/50 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500/50"
                  />
                  <span className="text-[10px] text-zinc-500 block">
                    Role ID automatically assigned to new users
                  </span>
                </div>
              </div>
            </div>

            {/* Save Buttons & Feedbacks */}
            <div className="flex items-center gap-4">
              <button
                type="submit"
                disabled={saving}
                className="py-2.5 px-6 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-700/50 text-zinc-100 rounded-xl text-xs font-bold flex items-center gap-2 border border-indigo-500/30 transition cursor-pointer disabled:cursor-not-allowed"
              >
                {saving ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    <span>Saving...</span>
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4" />
                    <span>Save Configs</span>
                  </>
                )}
              </button>
              
              {successMsg && (
                <span className="text-xs font-semibold text-green-400">{successMsg}</span>
              )}
            </div>
          </form>
        </main>
      </div>
    </div>
  );
}

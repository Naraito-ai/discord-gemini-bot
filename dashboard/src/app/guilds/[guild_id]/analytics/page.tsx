"use client";

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useDashboard } from "@/context/DashboardContext";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import { BarChart3, Loader2, Calendar } from "lucide-react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

export default function GuildAnalytics() {
  const { guild_id } = useParams();
  const { backendUrl, token } = useDashboard();
  
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [analyticsData, setAnalyticsData] = useState<any[]>([]);

  useEffect(() => {
    if (!token || !guild_id) return;
    
    const fetchAnalytics = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${backendUrl}/api/guilds/${guild_id}/analytics`, {
          headers: {
            "Authorization": `Bearer ${token}`
          }
        });
        if (res.ok) {
          const data = await res.json();
          // Map dates to readable format (e.g. Month Day)
          const formatted = data.map((d: any) => ({
            ...d,
            formattedDate: new Date(d.date).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            }),
          }));
          setAnalyticsData(formatted);
        }
      } catch (err) {
        console.error("Error fetching analytics:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchAnalytics();
  }, [guild_id, token]);

  if (loading) {
    return (
      <div className="min-h-screen flex bg-[#030305] text-zinc-100 font-['Plus_Jakarta_Sans']">
        <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />
        <div className="flex-1 lg:pl-64 flex flex-col min-w-0">
          <Header onMenuClick={() => setMobileOpen(true)} />
          <div className="flex-grow flex flex-col items-center justify-center gap-3">
            <Loader2 className="h-8 w-8 text-indigo-400 animate-spin" />
            <span className="text-xs text-zinc-500">Compiling Analytics Datasets...</span>
          </div>
        </div>
      </div>
    );
  }

  // Aggregate totals
  const totalMessages = analyticsData.reduce((acc, curr) => acc + (curr.messages_count || 0), 0);
  const totalCommands = analyticsData.reduce((acc, curr) => acc + (curr.commands_count || 0), 0);
  const totalJoins = analyticsData.reduce((acc, curr) => acc + (curr.joins_count || 0), 0);
  const totalLeaves = analyticsData.reduce((acc, curr) => acc + (curr.leaves_count || 0), 0);

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
                <BarChart3 className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-zinc-100">Server Activity Analytics</h2>
                <p className="text-xs text-zinc-500 font-medium">
                  Chronological reports of chat activity, slash commands activity, and member joins/leaves
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-xs text-zinc-400 bg-zinc-900/60 border border-zinc-800/40 px-3.5 py-1.5 rounded-xl font-semibold">
              <Calendar className="h-4 w-4 text-zinc-500" />
              <span>Past 15 Days Trend</span>
            </div>
          </div>

          {/* Aggregate Overview */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatsMiniCard title="Total Messages Logged" value={totalMessages} color="text-indigo-400" />
            <StatsMiniCard title="Total Commands Fired" value={totalCommands} color="text-purple-400" />
            <StatsMiniCard title="New Joins" value={totalJoins} color="text-emerald-400" />
            <StatsMiniCard title="Leaves" value={totalLeaves} color="text-red-400" />
          </div>

          {/* Area Chart - Chat Activity */}
          <div className="p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
              Chat & Message Volume Trend
            </h3>
            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={analyticsData}>
                  <defs>
                    <linearGradient id="colorMsg" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.2}/>
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f1f2e" vertical={false} />
                  <XAxis dataKey="formattedDate" stroke="#52525b" fontSize={11} tickLine={false} />
                  <YAxis stroke="#52525b" fontSize={11} tickLine={false} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#09090b", borderColor: "#27272a" }}
                    labelStyle={{ color: "#a1a1aa", fontSize: 11, fontWeight: "bold" }}
                    itemStyle={{ color: "#f4f4f5", fontSize: 12 }}
                  />
                  <Area type="monotone" dataKey="messages_count" name="Messages" stroke="#6366f1" strokeWidth={2} fillOpacity={1} fill="url(#colorMsg)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Split Charts (Commands & Joins/Leaves) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Commands Bar Chart */}
            <div className="p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl space-y-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                Slash Commands Executed
              </h3>
              <div className="h-[240px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={analyticsData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f1f2e" vertical={false} />
                    <XAxis dataKey="formattedDate" stroke="#52525b" fontSize={10} tickLine={false} />
                    <YAxis stroke="#52525b" fontSize={10} tickLine={false} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#09090b", borderColor: "#27272a" }}
                      labelStyle={{ color: "#a1a1aa", fontSize: 10, fontWeight: "bold" }}
                      itemStyle={{ color: "#f4f4f5", fontSize: 11 }}
                    />
                    <Bar dataKey="commands_count" name="Commands" fill="#c084fc" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Member Joins/Leaves Area Chart */}
            <div className="p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl space-y-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                Member Joins & Leaves
              </h3>
              <div className="h-[240px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={analyticsData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f1f2e" vertical={false} />
                    <XAxis dataKey="formattedDate" stroke="#52525b" fontSize={10} tickLine={false} />
                    <YAxis stroke="#52525b" fontSize={10} tickLine={false} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#09090b", borderColor: "#27272a" }}
                      labelStyle={{ color: "#a1a1aa", fontSize: 10, fontWeight: "bold" }}
                      itemStyle={{ color: "#f4f4f5", fontSize: 11 }}
                    />
                    <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: 11 }} />
                    <Area type="monotone" dataKey="joins_count" name="Joins" stroke="#10b981" strokeWidth={1.5} fill="none" />
                    <Area type="monotone" dataKey="leaves_count" name="Leaves" stroke="#ef4444" strokeWidth={1.5} fill="none" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function StatsMiniCard({ title, value, color }: { title: string; value: number; color: string }) {
  return (
    <div className="p-5 rounded-2xl glass-card flex flex-col justify-center">
      <span className="text-zinc-500 text-[10px] font-bold uppercase tracking-wider block mb-1">
        {title}
      </span>
      <h3 className={`text-xl font-bold ${color}`}>{value.toLocaleString()}</h3>
    </div>
  );
}

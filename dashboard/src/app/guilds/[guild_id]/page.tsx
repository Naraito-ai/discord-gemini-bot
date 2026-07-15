"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useDashboard } from "@/context/DashboardContext";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import { Server, Users, Hash, ShieldAlert, Award, Star, Loader2, Compass } from "lucide-react";

export default function GuildOverview() {
  const { guild_id } = useParams();
  const router = useRouter();
  const { backendUrl, token } = useDashboard();
  
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [guildData, setGuildData] = useState<any>(null);

  useEffect(() => {
    if (!token || !guild_id) return;
    
    const fetchGuildDetails = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${backendUrl}/api/guilds/${guild_id}`, {
          headers: {
            "Authorization": `Bearer ${token}`
          }
        });
        if (res.ok) {
          const data = await res.json();
          setGuildData(data);
        } else {
          router.push("/");
        }
      } catch (err) {
        console.error("Error fetching guild:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchGuildDetails();
  }, [guild_id, token]);

  if (loading) {
    return (
      <div className="min-h-screen flex bg-[#030305] text-zinc-100 font-['Plus_Jakarta_Sans']">
        <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />
        <div className="flex-1 lg:pl-64 flex flex-col min-w-0">
          <Header onMenuClick={() => setMobileOpen(true)} />
          <div className="flex-grow flex flex-col items-center justify-center gap-3">
            <Loader2 className="h-8 w-8 text-indigo-400 animate-spin" />
            <span className="text-xs text-zinc-500">Querying Server Resources...</span>
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
          {/* Guild Header Banner */}
          <div className="p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl flex flex-col sm:flex-row items-center justify-between gap-6 relative overflow-hidden">
            {/* Glow backdrop */}
            <div className="absolute right-0 top-0 w-[40%] h-[120%] bg-indigo-600/5 blur-[80px] rounded-full pointer-events-none" />

            <div className="flex items-center gap-5 relative z-10">
              {guildData?.icon ? (
                <img
                  src={guildData.icon}
                  alt={guildData.name}
                  className="h-16 w-16 rounded-2xl border border-zinc-800"
                />
              ) : (
                <div className="h-16 w-16 rounded-2xl bg-zinc-800 border border-zinc-700 flex items-center justify-center font-bold text-2xl text-zinc-400">
                  {guildData?.name?.charAt(0) || "S"}
                </div>
              )}
              <div>
                <h2 className="text-xl font-bold text-zinc-100">{guildData?.name}</h2>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[11px] font-bold text-indigo-400 uppercase tracking-wider">
                    Owner: {guildData?.owner_name}
                  </span>
                  <span className="text-zinc-700 text-xs">•</span>
                  <span className="text-[11px] text-zinc-500 font-medium">ID: {guild_id}</span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <span className="px-3.5 py-1.5 bg-indigo-600/10 border border-indigo-500/25 text-indigo-400 rounded-xl text-xs font-semibold">
                Boost Tier {guildData?.boost_level ?? 0}
              </span>
            </div>
          </div>

          {/* Quick Metrics Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard title="Members Count" value={guildData?.members ?? 0} icon={Users} color="text-indigo-400" />
            <MetricCard title="Total Roles" value={guildData?.roles_count ?? 0} icon={Award} color="text-purple-400" />
            <MetricCard title="Total Channels" value={guildData?.channels_count ?? 0} icon={Hash} color="text-blue-400" />
            <MetricCard title="Warnings Issued" value={guildData?.warnings_count ?? 0} icon={ShieldAlert} color="text-yellow-400" />
          </div>

          {/* Detailed Lists Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Roles list */}
            <div className="p-6 bg-zinc-950/40 rounded-2xl border border-zinc-800/40 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Server Roles (Preview)
                </h3>
              </div>
              <div className="space-y-2">
                {guildData?.roles && guildData.roles.length > 0 ? (
                  guildData.roles.map((role: any) => (
                    <div
                      key={role.id}
                      className="p-3 bg-zinc-900/40 rounded-xl border border-zinc-800/20 flex items-center justify-between"
                    >
                      <span className="text-xs font-semibold text-zinc-200">{role.name}</span>
                      <span className="text-[10px] text-zinc-500">ID: {role.id}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-zinc-500 italic">No roles configured.</p>
                )}
              </div>
            </div>

            {/* Channels list */}
            <div className="p-6 bg-zinc-950/40 rounded-2xl border border-zinc-800/40 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Channels list (Preview)
                </h3>
              </div>
              <div className="space-y-2">
                {guildData?.channels && guildData.channels.length > 0 ? (
                  guildData.channels.map((chan: any) => (
                    <div
                      key={chan.id}
                      className="p-3 bg-zinc-900/40 rounded-xl border border-zinc-800/20 flex items-center justify-between"
                    >
                      <div className="flex items-center gap-1.5">
                        <Hash className="h-3.5 w-3.5 text-zinc-500" />
                        <span className="text-xs font-semibold text-zinc-200">{chan.name}</span>
                      </div>
                      <span className="text-[10px] text-zinc-500 uppercase font-semibold">
                        {chan.type.replace("text", "TXT").replace("voice", "VC")}
                      </span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-zinc-500 italic">No channels configured.</p>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function MetricCard({ title, value, icon: Icon, color }: { title: string; value: any; icon: any; color: string }) {
  return (
    <div className="p-5 rounded-2xl glass-card flex items-center justify-between">
      <div className="space-y-1">
        <span className="text-zinc-500 text-[10px] font-bold uppercase tracking-wider">{title}</span>
        <h3 className="text-lg font-bold text-zinc-100">{value}</h3>
      </div>
      <div className={`p-3 bg-zinc-900/60 rounded-xl border border-zinc-800/40 ${color}`}>
        <Icon className="h-5 w-5" />
      </div>
    </div>
  );
}

"use client";

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useDashboard } from "@/context/DashboardContext";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import { Brain, Cpu, Clock, Coins, ShieldCheck, Loader2 } from "lucide-react";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip, Legend } from "recharts";

export default function GuildAIUsage() {
  const { guild_id } = useParams();
  const { backendUrl, token } = useDashboard();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [aiStats, setAIStats] = useState<any>(null);

  useEffect(() => {
    if (!token) return;

    const fetchAIStats = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${backendUrl}/api/ai/stats`, {
          headers: {
            "Authorization": `Bearer ${token}`
          }
        });
        if (res.ok) {
          const data = await res.json();
          setAIStats(data);
        }
      } catch (err) {
        console.error("Error fetching AI stats:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchAIStats();
  }, [token]);

  if (loading) {
    return (
      <div className="min-h-screen flex bg-[#030305] text-zinc-100 font-['Plus_Jakarta_Sans']">
        <Sidebar mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />
        <div className="flex-1 lg:pl-64 flex flex-col min-w-0">
          <Header onMenuClick={() => setMobileOpen(true)} />
          <div className="flex-grow flex flex-col items-center justify-center gap-3">
            <Loader2 className="h-8 w-8 text-indigo-400 animate-spin" />
            <span className="text-xs text-zinc-500">Querying AI Usage Models...</span>
          </div>
        </div>
      </div>
    );
  }

  // Model pie chart mapping
  const COLORS = ["#6366f1", "#a855f7", "#3b82f6", "#10b981"];
  const pieData = aiStats?.models?.map((m: any) => ({
    name: m.model,
    value: m.count
  })) || [{ name: "gemini-2.5-flash", value: 1 }];

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
                <Brain className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-zinc-100">Artificial Intelligence Insights</h2>
                <p className="text-xs text-zinc-500 font-medium">
                  Real-time monitoring of tokens spent, LLM models, and inference API response speed
                </p>
              </div>
            </div>
          </div>

          {/* AI Counters Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatsMiniCard
              title="Today's AI Requests"
              value={aiStats?.total_requests ?? 0}
              icon={Brain}
              desc="Total AI completions today"
              color="text-indigo-400"
            />
            <StatsMiniCard
              title="Tokens Consumed"
              value={(aiStats?.total_tokens ?? 0).toLocaleString()}
              icon={Coins}
              desc="Estimated context tokens processed"
              color="text-purple-400"
            />
            <StatsMiniCard
              title="Average Latency"
              value={`${aiStats?.avg_latency ?? 0}s`}
              icon={Clock}
              desc="Average API response turnaround"
              color="text-blue-400"
            />
            <StatsMiniCard
              title="Estimated Hosting Cost"
              value="$0.00"
              icon={ShieldCheck}
              desc="100% Free Gemini & Groq APIs!"
              color="text-emerald-400"
            />
          </div>

          {/* Detailed usage split */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Model Distribution (Pie Chart) */}
            <div className="p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl space-y-4 flex flex-col justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                Active Models Distribution
              </h3>
              <div className="h-[220px] w-full flex items-center justify-center">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={80}
                      paddingAngle={5}
                      dataKey="value"
                    >
                      {pieData.map((entry: any, index: number) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ backgroundColor: "#09090b", borderColor: "#27272a" }}
                      itemStyle={{ color: "#f4f4f5", fontSize: 11 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Model Specifications */}
            <div className="lg:col-span-2 p-6 bg-zinc-950/40 border border-zinc-800/40 rounded-2xl space-y-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                AI Integration Specs & Quota Details
              </h3>
              <div className="space-y-3.5">
                <ModelDetail
                  name="Google Gemini 2.5 Flash"
                  desc="Primary model used for server layout architecture design, channel permission configurations, and rich embeds styling."
                  speed="Ultra-fast (0.3s - 0.5s avg)"
                  cost="Free Tier (15 RPM | 1M TPM)"
                />
                <ModelDetail
                  name="Groq Llama 3.3 70B"
                  desc="Fallback and moderation model used to analyze toxicity checks, scan message duplicates, and detect user spams."
                  speed="Blazing fast (0.15s - 0.3s avg)"
                  cost="Free Tier (30 RPD)"
                />
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function StatsMiniCard({
  title,
  value,
  icon: Icon,
  desc,
  color,
}: {
  title: string;
  value: any;
  icon: any;
  desc: string;
  color: string;
}) {
  return (
    <div className="p-5 rounded-2xl glass-card flex items-center justify-between">
      <div className="space-y-1">
        <span className="text-zinc-500 text-[10px] font-bold uppercase tracking-wider">{title}</span>
        <h3 className={`text-xl font-bold ${color}`}>{value}</h3>
        <p className="text-[10px] text-zinc-500 leading-tight">{desc}</p>
      </div>
      <div className="p-3 bg-zinc-900/60 rounded-xl border border-zinc-800/40 text-zinc-400">
        <Icon className="h-5 w-5" />
      </div>
    </div>
  );
}

function ModelDetail({ name, desc, speed, cost }: { name: string; desc: string; speed: string; cost: string }) {
  return (
    <div className="p-4 bg-zinc-900/40 rounded-xl border border-zinc-800/30 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-bold text-zinc-200">{name}</h4>
        <span className="px-2 py-0.5 bg-indigo-500/10 text-indigo-400 rounded text-[9px] font-bold uppercase tracking-wider">
          Active
        </span>
      </div>
      <p className="text-xs text-zinc-400 leading-relaxed">{desc}</p>
      <div className="flex flex-wrap gap-4 mt-1 border-t border-zinc-800/30 pt-2 text-[10px] text-zinc-500">
        <div>
          <span className="font-bold">Latency:</span> <span className="text-zinc-400">{speed}</span>
        </div>
        <div>
          <span className="font-bold">Rate Limits:</span> <span className="text-zinc-400">{cost}</span>
        </div>
      </div>
    </div>
  );
}

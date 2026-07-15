"use client";

import React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useDashboard } from "@/context/DashboardContext";
import {
  LayoutDashboard,
  Terminal,
  Shield,
  BarChart3,
  Brain,
  Database,
  Settings,
  FolderLock,
  History,
  AlertTriangle,
  LogOut,
  ChevronDown,
  Server,
  Activity,
  Zap,
} from "lucide-react";

export default function Sidebar({ mobileOpen, setMobileOpen }: { mobileOpen?: boolean; setMobileOpen?: (open: boolean) => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { guilds, activeGuildId, activeGuild, selectGuild, logout } = useDashboard();

  const handleGuildSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    selectGuild(e.target.value);
    router.push("/");
  };

  const navItems = [
    { name: "Global Dashboard", icon: LayoutDashboard, path: "/", global: true },
    { name: "Live Terminal", icon: Terminal, path: "/console", global: true },
  ];

  const guildItems = [
    { name: "Server Overview", icon: Server, path: `/guilds/${activeGuildId}` },
    { name: "Server Analytics", icon: BarChart3, path: `/guilds/${activeGuildId}/analytics` },
    { name: "AI & Groq Usage", icon: Brain, path: `/guilds/${activeGuildId}/ai-usage` },
    { name: "Moderation Logs", icon: Shield, path: `/guilds/${activeGuildId}/moderation` },
    { name: "Database Backups", icon: Database, path: `/guilds/${activeGuildId}/backups` },
    { name: "Bot Settings", icon: Settings, path: `/guilds/${activeGuildId}/settings` },
  ];

  const isLinkActive = (path: string) => {
    return pathname === path;
  };

  const sidebarContent = (
    <div className="flex flex-col h-full bg-[#0a0a0d] border-r border-zinc-800/40 text-zinc-300 font-['Plus_Jakarta_Sans']">
      {/* Brand Logo Header */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-zinc-800/30">
        <div className="p-2 bg-indigo-500/10 rounded-xl border border-indigo-500/25">
          <Zap className="h-6 w-6 text-indigo-400" />
        </div>
        <div>
          <h1 className="font-bold text-[16px] text-zinc-100 tracking-tight leading-tight">GeminiBot</h1>
          <span className="text-[11px] text-zinc-500 font-medium">Control Dashboard</span>
        </div>
      </div>

      {/* Guild Selector (Dropdown) */}
      {guilds.length > 0 && (
        <div className="px-4 py-4 border-b border-zinc-800/20">
          <label className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-2 px-1">
            Active Server
          </label>
          <div className="relative">
            <select
              value={activeGuildId || ""}
              onChange={handleGuildSelect}
              className="w-full pl-3 pr-8 py-2 bg-zinc-900/60 rounded-xl border border-zinc-800/40 text-zinc-200 text-sm font-medium focus:outline-none focus:border-indigo-500/50 appearance-none cursor-pointer"
            >
              {guilds.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name} {g.invited ? "✅" : "❌"}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2.5 top-2.5 h-4 w-4 text-zinc-400 pointer-events-none" />
          </div>
        </div>
      )}

      {/* Navigation Links Scroll Area */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {/* Global Control Items */}
        <div className="space-y-1">
          <span className="text-[10px] text-zinc-600 font-bold uppercase tracking-wider block mb-2 px-3">
            Core Controls
          </span>
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isLinkActive(item.path);
            return (
              <Link
                key={item.path}
                href={item.path}
                onClick={() => setMobileOpen && setMobileOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200 ${
                  active
                    ? "bg-indigo-600/10 border border-indigo-500/20 text-indigo-400 font-semibold"
                    : "hover:bg-zinc-800/30 text-zinc-400 hover:text-zinc-200 border border-transparent"
                }`}
              >
                <Icon className={`h-4 w-4 ${active ? "text-indigo-400" : "text-zinc-500"}`} />
                {item.name}
              </Link>
            );
          })}
        </div>

        {/* Selected Server Controls */}
        {activeGuild && activeGuild.invited && (
          <div className="space-y-1">
            <span className="text-[10px] text-zinc-600 font-bold uppercase tracking-wider block mb-2 px-3">
              Server Administration
            </span>
            {guildItems.map((item) => {
              const Icon = item.icon;
              const active = isLinkActive(item.path);
              return (
                <Link
                  key={item.path}
                  href={item.path}
                  onClick={() => setMobileOpen && setMobileOpen(false)}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200 ${
                    active
                      ? "bg-indigo-600/10 border border-indigo-500/20 text-indigo-400 font-semibold"
                      : "hover:bg-zinc-800/30 text-zinc-400 hover:text-zinc-200 border border-transparent"
                  }`}
                >
                  <Icon className={`h-4 w-4 ${active ? "text-indigo-400" : "text-zinc-500"}`} />
                  {item.name}
                </Link>
              );
            })}
          </div>
        )}

        {/* Selected Server NOT Invited Banner */}
        {activeGuild && !activeGuild.invited && (
          <div className="p-3.5 bg-yellow-500/5 rounded-xl border border-yellow-500/20 space-y-2">
            <div className="flex items-center gap-2 text-yellow-400">
              <AlertTriangle className="h-4 w-4 flex-shrink-0" />
              <span className="text-[11px] font-bold uppercase tracking-wider">Bot Missing</span>
            </div>
            <p className="text-[11px] text-zinc-400 leading-relaxed">
              Bot has not been added to **{activeGuild.name}** yet. Please invite the bot first.
            </p>
            <a
              href={`https://discord.com/api/oauth2/authorize?client_id=${process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID || ""}&permissions=8&scope=bot%20applications.commands`}
              target="_blank"
              rel="noreferrer"
              className="block w-full py-1.5 bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20 rounded-lg text-center text-xs font-semibold transition"
            >
              Add to Server
            </a>
          </div>
        )}
      </div>

      {/* User Logout Area */}
      <div className="p-4 border-t border-zinc-800/30 bg-zinc-950/20 flex flex-col gap-3">
        <button
          onClick={logout}
          className="flex items-center justify-between w-full px-3 py-2 bg-zinc-900/40 hover:bg-red-500/10 hover:text-red-400 rounded-xl text-zinc-400 text-xs font-semibold border border-zinc-800/40 transition duration-200 cursor-pointer"
        >
          <span>Disconnect Session</span>
          <LogOut className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Sidebar */}
      <aside className="hidden lg:block w-64 h-screen fixed left-0 top-0 z-20 flex-shrink-0">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer Backdrop overlay */}
      {mobileOpen && (
        <div
          onClick={() => setMobileOpen && setMobileOpen(false)}
          className="lg:hidden fixed inset-0 bg-black/60 backdrop-blur-sm z-30 transition-opacity"
        />
      )}

      {/* Mobile Sidebar Slider */}
      <aside
        className={`lg:hidden fixed top-0 bottom-0 left-0 w-64 z-40 transform transition-transform duration-300 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {sidebarContent}
      </aside>
    </>
  );
}

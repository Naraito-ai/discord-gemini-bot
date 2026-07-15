"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { useRouter } from "next/navigation";

// Define Types
export interface Guild {
  id: string;
  name: string;
  icon: string | null;
  invited: boolean;
  members?: number;
  channels?: number;
  roles?: number;
}

export interface User {
  id: string;
  username: string;
  avatar: string | null;
}

interface DashboardContextType {
  token: string | null;
  user: User | null;
  guilds: Guild[];
  activeGuildId: string | null;
  activeGuild: Guild | null;
  botStats: any;
  wsConnected: boolean;
  wsEvents: any[];
  login: (token: string, user: User, guilds: Guild[]) => void;
  logout: () => void;
  selectGuild: (guildId: string) => void;
  fetchBotStats: () => Promise<void>;
  updateGuildStatus: (guildId: string, invited: boolean) => void;
  backendUrl: string;
  wsUrl: string;
}

const DashboardContext = createContext<DashboardContextType | undefined>(undefined);

export const DashboardProvider = ({ children }: { children: ReactNode }) => {
  const router = useRouter();
  
  // Base URLs (Adjust automatically based on deployment environment)
  const [backendUrl, setBackendUrl] = useState("http://localhost:8080");
  const [wsUrl, setWsUrl] = useState("ws://localhost:8080");

  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [activeGuildId, setActiveGuildId] = useState<string | null>(null);
  const [botStats, setBotStats] = useState<any>(null);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [wsEvents, setWsEvents] = useState<any[]>([]);

  // Dynamically set URLs in browser
  useEffect(() => {
    const isProd = window.location.hostname !== "localhost";
    // If prod, backend runs on Render, usually same subdomain or separate service
    const envBackend = process.env.NEXT_PUBLIC_BACKEND_URL;
    if (envBackend) {
      setBackendUrl(envBackend);
      setWsUrl(envBackend.replace(/^http/, "ws"));
    } else if (isProd) {
      // Fallback/Placeholder: Change to Render URL
      const prodUrl = "https://discord-gemini-bot-backend.onrender.com";
      setBackendUrl(prodUrl);
      setWsUrl(prodUrl.replace(/^http/, "ws"));
    }
  }, []);

  // Hydrate state from localStorage
  useEffect(() => {
    const savedToken = localStorage.getItem("dash_token");
    const savedUser = localStorage.getItem("dash_user");
    const savedGuilds = localStorage.getItem("dash_guilds");
    const savedActiveGuild = localStorage.getItem("dash_active_guild");

    if (savedToken && savedUser && savedGuilds) {
      setToken(savedToken);
      setUser(JSON.parse(savedUser));
      setGuilds(JSON.parse(savedGuilds));
      if (savedActiveGuild) {
        setActiveGuildId(savedActiveGuild);
      }
    }
  }, []);

  // WebSocket event subscription for alerts
  useEffect(() => {
    if (!token) {
      setWsConnected(false);
      return;
    }

    let ws: WebSocket;
    const connectWS = () => {
      try {
        ws = new WebSocket(`${wsUrl}/api/ws/events`);
        
        ws.onopen = () => {
          setWsConnected(true);
          console.log("🚀 Real-time events WebSocket connected.");
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            setWsEvents((prev) => [data, ...prev.slice(0, 49)]); // Maintain past 50 events
          } catch (err) {
            console.error("Error parsing WS message:", err);
          }
        };

        ws.onclose = () => {
          setWsConnected(false);
          console.log("WebSocket closed. Attempting reconnect in 5s...");
          setTimeout(connectWS, 5000);
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch (e) {
        console.error("Failed to connect to events WS:", e);
      }
    };

    connectWS();

    return () => {
      if (ws) ws.close();
    };
  }, [token, wsUrl]);

  const login = (newToken: string, newUser: User, newGuilds: Guild[]) => {
    localStorage.setItem("dash_token", newToken);
    localStorage.setItem("dash_user", JSON.stringify(newUser));
    localStorage.setItem("dash_guilds", JSON.stringify(newGuilds));
    
    setToken(newToken);
    setUser(newUser);
    setGuilds(newGuilds);
    
    if (newGuilds.length > 0) {
      const firstGuild = newGuilds[0].id;
      setActiveGuildId(firstGuild);
      localStorage.setItem("dash_active_guild", firstGuild);
    }
    
    router.push("/");
  };

  const logout = () => {
    localStorage.clear();
    setToken(null);
    setUser(null);
    setGuilds([]);
    setActiveGuildId(null);
    setBotStats(null);
    router.push("/");
  };

  const selectGuild = (guildId: string) => {
    setActiveGuildId(guildId);
    localStorage.setItem("dash_active_guild", guildId);
  };

  const fetchBotStats = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/bot/stats`);
      if (res.ok) {
        const data = await res.json();
        setBotStats(data);
      }
    } catch (err) {
      console.error("Failed to fetch bot stats:", err);
    }
  };

  const updateGuildStatus = (guildId: string, invited: boolean) => {
    setGuilds((prevGuilds) => {
      const updated = prevGuilds.map((g) => (g.id === guildId ? { ...g, invited } : g));
      localStorage.setItem("dash_guilds", JSON.stringify(updated));
      return updated;
    });
  };

  const activeGuild = guilds.find((g) => g.id === activeGuildId) || null;

  return (
    <DashboardContext.Provider
      value={{
        token,
        user,
        guilds,
        activeGuildId,
        activeGuild,
        botStats,
        wsConnected,
        wsEvents,
        login,
        logout,
        selectGuild,
        fetchBotStats,
        updateGuildStatus,
        backendUrl,
        wsUrl,
      }}
    >
      {children}
    </DashboardContext.Provider>
  );
};

export const useDashboard = () => {
  const context = useContext(DashboardContext);
  if (!context) {
    throw new Error("useDashboard must be used within a DashboardProvider");
  }
  return context;
};

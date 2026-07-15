"use client";

import React, { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useDashboard } from "@/context/DashboardContext";
import { Loader2 } from "lucide-react";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { login, backendUrl } = useDashboard();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    
    if (!code) {
      setError("No authorization code provided from Discord");
      return;
    }

    const exchangeCode = async () => {
      try {
        const res = await fetch(`${backendUrl}/api/auth/callback`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ code }),
        });

        if (res.ok) {
          const data = await res.json();
          // Log user in
          login(data.token, data.user, data.guilds);
        } else {
          const errData = await res.json();
          setError(errData.detail || "Failed to exchange Discord authorization code");
        }
      } catch (err) {
        console.error("OAuth exchange failure:", err);
        setError("Network error connecting to backend API");
      }
    };

    exchangeCode();
  }, [searchParams]);

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#020205] text-zinc-100 font-['Plus_Jakarta_Sans'] p-6">
        <div className="max-w-[400px] w-full text-center space-y-4 p-8 bg-red-950/20 border border-red-500/20 rounded-2xl backdrop-blur-md">
          <h2 className="text-lg font-bold text-red-400">Authentication Failed</h2>
          <p className="text-xs text-zinc-400 leading-relaxed">{error}</p>
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-xl text-xs font-semibold text-zinc-300 transition cursor-pointer"
          >
            Back to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#020205] text-zinc-100 font-['Plus_Jakarta_Sans'] gap-4">
      <Loader2 className="h-8 w-8 text-indigo-400 animate-spin" />
      <div className="text-center space-y-1">
        <p className="text-sm font-semibold text-zinc-300">Synchronizing Session...</p>
        <span className="text-[10px] text-zinc-500">Exchanging authorization credentials with Discord</span>
      </div>
    </div>
  );
}

export default function AuthCallback() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#020205] text-zinc-100 gap-4">
        <Loader2 className="h-8 w-8 text-indigo-400 animate-spin" />
        <span className="text-xs text-zinc-500">Loading auth session...</span>
      </div>
    }>
      <CallbackHandler />
    </Suspense>
  );
}


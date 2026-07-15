import type { Metadata } from "next";
import { DashboardProvider } from "@/context/DashboardContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "Discord Gemini Bot - Dashboard",
  description: "Enterprise-ready RAG & moderation administration panel powered by Gemini and Groq",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark scroll-smooth">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet" />
      </head>
      <body className="bg-[#030303] text-zinc-100 min-h-screen antialiased selection:bg-indigo-500/30 selection:text-indigo-200">
        <DashboardProvider>
          {children}
        </DashboardProvider>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DEEP6 v2 Dashboard",
  description: "Institutional order-flow trading dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-deep6-bg text-slate-100 min-h-screen">
        <div className="flex h-screen">
          {/* Sidebar */}
          <nav className="w-48 bg-deep6-panel border-r border-deep6-border flex flex-col p-4 shrink-0">
            <h1 className="text-lg font-bold text-deep6-accent mb-6">DEEP6 v2</h1>
            <a href="/" className="text-sm py-2 px-3 rounded hover:bg-deep6-border text-slate-300">
              Dashboard
            </a>
            <a href="/replay" className="text-sm py-2 px-3 rounded hover:bg-deep6-border text-slate-300 mt-1">
              Replay
            </a>
            <a href="/config" className="text-sm py-2 px-3 rounded hover:bg-deep6-border text-slate-300 mt-1">
              Config
            </a>
            <div className="mt-auto text-xs text-deep6-muted">v2.0.0</div>
          </nav>

          {/* Main content */}
          <main className="flex-1 overflow-auto p-6">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}

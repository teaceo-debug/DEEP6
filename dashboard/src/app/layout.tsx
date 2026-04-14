import type { Metadata } from "next";
import { Geist_Mono } from "next/font/google";
import "./globals.css";
import { WsProvider } from "@/providers/ws-provider";

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DEEP6 Dashboard",
  description: "Institutional-grade footprint chart trading system",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistMono.variable} dark`}>
      <body className="bg-zinc-950 text-zinc-100 min-h-screen font-mono">
        <WsProvider>
          {children}
        </WsProvider>
      </body>
    </html>
  );
}

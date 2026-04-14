import type { Metadata } from 'next';
import { JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { Scanlines } from '@/components/atmosphere/Scanlines';
import { Grain } from '@/components/atmosphere/Grain';
import { CRTSweep } from '@/components/atmosphere/CRTSweep';

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
  weight: 'variable',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'DEEP6',
  description: 'Footprint monitoring',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={jetbrainsMono.variable}>
      <body>
        {/* Visually-hidden h1 for screen readers — dashboard has no visible heading */}
        <h1 style={{
          position: 'absolute',
          width: '1px',
          height: '1px',
          padding: 0,
          margin: '-1px',
          overflow: 'hidden',
          clip: 'rect(0,0,0,0)',
          whiteSpace: 'nowrap',
          borderWidth: 0,
        }}>
          DEEP6 — NQ Footprint Trading Dashboard
        </h1>
        {/* Atmosphere layers — fixed, pointer-events none, z-index 2-4 */}
        <Grain />
        <Scanlines />
        <CRTSweep />
        {children}
      </body>
    </html>
  );
}

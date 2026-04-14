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
        {/* Atmosphere layers — fixed, pointer-events none, z-index 2-4 */}
        <Grain />
        <Scanlines />
        <CRTSweep />
        {children}
      </body>
    </html>
  );
}

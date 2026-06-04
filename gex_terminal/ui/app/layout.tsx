import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'GEX Doctor v2.0',
  description: 'Institutional Options Bias Terminal',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=800, initial-scale=1" />
      </head>
      <body>
        {children}
      </body>
    </html>
  )
}

import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import "./globals.css";
import { Providers } from "./providers";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "DermIQ",
  description: "Analytics intelligence for cosmetic dermatology practices",
};

// `maximumScale` is deliberately left at the default so pinch-zoom stays available —
// capping it is an accessibility regression.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans antialiased`}>
        <Providers>
          <div className="flex h-[100dvh] overflow-hidden">
            <Sidebar />
            {/* min-w-0 lets the column shrink below its content width, so a wide
                table scrolls inside its own wrapper instead of widening the page. */}
            <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
              <TopBar />
              <main className="flex-1 overflow-y-auto px-4 py-4 sm:px-6 sm:py-6">
                {children}
              </main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QuickBooks Online Invoicing & Payment Operations",
  description: "Enterprise QuickBooks Online Invoice Generator, Real-Time Payment Tracker, and Automated Dunning Platform.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 min-h-screen flex flex-col font-sans antialiased">
        <header className="bg-slate-900 text-white border-b border-slate-800 sticky top-0 z-50 shadow-md">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-9 h-9 rounded-lg bg-emerald-500 flex items-center justify-center font-black text-white text-lg shadow-sm">
                Q
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-bold text-base tracking-tight text-white">QuickBooks Online Invoicing</span>
                  <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                    Enterprise v1.3.0
                  </span>
                </div>
                <p className="text-xs text-slate-400">Intuit API v3 &bull; Webhooks Engine &bull; Automated Dunning Escalation</p>
              </div>
            </div>

            <div className="flex items-center space-x-4">
              <div className="hidden sm:flex items-center space-x-2 text-xs text-slate-300">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>Vercel &bull; Next.js 14</span>
              </div>
              <a
                href="/api/docs"
                target="_blank"
                rel="noreferrer"
                className="text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-md border border-slate-700 transition"
              >
                FastAPI Docs
              </a>
            </div>
          </div>
        </header>

        <div className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </div>

        <footer className="bg-white border-t border-slate-200 py-6 text-center text-xs text-slate-500">
          <div className="max-w-7xl mx-auto px-4">
            <p className="font-medium text-slate-600">QuickBooks Online Invoicing &amp; Payment Reconciliation Platform</p>
            <p className="mt-1 text-slate-400">Deployed on Vercel &bull; Powered by FastAPI &amp; Intuit Accounting API v3 &bull; MIT License</p>
          </div>
        </footer>
      </body>
    </html>
  );
}

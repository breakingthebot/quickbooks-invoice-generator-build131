# QuickBooks Invoicing Web Application (Vercel Ready)

Modern Next.js 14, React 18, TypeScript, and Tailwind CSS web application for the QuickBooks Online Invoicing and Payment Reconciliation platform.

---

## Features
- **Executive Financial KPIs**: Real-time cards showing Total Invoiced, Outstanding Balance, Collected Revenue, and Overdue Accounts.
- **Accounts Receivable Aging Schedule**: Visual breakdown across aging buckets (Current, 1-30d, 31-60d, 61-90d, 90+d).
- **Interactive Invoice Creation Wizard**: Modal to draft customer orders, add dynamic line items, taxes, discounts, and generate QBO invoices in real-time.
- **Payment Settlement Modal**: One-click manual payment recording with balance recalculation.
- **Automated Dunning Escalation Action**: Trigger batch dunning cycles directly from the web interface.
- **Real-Time Audit Streams**: Live display of recent dunning notice dispatches and cryptographic HMAC-SHA256 webhook deliveries.

---

## Local Development

Ensure the FastAPI backend is running:
```bash
# In project root:
qb-invoicing serve --host 127.0.0.1 --port 8000
```

Then start the Next.js development server:
```bash
cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser.

---

## Deploying to Vercel

### Option 1: Vercel Dashboard (Git Integration)
1. Push your repository to GitHub.
2. Import the project in your [Vercel Dashboard](https://vercel.com/new).
3. Set the **Root Directory** to `web`.
4. Configure Environment Variable:
   - `NEXT_PUBLIC_API_URL`: Your hosted FastAPI backend URL (e.g. `https://api.yourcompany.com`).
5. Click **Deploy**.

### Option 2: Vercel CLI
```bash
# Install Vercel CLI if needed
npm install -g vercel

# Deploy from repository root
vercel

# Deploy to production
vercel --prod
```

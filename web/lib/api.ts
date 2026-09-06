/**
 * Client API services and TypeScript types for QuickBooks Online Invoicing.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export interface FinancialMetrics {
  total_invoices: number;
  total_invoiced_amount: string | number;
  total_collected_amount: string | number;
  total_outstanding_balance: string | number;
  paid_invoices_count: number;
  partial_invoices_count: number;
  pending_invoices_count: number;
  overdue_invoices_count: number;
}

export interface InvoiceRecord {
  id?: number;
  qbo_invoice_id: string;
  order_id: string;
  doc_number: string;
  customer_name: string;
  customer_email: string;
  txn_date: string;
  due_date?: string;
  total_amount: number;
  balance_due: number;
  payment_status: 'PENDING' | 'PARTIAL' | 'PAID' | 'OVERDUE' | 'VOIDED';
  currency: string;
  created_at: string;
  updated_at: string;
}

export interface AgingBucketInvoice {
  invoice_id: string;
  doc_number: string;
  customer_name: string;
  customer_email?: string;
  due_date: string;
  days_overdue: number;
  balance_due: number;
  bucket: string;
}

export interface AgingScheduleReport {
  as_of_date: string;
  current_amount: number;
  days_1_30_amount: number;
  days_31_60_amount: number;
  days_61_90_amount: number;
  days_over_90_amount: number;
  total_receivables: number;
  invoices: AgingBucketInvoice[];
}

export interface DunningNoticeRecord {
  id?: number;
  invoice_id: string;
  doc_number: string;
  customer_name: string;
  customer_email?: string;
  escalation_level: number;
  level_name: string;
  days_overdue: number;
  balance_due: number;
  subject: string;
  sent_at: string;
  status: string;
  body_preview?: string;
}

export interface DunningBatchResult {
  evaluated_count: number;
  notices_sent_count: number;
  skipped_cooldown_count: number;
  current_count: number;
  notices: DunningNoticeRecord[];
}

export interface WebhookEventRecord {
  id?: number;
  event_id: string;
  realm_id: string;
  entity_name: string;
  entity_id: string;
  operation: string;
  processed_at: string;
}

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const errorBody = await res.text().catch(() => '');
    throw new Error(`API Error ${res.status}: ${errorBody || res.statusText}`);
  }

  return res.json();
}

export const api = {
  getMetrics: () => request<FinancialMetrics>('/api/metrics'),
  
  getInvoices: (status?: string) => 
    request<InvoiceRecord[]>(status ? `/api/invoices?status=${status}` : '/api/invoices'),
  
  getInvoice: (id: string) => 
    request<{ invoice: InvoiceRecord; payments: any[] }>(`/api/invoices/${id}`),

  createInvoice: (order: any) =>
    request<InvoiceRecord>('/api/orders/generate', {
      method: 'POST',
      body: JSON.stringify(order),
    }),

  recordPayment: (invoiceId: string, payment: { amount: number; payment_method: string; reference_num?: string }) =>
    request<{ status: string; payment: any; invoice: InvoiceRecord }>(`/api/invoices/${invoiceId}/payment`, {
      method: 'POST',
      body: JSON.stringify(payment),
    }),

  getAgingReport: (asOfDate?: string) =>
    request<AgingScheduleReport>(asOfDate ? `/api/dunning/aging-report?as_of_date=${asOfDate}` : '/api/dunning/aging-report'),

  runDunning: (opts?: { dry_run?: boolean; force?: boolean; as_of_date?: string }) =>
    request<DunningBatchResult>('/api/dunning/run', {
      method: 'POST',
      body: JSON.stringify(opts || {}),
    }),

  getDunningHistory: (limit: number = 25) =>
    request<DunningNoticeRecord[]>(`/api/dunning/history?limit=${limit}`),

  getWebhookEvents: (limit: number = 10) =>
    request<WebhookEventRecord[]>(`/api/webhooks/events?limit=${limit}`),
};

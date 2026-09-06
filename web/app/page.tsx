"use client";

import React, { useEffect, useState, useTransition } from "react";
import {
  DollarSign,
  FileText,
  AlertCircle,
  CheckCircle2,
  Clock,
  PlusCircle,
  RefreshCw,
  Send,
  CreditCard,
  ExternalLink,
  ShieldCheck,
  ChevronRight,
  TrendingUp,
} from "lucide-react";
import {
  api,
  FinancialMetrics,
  InvoiceRecord,
  AgingScheduleReport,
  DunningNoticeRecord,
  WebhookEventRecord,
} from "../lib/api";

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<FinancialMetrics | null>(null);
  const [invoices, setInvoices] = useState<InvoiceRecord[]>([]);
  const [aging, setAging] = useState<AgingScheduleReport | null>(null);
  const [dunningHistory, setDunningHistory] = useState<DunningNoticeRecord[]>([]);
  const [webhookEvents, setWebhookEvents] = useState<WebhookEventRecord[]>([]);

  const [filterStatus, setFilterStatus] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Modals
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [showPaymentModal, setShowPaymentModal] = useState<boolean>(false);
  const [selectedInvoice, setSelectedInvoice] = useState<InvoiceRecord | null>(null);
  const [isDunningPending, startDunningTransition] = useTransition();

  // Create Form State
  const [orderForm, setOrderForm] = useState({
    order_id: `WEB-${Math.floor(1000 + Math.random() * 9000)}`,
    customer_name: "",
    customer_email: "",
    company_name: "",
    currency: "USD",
    tax_rate_percent: 8.0,
    shipping_fee: 15.0,
    discount_total: 0.0,
    items: [
      { name: "Professional Consultation & Advisory", quantity: 1, unit_price: 350.0, tax_code: "TAX" },
    ],
  });

  // Payment Form State
  const [paymentForm, setPaymentForm] = useState({
    amount: 0.0,
    payment_method: "CreditCard",
    reference_num: `TXN-${Math.floor(10000 + Math.random() * 90000)}`,
  });

  const loadData = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const [m, invs, ag, dh, we] = await Promise.all([
        api.getMetrics().catch(() => null),
        api.getInvoices().catch(() => []),
        api.getAgingReport().catch(() => null),
        api.getDunningHistory(10).catch(() => []),
        api.getWebhookEvents(8).catch(() => []),
      ]);

      if (m) setMetrics(m);
      setInvoices(invs);
      if (ag) setAging(ag);
      setDunningHistory(dh);
      setWebhookEvents(we);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to connect to QuickBooks Invoicing backend.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleRunDunning = () => {
    startDunningTransition(async () => {
      try {
        const result = await api.runDunning({ force: false });
        alert(
          `Dunning Cycle Completed Successfully!\n\nEvaluated: ${result.evaluated_count} open invoices\nNotices Dispatched: ${result.notices_sent_count}\nSkipped (Cooldown): ${result.skipped_cooldown_count}`
        );
        loadData();
      } catch (err: any) {
        alert(`Dunning execution failed: ${err.message}`);
      }
    });
  };

  const handleCreateInvoiceSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        order_id: orderForm.order_id,
        customer: {
          name: orderForm.customer_name,
          email: orderForm.customer_email,
          company_name: orderForm.company_name,
        },
        currency: orderForm.currency,
        tax_rate_percent: Number(orderForm.tax_rate_percent),
        shipping_fee: Number(orderForm.shipping_fee),
        discount_total: Number(orderForm.discount_total),
        items: orderForm.items.map((i) => ({
          name: i.name,
          quantity: Number(i.quantity),
          unit_price: Number(i.unit_price),
          tax_code: i.tax_code,
        })),
      };

      await api.createInvoice(payload);
      setShowCreateModal(false);
      // Reset form
      setOrderForm({
        order_id: `WEB-${Math.floor(1000 + Math.random() * 9000)}`,
        customer_name: "",
        customer_email: "",
        company_name: "",
        currency: "USD",
        tax_rate_percent: 8.0,
        shipping_fee: 15.0,
        discount_total: 0.0,
        items: [{ name: "Professional Consultation & Advisory", quantity: 1, unit_price: 350.0, tax_code: "TAX" }],
      });
      loadData();
    } catch (err: any) {
      alert(`Invoice generation failed: ${err.message}`);
    }
  };

  const openPaymentDialog = (invoice: InvoiceRecord) => {
    setSelectedInvoice(invoice);
    setPaymentForm({
      amount: invoice.balance_due,
      payment_method: "CreditCard",
      reference_num: `TXN-${Math.floor(10000 + Math.random() * 90000)}`,
    });
    setShowPaymentModal(true);
  };

  const handleRecordPaymentSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedInvoice) return;
    try {
      await api.recordPayment(selectedInvoice.qbo_invoice_id, {
        amount: Number(paymentForm.amount),
        payment_method: paymentForm.payment_method,
        reference_num: paymentForm.reference_num,
      });
      setShowPaymentModal(false);
      loadData();
    } catch (err: any) {
      alert(`Payment recording failed: ${err.message}`);
    }
  };

  const filteredInvoices = invoices.filter((inv) => {
    const matchesStatus = filterStatus === "ALL" || inv.payment_status === filterStatus;
    const matchesSearch =
      inv.customer_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      inv.doc_number.toLowerCase().includes(searchQuery.toLowerCase()) ||
      inv.order_id.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesStatus && matchesSearch;
  });

  return (
    <div className="space-y-8">
      {/* Top Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">Invoice Operations &amp; Ledger</h1>
          <p className="text-sm text-slate-500">Live synchronized with QuickBooks Online Accounting API v3</p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            onClick={loadData}
            className="inline-flex items-center px-3.5 py-2 border border-slate-300 shadow-sm text-xs font-semibold rounded-lg text-slate-700 bg-white hover:bg-slate-50 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center px-4 py-2 border border-transparent text-xs font-bold rounded-lg shadow-sm text-white bg-emerald-600 hover:bg-emerald-700 transition"
          >
            <PlusCircle className="w-4 h-4 mr-1.5" />
            Create Invoice
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-sm flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-5 h-5 text-amber-600 shrink-0" />
            <span>{errorMsg} (Ensure FastAPI server is running: <code className="font-mono bg-amber-100 px-1 py-0.5 rounded">qb-invoicing serve</code>)</span>
          </div>
          <button onClick={loadData} className="underline text-xs font-bold text-amber-800 ml-4">
            Retry
          </button>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200 flex flex-col justify-between">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Total Invoiced</span>
            <div className="text-2xl font-extrabold text-slate-900 mt-1">
              ${Number(metrics?.total_invoiced_amount || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </div>
          </div>
          <div className="text-xs font-medium text-slate-500 mt-3 flex items-center">
            <FileText className="w-3.5 h-3.5 mr-1 text-slate-400" />
            {metrics?.total_invoices || 0} invoices recorded
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200 flex flex-col justify-between">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-600">Total Collected</span>
            <div className="text-2xl font-extrabold text-emerald-600 mt-1">
              ${Number(metrics?.total_collected_amount || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </div>
          </div>
          <div className="text-xs font-medium text-emerald-600 mt-3 flex items-center">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1 text-emerald-500" />
            {metrics?.paid_invoices_count || 0} fully settled
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200 flex flex-col justify-between">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-amber-600">Receivables Balance</span>
            <div className="text-2xl font-extrabold text-amber-600 mt-1">
              ${Number(metrics?.total_outstanding_balance || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </div>
          </div>
          <div className="text-xs font-medium text-amber-700 mt-3 flex items-center">
            <Clock className="w-3.5 h-3.5 mr-1 text-amber-500" />
            {(metrics?.pending_invoices_count || 0) + (metrics?.partial_invoices_count || 0)} open accounts
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200 flex flex-col justify-between">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-rose-600">Overdue Risk</span>
            <div className="text-2xl font-extrabold text-rose-600 mt-1">{metrics?.overdue_invoices_count || 0}</div>
          </div>
          <div className="text-xs font-medium text-rose-600 mt-3 flex items-center">
            <AlertCircle className="w-3.5 h-3.5 mr-1 text-rose-500" />
            Requires dunning escalation
          </div>
        </div>
      </div>

      {/* Accounts Receivable Aging Schedule */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-base font-bold text-slate-900">Accounts Receivable Aging Schedule</h2>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 font-medium">
                As of {aging?.as_of_date || "Today"}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Partitioned into industry-standard aging buckets with automated escalation tiers
            </p>
          </div>
          <button
            onClick={handleRunDunning}
            disabled={isDunningPending}
            className="inline-flex items-center px-4 py-2 border border-transparent text-xs font-bold rounded-lg shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 transition disabled:opacity-50"
          >
            <Send className={`w-3.5 h-3.5 mr-1.5 ${isDunningPending ? "animate-pulse" : ""}`} />
            {isDunningPending ? "Running Escalation..." : "Run Dunning Escalation"}
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-5 text-center">
          <div className="p-4 rounded-xl bg-emerald-50/70 border border-emerald-100">
            <span className="text-[11px] font-bold text-emerald-800 uppercase tracking-wider">Current</span>
            <div className="text-xl font-black text-emerald-900 mt-1">
              ${Number(aging?.current_amount || 0).toFixed(2)}
            </div>
            <div className="text-[11px] text-emerald-600 mt-0.5">Within payment terms</div>
          </div>

          <div className="p-4 rounded-xl bg-blue-50/70 border border-blue-100">
            <span className="text-[11px] font-bold text-blue-800 uppercase tracking-wider">1-30 Days</span>
            <div className="text-xl font-black text-blue-900 mt-1">
              ${Number(aging?.days_1_30_amount || 0).toFixed(2)}
            </div>
            <div className="text-[11px] text-blue-600 mt-0.5">Tier 1: Friendly Reminder</div>
          </div>

          <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-100">
            <span className="text-[11px] font-bold text-amber-800 uppercase tracking-wider">31-60 Days</span>
            <div className="text-xl font-black text-amber-900 mt-1">
              ${Number(aging?.days_31_60_amount || 0).toFixed(2)}
            </div>
            <div className="text-[11px] text-amber-600 mt-0.5">Tier 2: Urgent Notice</div>
          </div>

          <div className="p-4 rounded-xl bg-orange-50/70 border border-orange-100">
            <span className="text-[11px] font-bold text-orange-800 uppercase tracking-wider">61-90 Days</span>
            <div className="text-xl font-black text-orange-900 mt-1">
              ${Number(aging?.days_61_90_amount || 0).toFixed(2)}
            </div>
            <div className="text-[11px] text-orange-600 mt-0.5">Tier 3: Final Demand</div>
          </div>

          <div className="p-4 rounded-xl bg-rose-50/70 border border-rose-100">
            <span className="text-[11px] font-bold text-rose-800 uppercase tracking-wider">90+ Days</span>
            <div className="text-xl font-black text-rose-900 mt-1">
              ${Number(aging?.days_over_90_amount || 0).toFixed(2)}
            </div>
            <div className="text-[11px] text-rose-600 mt-0.5">Tier 4: Collections Warning</div>
          </div>
        </div>
      </div>

      {/* Main Invoices Ledger */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">Tracked QuickBooks Invoices</h2>
            <p className="text-xs text-slate-500">Live status synchronized with QuickBooks Online Accounting API v3</p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Search Input */}
            <input
              type="text"
              placeholder="Search customer, invoice #..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="text-xs px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500 w-48"
            />

            {/* Status Tabs */}
            <div className="flex p-0.5 bg-slate-100 rounded-lg text-xs font-semibold">
              {["ALL", "PENDING", "PARTIAL", "PAID", "OVERDUE"].map((st) => (
                <button
                  key={st}
                  onClick={() => setFilterStatus(st)}
                  className={`px-2.5 py-1 rounded-md transition ${
                    filterStatus === st ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="bg-slate-50/70 text-slate-500 text-xs uppercase tracking-wider font-semibold border-b border-slate-200">
                <th className="py-3 px-4">Doc #</th>
                <th className="py-3 px-4">QuickBooks ID</th>
                <th className="py-3 px-4">Customer</th>
                <th className="py-3 px-4">Txn Date</th>
                <th className="py-3 px-4">Due Date</th>
                <th className="py-3 px-4 text-right">Total</th>
                <th className="py-3 px-4 text-right">Balance</th>
                <th className="py-3 px-4 text-center">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredInvoices.map((inv) => {
                const badgeStyle = {
                  PAID: "bg-emerald-100 text-emerald-800 border-emerald-200",
                  PENDING: "bg-amber-100 text-amber-800 border-amber-200",
                  PARTIAL: "bg-blue-100 text-blue-800 border-blue-200",
                  OVERDUE: "bg-rose-100 text-rose-800 border-rose-200",
                  VOIDED: "bg-gray-100 text-gray-800 border-gray-200",
                }[inv.payment_status] || "bg-gray-100 text-gray-800 border-gray-200";

                return (
                  <tr key={inv.doc_number} className="hover:bg-slate-50/80 transition">
                    <td className="py-3.5 px-4 font-mono font-bold text-indigo-600">
                      <a
                        href={`/api/invoices/${inv.doc_number}/html`}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:underline flex items-center"
                      >
                        {inv.doc_number}
                        <ExternalLink className="w-3 h-3 ml-1 text-slate-400" />
                      </a>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-xs text-slate-500">{inv.qbo_invoice_id}</td>
                    <td className="py-3.5 px-4 text-slate-800 font-medium">{inv.customer_name}</td>
                    <td className="py-3.5 px-4 text-slate-500 text-xs">{inv.txn_date}</td>
                    <td className="py-3.5 px-4 text-slate-500 text-xs">{inv.due_date || "Upon Receipt"}</td>
                    <td className="py-3.5 px-4 text-right font-semibold text-slate-900">${inv.total_amount.toFixed(2)}</td>
                    <td className={`py-3.5 px-4 text-right font-black ${inv.balance_due === 0 ? "text-emerald-600" : "text-amber-600"}`}>
                      ${inv.balance_due.toFixed(2)}
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold border ${badgeStyle}`}>
                        {inv.payment_status}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      {inv.balance_due > 0 && inv.payment_status !== "VOIDED" ? (
                        <button
                          onClick={() => openPaymentDialog(inv)}
                          className="inline-flex items-center px-2.5 py-1 text-xs font-semibold rounded bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200 transition"
                        >
                          <CreditCard className="w-3 h-3 mr-1" />
                          Record Pay
                        </button>
                      ) : (
                        <span className="text-xs text-slate-400 font-medium">Settled</span>
                      )}
                    </td>
                  </tr>
                );
              })}

              {filteredInvoices.length === 0 && (
                <tr>
                  <td colSpan={9} className="text-center py-12 text-slate-400">
                    No invoices matching current filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Dunning & Webhook Split Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Dunning Notice History */}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="p-5 border-b border-slate-100">
            <h3 className="text-base font-bold text-slate-900">Dunning Notice Escalation History</h3>
            <p className="text-xs text-slate-500">Audit trail of automated payment reminders dispatched</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                  <th className="py-2.5 px-4">Doc #</th>
                  <th className="py-2.5 px-4">Customer</th>
                  <th className="py-2.5 px-4">Tier</th>
                  <th className="py-2.5 px-4">Overdue</th>
                  <th className="py-2.5 px-4">Balance</th>
                  <th className="py-2.5 px-4">Dispatched</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {dunningHistory.map((d, idx) => (
                  <tr key={idx} className="hover:bg-slate-50">
                    <td className="py-2.5 px-4 font-mono font-medium text-slate-700">{d.doc_number}</td>
                    <td className="py-2.5 px-4 text-slate-800">{d.customer_name}</td>
                    <td className="py-2.5 px-4">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100">
                        Tier {d.escalation_level}: {d.level_name}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-slate-600">{d.days_overdue} days</td>
                    <td className="py-2.5 px-4 font-semibold text-slate-800">${Number(d.balance_due).toFixed(2)}</td>
                    <td className="py-2.5 px-4 text-slate-400 font-mono">{d.sent_at?.slice(0, 16).replace("T", " ")}</td>
                  </tr>
                ))}
                {dunningHistory.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-center py-8 text-slate-400">
                      No dunning notices dispatched yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Webhooks Ingestion Stream */}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="p-5 border-b border-slate-100 flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-slate-900">QuickBooks Webhook Event Stream</h3>
              <p className="text-xs text-slate-500">Cryptographically verified inbound Intuit push notifications</p>
            </div>
            <span className="text-[11px] bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded-full border border-emerald-200">
              HMAC-SHA256 Active
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                  <th className="py-2.5 px-4">Event ID</th>
                  <th className="py-2.5 px-4">Entity</th>
                  <th className="py-2.5 px-4">Operation</th>
                  <th className="py-2.5 px-4">Target ID</th>
                  <th className="py-2.5 px-4">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {webhookEvents.map((w, idx) => (
                  <tr key={idx} className="hover:bg-slate-50">
                    <td className="py-2.5 px-4 font-mono text-slate-500">{w.event_id.slice(0, 12)}...</td>
                    <td className="py-2.5 px-4 font-bold text-indigo-600">{w.entity_name}</td>
                    <td className="py-2.5 px-4 text-slate-700">{w.operation}</td>
                    <td className="py-2.5 px-4 font-mono text-slate-500">{w.entity_id}</td>
                    <td className="py-2.5 px-4 text-slate-400 font-mono">{w.processed_at?.slice(0, 16).replace("T", " ")}</td>
                  </tr>
                ))}
                {webhookEvents.length === 0 && (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-slate-400">
                      No webhook push notifications received yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* MODAL: Create Invoice */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-xl w-full p-6 shadow-2xl border border-slate-200 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-900">Create New QuickBooks Online Invoice</h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-slate-600 text-lg font-bold"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleCreateInvoiceSubmit} className="space-y-4 mt-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Customer Name *</label>
                  <input
                    required
                    type="text"
                    value={orderForm.customer_name}
                    onChange={(e) => setOrderForm({ ...orderForm, customer_name: e.target.value })}
                    placeholder="e.g. Jordan Miller"
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Customer Email *</label>
                  <input
                    required
                    type="email"
                    value={orderForm.customer_email}
                    onChange={(e) => setOrderForm({ ...orderForm, customer_email: e.target.value })}
                    placeholder="jordan@company.com"
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Order / Doc Ref</label>
                  <input
                    type="text"
                    value={orderForm.order_id}
                    onChange={(e) => setOrderForm({ ...orderForm, order_id: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg font-mono outline-none"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Currency</label>
                  <select
                    value={orderForm.currency}
                    onChange={(e) => setOrderForm({ ...orderForm, currency: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg outline-none"
                  >
                    <option value="USD">USD ($)</option>
                    <option value="EUR">EUR (€)</option>
                    <option value="GBP">GBP (£)</option>
                    <option value="CAD">CAD ($)</option>
                  </select>
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Tax Rate (%)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={orderForm.tax_rate_percent}
                    onChange={(e) => setOrderForm({ ...orderForm, tax_rate_percent: parseFloat(e.target.value) || 0 })}
                    className="w-full px-3 py-2 border rounded-lg outline-none"
                  />
                </div>
              </div>

              {/* Line Items */}
              <div className="pt-2 border-t border-slate-100">
                <label className="block font-semibold text-slate-700 mb-2">Invoice Line Item</label>
                <div className="grid grid-cols-6 gap-2">
                  <div className="col-span-3">
                    <input
                      type="text"
                      placeholder="Item Description"
                      value={orderForm.items[0].name}
                      onChange={(e) => {
                        const items = [...orderForm.items];
                        items[0].name = e.target.value;
                        setOrderForm({ ...orderForm, items });
                      }}
                      className="w-full px-3 py-2 border rounded-lg outline-none"
                    />
                  </div>
                  <div className="col-span-1">
                    <input
                      type="number"
                      placeholder="Qty"
                      value={orderForm.items[0].quantity}
                      onChange={(e) => {
                        const items = [...orderForm.items];
                        items[0].quantity = parseInt(e.target.value) || 1;
                        setOrderForm({ ...orderForm, items });
                      }}
                      className="w-full px-3 py-2 border rounded-lg outline-none text-center"
                    />
                  </div>
                  <div className="col-span-2">
                    <input
                      type="number"
                      step="0.01"
                      placeholder="Unit Price"
                      value={orderForm.items[0].unit_price}
                      onChange={(e) => {
                        const items = [...orderForm.items];
                        items[0].unit_price = parseFloat(e.target.value) || 0;
                        setOrderForm({ ...orderForm, items });
                      }}
                      className="w-full px-3 py-2 border rounded-lg outline-none text-right"
                    />
                  </div>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100 flex items-center justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-slate-700 font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-lg shadow-sm"
                >
                  Generate Invoice in QBO
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: Record Payment */}
      {showPaymentModal && selectedInvoice && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900">Record Payment &bull; {selectedInvoice.doc_number}</h3>
              <button
                onClick={() => setShowPaymentModal(false)}
                className="text-slate-400 hover:text-slate-600 text-lg font-bold"
              >
                &times;
              </button>
            </div>

            <div className="py-3 text-xs bg-slate-50 rounded-lg p-3 my-3">
              <div className="flex justify-between text-slate-600 mb-1">
                <span>Customer:</span> <strong className="text-slate-900">{selectedInvoice.customer_name}</strong>
              </div>
              <div className="flex justify-between text-slate-600">
                <span>Current Balance Due:</span>
                <strong className="text-amber-600 font-bold">${selectedInvoice.balance_due.toFixed(2)}</strong>
              </div>
            </div>

            <form onSubmit={handleRecordPaymentSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Payment Amount ($) *</label>
                <input
                  required
                  type="number"
                  step="0.01"
                  max={selectedInvoice.balance_due}
                  value={paymentForm.amount}
                  onChange={(e) => setPaymentForm({ ...paymentForm, amount: parseFloat(e.target.value) || 0 })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500 font-bold text-sm outline-none"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Payment Method</label>
                <select
                  value={paymentForm.payment_method}
                  onChange={(e) => setPaymentForm({ ...paymentForm, payment_method: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg outline-none"
                >
                  <option value="CreditCard">Credit Card</option>
                  <option value="BankTransfer">Bank Transfer / ACH</option>
                  <option value="Check">Check</option>
                  <option value="Cash">Cash</option>
                </select>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Reference / Transaction Number</label>
                <input
                  type="text"
                  value={paymentForm.reference_num}
                  onChange={(e) => setPaymentForm({ ...paymentForm, reference_num: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg font-mono outline-none"
                />
              </div>

              <div className="pt-4 border-t border-slate-100 flex items-center justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setShowPaymentModal(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-slate-700 font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-lg shadow-sm"
                >
                  Confirm Payment
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

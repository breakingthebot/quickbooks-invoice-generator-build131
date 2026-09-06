package com.breakingthebot.qbinvoicing.data.model

import com.google.gson.annotations.SerializedName

/**
 * Domain DTO models mapping directly to the FastAPI REST API.
 */

data class FinancialMetricsDto(
    @SerializedName("total_invoiced") val totalInvoiced: Double = 0.0,
    @SerializedName("total_collected") val totalCollected: Double = 0.0,
    @SerializedName("total_outstanding") val totalOutstanding: Double = 0.0,
    @SerializedName("total_overdue") val totalOverdue: Double = 0.0,
    @SerializedName("currency") val currency: String = "USD",
    @SerializedName("count_by_status") val countByStatus: Map<String, Int> = emptyMap(),
    @SerializedName("total_invoices_count") val totalInvoicesCount: Int = 0
)

data class InvoiceDto(
    @SerializedName("qbo_invoice_id") val qboInvoiceId: String,
    @SerializedName("order_id") val orderId: String? = null,
    @SerializedName("doc_number") val docNumber: String,
    @SerializedName("customer_name") val customerName: String,
    @SerializedName("customer_email") val customerEmail: String? = null,
    @SerializedName("txn_date") val txnDate: String,
    @SerializedName("due_date") val dueDate: String,
    @SerializedName("total_amount") val totalAmount: Double,
    @SerializedName("balance_due") val balanceDue: Double,
    @SerializedName("payment_status") val paymentStatus: String,
    @SerializedName("currency") val currency: String = "USD",
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("updated_at") val updatedAt: String? = null
)

data class LineItemDto(
    @SerializedName("item_name") val itemName: String,
    @SerializedName("description") val description: String? = null,
    @SerializedName("unit_price") val unitPrice: Double,
    @SerializedName("quantity") val quantity: Double,
    @SerializedName("amount") val amount: Double,
    @SerializedName("tax_code") val taxCode: String = "TAX"
)

data class PaymentRecordDto(
    @SerializedName("qbo_payment_id") val qboPaymentId: String,
    @SerializedName("qbo_invoice_id") val qboInvoiceId: String,
    @SerializedName("amount") val amount: Double,
    @SerializedName("payment_method") val paymentMethod: String,
    @SerializedName("txn_date") val txnDate: String,
    @SerializedName("reference_num") val referenceNum: String? = null,
    @SerializedName("currency") val currency: String = "USD",
    @SerializedName("created_at") val createdAt: String? = null
)

data class InvoiceDetailDto(
    @SerializedName("invoice") val invoice: InvoiceDto,
    @SerializedName("payments") val payments: List<PaymentRecordDto> = emptyList(),
    @SerializedName("line_items") val lineItems: List<LineItemDto> = emptyList(),
    @SerializedName("html_url") val htmlUrl: String? = null
)

data class AgingBucketDto(
    @SerializedName("bucket_name") val bucketName: String,
    @SerializedName("min_days") val minDays: Int,
    @SerializedName("max_days") val maxDays: Int?,
    @SerializedName("invoice_count") val invoiceCount: Int,
    @SerializedName("total_balance") val totalBalance: Double,
    @SerializedName("severity") val severity: String
)

data class AgingScheduleReportDto(
    @SerializedName("as_of_date") val asOfDate: String,
    @SerializedName("total_receivables") val totalReceivables: Double,
    @SerializedName("total_overdue_receivables") val totalOverdueReceivables: Double,
    @SerializedName("currency") val currency: String = "USD",
    @SerializedName("buckets") val buckets: List<AgingBucketDto> = emptyList()
)

data class DunningRecordDto(
    @SerializedName("id") val id: Int,
    @SerializedName("invoice_id") val invoiceId: String,
    @SerializedName("doc_number") val docNumber: String,
    @SerializedName("customer_name") val customerName: String,
    @SerializedName("customer_email") val customerEmail: String,
    @SerializedName("escalation_level") val escalationLevel: Int,
    @SerializedName("level_name") val levelName: String,
    @SerializedName("days_overdue") val daysOverdue: Int,
    @SerializedName("balance_due") val balanceDue: Double,
    @SerializedName("subject") val subject: String,
    @SerializedName("sent_at") val sentAt: String,
    @SerializedName("status") val status: String,
    @SerializedName("body_preview") val bodyPreview: String
)

data class WebhookEventDto(
    @SerializedName("id") val id: Int,
    @SerializedName("event_id") val eventId: String,
    @SerializedName("realm_id") val realmId: String,
    @SerializedName("entity_name") val entityName: String,
    @SerializedName("entity_id") val entityId: String,
    @SerializedName("operation") val operation: String,
    @SerializedName("event_date") val eventDate: String,
    @SerializedName("processed") val processed: Boolean,
    @SerializedName("processed_at") val processedAt: String? = null,
    @SerializedName("result_summary") val resultSummary: String? = null
)

// Request payloads
data class CreateOrderItemDto(
    @SerializedName("item_id") val itemId: String = "ITEM-1",
    @SerializedName("name") val name: String,
    @SerializedName("description") val description: String = "",
    @SerializedName("unit_price") val unitPrice: Double,
    @SerializedName("quantity") val quantity: Double,
    @SerializedName("tax_code") val taxCode: String = "TAX"
)

data class CreateOrderCustomerDto(
    @SerializedName("name") val name: String,
    @SerializedName("email") val email: String
)

data class CreateOrderRequestDto(
    @SerializedName("order_id") val orderId: String,
    @SerializedName("order_number") val orderNumber: String,
    @SerializedName("customer") val customer: CreateOrderCustomerDto,
    @SerializedName("items") val items: List<CreateOrderItemDto>,
    @SerializedName("currency") val currency: String = "USD",
    @SerializedName("shipping_fee") val shippingFee: Double = 0.0,
    @SerializedName("tax_rate") val taxRate: Double = 0.0,
    @SerializedName("discount_total") val discountTotal: Double = 0.0,
    @SerializedName("payment_terms_days") val paymentTermsDays: Int = 30
)

data class RecordPaymentRequestDto(
    @SerializedName("amount") val amount: Double,
    @SerializedName("payment_method") val paymentMethod: String = "CreditCard",
    @SerializedName("reference_num") val referenceNum: String = "",
    @SerializedName("txn_date") val txnDate: String? = null
)

data class PaymentResponseDto(
    @SerializedName("success") val success: Boolean,
    @SerializedName("message") val message: String,
    @SerializedName("invoice") val invoice: InvoiceDto
)

data class DunningRunRequestDto(
    @SerializedName("cooldown_days") val cooldownDays: Int = 7,
    @SerializedName("force") val force: Boolean = false,
    @SerializedName("dry_run") val dryRun: Boolean = false
)

data class DunningRunResultDto(
    @SerializedName("success") val success: Boolean,
    @SerializedName("total_eligible") val totalEligible: Int,
    @SerializedName("sent_count") val sentCount: Int,
    @SerializedName("skipped_cooldown_count") val skippedCooldownCount: Int,
    @SerializedName("notices") val notices: List<DunningRecordDto> = emptyList()
)

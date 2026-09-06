package com.breakingthebot.qbinvoicing.data.api

import com.breakingthebot.qbinvoicing.data.model.*
import retrofit2.Response
import retrofit2.http.*

/**
 * Retrofit REST client endpoints for QuickBooks Invoicing & Dunning backend.
 */
interface QbApiService {

    @GET("/api/metrics")
    suspend fun getMetrics(): Response<FinancialMetricsDto>

    @GET("/api/invoices")
    suspend fun getInvoices(
        @Query("status") status: String? = null,
        @Query("limit") limit: Int = 100
    ): Response<List<InvoiceDto>>

    @GET("/api/invoices/{id}")
    suspend fun getInvoiceDetail(
        @Path("id") invoiceId: String
    ): Response<InvoiceDetailDto>

    @POST("/api/orders/generate")
    suspend fun generateInvoice(
        @Body request: CreateOrderRequestDto
    ): Response<InvoiceDto>

    @POST("/api/invoices/{id}/payment")
    suspend fun recordPayment(
        @Path("id") invoiceId: String,
        @Body request: RecordPaymentRequestDto
    ): Response<PaymentResponseDto>

    @GET("/api/dunning/aging-report")
    suspend fun getAgingReport(
        @Query("as_of") asOf: String? = null
    ): Response<AgingScheduleReportDto>

    @GET("/api/dunning/history")
    suspend fun getDunningHistory(
        @Query("limit") limit: Int = 50
    ): Response<List<DunningRecordDto>>

    @POST("/api/dunning/run")
    suspend fun runDunning(
        @Body request: DunningRunRequestDto = DunningRunRequestDto()
    ): Response<DunningRunResultDto>

    @GET("/api/webhooks/events")
    suspend fun getWebhookEvents(
        @Query("limit") limit: Int = 50
    ): Response<List<WebhookEventDto>>
}

package com.breakingthebot.qbinvoicing.data.repository

import com.breakingthebot.qbinvoicing.data.api.ApiClient
import com.breakingthebot.qbinvoicing.data.model.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Repository mediating access to the QuickBooks backend API.
 */
class QbRepository {

    suspend fun getMetrics(): Result<FinancialMetricsDto> = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.getService().getMetrics()
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getInvoices(status: String? = null): Result<List<InvoiceDto>> = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.getService().getInvoices(status = status)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getInvoiceDetail(invoiceId: String): Result<InvoiceDetailDto> = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.getService().getInvoiceDetail(invoiceId)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun generateInvoice(request: CreateOrderRequestDto): Result<InvoiceDto> = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.getService().generateInvoice(request)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.errorBody()?.string() ?: response.message()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun recordPayment(
        invoiceId: String,
        amount: Double,
        method: String,
        ref: String
    ): Result<PaymentResponseDto> = withContext(Dispatchers.IO) {
        try {
            val req = RecordPaymentRequestDto(
                amount = amount,
                paymentMethod = method,
                referenceNum = ref
            )
            val response = ApiClient.getService().recordPayment(invoiceId, req)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.errorBody()?.string() ?: response.message()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getAgingReport(): Result<AgingScheduleReportDto> = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.getService().getAgingReport()
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getDunningHistory(): Result<List<DunningRecordDto>> = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.getService().getDunningHistory()
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun runDunning(force: Boolean = false): Result<DunningRunResultDto> = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.getService().runDunning(DunningRunRequestDto(force = force))
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.errorBody()?.string() ?: response.message()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getWebhookEvents(): Result<List<WebhookEventDto>> = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.getService().getWebhookEvents()
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception("HTTP ${response.code()}: ${response.message()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}

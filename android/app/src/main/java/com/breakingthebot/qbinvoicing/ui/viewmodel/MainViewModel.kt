package com.breakingthebot.qbinvoicing.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.breakingthebot.qbinvoicing.data.api.ApiClient
import com.breakingthebot.qbinvoicing.data.model.*
import com.breakingthebot.qbinvoicing.data.repository.QbRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class UiState<out T> {
    object Idle : UiState<Nothing>()
    object Loading : UiState<Nothing>()
    data class Success<T>(val data: T) : UiState<T>()
    data class Error(val message: String) : UiState<Nothing>()
}

class MainViewModel(
    private val repository: QbRepository = QbRepository()
) : ViewModel() {

    private val _serverUrl = MutableStateFlow(ApiClient.getBaseUrl())
    val serverUrl: StateFlow<String> = _serverUrl.asStateFlow()

    private val _metricsState = MutableStateFlow<UiState<FinancialMetricsDto>>(UiState.Loading)
    val metricsState: StateFlow<UiState<FinancialMetricsDto>> = _metricsState.asStateFlow()

    private val _agingReportState = MutableStateFlow<UiState<AgingScheduleReportDto>>(UiState.Loading)
    val agingReportState: StateFlow<UiState<AgingScheduleReportDto>> = _agingReportState.asStateFlow()

    private val _invoicesState = MutableStateFlow<UiState<List<InvoiceDto>>>(UiState.Loading)
    val invoicesState: StateFlow<UiState<List<InvoiceDto>>> = _invoicesState.asStateFlow()

    private val _selectedFilter = MutableStateFlow("ALL")
    val selectedFilter: StateFlow<String> = _selectedFilter.asStateFlow()

    private val _dunningHistoryState = MutableStateFlow<UiState<List<DunningRecordDto>>>(UiState.Idle)
    val dunningHistoryState: StateFlow<UiState<List<DunningRecordDto>>> = _dunningHistoryState.asStateFlow()

    private val _webhooksState = MutableStateFlow<UiState<List<WebhookEventDto>>>(UiState.Idle)
    val webhooksState: StateFlow<UiState<List<WebhookEventDto>>> = _webhooksState.asStateFlow()

    private val _actionMessage = MutableStateFlow<String?>(null)
    val actionMessage: StateFlow<String?> = _actionMessage.asStateFlow()

    private val _isDunningRunning = MutableStateFlow(false)
    val isDunningRunning: StateFlow<Boolean> = _isDunningRunning.asStateFlow()

    init {
        refreshAll()
    }

    fun updateServerUrl(newUrl: String) {
        ApiClient.setBaseUrl(newUrl)
        _serverUrl.value = ApiClient.getBaseUrl()
        refreshAll()
    }

    fun clearActionMessage() {
        _actionMessage.value = null
    }

    fun setFilter(status: String) {
        _selectedFilter.value = status
        fetchInvoices(if (status == "ALL") null else status)
    }

    fun refreshAll() {
        fetchMetrics()
        fetchAgingReport()
        fetchInvoices(if (_selectedFilter.value == "ALL") null else _selectedFilter.value)
        fetchDunningHistory()
        fetchWebhooks()
    }

    fun fetchMetrics() {
        viewModelScope.launch {
            _metricsState.value = UiState.Loading
            repository.getMetrics().fold(
                onSuccess = { _metricsState.value = UiState.Success(it) },
                onFailure = { _metricsState.value = UiState.Error(it.message ?: "Failed to fetch metrics") }
            )
        }
    }

    fun fetchAgingReport() {
        viewModelScope.launch {
            _agingReportState.value = UiState.Loading
            repository.getAgingReport().fold(
                onSuccess = { _agingReportState.value = UiState.Success(it) },
                onFailure = { _agingReportState.value = UiState.Error(it.message ?: "Failed to fetch aging report") }
            )
        }
    }

    fun fetchInvoices(status: String? = null) {
        viewModelScope.launch {
            _invoicesState.value = UiState.Loading
            repository.getInvoices(status).fold(
                onSuccess = { _invoicesState.value = UiState.Success(it) },
                onFailure = { _invoicesState.value = UiState.Error(it.message ?: "Failed to fetch invoices") }
            )
        }
    }

    fun fetchDunningHistory() {
        viewModelScope.launch {
            _dunningHistoryState.value = UiState.Loading
            repository.getDunningHistory().fold(
                onSuccess = { _dunningHistoryState.value = UiState.Success(it) },
                onFailure = { _dunningHistoryState.value = UiState.Error(it.message ?: "Failed to fetch dunning history") }
            )
        }
    }

    fun fetchWebhooks() {
        viewModelScope.launch {
            _webhooksState.value = UiState.Loading
            repository.getWebhookEvents().fold(
                onSuccess = { _webhooksState.value = UiState.Success(it) },
                onFailure = { _webhooksState.value = UiState.Error(it.message ?: "Failed to fetch webhooks") }
            )
        }
    }

    fun createInvoice(
        orderId: String,
        customerName: String,
        customerEmail: String,
        items: List<CreateOrderItemDto>,
        taxRate: Double,
        shippingFee: Double,
        paymentTermsDays: Int,
        onComplete: (Boolean, String) -> Unit
    ) {
        viewModelScope.launch {
            val request = CreateOrderRequestDto(
                orderId = orderId,
                orderNumber = orderId,
                customer = CreateOrderCustomerDto(name = customerName, email = customerEmail),
                items = items,
                taxRate = taxRate,
                shippingFee = shippingFee,
                paymentTermsDays = paymentTermsDays
            )
            repository.generateInvoice(request).fold(
                onSuccess = {
                    _actionMessage.value = "Created Invoice ${it.docNumber} (${it.qboInvoiceId})"
                    refreshAll()
                    onComplete(true, "Successfully generated Invoice ${it.docNumber}!")
                },
                onFailure = {
                    val msg = it.message ?: "Error generating invoice"
                    _actionMessage.value = msg
                    onComplete(false, msg)
                }
            )
        }
    }

    fun recordPayment(
        invoiceId: String,
        amount: Double,
        method: String,
        ref: String,
        onComplete: (Boolean, String) -> Unit
    ) {
        viewModelScope.launch {
            repository.recordPayment(invoiceId, amount, method, ref).fold(
                onSuccess = {
                    _actionMessage.value = "Recorded payment: ${it.message}"
                    refreshAll()
                    onComplete(true, it.message)
                },
                onFailure = {
                    val msg = it.message ?: "Error recording payment"
                    _actionMessage.value = msg
                    onComplete(false, msg)
                }
            )
        }
    }

    fun runDunningEscalation(force: Boolean = false) {
        viewModelScope.launch {
            _isDunningRunning.value = true
            repository.runDunning(force = force).fold(
                onSuccess = {
                    _actionMessage.value = "Dunning Run: Dispatched ${it.sentCount} notices (${it.skippedCooldownCount} suppressed by cooldown)"
                    refreshAll()
                },
                onFailure = {
                    _actionMessage.value = "Dunning failed: ${it.message}"
                }
            )
            _isDunningRunning.value = false
        }
    }
}

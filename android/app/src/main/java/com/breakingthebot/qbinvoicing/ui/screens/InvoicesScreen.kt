package com.breakingthebot.qbinvoicing.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.breakingthebot.qbinvoicing.data.model.InvoiceDto
import com.breakingthebot.qbinvoicing.ui.components.RecordPaymentDialog
import com.breakingthebot.qbinvoicing.ui.components.StatusBadge
import com.breakingthebot.qbinvoicing.ui.components.formatCurrency
import com.breakingthebot.qbinvoicing.ui.theme.QbGreenPrimary
import com.breakingthebot.qbinvoicing.ui.viewmodel.MainViewModel
import com.breakingthebot.qbinvoicing.ui.viewmodel.UiState

@Composable
fun InvoicesScreen(
    viewModel: MainViewModel,
    modifier: Modifier = Modifier
) {
    val invoicesState by viewModel.invoicesState.collectAsState()
    val selectedFilter by viewModel.selectedFilter.collectAsState()
    var searchQuery by remember { mutableStateOf("") }
    var payingInvoice by remember { mutableStateOf<InvoiceDto?>(null) }

    val filterOptions = listOf("ALL", "PENDING", "PARTIAL", "PAID", "OVERDUE", "VOIDED")

    if (payingInvoice != null) {
        RecordPaymentDialog(
            invoice = payingInvoice!!,
            onDismiss = { payingInvoice = null },
            onConfirm = { amount, method, ref ->
                val invId = payingInvoice!!.qboInvoiceId
                payingInvoice = null
                viewModel.recordPayment(invId, amount, method, ref) { _, _ -> }
            }
        )
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        // Search Bar
        OutlinedTextField(
            value = searchQuery,
            onValueChange = { searchQuery = it },
            placeholder = { Text("Search by invoice # or customer") },
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
            singleLine = true,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth()
        )

        Spacer(modifier = Modifier.height(12.dp))

        // Status Filter Chips
        LazyRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            items(filterOptions) { status ->
                FilterChip(
                    selected = selectedFilter == status,
                    onClick = { viewModel.setFilter(status) },
                    label = { Text(status, fontSize = 12.sp) },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = QbGreenPrimary.copy(alpha = 0.15f),
                        selectedLabelColor = QbGreenPrimary
                    )
                )
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Invoices List
        when (val state = invoicesState) {
            is UiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(32.dp),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator(color = QbGreenPrimary)
                }
            }
            is UiState.Success -> {
                val filtered = state.data.filter { inv ->
                    searchQuery.isBlank() ||
                            inv.docNumber.contains(searchQuery, ignoreCase = true) ||
                            inv.customerName.contains(searchQuery, ignoreCase = true) ||
                            (inv.orderId?.contains(searchQuery, ignoreCase = true) == true)
                }

                if (filtered.isEmpty()) {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(32.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = if (searchQuery.isNotBlank()) "No invoices match '$searchQuery'" else "No invoices found for status '$selectedFilter'",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                        )
                    }
                } else {
                    LazyColumn(
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                        modifier = Modifier.fillMaxSize()
                    ) {
                        items(filtered, key = { it.qboInvoiceId }) { invoice ->
                            InvoiceCard(
                                invoice = invoice,
                                onRecordPayment = { payingInvoice = invoice }
                            )
                        }
                    }
                }
            }
            is UiState.Error -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(32.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            text = "Error: ${state.message}",
                            color = MaterialTheme.colorScheme.error
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Button(onClick = { viewModel.refreshAll() }) {
                            Text("Retry")
                        }
                    }
                }
            }
            else -> {}
        }
    }
}

@Composable
fun InvoiceCard(
    invoice: InvoiceDto,
    onRecordPayment: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(
            modifier = Modifier
                .padding(14.dp)
                .fillMaxWidth()
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = invoice.docNumber,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "QBO ID: ${invoice.qboInvoiceId} • Order: ${invoice.orderId ?: "N/A"}",
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                    )
                }
                StatusBadge(status = invoice.paymentStatus)
            }

            Spacer(modifier = Modifier.height(8.dp))
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f))
            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text(
                        text = invoice.customerName,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold
                    )
                    Text(
                        text = invoice.customerEmail ?: "",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Due: ${invoice.dueDate}",
                        style = MaterialTheme.typography.labelSmall,
                        color = if (invoice.paymentStatus == "OVERDUE") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
                    )
                }

                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = formatCurrency(invoice.totalAmount),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    if (invoice.balanceDue > 0) {
                        Text(
                            text = "Bal: ${formatCurrency(invoice.balanceDue)}",
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.SemiBold,
                            color = MaterialTheme.colorScheme.primary
                        )
                    } else {
                        Text(
                            text = "Paid in full",
                            style = MaterialTheme.typography.labelSmall,
                            color = QbGreenPrimary
                        )
                    }
                }
            }

            if (invoice.balanceDue > 0 && invoice.paymentStatus != "VOIDED") {
                Spacer(modifier = Modifier.height(10.dp))
                Button(
                    onClick = onRecordPayment,
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = QbGreenPrimary),
                    contentPadding = PaddingValues(vertical = 8.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Payment,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("Record Payment", fontSize = 13.sp)
                }
            }
        }
    }
}

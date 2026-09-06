package com.breakingthebot.qbinvoicing.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
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
import com.breakingthebot.qbinvoicing.data.model.CreateOrderItemDto
import com.breakingthebot.qbinvoicing.ui.components.formatCurrency
import com.breakingthebot.qbinvoicing.ui.theme.QbGreenPrimary
import com.breakingthebot.qbinvoicing.ui.theme.QbNavyPrimary
import com.breakingthebot.qbinvoicing.ui.viewmodel.MainViewModel

data class DraftItem(
    val id: String = java.util.UUID.randomUUID().toString(),
    var name: String = "",
    var unitPrice: String = "",
    var quantity: String = "1"
)

@Composable
fun CreateInvoiceScreen(
    viewModel: MainViewModel,
    onInvoiceCreated: () -> Unit,
    modifier: Modifier = Modifier
) {
    var customerName by remember { mutableStateOf("Acme Corp") }
    var customerEmail by remember { mutableStateOf("billing@acmecorp.com") }
    var orderId by remember { mutableStateOf("MOB-${(System.currentTimeMillis() % 10000)}") }
    var paymentTermsDays by remember { mutableStateOf(30) }
    var taxRateText by remember { mutableStateOf("8.5") }
    var shippingFeeText by remember { mutableStateOf("15.00") }
    var isSubmitting by remember { mutableStateOf(false) }
    var errorBanner by remember { mutableStateOf<String?>(null) }

    var draftItems by remember {
        mutableStateOf(
            listOf(
                DraftItem(name = "Professional Consulting Services", unitPrice = "350.00", quantity = "2"),
                DraftItem(name = "Cloud Deployment Setup", unitPrice = "500.00", quantity = "1")
            )
        )
    }

    // Math calculations
    val subtotal = draftItems.sumOf { item ->
        val price = item.unitPrice.toDoubleOrNull() ?: 0.0
        val qty = item.quantity.toDoubleOrNull() ?: 0.0
        price * qty
    }
    val taxRate = (taxRateText.toDoubleOrNull() ?: 0.0) / 100.0
    val taxAmount = subtotal * taxRate
    val shipping = shippingFeeText.toDoubleOrNull() ?: 0.0
    val grandTotal = subtotal + taxAmount + shipping

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            Text(
                text = "Create QBO Invoice",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold
            )
            Text(
                text = "Generate and synchronize an invoice directly to QuickBooks Online Accounting API v3.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
            )
        }

        if (errorBanner != null) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)
                ) {
                    Text(
                        text = errorBanner!!,
                        modifier = Modifier.padding(12.dp),
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        fontSize = 13.sp
                    )
                }
            }
        }

        // Customer Info Card
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Column(
                    modifier = Modifier
                        .padding(16.dp)
                        .fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Text(
                        text = "Customer Details",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold
                    )

                    OutlinedTextField(
                        value = customerName,
                        onValueChange = { customerName = it },
                        label = { Text("Customer / Business Name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    OutlinedTextField(
                        value = customerEmail,
                        onValueChange = { customerEmail = it },
                        label = { Text("Customer Email") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        OutlinedTextField(
                            value = orderId,
                            onValueChange = { orderId = it },
                            label = { Text("Order ID") },
                            singleLine = true,
                            modifier = Modifier.weight(1f)
                        )

                        Column(modifier = Modifier.weight(1f)) {
                            Text("Terms:", style = MaterialTheme.typography.labelSmall)
                            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                listOf(15, 30, 60).forEach { days ->
                                    FilterChip(
                                        selected = paymentTermsDays == days,
                                        onClick = { paymentTermsDays = days },
                                        label = { Text("Net $days", fontSize = 11.sp) }
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        // Line Items Repeater
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Line Items",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold
                )
                TextButton(
                    onClick = {
                        draftItems = draftItems + DraftItem(name = "", unitPrice = "0.00", quantity = "1")
                    }
                ) {
                    Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Add Row")
                }
            }
        }

        items(draftItems.size) { index ->
            val item = draftItems[index]
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(8.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))
            ) {
                Column(
                    modifier = Modifier
                        .padding(12.dp)
                        .fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "Item #${index + 1}",
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 12.sp
                        )
                        if (draftItems.size > 1) {
                            IconButton(
                                onClick = {
                                    draftItems = draftItems.toMutableList().apply { removeAt(index) }
                                },
                                modifier = Modifier.size(24.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Delete,
                                    contentDescription = "Remove",
                                    tint = MaterialTheme.colorScheme.error,
                                    modifier = Modifier.size(16.dp)
                                )
                            }
                        }
                    }

                    OutlinedTextField(
                        value = item.name,
                        onValueChange = { newName ->
                            draftItems = draftItems.toMutableList().apply {
                                this[index] = this[index].copy(name = newName)
                            }
                        },
                        label = { Text("Item Description") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        OutlinedTextField(
                            value = item.unitPrice,
                            onValueChange = { newPrice ->
                                draftItems = draftItems.toMutableList().apply {
                                    this[index] = this[index].copy(unitPrice = newPrice)
                                }
                            },
                            label = { Text("Unit Price ($)") },
                            singleLine = true,
                            modifier = Modifier.weight(1f)
                        )
                        OutlinedTextField(
                            value = item.quantity,
                            onValueChange = { newQty ->
                                draftItems = draftItems.toMutableList().apply {
                                    this[index] = this[index].copy(quantity = newQty)
                                }
                            },
                            label = { Text("Quantity") },
                            singleLine = true,
                            modifier = Modifier.weight(1f)
                        )
                    }
                }
            }
        }

        // Adjustments: Tax & Shipping
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Row(
                    modifier = Modifier
                        .padding(16.dp)
                        .fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    OutlinedTextField(
                        value = taxRateText,
                        onValueChange = { taxRateText = it },
                        label = { Text("Tax Rate (%)") },
                        singleLine = true,
                        modifier = Modifier.weight(1f)
                    )
                    OutlinedTextField(
                        value = shippingFeeText,
                        onValueChange = { shippingFeeText = it },
                        label = { Text("Shipping Fee ($)") },
                        singleLine = true,
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }

        // Totals & Submit
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = QbNavyPrimary)
            ) {
                Column(
                    modifier = Modifier
                        .padding(16.dp)
                        .fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("Subtotal:", color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.8f))
                        Text(formatCurrency(subtotal), color = MaterialTheme.colorScheme.onPrimary)
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("Estimated Tax (${taxRateText}%):", color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.8f))
                        Text(formatCurrency(taxAmount), color = MaterialTheme.colorScheme.onPrimary)
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("Shipping:", color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.8f))
                        Text(formatCurrency(shipping), color = MaterialTheme.colorScheme.onPrimary)
                    }
                    HorizontalDivider(modifier = Modifier.padding(vertical = 6.dp), color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.2f))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("Total Amount Due:", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onPrimary)
                        Text(formatCurrency(grandTotal), fontWeight = FontWeight.Bold, fontSize = 18.sp, color = QbGreenPrimary)
                    }

                    Spacer(modifier = Modifier.height(10.dp))

                    Button(
                        onClick = {
                            if (customerName.isBlank()) {
                                errorBanner = "Please specify a customer name"
                                return@Button
                            }
                            val items = draftItems.mapIndexed { idx, it ->
                                CreateOrderItemDto(
                                    itemId = "ITEM-${idx + 1}",
                                    name = it.name.ifBlank { "Line Item ${idx + 1}" },
                                    unitPrice = it.unitPrice.toDoubleOrNull() ?: 0.0,
                                    quantity = it.quantity.toDoubleOrNull() ?: 1.0
                                )
                            }
                            isSubmitting = true
                            errorBanner = null
                            viewModel.createInvoice(
                                orderId = orderId,
                                customerName = customerName,
                                customerEmail = customerEmail,
                                items = items,
                                taxRate = (taxRateText.toDoubleOrNull() ?: 0.0) / 100.0,
                                shippingFee = shipping,
                                paymentTermsDays = paymentTermsDays
                            ) { success, msg ->
                                isSubmitting = false
                                if (success) {
                                    onInvoiceCreated()
                                } else {
                                    errorBanner = msg
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = QbGreenPrimary),
                        enabled = !isSubmitting
                    ) {
                        if (isSubmitting) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                strokeWidth = 2.dp,
                                color = MaterialTheme.colorScheme.onPrimary
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Generating Invoice...")
                        } else {
                            Text("Generate QBO Invoice", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }

        item {
            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}

package com.breakingthebot.qbinvoicing.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.breakingthebot.qbinvoicing.ui.components.AgingBucketCard
import com.breakingthebot.qbinvoicing.ui.components.MetricCard
import com.breakingthebot.qbinvoicing.ui.theme.*
import com.breakingthebot.qbinvoicing.ui.viewmodel.MainViewModel
import com.breakingthebot.qbinvoicing.ui.viewmodel.UiState

@Composable
fun DashboardScreen(
    viewModel: MainViewModel,
    onNavigateToNewInvoice: () -> Unit,
    modifier: Modifier = Modifier
) {
    val metricsState by viewModel.metricsState.collectAsState()
    val agingState by viewModel.agingReportState.collectAsState()
    val isDunningRunning by viewModel.isDunningRunning.collectAsState()
    val serverUrl by viewModel.serverUrl.collectAsState()

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Server Endpoint Indicator Chip
        item {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(8.dp)
                            .clip(RoundedCornerShape(4.dp))
                            .background(QbGreenPrimary)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "Connected: $serverUrl",
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                IconButton(
                    onClick = { viewModel.refreshAll() },
                    modifier = Modifier.size(24.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Refresh,
                        contentDescription = "Refresh",
                        modifier = Modifier.size(16.dp)
                    )
                }
            }
        }

        // Financial KPIs Header
        item {
            Text(
                text = "Financial Metrics",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )
        }

        // Metrics Grid
        when (val state = metricsState) {
            is UiState.Loading -> {
                item {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(140.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(color = QbGreenPrimary)
                    }
                }
            }
            is UiState.Success -> {
                val m = state.data
                item {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        MetricCard(
                            title = "Total Invoiced",
                            amount = m.totalInvoiced,
                            count = m.totalInvoicesCount,
                            accentColor = QbNavyPrimary,
                            icon = Icons.AutoMirrored.Filled.ReceiptLong,
                            modifier = Modifier.weight(1f)
                        )
                        MetricCard(
                            title = "Collected Revenue",
                            amount = m.totalCollected,
                            count = m.countByStatus["PAID"] ?: 0,
                            accentColor = StatusPaid,
                            icon = Icons.Default.CheckCircle,
                            modifier = Modifier.weight(1f)
                        )
                    }
                }
                item {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        MetricCard(
                            title = "Outstanding",
                            amount = m.totalOutstanding,
                            count = (m.countByStatus["PENDING"] ?: 0) + (m.countByStatus["PARTIAL"] ?: 0),
                            accentColor = StatusPending,
                            icon = Icons.Default.Schedule,
                            modifier = Modifier.weight(1f)
                        )
                        MetricCard(
                            title = "Overdue",
                            amount = m.totalOverdue,
                            count = m.countByStatus["OVERDUE"] ?: 0,
                            accentColor = StatusOverdue,
                            icon = Icons.Default.Warning,
                            modifier = Modifier.weight(1f)
                        )
                    }
                }
            }
            is UiState.Error -> {
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)
                    ) {
                        Text(
                            text = "Error loading metrics: ${state.message}",
                            modifier = Modifier.padding(16.dp),
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                    }
                }
            }
            else -> {}
        }

        // Accounts Receivable Aging Section
        item {
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "A/R Aging Schedule",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
            }
        }

        when (val state = agingState) {
            is UiState.Loading -> {
                item {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = QbGreenPrimary)
                }
            }
            is UiState.Success -> {
                item {
                    LazyRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        items(state.data.buckets) { bucket ->
                            AgingBucketCard(
                                bucket = bucket,
                                modifier = Modifier.width(130.dp)
                            )
                        }
                    }
                }
            }
            is UiState.Error -> {
                item {
                    Text(
                        text = "Unable to load aging buckets: ${state.message}",
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
            else -> {}
        }

        // Quick Actions & Dunning Escalation Button
        item {
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Quick Actions",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Button(
                        onClick = onNavigateToNewInvoice,
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = QbGreenPrimary)
                    ) {
                        Icon(imageVector = Icons.Default.Add, contentDescription = null)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Create New Invoice", fontWeight = FontWeight.Bold)
                    }

                    OutlinedButton(
                        onClick = { viewModel.runDunningEscalation(force = false) },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isDunningRunning
                    ) {
                        if (isDunningRunning) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                strokeWidth = 2.dp,
                                color = QbNavyPrimary
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Running Escalation...")
                        } else {
                            Icon(
                                imageVector = Icons.AutoMirrored.Filled.Send,
                                contentDescription = null,
                                tint = QbNavyPrimary
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Run Dunning Escalation", color = QbNavyPrimary, fontWeight = FontWeight.SemiBold)
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

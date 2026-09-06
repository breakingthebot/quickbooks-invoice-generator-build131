package com.breakingthebot.qbinvoicing.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
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
import com.breakingthebot.qbinvoicing.data.model.DunningRecordDto
import com.breakingthebot.qbinvoicing.data.model.WebhookEventDto
import com.breakingthebot.qbinvoicing.ui.components.formatCurrency
import com.breakingthebot.qbinvoicing.ui.theme.*
import com.breakingthebot.qbinvoicing.ui.viewmodel.MainViewModel
import com.breakingthebot.qbinvoicing.ui.viewmodel.UiState

@Composable
fun ActivityScreen(
    viewModel: MainViewModel,
    modifier: Modifier = Modifier
) {
    var selectedTab by remember { mutableStateOf(0) }
    val dunningState by viewModel.dunningHistoryState.collectAsState()
    val webhooksState by viewModel.webhooksState.collectAsState()

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        TabRow(selectedTabIndex = selectedTab) {
            Tab(
                selected = selectedTab == 0,
                onClick = {
                    selectedTab = 0
                    viewModel.fetchDunningHistory()
                },
                text = { Text("Dunning Notices") },
                icon = { Icon(Icons.Default.MailOutline, contentDescription = null, modifier = Modifier.size(16.dp)) }
            )
            Tab(
                selected = selectedTab == 1,
                onClick = {
                    selectedTab = 1
                    viewModel.fetchWebhooks()
                },
                text = { Text("QBO Webhooks") },
                icon = { Icon(Icons.Default.SyncAlt, contentDescription = null, modifier = Modifier.size(16.dp)) }
            )
        }

        Spacer(modifier = Modifier.height(12.dp))

        when (selectedTab) {
            0 -> DunningHistoryList(dunningState)
            1 -> WebhookEventsList(webhooksState)
        }
    }
}

@Composable
fun DunningHistoryList(state: UiState<List<DunningRecordDto>>) {
    when (state) {
        is UiState.Loading -> {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = QbGreenPrimary)
            }
        }
        is UiState.Success -> {
            if (state.data.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No dunning notices recorded yet.", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                }
            } else {
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    modifier = Modifier.fillMaxSize()
                ) {
                    items(state.data, key = { it.id }) { notice ->
                        DunningNoticeCard(notice)
                    }
                }
            }
        }
        is UiState.Error -> {
            Text("Error: ${state.message}", color = MaterialTheme.colorScheme.error)
        }
        else -> {}
    }
}

@Composable
fun DunningNoticeCard(notice: DunningRecordDto) {
    val tierColor = when (notice.escalationLevel) {
        1 -> SeverityLow
        2 -> SeverityMedium
        3 -> SeverityHigh
        4 -> SeverityCritical
        else -> SeverityCurrent
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(10.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
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
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(6.dp))
                            .background(tierColor.copy(alpha = 0.15f))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = "Tier ${notice.escalationLevel}: ${notice.levelName}",
                            color = tierColor,
                            fontWeight = FontWeight.Bold,
                            fontSize = 10.sp
                        )
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(text = notice.docNumber, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                }
                Text(
                    text = "${notice.daysOverdue}d overdue",
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.error,
                    fontWeight = FontWeight.SemiBold
                )
            }

            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = "${notice.customerName} (${notice.customerEmail})",
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.Medium
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = notice.subject,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
            )

            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "Balance: ${formatCurrency(notice.balanceDue)}",
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = QbNavyPrimary
                )
                Text(
                    text = notice.sentAt.take(19).replace("T", " "),
                    fontSize = 10.sp,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f)
                )
            }
        }
    }
}

@Composable
fun WebhookEventsList(state: UiState<List<WebhookEventDto>>) {
    when (state) {
        is UiState.Loading -> {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = QbGreenPrimary)
            }
        }
        is UiState.Success -> {
            if (state.data.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No webhook notifications received yet.", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                }
            } else {
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    modifier = Modifier.fillMaxSize()
                ) {
                    items(state.data, key = { it.id }) { event ->
                        WebhookEventCard(event)
                    }
                }
            }
        }
        is UiState.Error -> {
            Text("Error: ${state.message}", color = MaterialTheme.colorScheme.error)
        }
        else -> {}
    }
}

@Composable
fun WebhookEventCard(event: WebhookEventDto) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(10.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
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
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(6.dp))
                            .background(QbGreenPrimary.copy(alpha = 0.15f))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = "${event.entityName}.${event.operation}",
                            color = QbGreenDark,
                            fontWeight = FontWeight.Bold,
                            fontSize = 11.sp
                        )
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(text = "ID: ${event.entityId}", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                }

                Text(
                    text = if (event.processed) "Processed" else "Pending",
                    fontSize = 10.sp,
                    color = if (event.processed) QbGreenPrimary else StatusPending,
                    fontWeight = FontWeight.Bold
                )
            }

            if (!event.resultSummary.isNullOrBlank()) {
                Spacer(modifier = Modifier.height(6.dp))
                Text(
                    text = event.resultSummary,
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f)
                )
            }

            Spacer(modifier = Modifier.height(6.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "Realm: ${event.realmId}",
                    fontSize = 10.sp,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f)
                )
                Text(
                    text = event.eventDate.take(19).replace("T", " "),
                    fontSize = 10.sp,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f)
                )
            }
        }
    }
}

package com.breakingthebot.qbinvoicing

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.breakingthebot.qbinvoicing.ui.components.ServerSettingsDialog
import com.breakingthebot.qbinvoicing.ui.screens.*
import com.breakingthebot.qbinvoicing.ui.theme.*
import com.breakingthebot.qbinvoicing.ui.viewmodel.MainViewModel

enum class NavigationItem(val label: String, val icon: ImageVector) {
    DASHBOARD("Dashboard", Icons.Default.Dashboard),
    INVOICES("Invoices", Icons.AutoMirrored.Filled.ReceiptLong),
    NEW_INVOICE("New Invoice", Icons.Default.AddCircleOutline),
    ACTIVITY("Activity", Icons.Default.NotificationsNone)
}

class MainActivity : ComponentActivity() {

    private val viewModel: MainViewModel by viewModels()

    @OptIn(ExperimentalMaterial3Api::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            QbInvoicingTheme {
                var currentTab by remember { mutableStateOf(NavigationItem.DASHBOARD) }
                var showServerConfigDialog by remember { mutableStateOf(false) }
                val snackbarHostState = remember { SnackbarHostState() }
                val actionMessage by viewModel.actionMessage.collectAsState()
                val serverUrl by viewModel.serverUrl.collectAsState()

                // Show snackbar when actionMessage updates
                LaunchedEffect(actionMessage) {
                    actionMessage?.let {
                        snackbarHostState.showSnackbar(it)
                        viewModel.clearActionMessage()
                    }
                }

                if (showServerConfigDialog) {
                    ServerSettingsDialog(
                        currentUrl = serverUrl,
                        onDismiss = { showServerConfigDialog = false },
                        onSave = { newUrl ->
                            viewModel.updateServerUrl(newUrl)
                            showServerConfigDialog = false
                        }
                    )
                }

                Scaffold(
                    topBar = {
                        TopAppBar(
                            title = {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(
                                        imageVector = Icons.Default.AccountBalance,
                                        contentDescription = null,
                                        tint = QbGreenPrimary,
                                        modifier = Modifier.size(24.dp)
                                    )
                                    Spacer(modifier = Modifier.width(10.dp))
                                    Column {
                                        Text(
                                            text = "QuickBooks Invoicing",
                                            style = MaterialTheme.typography.titleMedium,
                                            fontWeight = FontWeight.Bold,
                                            color = QbNavyPrimary
                                        )
                                        Text(
                                            text = "v1.4.0 • Enterprise Mobile Client",
                                            fontSize = 10.sp,
                                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f)
                                        )
                                    }
                                }
                            },
                            actions = {
                                IconButton(onClick = { viewModel.refreshAll() }) {
                                    Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = QbNavyPrimary)
                                }
                                IconButton(onClick = { showServerConfigDialog = true }) {
                                    Icon(Icons.Default.Settings, contentDescription = "Server Settings", tint = QbNavyPrimary)
                                }
                            },
                            colors = TopAppBarDefaults.topAppBarColors(
                                containerColor = MaterialTheme.colorScheme.surface
                            )
                        )
                    },
                    bottomBar = {
                        NavigationBar(
                            containerColor = MaterialTheme.colorScheme.surface,
                            tonalElevation = 8.dp
                        ) {
                            NavigationItem.values().forEach { item ->
                                NavigationBarItem(
                                    selected = currentTab == item,
                                    onClick = { currentTab = item },
                                    icon = { Icon(item.icon, contentDescription = item.label) },
                                    label = { Text(item.label, fontSize = 11.sp) },
                                    colors = NavigationBarItemDefaults.colors(
                                        selectedIconColor = QbGreenPrimary,
                                        selectedTextColor = QbGreenPrimary,
                                        indicatorColor = QbGreenLight
                                    )
                                )
                            }
                        }
                    },
                    snackbarHost = { SnackbarHost(snackbarHostState) }
                ) { innerPadding ->
                    Box(modifier = Modifier.padding(innerPadding)) {
                        when (currentTab) {
                            NavigationItem.DASHBOARD -> DashboardScreen(
                                viewModel = viewModel,
                                onNavigateToNewInvoice = { currentTab = NavigationItem.NEW_INVOICE }
                            )
                            NavigationItem.INVOICES -> InvoicesScreen(
                                viewModel = viewModel
                            )
                            NavigationItem.NEW_INVOICE -> CreateInvoiceScreen(
                                viewModel = viewModel,
                                onInvoiceCreated = {
                                    currentTab = NavigationItem.INVOICES
                                }
                            )
                            NavigationItem.ACTIVITY -> ActivityScreen(
                                viewModel = viewModel
                            )
                        }
                    }
                }
            }
        }
    }
}

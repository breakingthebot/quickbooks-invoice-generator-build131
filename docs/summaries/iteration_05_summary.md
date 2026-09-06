# Technical Summary: Iteration 05 (v1.4.0)

**Project**: QuickBooks Online Invoice Generator & Payment Status Tracker  
**Build**: 131  
**Version**: `v1.4.0`  
**Date**: 2026-09-05  
**Platform**: Android (Kotlin, Jetpack Compose, Material 3, Retrofit 2, Coroutines)  

---

## 1. Executive Summary

Iteration 5 expands the QuickBooks Online invoice generator and payment status tracker ecosystem into a native mobile platform with a high-performance Android application built in Kotlin. Utilizing modern Android architecture—Jetpack Compose, Material 3, Coroutines, StateFlow, ViewModel, and Retrofit 2—the mobile client offers enterprise accounting operators real-time oversight of financial metrics, overdue aging schedules, invoice ledger settlement, dynamic invoice creation, and automated dunning escalation directly from mobile devices.

---

## 2. Key Architecture & File Structure

```
android/
├── app/
│   ├── build.gradle.kts                   # AGP 8.9.1, Kotlin 2.0.21, Compose BOM, Retrofit, OkHttp
│   ├── proguard-rules.pro
│   └── src/
│       ├── main/
│       │   ├── AndroidManifest.xml        # Cleartext traffic, Internet & Network permissions
│       │   ├── res/
│       │   │   ├── values/strings.xml
│       │   │   └── xml/network_security_config.xml
│       │   └── java/com/breakingthebot/qbinvoicing/
│       │       ├── MainActivity.kt        # Compose Scaffold, TopAppBar, Bottom Navigation
│       │       ├── data/
│       │       │   ├── api/
│       │       │   │   ├── ApiClient.kt    # Retrofit client with dynamic base URL
│       │       │   │   └── QbApiService.kt # REST API endpoints definition
│       │       │   ├── model/
│       │       │   │   └── Models.kt       # DTOs: Invoice, Payment, Metrics, Aging, Dunning
│       │       │   └── repository/
│       │       │       └── QbRepository.kt # Coroutine repository with Result<T> wrapping
│       │       └── ui/
│       │           ├── components/
│       │           │   └── CommonComponents.kt # MetricCard, StatusBadge, Dialogs
│       │           ├── screens/
│       │           │   ├── DashboardScreen.kt     # Financial KPIs & A/R Aging Schedule
│       │           │   ├── InvoicesScreen.kt      # Search, status chips, payment dialog
│       │           │   ├── CreateInvoiceScreen.kt # Customer details, repeater, calculations
│       │           │   └── ActivityScreen.kt      # Dunning notices & Webhooks split feed
│       │           ├── theme/
│       │           │   ├── Color.kt        # QBO Green (#2CA01C) & Navy (#0D233A)
│       │           │   ├── Theme.kt        # Material 3 dynamic color scheme
│       │           │   └── Type.kt
│       │           └── viewmodel/
│       │               └── MainViewModel.kt # StateFlows and reactive UI actions
│       └── test/java/com/breakingthebot/qbinvoicing/
│           └── QbModelsTest.kt            # Unit tests for domain models & calculations
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties                      # JVM 2GB heap, AndroidX, JDK 17
├── gradlew & gradlew.bat
└── README.md                              # Mobile setup and architecture guide
```

---

## 3. Core Android Capabilities

1. **Reactive Financial Dashboard (`DashboardScreen.kt`)**:
   - Live KPI cards: Total Invoiced, Outstanding Receivables, Collected Revenue, and Overdue Balances.
   - Accounts Receivable Aging Schedule horizontal scroll: Current, 1–30d, 31–60d, 61–90d, and 90+d buckets with severity color badges.
   - One-touch "Run Dunning Escalation" action button with live progress spinner and snackbar notification.
   - Real-time connected server indicator showing active host.

2. **Invoice Ledger & Settlement (`InvoicesScreen.kt`)**:
   - Status filtering chips (`ALL`, `PENDING`, `PARTIAL`, `PAID`, `OVERDUE`, `VOIDED`).
   - Instant search field filtering by customer name, order number, or invoice document number.
   - Material 3 `RecordPaymentDialog` allowing settlement using Credit Card, Bank Transfer, Check, or Cash with reference numbers.

3. **Dynamic Invoice Generator (`CreateInvoiceScreen.kt`)**:
   - Customer metadata fields (name, email, order ID).
   - Configurable Net terms (15, 30, 60 days).
   - Interactive line items repeater allowing dynamic adding/removing of items with unit price and quantity.
   - Real-time calculation card computing Subtotal, Sales Tax %, Shipping Fee, and Total Due.
   - "Generate QBO Invoice" button submitting directly to FastAPI backend and Intuit QBO API v3.

4. **Audit Trail & Webhooks (`ActivityScreen.kt`)**:
   - Tab 1: Dunning Notices history with escalation level badges (Tier 1–4), customer info, overdue days, and timestamp.
   - Tab 2: Ingested QuickBooks Online Webhook events with entity name, operation, and processing status.

5. **Dynamic Backend Configuration (`ApiClient.kt` & `ServerSettingsDialog`)**:
   - In-app URL switcher enabling instant toggling between Android Emulator (`http://10.0.2.2:8000/`), local WiFi network (`http://192.168.x.x:8000/`), and public tunneling services (ngrok/Cloudflare).

---

## 4. Verification & Testing

- **Android Unit Tests**: 4 / 4 passed in `QbModelsTest` (`gradlew.bat testDebugUnitTest`, 53s).
- **Kotlin Compilation**: Clean compile with zero warnings using Compose 1.3 and Kotlin 2.0.21.
- **Python Test Suite**: 43 / 43 Pytest tests passing (8.16s).

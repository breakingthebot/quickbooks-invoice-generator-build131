# QuickBooks Online Mobile Client (Android)

[![Platform](https://img.shields.io/badge/Platform-Android-green.svg)](https://developer.android.com)
[![Kotlin](https://img.shields.io/badge/Kotlin-2.0.21-purple.svg)](https://kotlinlang.org)
[![Compose](https://img.shields.io/badge/Jetpack%20Compose-Material%203-blue.svg)](https://developer.android.com/jetpack/compose)
[![Retrofit](https://img.shields.io/badge/Networking-Retrofit%202-red.svg)](https://square.github.io/retrofit/)

A native Android mobile application for QuickBooks Online invoice management, real-time payment reconciliation, and automated dunning escalation tracking.

---

## Features

- **Executive Financial Dashboard**:
  - Live metric cards: Total Invoiced, Collected Revenue, Outstanding Receivables, and Overdue Balances.
  - Accounts Receivable Aging Schedule buckets: Current, 1–30d, 31–60d, 61–90d, and 90+d with severity indicators.
  - One-touch "Run Dunning Escalation" button with real-time feedback.
- **Invoice Ledger & Payment Settlement**:
  - Filter by status (`ALL`, `PENDING`, `PARTIAL`, `PAID`, `OVERDUE`, `VOIDED`).
  - Search invoices by customer name, order number, or document number.
  - One-click "Record Payment" dialog supporting `CreditCard`, `BankTransfer`, `Check`, and `Cash` with reference tracking.
- **Mobile Invoice Generator**:
  - Interactive invoice creation wizard with customer details, Net terms (15/30/60 days).
  - Dynamic line items repeater (add/remove item rows, unit price, quantity).
  - Live subtotal, tax %, and shipping calculation.
- **Activity & Audit Trail**:
  - Tabbed split feeds for dispatched dunning notices and cryptographic QuickBooks webhooks.
- **Configurable Backend Connection**:
  - In-app endpoint switcher: defaults to `http://10.0.2.2:8000/` for the standard Android emulator, with instant support for local network IPs (`http://192.168.x.x:8000/`) or public tunnels (e.g. ngrok).

---

## Architecture

```
android/
├── app/
│   ├── src/
│   │   ├── main/
│   │   │   ├── AndroidManifest.xml
│   │   │   ├── java/com/breakingthebot/qbinvoicing/
│   │   │   │   ├── MainActivity.kt
│   │   │   │   ├── data/
│   │   │   │   │   ├── api/
│   │   │   │   │   │   ├── ApiClient.kt        # Retrofit singleton & base URL config
│   │   │   │   │   │   └── QbApiService.kt     # REST API endpoint definitions
│   │   │   │   │   ├── model/
│   │   │   │   │   │   └── Models.kt           # Domain DTOs
│   │   │   │   │   └── repository/
│   │   │   │   │       └── QbRepository.kt     # Safe Coroutine data repository
│   │   │   │   └── ui/
│   │   │   │       ├── components/
│   │   │   │       │   └── CommonComponents.kt # MetricCard, StatusBadge, Dialogs
│   │   │   │       ├── screens/
│   │   │   │       │   ├── DashboardScreen.kt
│   │   │   │       │   ├── InvoicesScreen.kt
│   │   │   │       │   ├── CreateInvoiceScreen.kt
│   │   │   │       │   └── ActivityScreen.kt
│   │   │   │       ├── theme/
│   │   │   │       │   ├── Color.kt            # QuickBooks Green / Navy palette
│   │   │   │       │   ├── Theme.kt            # Material 3 dynamic theme
│   │   │   │       │   └── Type.kt
│   │   │   │       └── viewmodel/
│   │   │   │           └── MainViewModel.kt    # StateFlow and business logic
│   │   │   └── res/
│   │   └── test/
│   │       └── java/com/breakingthebot/qbinvoicing/
│   │           └── QbModelsTest.kt
│   └── build.gradle.kts
├── gradle/wrapper/
├── build.gradle.kts
├── settings.gradle.kts
└── gradle.properties
```

---

## Getting Started

### 1. Start the Python Backend
Ensure the FastAPI service is running:
```bash
qb-invoicing serve --host 0.0.0.0 --port 8000
```

### 2. Open in Android Studio
1. Open **Android Studio** (Koala / Ladybug or newer).
2. Click **File -> Open** and select the `android/` directory inside this repository.
3. Allow Gradle to sync.
4. Select an Android Emulator or physical device running Android 7.0+ (API 24+).
5. Click **Run** (green play button).

### 3. Connecting to the Backend
* **Android Emulator**: Uses `http://10.0.2.2:8000/` automatically (already set as default).
* **Physical Device**: Tap the **Settings icon** in the top bar and enter your PC's local WiFi IP (e.g. `http://192.168.1.10:8000/`) or an ngrok tunnel URL (`https://your-tunnel.ngrok-free.app/`).

---

## Running Unit Tests

From the `android/` directory:
```bash
./gradlew testDebugUnitTest
```
Or on Windows:
```cmd
gradlew.bat testDebugUnitTest
```

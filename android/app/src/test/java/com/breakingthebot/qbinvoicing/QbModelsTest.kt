package com.breakingthebot.qbinvoicing

import com.breakingthebot.qbinvoicing.data.model.*
import org.junit.Assert.*
import org.junit.Test

class QbModelsTest {

    @Test
    fun testFinancialMetricsDefaults() {
        val metrics = FinancialMetricsDto(
            totalInvoiced = 1500.0,
            totalCollected = 500.0,
            totalOutstanding = 1000.0,
            totalOverdue = 250.0,
            countByStatus = mapOf("PAID" to 2, "PENDING" to 3, "OVERDUE" to 1),
            totalInvoicesCount = 6
        )

        assertEquals(1500.0, metrics.totalInvoiced, 0.001)
        assertEquals(500.0, metrics.totalCollected, 0.001)
        assertEquals(1000.0, metrics.totalOutstanding, 0.001)
        assertEquals(250.0, metrics.totalOverdue, 0.001)
        assertEquals(6, metrics.totalInvoicesCount)
        assertEquals(2, metrics.countByStatus["PAID"])
    }

    @Test
    fun testInvoiceDtoProperties() {
        val invoice = InvoiceDto(
            qboInvoiceId = "1001",
            orderId = "ORD-99",
            docNumber = "INV-2026-001",
            customerName = "Acme Corp",
            customerEmail = "billing@acmecorp.com",
            txnDate = "2026-09-01",
            dueDate = "2026-10-01",
            totalAmount = 650.00,
            balanceDue = 350.00,
            paymentStatus = "PARTIAL"
        )

        assertEquals("INV-2026-001", invoice.docNumber)
        assertEquals("PARTIAL", invoice.paymentStatus)
        assertEquals(350.00, invoice.balanceDue, 0.001)
        assertTrue(invoice.balanceDue < invoice.totalAmount)
    }

    @Test
    fun testAgingBucketSeverity() {
        val currentBucket = AgingBucketDto(
            bucketName = "Current",
            minDays = 0,
            maxDays = 0,
            invoiceCount = 5,
            totalBalance = 1200.0,
            severity = "current"
        )
        assertEquals("Current", currentBucket.bucketName)
        assertEquals(0, currentBucket.minDays)
        assertEquals(5, currentBucket.invoiceCount)

        val criticalBucket = AgingBucketDto(
            bucketName = "90+ Days",
            minDays = 91,
            maxDays = null,
            invoiceCount = 2,
            totalBalance = 800.0,
            severity = "critical"
        )
        assertNull(criticalBucket.maxDays)
        assertEquals("critical", criticalBucket.severity)
    }

    @Test
    fun testCreateOrderPayload() {
        val items = listOf(
            CreateOrderItemDto(name = "Item 1", unitPrice = 100.0, quantity = 2.0),
            CreateOrderItemDto(name = "Item 2", unitPrice = 50.0, quantity = 1.0)
        )
        val request = CreateOrderRequestDto(
            orderId = "MOB-1234",
            orderNumber = "MOB-1234",
            customer = CreateOrderCustomerDto(name = "Jane Doe", email = "jane@example.com"),
            items = items,
            taxRate = 0.08,
            shippingFee = 15.0
        )

        val subtotal = request.items.sumOf { it.unitPrice * it.quantity }
        val tax = subtotal * request.taxRate
        val total = subtotal + tax + request.shippingFee

        assertEquals(250.0, subtotal, 0.001)
        assertEquals(20.0, tax, 0.001)
        assertEquals(285.0, total, 0.001)
    }
}

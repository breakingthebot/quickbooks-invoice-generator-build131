package com.breakingthebot.qbinvoicing.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkColorScheme = darkColorScheme(
    primary = QbGreenPrimary,
    onPrimary = Color.White,
    primaryContainer = QbGreenDark,
    onPrimaryContainer = QbGreenLight,
    secondary = QbNavyPrimary,
    background = SurfaceDark,
    surface = CardDark,
    onBackground = Color(0xFFF1F5F9),
    onSurface = Color(0xFFF1F5F9),
)

private val LightColorScheme = lightColorScheme(
    primary = QbGreenPrimary,
    onPrimary = Color.White,
    primaryContainer = QbGreenLight,
    onPrimaryContainer = QbGreenDark,
    secondary = QbNavyPrimary,
    background = SurfaceLight,
    surface = CardLight,
    onBackground = Color(0xFF0F172A),
    onSurface = Color(0xFF0F172A),
)

@Composable
fun QbInvoicingTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}

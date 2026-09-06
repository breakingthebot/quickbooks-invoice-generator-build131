/*
 * Declares shared Gradle plugins for the QuickBooks Online Mobile Client.
 * Connects to: settings.gradle.kts and app/build.gradle.kts.
 */
plugins {
    id("com.android.application") version "8.9.1" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.serialization") version "2.0.21" apply false
}

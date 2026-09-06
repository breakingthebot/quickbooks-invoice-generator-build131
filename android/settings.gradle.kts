/*
 * Configures the Gradle modules and repositories for the QuickBooks Online Mobile Client.
 * Connects to: app/build.gradle.kts and root build.gradle.kts.
 */
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "QbInvoicingMobile"
include(":app")

# ProGuard rules for QuickBooks Online Mobile Client
-keepattributes *Annotation*
-keepclassmembers class * {
    @com.google.gson.annotations.SerializedName <fields>;
}

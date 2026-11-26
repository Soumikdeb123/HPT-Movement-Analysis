package au.edu.adelaide.hpt.hpt_player_analysis

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val permissionRequest = 4617
    private val resultId = 1
    private val progressId = 2
    private val manager get() = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
    private var notificationsChannel: MethodChannel? = null
    private var askingPermission = false
    private var pending: Notice? = null

    private data class Notice(
        val title: String, val body: String?, val ongoing: Boolean, val start: Boolean
    )

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        manager.cancel(progressId)
        notificationsChannel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger, "hpt/analysis_notifications"
        ).also { channel ->
            channel.setMethodCallHandler { call, result ->
                when (call.method) {
                    "show" -> {
                        val notice = Notice(
                            requireNotNull(call.argument<String>("title")),
                            call.argument<String>("body"),
                            call.argument<Boolean>("ongoing") == true,
                            call.argument<Boolean>("start") == true
                        )
                        showWhenAllowed(notice)
                        result.success(null)
                    }
                    "clearProgress" -> {
                        if (pending?.ongoing == true) pending = null
                        manager.cancel(progressId)
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
        }
    }

    private fun showWhenAllowed(notice: Notice) {
        if (notice.start) manager.cancel(resultId)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            if (notice.start && !askingPermission &&
                !shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS)
            ) {
                askingPermission = true
                requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), permissionRequest)
            }
            if (askingPermission) pending = notice
            return
        }
        pending = null
        post(notice)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != permissionRequest) return
        askingPermission = false
        val latest = pending
        pending = null
        if (latest != null && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            post(latest)
        }
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        notificationsChannel?.setMethodCallHandler(null)
        notificationsChannel = null
        pending = null
        askingPermission = false
        manager.cancel(progressId)
        super.cleanUpFlutterEngine(flutterEngine)
    }

    @Suppress("DEPRECATION")
    private fun post(notice: Notice) {
        val ongoing = notice.ongoing
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = if (ongoing) {
                NotificationChannel("analysis_progress", "Analysis progress", NotificationManager.IMPORTANCE_LOW)
            } else {
                NotificationChannel("analysis_results", "Analysis results", NotificationManager.IMPORTANCE_DEFAULT)
            }
            manager.createNotificationChannel(channel)
            Notification.Builder(this, channel.id)
        } else {
            Notification.Builder(this).apply {
                if (ongoing) setPriority(Notification.PRIORITY_LOW) else setDefaults(Notification.DEFAULT_ALL)
            }
        }
        val intent = Intent(this, MainActivity::class.java).apply {
            action = Intent.ACTION_MAIN
            addCategory(Intent.CATEGORY_LAUNCHER)
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val openApp = PendingIntent.getActivity(
            this, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        builder.setSmallIcon(R.drawable.ic_analysis_notification)
            .setContentTitle(notice.title)
            .setContentText(notice.body)
            .setContentIntent(openApp)
            .setOnlyAlertOnce(ongoing)
            .setOngoing(ongoing)
            .setAutoCancel(!ongoing)
        if (notice.start) builder.setProgress(0, 0, true)
        if (!ongoing) {
            manager.cancel(progressId)
        }
        manager.notify(if (ongoing) progressId else resultId, builder.build())
    }
}

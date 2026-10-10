package com.attempt1.lifefirstapp; // Ensure this matches your package structure

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.core.app.NotificationCompat;
import androidx.work.Constraints;
import androidx.work.Data;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.WorkManager;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

// Import your worker classes (adjust package if needed)
import com.attempt1.lifefirstapp.workers.FcmDataWorker;
import com.attempt1.lifefirstapp.workers.TokenUploadWorker;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public class MyFirebaseMessagingService extends FirebaseMessagingService {

    private static final String TAG = "MyFirebaseMsgService";
    private final AtomicInteger notificationIdGenerator = new AtomicInteger(0);

    public static final String FCM_PREFS_NAME = "FCM_Prefs";
    public static final String PREF_KEY_FCM_TOKEN = "fcm_last_known_token";
    public static final String PREF_KEY_TOKEN_SENT_SUCCESSFULLY = "fcm_token_sent_successfully";

    private static final String TOKEN_UPLOAD_WORK_TAG = "TokenUploadWork"; // For unique work
    private static final String FCM_MESSAGE_PROCESSING_WORK_TAG = "FcmMessageProcessingWork";

    @Override
    public void onNewToken(@NonNull String token) {
        Log.i(TAG, "New FCM token received: " + token);

        SharedPreferences prefs = getApplicationContext().getSharedPreferences(FCM_PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit()
                .putString(PREF_KEY_FCM_TOKEN, token)
                .putBoolean(PREF_KEY_TOKEN_SENT_SUCCESSFULLY, false)
                .apply();
        Log.d(TAG, "Stored new token locally, marked as not sent.");

        sendTokenToServerWork(getApplicationContext(), token);
    }

    @Override
    public void onMessageReceived(@NonNull RemoteMessage remoteMessage) {
        Log.d(TAG, "From: " + remoteMessage.getFrom());

        // Fixed syntax error: removed misplaced quote
        if (remoteMessage.getData() != null && !remoteMessage.getData().isEmpty()) {
            Log.d(TAG, "Message data payload: " + remoteMessage.getData());
            scheduleDataProcessingJob(remoteMessage.getData());
        }

        if (remoteMessage.getNotification() != null) {
            String title = remoteMessage.getNotification().getTitle();
            String body = remoteMessage.getNotification().getBody();

            Log.i(TAG, "Message Notification Title: " + (title != null ? title : "N/A"));
            Log.i(TAG, "Message Notification Body: " + (body != null ? body : "N/A"));

            sendNotification(title, body, remoteMessage.getData());
        }
    }

    private void scheduleDataProcessingJob(Map<String, String> dataMap) {
        Data.Builder dataBuilder = new Data.Builder();
        for (Map.Entry<String, String> entry : dataMap.entrySet()) {
            dataBuilder.putString(entry.getKey(), entry.getValue());
        }

        OneTimeWorkRequest fcmDataWorkRequest =
                new OneTimeWorkRequest.Builder(FcmDataWorker.class)
                        .setInputData(dataBuilder.build())
                        .addTag(FCM_MESSAGE_PROCESSING_WORK_TAG + "_" + System.currentTimeMillis())
                        .build();

        WorkManager.getInstance(getApplicationContext()).enqueue(fcmDataWorkRequest);
        Log.d(TAG, "Scheduled FCM data processing job.");
    }

    public static void sendTokenToServerWork(@NonNull Context context, @NonNull String token) {
        Log.i(TAG, "Scheduling WorkManager job to upload token: " + token);

        Data inputData = new Data.Builder()
                .putString(TokenUploadWorker.KEY_FCM_TOKEN, token)
                .build();

        Constraints constraints = new Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build();

        String uniqueWorkName = TOKEN_UPLOAD_WORK_TAG + "_" + token;

        OneTimeWorkRequest tokenUploadWorkRequest =
                new OneTimeWorkRequest.Builder(TokenUploadWorker.class)
                        .setInputData(inputData)
                        .setConstraints(constraints)
                        .addTag(TOKEN_UPLOAD_WORK_TAG)
                        .build();

        WorkManager.getInstance(context.getApplicationContext())
                .enqueueUniqueWork(
                        uniqueWorkName,
                        ExistingWorkPolicy.REPLACE,
                        tokenUploadWorkRequest);

        Log.i(TAG, "WorkManager job enqueued for token: " + token + " with unique name: " + uniqueWorkName);
    }

    private void sendNotification(String messageTitle, String messageBody, Map<String, String> data) {
        Intent intent = new Intent(this, MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);

        if (data != null) {
            for (Map.Entry<String, String> entry : data.entrySet()) {
                intent.putExtra(entry.getKey(), entry.getValue());
            }
        }

        PendingIntent pendingIntent = PendingIntent.getActivity(
                this,
                notificationIdGenerator.incrementAndGet(), // Unique request code
                intent,
                PendingIntent.FLAG_ONE_SHOT | PendingIntent.FLAG_IMMUTABLE);

        String channelId = getString(R.string.default_notification_channel_id); // Define in strings.xml
        Uri defaultSoundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);

        NotificationCompat.Builder notificationBuilder =
                new NotificationCompat.Builder(this, channelId)
                        .setSmallIcon(R.drawable.ic_stat_notification) // Ensure this drawable exists
                        .setContentTitle(messageTitle != null ? messageTitle : getString(R.string.app_name)) // Default title
                        .setContentText(messageBody)
                        .setAutoCancel(true)
                        .setSound(defaultSoundUri)
                        .setContentIntent(pendingIntent)
                        .setPriority(NotificationCompat.PRIORITY_DEFAULT);

        NotificationManager notificationManager =
                (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);

        if (notificationManager == null) {
            Log.e(TAG, "NotificationManager service is not available.");
            return;
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            CharSequence name = getString(R.string.default_notification_channel_name);
            String description = getString(R.string.default_notification_channel_description);
            int importance = NotificationManager.IMPORTANCE_DEFAULT;
            NotificationChannel channel = new NotificationChannel(channelId, name, importance);
            channel.setDescription(description);

            notificationManager.createNotificationChannel(channel);
        }

        // Use a unique ID for each notification if you want to show multiple notifications
        notificationManager.notify(notificationIdGenerator.incrementAndGet(), notificationBuilder.build());
        Log.d(TAG, "Notification sent: " + (messageTitle != null ? messageTitle : "N/A"));

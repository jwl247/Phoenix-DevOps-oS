package com.attempt1.lifefirstapp;

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
import com.attempt1.lifefirstapp.workers.FcmDataWorker;
import com.attempt1.lifefirstapp.workers.TokenUploadWorker;

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

import java.util.Map;

public class MyFirebaseMessagingService extends FirebaseMessagingService {

    private static final String TAG = "MyFirebaseMsgService";

    // SharedPreferences constants for token management
    private static final String FCM_PREFS_NAME = "FCM_Prefs";
    private static final String PREF_KEY_FCM_TOKEN = "fcm_token";
    private static final String PREF_KEY_TOKEN_SENT_SUCCESSFULLY = "fcm_token_sent_successfully";

    // WorkManager constants
    private static final String TOKEN_UPLOAD_WORK_TAG = "TokenUploadWork";
    private static final String FCM_MESSAGE_PROCESSING_WORK_TAG = "FcmMessageProcessingWork";


    @Override
    public void onMessageReceived(@NonNull RemoteMessage remoteMessage) {
        Log.d(TAG, "From: " + remoteMessage.getFrom());

        // The data payload is always available.
        Map<String, String> data = remoteMessage.getData();
        if (!data.isEmpty()) {
            Log.d(TAG, "Message data payload: " + data);

            // Schedule a background job for any long-running processing.
            scheduleDataProcessingJob(data);

            // To handle notifications consistently, extract display info from the data payload.
            // Your server should send 'title' and 'body' inside the 'data' object.
            String title = data.get("title");
            String body = data.get("body");

            if (title != null && body != null) {
                sendNotification(title, body, data);
            }
        }
    }

    private void scheduleDataProcessingJob(Map<String, String> dataMap) {
        Data.Builder dataBuilder = new Data.Builder();
        for (Map.Entry<String, String> entry : dataMap.entrySet()) {
            dataBuilder.putString(entry.getKey(), entry.getValue());
        }

        OneTimeWorkRequest workRequest = new OneTimeWorkRequest.Builder(FcmDataWorker.class)
                .setInputData(dataBuilder.build())
                .addTag(FCM_MESSAGE_PROCESSING_WORK_TAG)
                .build();
        WorkManager.getInstance(getApplicationContext()).enqueue(workRequest);
        Log.d(TAG, "Scheduled FCM data processing job.");
    }

    @Override
    public void onNewToken(@NonNull String token) {
        Log.i(TAG, "New FCM token received: " + token);
        storeTokenLocally(token);
        sendTokenToServerWork(token);
    }

    private void storeTokenLocally(String token) {
        SharedPreferences prefs = getApplicationContext().getSharedPreferences(FCM_PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit()
                .putString(PREF_KEY_FCM_TOKEN, token)
                .putBoolean(PREF_KEY_TOKEN_SENT_SUCCESSFULLY, false) // Mark as not yet sent
                .apply();
        Log.d(TAG, "Token stored locally.");
    }

    /**
     * Schedules a WorkManager job to send the token to the server.
     * This is now an instance method to avoid static context access.
     */
    private void sendTokenToServerWork(String token) {
        Data inputData = new Data.Builder()
                .putString(TokenUploadWorker.KEY_FCM_TOKEN, token)
                .build();

        Constraints constraints = new Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build();

        OneTimeWorkRequest tokenUploadWorkRequest =
                new OneTimeWorkRequest.Builder(TokenUploadWorker.class)
                        .setInputData(inputData)
                        .setConstraints(constraints)
                        .addTag(TOKEN_UPLOAD_WORK_TAG)
                        .build();

        // Use getApplicationContext() from the service instance.
        WorkManager.getInstance(getApplicationContext())
                .enqueueUniqueWork(
                        TOKEN_UPLOAD_WORK_TAG,
                        ExistingWorkPolicy.REPLACE,
                        tokenUploadWorkRequest);

        Log.i(TAG, "WorkManager job scheduled to upload token.");
    }

    /**
     * Creates and displays a notification using the message data.
     */
    private void sendNotification(String messageTitle, String messageBody, Map<String, String> data) {
        Intent intent = new Intent(this, MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP);

        // Add data from FCM to intent extras to be used by MainActivity
        for (Map.Entry<String, String> entry : data.entrySet()) {
            intent.putExtra(entry.getKey(), entry.getValue());
        }

        // Use a fixed request code. The uniqueness of the PendingIntent is determined by the Intent.
        int requestCode = 0;
        PendingIntent pendingIntent = PendingIntent.getActivity(
                this,
                requestCode,
                intent,
                PendingIntent.FLAG_ONE_SHOT | PendingIntent.FLAG_IMMUTABLE
        );

        String channelId = getString(R.string.default_notification_channel_id);
        Uri defaultSoundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);

        NotificationCompat.Builder notificationBuilder =
                new NotificationCompat.Builder(this, channelId)
                        .setSmallIcon(R.drawable.ic_stat_notification) // Ensure this drawable exists
                        .setContentTitle(messageTitle)
                        .setContentText(messageBody)
                        .setAutoCancel(true)
                        .setSound(defaultSoundUri)
                        .setContentIntent(pendingIntent)
                        .setPriority(NotificationCompat.PRIORITY_DEFAULT);

        NotificationManager notificationManager =
                (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);




             if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                 CharSequence name = getString(R.string.default_notification_channel_name);
                 String description = getString(R.string.default_notification_channel_description);
                 int importance = NotificationManager.IMPORTANCE_DEFAULT;
                 NotificationChannel channel = new NotificationChannel(channelId, name, importance);
                 channel.setDescription(description);
                 notificationManager.createNotificationChannel(channel);
             }

        // Use a fixed ID to ensure this notification updates the previous one.
        // If you need to show multiple notifications, generate a unique but stable ID
        // from the message content itself.
        int notificationId = 1;
        notificationManager.notify(notificationId, notificationBuilder.build());
        Log.d(TAG, "Notification sent: " + messageTitle);
    }
}



package com.attempt1.lifefirstapp.workers

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.delay

class TokenUploadWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    companion object {
        const val KEY_FCM_TOKEN = "fcm_token"
        private const val TAG = "TokenUploadWorker"
    }

    override suspend fun doWork(): Result {
        // Retrieve the token from the input data
        val token = inputData.getString(KEY_FCM_TOKEN)

        if (token.isNullOrEmpty()) {
            Log.e(TAG, "FCM token is null or empty. Failing work.")
            return Result.failure()
        }

        return try {
            Log.d(TAG, "Uploading token to server: $token")

            // TODO: Replace this with your actual network call to your server.
            // This delay simulates a network request.
            delay(2000) // Simulate a 2-second network call

            // For this example, we'll assume the upload was successful.
            // In a real app, you would check the response from your server.
            val isSuccessful = true

            if (isSuccessful) {
                Log.i(TAG, "Token successfully uploaded to server.")
                Result.success()
            } else {
                Log.w(TAG, "Failed to upload token to server. Retrying...")
                Result.retry()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error uploading token", e)
            // If the network request fails due to an exception, retry the work.
            Result.retry()
        }
    }
}
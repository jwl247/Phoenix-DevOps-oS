// path: app/src/main/java/com/attempt1/lifefirstapp/FcmDataWorker.java

package com.attempt1.lifefirstapp.workers;

import android.content.Context;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import java.util.Map;

public class FcmDataWorker extends Worker {

    private static final String TAG = "FcmDataWorker";

    public FcmDataWorker(
            @NonNull Context context,
            @NonNull WorkerParameters workerParams) {
        super(context, workerParams);
    }

    @NonNull
    @Override
    public Result doWork() {
        // The data from the FCM message is in inputData.
        Map<String, Object> data = getInputData().getKeyValueMap();
        Log.d(TAG, "Processing data from FCM message: " + data);

        // TODO: Add your logic to process the data.
        // For example, you could sync content, update a local database, etc.

        return Result.success();
    }
}
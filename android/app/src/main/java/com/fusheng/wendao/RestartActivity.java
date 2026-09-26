package com.fusheng.wendao;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import android.view.Gravity;
import android.widget.TextView;

/** A separate short-lived process can restart Python with fresh DLC registrations. */
public class RestartActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        TextView label = new TextView(this);
        label.setText("正在重新展开山河…"); label.setTextSize(20); label.setGravity(Gravity.CENTER);
        setContentView(label);
        int oldPid = getIntent().getIntExtra("oldPid", -1);
        if (oldPid > 0 && oldPid != Process.myPid()) Process.killProcess(oldPid);
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            Intent launch = new Intent(this, MainActivity.class);
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
            startActivity(launch);
            finish();
        }, 600);
    }
}

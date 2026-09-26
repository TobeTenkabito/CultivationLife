package com.fusheng.wendao;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Process;
import android.view.Gravity;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Collections;

public class MainActivity extends Activity {
    private WebView web;
    private String origin;
    private boolean destroyed;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        showLoading("浮生问道\n正在展开山河绘卷…");
        new Thread(() -> {
            try {
                File bundle = new File(getCacheDir(), "game-assets.zip");
                String digest;
                try (InputStream in = getAssets().open("game-assets.sha256")) {
                    ByteArrayOutputStream data = new ByteArrayOutputStream();
                    byte[] chunk = new byte[4096]; int n;
                    while ((n = in.read(chunk)) != -1) data.write(chunk, 0, n);
                    digest = new String(data.toByteArray(), StandardCharsets.UTF_8).trim();
                }
                // Copy into the app's sandbox; this requires no storage permission.
                try (InputStream in = getAssets().open("game-assets.zip");
                     FileOutputStream out = new FileOutputStream(bundle)) {
                    byte[] chunk = new byte[32768]; int n;
                    while ((n = in.read(chunk)) != -1) out.write(chunk, 0, n);
                }
                synchronized (MainActivity.class) {
                    if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                }
                String session = Python.getInstance().getModule("android_runtime")
                        .callAttr("start", getFilesDir().getAbsolutePath(), bundle.getAbsolutePath(), digest).toString();
                String[] parts = session.split("\\|", 2);
                runOnUiThread(() -> { if (!destroyed) openGame(parts[0], parts[1]); });
            } catch (Exception error) {
                android.util.Log.e("CultivationLife", "Startup failed", error);
                runOnUiThread(() -> {
                    if (!destroyed) new AlertDialog.Builder(this).setTitle("未能展开绘卷")
                        .setMessage("本地游戏启动失败。请关闭应用后重试。\n" + error.getMessage())
                        .setPositiveButton("关闭", (d, w) -> finishAndRemoveTask()).show();
                });
            }
        }, "game-startup").start();
    }

    private void showLoading(String message) {
        TextView label = new TextView(this);
        label.setText(message); label.setTextSize(21); label.setGravity(Gravity.CENTER);
        label.setTextColor(Color.rgb(40, 60, 50)); label.setBackgroundColor(Color.rgb(243, 241, 231));
        setContentView(label);
    }

    @SuppressWarnings("SetJavaScriptEnabled")
    private void openGame(String base, String token) {
        origin = base;
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        web = new WebView(this);
        web.setBackgroundColor(Color.rgb(243, 241, 231));
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setTextZoom(100);
        web.setWebChromeClient(new WebChromeClient());
        web.addJavascriptInterface(new Bridge(), "AndroidGame");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return !request.getUrl().toString().startsWith(origin + "/");
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (url.startsWith(origin + "/")) return null;
                return new WebResourceResponse("text/plain", "utf-8", 403, "Forbidden",
                        Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
            }
        });
        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(web, false);
        cookies.setCookie(origin, "cultivation_session=" + token + "; Path=/; HttpOnly; SameSite=Strict", ok -> {
            if (!destroyed) { setContentView(web); web.loadUrl(origin + "/"); }
        });
    }

    public class Bridge {
        @JavascriptInterface public void setTheme(String theme) {
            int color = switch (theme) {
                case "b" -> Color.rgb(20, 28, 47);
                case "c" -> Color.rgb(56, 91, 78);
                case "d" -> Color.rgb(88, 32, 29);
                case "e" -> Color.rgb(64, 85, 76);
                case "f" -> Color.rgb(99, 77, 44);
                default -> Color.rgb(38, 63, 53);
            };
            runOnUiThread(() -> { getWindow().setStatusBarColor(color); getWindow().setNavigationBarColor(color); });
        }
        @JavascriptInterface public void restart() {
            runOnUiThread(() -> {
                Intent intent = new Intent(MainActivity.this, RestartActivity.class);
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                intent.putExtra("oldPid", Process.myPid());
                startActivity(intent);
                finishAndRemoveTask();
            });
        }
    }

    @Override public void onBackPressed() {
        if (web == null) { finishAndRemoveTask(); return; }
        web.evaluateJavascript("window.AndroidUI ? AndroidUI.back() : false", handled -> {
            if (!"true".equals(handled) && !destroyed) new AlertDialog.Builder(this)
                .setTitle("暂别山河").setMessage("每次行动后已自动保存进度。是否退出游戏？")
                .setNegativeButton("继续修行", null)
                .setPositiveButton("退出", (dialog, which) -> {
                    finishAndRemoveTask();
                    // The embedded Python runtime cannot be re-initialized in
                    // the same process. Explicit exit also closes its server.
                    Process.killProcess(Process.myPid());
                }).show();
        });
    }

    @Override protected void onPause() { if (web != null) web.onPause(); super.onPause(); }
    @Override protected void onResume() { super.onResume(); if (web != null) web.onResume(); }
    @Override protected void onDestroy() {
        destroyed = true;
        if (web != null) { web.removeJavascriptInterface("AndroidGame"); web.destroy(); web = null; }
        super.onDestroy();
    }
}

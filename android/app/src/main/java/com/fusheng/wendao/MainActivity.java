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
    private static final int DEBUG_EXPORT = 5701, DEBUG_IMPORT = 5702;
    private String pendingDebugExport;

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
                String buildRecord;
                try (InputStream in = getAssets().open("game-build.json")) {
                    ByteArrayOutputStream data = new ByteArrayOutputStream();
                    byte[] chunk = new byte[4096]; int n;
                    while ((n = in.read(chunk)) != -1) data.write(chunk, 0, n);
                    buildRecord = new String(data.toByteArray(), StandardCharsets.UTF_8);
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
                        .callAttr("start", getFilesDir().getAbsolutePath(), bundle.getAbsolutePath(), digest, buildRecord).toString();
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
        @JavascriptInterface public void requestDebugMode() {
            runOnUiThread(() -> {
                if (destroyed) return;
                boolean enabled = Python.getInstance().getModule("android_runtime")
                        .callAttr("debug_mode_enabled").toBoolean();
                new AlertDialog.Builder(MainActivity.this).setTitle("开发者模式")
                    .setMessage(enabled ? "关闭开发者模式？调试副本会保留，正常角色不受影响。"
                        : "开启开发者控制台？修改仅作用于独立调试副本；不会开启 WebView 远程调试。")
                    .setNegativeButton("取消", null)
                    .setPositiveButton(enabled ? "关闭" : "开启", (dialog, which) -> {
                        Python.getInstance().getModule("android_runtime").callAttr("set_debug_mode", !enabled);
                        web.evaluateJavascript("sessionStorage.removeItem('cultivation-debug-session'); location.reload()", null);
                    }).show();
            });
        }
        @JavascriptInterface public void exportDebugBundle(String text) {
            if (text == null || text.length() > 64 * 1024 * 1024) return;
            if (!Python.getInstance().getModule("android_runtime").callAttr("debug_mode_enabled").toBoolean()) return;
            runOnUiThread(() -> {
                if (destroyed || pendingDebugExport != null) return;
                pendingDebugExport = text;
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.setType("application/json"); intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.putExtra(Intent.EXTRA_TITLE, "CultivationLife-repro.json");
                startActivityForResult(intent, DEBUG_EXPORT);
            });
        }
        @JavascriptInterface public void importDebugBundle() {
            if (!Python.getInstance().getModule("android_runtime").callAttr("debug_mode_enabled").toBoolean()) return;
            runOnUiThread(() -> {
                if (destroyed) return;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.setType("application/json"); intent.addCategory(Intent.CATEGORY_OPENABLE);
                startActivityForResult(intent, DEBUG_IMPORT);
            });
        }
        @JavascriptInterface public boolean copySaveCode(String text) {
            if (text == null || text.length() > 120000 || !(text.startsWith("FSWD1.") || text.startsWith("FSWDP1."))) return false;
            try {
                android.content.ClipboardManager clipboard = (android.content.ClipboardManager)getSystemService(CLIPBOARD_SERVICE);
                clipboard.setPrimaryClip(android.content.ClipData.newPlainText("浮生问道存档码", text));
                return true;
            } catch (RuntimeException error) { return false; }
        }
        @JavascriptInterface public String readSaveCode() {
            try {
                android.content.ClipboardManager clipboard = (android.content.ClipboardManager)getSystemService(CLIPBOARD_SERVICE);
                android.content.ClipData clip = clipboard.getPrimaryClip();
                if (clip == null || clip.getItemCount() == 0) return "";
                CharSequence text = clip.getItemAt(0).getText();
                return text != null && text.length() <= 17 * 1024 * 1024 ? text.toString() : "";
            } catch (RuntimeException error) { return ""; }
        }
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

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != DEBUG_EXPORT && request != DEBUG_IMPORT) return;
        String exporting = pendingDebugExport;
        pendingDebugExport = null;
        if (result != RESULT_OK || data == null || data.getData() == null) return;
        new Thread(() -> {
            try {
                if (!Python.getInstance().getModule("android_runtime").callAttr("debug_mode_enabled").toBoolean()) return;
                if (request == DEBUG_EXPORT) {
                    try (java.io.OutputStream out = getContentResolver().openOutputStream(data.getData())) {
                        if (out == null || exporting == null) throw new java.io.IOException("无法写入复现包");
                        out.write(exporting.getBytes(StandardCharsets.UTF_8));
                    }
                    runOnUiThread(() -> { if (!destroyed) web.evaluateJavascript("window.DebugConsole?.notify('复现包已保存。')", null); });
                } else {
                    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                    try (InputStream in = getContentResolver().openInputStream(data.getData())) {
                        if (in == null) throw new java.io.IOException("无法读取复现包");
                        byte[] buffer = new byte[32768]; int n;
                        while ((n = in.read(buffer)) != -1) {
                            if (bytes.size() + n > 64 * 1024 * 1024) throw new java.io.IOException("复现包超过 64 MiB");
                            bytes.write(buffer, 0, n);
                        }
                    }
                    String text = new String(bytes.toByteArray(), StandardCharsets.UTF_8);
                    runOnUiThread(() -> { if (!destroyed) {
                        web.evaluateJavascript("window.DebugConsole?.beginNativeImport()", ignored -> deliverDebugImport(text, 0));
                    }});
                }
            } catch (Exception error) {
                runOnUiThread(() -> { if (!destroyed) web.evaluateJavascript(
                    "window.DebugConsole?.notify(" + org.json.JSONObject.quote("复现包操作失败：" + error.getMessage()) + ")", null); });
            }
        }, "debug-document").start();
    }

    private void deliverDebugImport(String text, int offset) {
        if (destroyed) return;
        if (offset == text.length()) {
            web.evaluateJavascript("window.DebugConsole?.finishNativeImport()", null);
            return;
        }
        int end = Math.min(offset + 48 * 1024, text.length());
        String chunk = org.json.JSONObject.quote(text.substring(offset, end));
        web.evaluateJavascript("window.DebugConsole?.appendNativeImport(" + chunk + ")",
                ignored -> deliverDebugImport(text, end));
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

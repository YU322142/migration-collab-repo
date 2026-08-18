package io.github.mcmodsync;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Detects mobile / launcher environments where separate Swing windows are
 * unavailable or unreliable for the player, and formats a log-friendly fingerprint.
 *
 * Real-world baseline from Zalith Launcher (Android):
 * - os.name is spoofed to "Linux"
 * - os.version is "Android-12" (or similar)
 * - java.awt.headless=false, but AWT is Cacio stub toolkit
 * - env: ZALITH_VERSION_CODE, POJAV_*, AWTSTUB_*, MOD_ANDROID_RUNTIME
 * - props: pojav.path.*, minecraft.launcher.brand, glfwstub.*, cacio.*
 * - paths under /storage/emulated/0/Android/data/... or /data/user/0/...
 */
final class RuntimeEnvironment {
    enum UiCapability {
        SWING_DIALOGS,
        LOG_AND_STATUS_FILE
    }

    private final boolean mobile;
    private final boolean headlessGraphics;
    private final boolean cacioAwt;
    private final boolean dialogsForcedOff;
    private final boolean dialogsUsable;
    private final String launcherName;
    private final List<String> signals;
    private final Map<String, String> properties;

    private RuntimeEnvironment(
            boolean mobile,
            boolean headlessGraphics,
            boolean cacioAwt,
            boolean dialogsForcedOff,
            boolean dialogsUsable,
            String launcherName,
            List<String> signals,
            Map<String, String> properties) {
        this.mobile = mobile;
        this.headlessGraphics = headlessGraphics;
        this.cacioAwt = cacioAwt;
        this.dialogsForcedOff = dialogsForcedOff;
        this.dialogsUsable = dialogsUsable;
        this.launcherName = launcherName;
        this.signals = List.copyOf(signals);
        this.properties = Map.copyOf(properties);
    }

    static RuntimeEnvironment detect() {
        Map<String, String> properties = new LinkedHashMap<>();
        put(properties, "os.name", System.getProperty("os.name"));
        put(properties, "os.arch", System.getProperty("os.arch"));
        put(properties, "os.version", System.getProperty("os.version"));
        put(properties, "java.vendor", System.getProperty("java.vendor"));
        put(properties, "java.vm.name", System.getProperty("java.vm.name"));
        put(properties, "java.vm.vendor", System.getProperty("java.vm.vendor"));
        put(properties, "java.runtime.name", System.getProperty("java.runtime.name"));
        put(properties, "java.home", System.getProperty("java.home"));
        put(properties, "user.home", System.getProperty("user.home"));
        put(properties, "java.io.tmpdir", System.getProperty("java.io.tmpdir"));
        put(properties, "java.awt.headless", System.getProperty("java.awt.headless"));
        put(properties, "awt.toolkit", System.getProperty("awt.toolkit"));
        put(properties, "java.awt.graphicsenv", System.getProperty("java.awt.graphicsenv"));
        put(properties, "minecraft.launcher.brand", System.getProperty("minecraft.launcher.brand"));
        put(properties, "net.minecraft.clientmodname", System.getProperty("net.minecraft.clientmodname"));
        put(properties, "pojav.path.minecraft", System.getProperty("pojav.path.minecraft"));
        put(properties, "pojav.path.private.account", System.getProperty("pojav.path.private.account"));
        put(properties, "glfwstub.windowWidth", System.getProperty("glfwstub.windowWidth"));
        put(properties, "loader.disable_forked_guis", System.getProperty("loader.disable_forked_guis"));
        put(properties, "modsync.disableDialogs", System.getProperty("modsync.disableDialogs"));
        put(properties, "modsync.forceHeadless", System.getProperty("modsync.forceHeadless"));
        put(properties, "modsync.forceMobile", System.getProperty("modsync.forceMobile"));

        Map<String, String> env = new LinkedHashMap<>();
        put(env, "ZALITH_VERSION_CODE", System.getenv("ZALITH_VERSION_CODE"));
        put(env, "POJAV_NATIVEDIR", System.getenv("POJAV_NATIVEDIR"));
        put(env, "POJAV_RENDERER", System.getenv("POJAV_RENDERER"));
        put(env, "POJAV_HOME", System.getenv("POJAV_HOME"));
        put(env, "AWTSTUB_WIDTH", System.getenv("AWTSTUB_WIDTH"));
        put(env, "AWTSTUB_HEIGHT", System.getenv("AWTSTUB_HEIGHT"));
        put(env, "MOD_ANDROID_RUNTIME", System.getenv("MOD_ANDROID_RUNTIME"));
        put(env, "FCL_HOME", System.getenv("FCL_HOME"));
        put(env, "HOME", System.getenv("HOME"));
        put(env, "JAVA_HOME", System.getenv("JAVA_HOME"));
        put(env, "TMPDIR", System.getenv("TMPDIR"));

        List<String> signals = new ArrayList<>();
        boolean forceMobile = Boolean.getBoolean("modsync.forceMobile");
        boolean forceHeadless = Boolean.getBoolean("modsync.forceHeadless");
        boolean disableDialogs = Boolean.getBoolean("modsync.disableDialogs");
        if (forceMobile) {
            signals.add("modsync.forceMobile=true");
        }
        if (forceHeadless) {
            signals.add("modsync.forceHeadless=true");
        }
        if (disableDialogs) {
            signals.add("modsync.disableDialogs=true");
        }

        String osName = lower(properties.get("os.name"));
        String osVersion = lower(properties.get("os.version"));
        String javaHome = lower(properties.get("java.home"));
        String userHome = lower(properties.get("user.home"));
        String tmpDir = lower(properties.get("java.io.tmpdir"));
        String toolkit = lower(properties.get("awt.toolkit"));
        String graphicsEnv = lower(properties.get("java.awt.graphicsenv"));
        String launcherBrand = firstNonBlank(
                properties.get("minecraft.launcher.brand"),
                properties.get("net.minecraft.clientmodname"));
        String launcherLower = lower(launcherBrand);
        String pojavMinecraft = lower(properties.get("pojav.path.minecraft"));
        String classPath = lower(System.getProperty("java.class.path", ""));
        String libraryPath = lower(System.getProperty("java.library.path", ""));

        boolean androidOsName = containsAny(osName, "android");
        boolean androidOsVersion = containsAny(osVersion, "android");
        boolean androidPath = containsAny(javaHome, "/data/user/", "/data/data/", "/storage/emulated/", "android/data")
                || containsAny(userHome, "/data/user/", "/data/data/", "/storage/emulated/", "android/data")
                || containsAny(tmpDir, "/data/user/", "/data/data/", "/storage/emulated/")
                || containsAny(lower(env.get("HOME")), "/storage/emulated/", "android/data", "/data/user/")
                || containsAny(lower(env.get("JAVA_HOME")), "/data/user/", "/data/data/")
                || containsAny(lower(env.get("TMPDIR")), "/data/user/", "/data/data/");
        boolean pojavFingerprint = !isBlank(env.get("POJAV_NATIVEDIR"))
                || !isBlank(env.get("POJAV_RENDERER"))
                || !isBlank(env.get("POJAV_HOME"))
                || !isBlank(properties.get("pojav.path.minecraft"))
                || !isBlank(properties.get("pojav.path.private.account"))
                || containsAny(launcherLower, "pojavlauncher", "pojav launcher")
                || containsAny(pojavMinecraft, "pojav");
        boolean zalithFingerprint = !isBlank(env.get("ZALITH_VERSION_CODE"))
                || containsAny(launcherLower, "zalith launcher 2", "zalithlauncher2", "zalithlauncher.v2")
                || containsAny(javaHome, "zalithlauncher.v2")
                || containsAny(userHome, "zalithlauncher.v2")
                || containsAny(libraryPath, "zalithlauncher.v2")
                || containsAny(classPath, "zalithlauncher.v2")
                || containsAny(lower(env.get("HOME")), "zalithlauncher.v2");
        boolean foldCraftFingerprint = !isBlank(env.get("FCL_HOME"))
                || containsAny(launcherLower, "foldcraft", "fcl")
                || containsAny(javaHome, "foldcraftlauncher", "fcl");
        boolean mcinaboxFingerprint = containsAny(launcherLower, "mcinabox")
                || containsAny(javaHome, "mcinabox")
                || containsAny(userHome, "mcinabox")
                || containsAny(libraryPath, "mcinabox")
                || containsAny(classPath, "mcinabox")
                || containsAny(lower(env.get("HOME")), "mcinabox");
        boolean awtStubFingerprint = !isBlank(env.get("AWTSTUB_WIDTH"))
                || !isBlank(env.get("AWTSTUB_HEIGHT"))
                || !isBlank(properties.get("glfwstub.windowWidth"));
        boolean cacioAwt = containsAny(toolkit, "cacio")
                || containsAny(graphicsEnv, "cacio")
                || containsAny(classPath, "cacio");
        boolean androidRuntimeMod = !isBlank(env.get("MOD_ANDROID_RUNTIME"));
        boolean forkedGuiDisabled = "true".equalsIgnoreCase(properties.get("loader.disable_forked_guis"));

        if (androidOsName) {
            signals.add("os.name contains android");
        }
        if (androidOsVersion) {
            signals.add("os.version indicates Android (" + properties.get("os.version") + ")");
        }
        if (androidPath) {
            signals.add("paths under Android app storage");
        }
        if (pojavFingerprint) {
            signals.add("Pojav-compatible env/props present");
        }
        if (zalithFingerprint) {
            signals.add("Zalith Launcher fingerprint matched");
        }
        if (foldCraftFingerprint) {
            signals.add("Fold Craft / FCL fingerprint matched");
        }
        if (mcinaboxFingerprint) {
            signals.add("MCinaBox fingerprint matched");
        }
        if (awtStubFingerprint) {
            signals.add("AWT/GLFW stub window metrics present");
        }
        if (cacioAwt) {
            signals.add("Cacio AWT toolkit (mobile pseudo-desktop)");
        }
        if (androidRuntimeMod) {
            signals.add("MOD_ANDROID_RUNTIME set");
        }
        if (forkedGuiDisabled) {
            signals.add("loader.disable_forked_guis=true");
        }

        // Mobile behavior is intentionally restricted to the four supported
        // launchers. Generic Android/Cacio signals alone stay on desktop logic.
        boolean mobile = forceMobile
                || pojavFingerprint
                || zalithFingerprint
                || foldCraftFingerprint
                || mcinaboxFingerprint;

        boolean headlessGraphics;
        try {
            headlessGraphics = java.awt.GraphicsEnvironment.isHeadless()
                    || "true".equalsIgnoreCase(properties.getOrDefault("java.awt.headless", ""));
        } catch (Throwable failure) {
            headlessGraphics = true;
            signals.add("GraphicsEnvironment probe failed: " + failure.getClass().getSimpleName());
        }
        if (headlessGraphics) {
            signals.add("graphics headless");
        }

        // Desktop keeps the original Swing window design.
        // Only mobile/Cacio/headless/forced flags switch to log+status progress.
        // loader.disable_forked_guis alone must NOT change desktop behavior.
        boolean dialogsUsable = !mobile
                && !headlessGraphics
                && !cacioAwt
                && !forceHeadless
                && !disableDialogs;
        if (!dialogsUsable) {
            if (mobile || cacioAwt) {
                signals.add("mobile/Cacio runtime => log + ui-status progress (no separate Swing window)");
            } else if (headlessGraphics || forceHeadless || disableDialogs) {
                signals.add("dialogs disabled or unavailable");
            }
        }

        String resolvedLauncher = !isBlank(launcherBrand)
                ? launcherBrand
                : (zalithFingerprint ? "Zalith Launcher"
                        : pojavFingerprint ? "PojavLauncher"
                        : foldCraftFingerprint ? "Fold Craft Launcher"
                        : mcinaboxFingerprint ? "MCinaBox"
                        : mobile ? "mobile" : "desktop");

        for (Map.Entry<String, String> entry : env.entrySet()) {
            if (!isBlank(entry.getValue())) {
                properties.put("env." + entry.getKey(), entry.getValue());
            }
        }

        return new RuntimeEnvironment(
                mobile,
                headlessGraphics,
                cacioAwt,
                forceHeadless || disableDialogs,
                dialogsUsable,
                resolvedLauncher,
                signals,
                properties);
    }

    boolean mobile() {
        return mobile;
    }

    boolean headlessGraphics() {
        return headlessGraphics;
    }

    boolean cacioAwt() {
        return cacioAwt;
    }

    boolean dialogsForcedOff() {
        return dialogsForcedOff;
    }

    boolean dialogsUsable() {
        return dialogsUsable;
    }

    String launcherName() {
        return launcherName;
    }

    UiCapability uiCapability() {
        return dialogsUsable ? UiCapability.SWING_DIALOGS : UiCapability.LOG_AND_STATUS_FILE;
    }

    List<String> signals() {
        return signals;
    }

    String summaryLine() {
        return "mobile=" + mobile
                + ", launcher=" + launcherName
                + ", cacio=" + cacioAwt
                + ", dialogs=" + (dialogsUsable ? "swing" : "disabled")
                + ", progress=" + (dialogsUsable ? "window+log" : "log+ui-status.txt+progress.log")
                + ", signals=" + (signals.isEmpty() ? "none" : String.join("; ", signals));
    }

    String detailedReport() {
        StringBuilder builder = new StringBuilder();
        builder.append("runtime mobile=").append(mobile)
                .append(", launcher=").append(launcherName)
                .append(", headlessGraphics=").append(headlessGraphics)
                .append(", cacioAwt=").append(cacioAwt)
                .append(", dialogsUsable=").append(dialogsUsable)
                .append(", ui=").append(uiCapability()).append('\n');
        builder.append("signals:\n");
        if (signals.isEmpty()) {
            builder.append("  (none)\n");
        } else {
            for (String signal : signals) {
                builder.append("  - ").append(signal).append('\n');
            }
        }
        builder.append("properties:\n");
        for (Map.Entry<String, String> entry : properties.entrySet()) {
            builder.append("  ").append(entry.getKey()).append('=')
                    .append(entry.getValue() == null ? "" : entry.getValue()).append('\n');
        }
        return builder.toString().stripTrailing();
    }

    private static void put(Map<String, String> map, String key, String value) {
        map.put(key, value == null ? "" : value);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static String lower(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT);
    }

    private static boolean containsAny(String haystack, String... needles) {
        if (haystack == null || haystack.isEmpty()) {
            return false;
        }
        for (String needle : needles) {
            if (needle != null && !needle.isEmpty() && haystack.contains(needle.toLowerCase(Locale.ROOT))) {
                return true;
            }
        }
        return false;
    }

    private static String firstNonBlank(String... values) {
        if (values == null) {
            return "";
        }
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return "";
    }
}

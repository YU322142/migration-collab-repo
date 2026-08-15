package io.github.mcmodsync;

import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

public final class ModSyncAgent {
    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm:ss");
    private static InstanceGuard instanceGuard;
    private static volatile DisplayLanguage language = DisplayLanguage.detect(null);

    private ModSyncAgent() {
    }

    public static void premain(String agentArguments, Instrumentation instrumentation) {
        System.setProperty("modsync.agent.active", "true");
        log("MCModSync " + BuildInfo.VERSION + " 启动前校验开始",
                "MCModSync " + BuildInfo.VERSION + " pre-launch verification started");
        try {
            Path bootstrapDirectory = ModSyncConfig.determineGameDirectory(agentArguments, null);
            language = DisplayLanguage.detect(bootstrapDirectory);
            ManagedClientConfig.installFromBootstrapJar(bootstrapDirectory, ModSyncAgent::log);
            ModSyncConfig config = ModSyncConfig.fromEnvironment(agentArguments);
            System.clearProperty("modsync.managedConfigChanged");
            System.setProperty("modsync.gameDir", config.gameDirectory().toString());
            language = DisplayLanguage.detect(config.gameDirectory());
            log("游戏目录: " + config.gameDirectory(), "Game directory: " + config.gameDirectory());
            RuntimeEnvironment environment = RuntimeEnvironment.detect();
            if (environment.mobile() || !environment.dialogsUsable()) {
                log("运行环境: " + environment.summaryLine(),
                        "Runtime environment: " + environment.summaryLine());
            }
            if (environment.mobile()) {
                log("手机端 Mod 清单: " + config.manifestUri(),
                        "Mobile mod catalog: " + config.manifestUri());
            }
            instanceGuard = InstanceGuard.acquire(config.gameDirectory());
            Runtime.getRuntime().addShutdownHook(new Thread(ModSyncAgent::releaseGuard, "MCModSync-lock-release"));
            SyncResult result = ModSyncCoordinator.synchronize(
                    config, ModSyncAgent::log, new UserNotifier(false, config.gameDirectory()));
            System.setProperty("modsync.status", result.status().name());
            log("启动前校验结束: " + result.status(),
                    "Pre-launch verification finished: " + result.status());
            if (Boolean.getBoolean("modsync.managedConfigChanged")) {
                System.err.println("[MCModSync] RESTART_REQUIRED");
                log("服务器管理的客户端配置已更新；本次启动正常结束，请重新启动以使用新配置",
                        "The server-managed client configuration was updated; this launch ended normally. "
                                + "Launch again to use the new configuration");
                releaseGuard();
                if (Boolean.getBoolean("modsync.disableProcessExit")) {
                    throw new RuntimeException("MCModSync 客户端配置已更新；测试模式禁用了正常退出");
                }
                System.exit(0);
            }
        } catch (Throwable failure) {
            System.err.println("[MCModSync] STARTUP_BLOCKED");
            System.err.println("[MCModSync] " + language.text(
                    "致命错误：无法保证同步内容完整，Minecraft 启动已中止。",
                    "Fatal error: synchronized content integrity cannot be guaranteed; Minecraft startup stopped."));
            failure.printStackTrace(System.err);
            UserNotifier.showFatalError(failure);
            releaseGuard();
            if (Boolean.getBoolean("modsync.disableProcessExit")) {
                throw new RuntimeException("MCModSync 已阻止启动；测试模式禁用了正常退出", failure);
            }
            System.exit(0);
        }
    }

    private static void log(String message) {
        System.out.println("[MCModSync " + TIME.format(LocalDateTime.now()) + "] " + message);
    }

    private static void log(String chinese, String english) {
        log(language.text(chinese, english));
    }

    private static synchronized void releaseGuard() {
        if (instanceGuard == null) {
            return;
        }
        try {
            instanceGuard.close();
        } catch (Exception ignored) {
        } finally {
            instanceGuard = null;
        }
    }
}

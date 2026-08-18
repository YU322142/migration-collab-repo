package io.github.mcmodsync;

import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/**
 * Shared startup policy for Fabric's PreLaunch callback and NeoForge's
 * client-side @Mod constructor.
 */
final class PortablePreLaunchEntrypoint {
    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm:ss");
    private static InstanceGuard instanceGuard;
    private static volatile DisplayLanguage language = DisplayLanguage.detect(null);

    private PortablePreLaunchEntrypoint() {
    }

    static void run(String loaderName, GameDirectoryLocator locator) {
        if (Boolean.getBoolean("modsync.agent.active")) {
            log(language, "已由 -javaagent 完成启动前校验，" + loaderName + " 入口不再重复执行",
                    "Pre-launch verification was completed by -javaagent; the "
                            + loaderName + " entrypoint will not repeat it");
            return;
        }

        log(language, "MCSync " + BuildInfo.VERSION + " " + loaderName + " 便携模式校验开始",
                "MCSync " + BuildInfo.VERSION + " " + loaderName + " portable-mode verification started");
        try {
            Path gameDirectory = locator.locate().toAbsolutePath().normalize();
            // Pin this property before loading configuration so a stale test or
            // launcher property cannot redirect a mobile in-process update.
            System.setProperty("modsync.gameDir", gameDirectory.toString());
            language = DisplayLanguage.detect(gameDirectory);
            log(language, "游戏目录: " + gameDirectory, "Game directory: " + gameDirectory);
            ManagedClientConfig.installFromBootstrapJar(gameDirectory,
                    message -> log(language, message));
            ModSyncConfig config = ModSyncConfig.fromEnvironment(null, gameDirectory);
            language = DisplayLanguage.detect(config.gameDirectory());
            System.clearProperty("modsync.managedConfigChanged");
            RuntimeEnvironment environment = RuntimeEnvironment.detect();
            if (environment.mobile()) {
                log(language, "手机端 Mod 清单: " + config.manifestUri(),
                        "Mobile mod catalog: " + config.manifestUri());
                log(language, "手机端资源包清单: " + config.resourcePackManifestUri(),
                        "Mobile resource-pack catalog: " + config.resourcePackManifestUri());
            }
            if (environment.mobile() || !environment.dialogsUsable()) {
                log(language, "运行环境: " + environment.summaryLine(),
                        "Runtime environment: " + environment.summaryLine());
            }
            instanceGuard = InstanceGuard.acquire(config.gameDirectory());
            Runtime.getRuntime().addShutdownHook(
                    new Thread(PortablePreLaunchEntrypoint::releaseGuard, "MCSync-lock-release"));

            if (shouldUpdateInProcess(environment)) {
                runMobileInProcessUpdate(loaderName, config);
                return;
            }

            SyncProbeResult result = ModSyncCoordinator.probe(
                    config,
                    message -> log(language, message),
                    new UserNotifier(true, config.gameDirectory()));
            System.setProperty("modsync.status", result.status().name());
            log(language, loaderName + " 便携模式只读校验结束: " + result.status(),
                    loaderName + " portable read-only verification finished: " + result.status());

            if (result.status() == SyncProbeResult.Status.CHANGES_REQUIRED) {
                boolean helperStarted = PortableUpdateHelper.schedule(
                        config, message -> log(language, message), loaderName);
                System.err.println("[MCSync] RESTART_REQUIRED");
                if (helperStarted) {
                    log(language,
                            "更新窗口已经启动；Minecraft 将正常退出，更新完成后请重新启动",
                            "The update window started; Minecraft will exit normally. Launch again after the update");
                    exitProcess(0);
                }
                throw new RestartRequiredException(language.text(
                        "MCSync 检测到同步内容变化。本次 " + loaderName + " 启动已停止；"
                                + "辅助进程会在当前 Java 完全退出后自动下载并替换。"
                                + "请等待“更新完成”窗口，再回到启动器启动一次。",
                        "MCSync detected synchronized-content changes. This " + loaderName
                                + " launch was stopped; the helper will download and replace files after Java exits."
                                + " Wait for the update-complete window, then launch the instance again."));
            }
        } catch (InstanceGuard.AlreadyRunningException busy) {
            releaseGuard();
            System.err.println("[MCSync] STARTUP_CANCELLED_UPDATE_BUSY");
            log(language, "本次启动已安全取消：同步辅助进程仍在工作，或该实例已有 Minecraft 正在运行",
                    "This launch was cancelled safely: the sync helper is still working or Minecraft is already "
                            + "running for this instance");
            UserNotifier.showInstanceBusy();
            exitProcess(0);
        } catch (RestartRequiredException expected) {
            releaseGuard();
            throw expected;
        } catch (Throwable failure) {
            releaseGuard();
            System.err.println("[MCSync] STARTUP_BLOCKED");
            System.err.println("[MCSync] " + language.text(
                    "致命错误：无法保证同步内容完整，Minecraft 启动已中止。",
                    "Fatal error: synchronized content integrity cannot be guaranteed; Minecraft startup stopped."));
            failure.printStackTrace(System.err);
            UserNotifier.showFatalError(failure);
            exitProcess(0);
        }
    }

    private static void runMobileInProcessUpdate(String loaderName, ModSyncConfig config) throws Exception {
        log(language, "手机端模式：先在当前进程下载并禁用旧模组，完成后再退出并要求重新启动",
                "Mobile mode: downloading and disabling old mods in this process, then exiting for a restart");
        UserNotifier notifier = new UserNotifier(true, config.gameDirectory());
        SyncResult result = ModSyncCoordinator.synchronize(
                config, message -> log(language, message), notifier);
        System.setProperty("modsync.status", result.status().name());
        log(language, "手机端同步结束: " + result.status()
                        + " (下载/替换 " + result.downloaded()
                        + "，移入备份/禁用 " + result.quarantined()
                        + "，无需更改 " + result.unchanged() + ")",
                "Mobile synchronization finished: " + result.status()
                        + " (downloaded/replaced " + result.downloaded()
                        + ", moved to backup/disabled " + result.quarantined()
                        + ", unchanged " + result.unchanged() + ")");

        if (result.status() == SyncResult.Status.UPDATED) {
            System.err.println("[MCSync] RESTART_REQUIRED");
            log(language, "旧模组已禁用并移入备份，新文件已就绪。请重新启动游戏以加载更新后的 Mod。",
                    "Old mods were disabled and moved to backup; new files are ready. Restart to load updated mods.");
            releaseGuard();
            if (Boolean.getBoolean("modsync.disableProcessExit")) {
                throw new RestartRequiredException(language.text(
                        "MCSync 手机端已在当前进程完成下载并禁用旧模组。本次启动已停止，请重新启动游戏。",
                        "MCSync mobile synchronization completed in-process; restart is required."));
            }
            exitProcess(0);
        }

        log(language, "手机端无需退出重进: " + result.status(),
                "Mobile restart is not required: " + result.status());
    }

    private static boolean shouldUpdateInProcess(RuntimeEnvironment environment) {
        if (Boolean.getBoolean("modsync.forceDesktopHelper")) {
            return false;
        }
        if (Boolean.getBoolean("modsync.forceMobileInProcessUpdate")) {
            return true;
        }
        return environment.mobile();
    }

    private static void exitProcess(int code) {
        if (Boolean.getBoolean("modsync.disableProcessExit")) {
            throw new RestartRequiredException(language.text(
                    "MCSync 请求退出进程 (code=" + code + ")，但测试模式禁用了 System.exit。",
                    "MCSync requested process exit (code=" + code + "), but test mode disabled System.exit."));
        }
        System.exit(code);
    }

    private static void log(DisplayLanguage currentLanguage, String chinese, String english) {
        log(currentLanguage.text(chinese, english));
    }

    private static void log(DisplayLanguage currentLanguage, String localizedMessage) {
        log(localizedMessage);
    }

    private static void log(String message) {
        System.out.println("[MCSync " + TIME.format(LocalDateTime.now()) + "] " + message);
    }

    static synchronized void releaseGuard() {
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

    @FunctionalInterface
    interface GameDirectoryLocator {
        Path locate() throws Exception;
    }

    static final class RestartRequiredException extends RuntimeException {
        private RestartRequiredException(String message) {
            super(message);
        }
    }
}

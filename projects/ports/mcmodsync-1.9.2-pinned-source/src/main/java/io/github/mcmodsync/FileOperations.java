package io.github.mcmodsync;

import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

final class FileOperations {
    private final int attempts;

    FileOperations(int attempts) {
        this.attempts = attempts;
    }

    void move(Path source, Path target, boolean replace) throws IOException {
        IOException last = null;
        for (int attempt = 1; attempt <= attempts; attempt++) {
            try {
                Files.createDirectories(target.getParent());
                moveOnce(source, target, replace);
                return;
            } catch (IOException exception) {
                last = exception;
                if (attempt == attempts) {
                    break;
                }
                sleep(attempt);
            }
        }
        throw new IOException(
                "多次尝试后仍无法移动文件；可能被其他程序占用、被设为只读，或当前用户没有写入权限: "
                        + source + " -> " + target,
                last);
    }

    void deleteIfExists(Path path) throws IOException {
        IOException last = null;
        for (int attempt = 1; attempt <= attempts; attempt++) {
            try {
                Files.deleteIfExists(path);
                return;
            } catch (IOException exception) {
                last = exception;
                if (attempt == attempts) {
                    break;
                }
                sleep(attempt);
            }
        }
        throw new IOException(
                "多次尝试后仍无法删除文件；可能被其他程序占用、被设为只读，或当前用户没有写入权限: " + path,
                last);
    }

    private static void moveOnce(Path source, Path target, boolean replace) throws IOException {
        try {
            if (replace) {
                Files.move(source, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } else {
                Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
            }
        } catch (AtomicMoveNotSupportedException exception) {
            if (replace) {
                Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
            } else {
                Files.move(source, target);
            }
        }
    }

    private static void sleep(int attempt) throws IOException {
        long delay = Math.min(150L * attempt, 1_000L);
        try {
            Thread.sleep(delay);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IOException("等待被占用文件释放时线程被中断", exception);
        }
    }
}

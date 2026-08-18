package io.github.mcmodsync;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

final class InstanceGuard implements AutoCloseable {
    private final FileChannel channel;
    private final FileLock lock;

    private InstanceGuard(FileChannel channel, FileLock lock) {
        this.channel = channel;
        this.lock = lock;
    }

    static InstanceGuard acquire(Path gameDirectory) throws IOException {
        Path stateDirectory = gameDirectory.resolve(".modsync");
        Files.createDirectories(stateDirectory);
        Path lockPath = stateDirectory.resolve("instance.lock");
        FileChannel channel = FileChannel.open(
                lockPath,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE);
        try {
            FileLock lock = channel.tryLock();
            if (lock == null) {
                channel.close();
                throw new AlreadyRunningException(
                        "该游戏实例正在同步更新，或已有一个 Minecraft/Java 进程正在运行");
            }
            return new InstanceGuard(channel, lock);
        } catch (OverlappingFileLockException exception) {
            channel.close();
            throw new AlreadyRunningException(
                    "该游戏实例正在同步更新，或已在当前 Java 进程中锁定",
                    exception);
        } catch (IOException exception) {
            try {
                channel.close();
            } catch (IOException closeFailure) {
                exception.addSuppressed(closeFailure);
            }
            throw exception;
        }
    }

    @Override
    public void close() throws IOException {
        IOException failure = null;
        try {
            lock.close();
        } catch (IOException exception) {
            failure = exception;
        }
        try {
            channel.close();
        } catch (IOException exception) {
            if (failure == null) {
                failure = exception;
            } else {
                failure.addSuppressed(exception);
            }
        }
        if (failure != null) {
            throw failure;
        }
    }

    static final class AlreadyRunningException extends IOException {
        private AlreadyRunningException(String message) {
            super(message);
        }

        private AlreadyRunningException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}

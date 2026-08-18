package io.github.mcmodsync;

public final class DummyMain {
    private DummyMain() {
    }

    public static void main(String[] arguments) {
        System.out.println("Dummy main reached; modsync.status=" + System.getProperty("modsync.status"));
    }
}

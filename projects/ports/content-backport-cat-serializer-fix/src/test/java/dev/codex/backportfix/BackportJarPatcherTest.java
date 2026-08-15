package dev.codex.backportfix;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class BackportJarPatcherTest {
    @TempDir
    Path temporaryDirectory;

    @Test
    void patchesExactJarReproduciblyAndSatisfiesRegistryLifecycleContract() throws Exception {
        Path input = Path.of(System.getProperty("backport.inputJar")).toAbsolutePath().normalize();
        Path first = temporaryDirectory.resolve("first.jar");
        Path second = temporaryDirectory.resolve("second.jar");

        BackportJarPatcher.PatchResult firstResult = BackportJarPatcher.patch(input, first);
        BackportJarPatcher.PatchResult secondResult = BackportJarPatcher.patch(input, second);
        assertEquals(firstResult.outputSha256(), secondResult.outputSha256());
        assertEquals(Files.mismatch(first, second), -1L);
        assertEquals(8, firstResult.replacedUnboundGetSites());

        BackportJarVerifier.VerificationResult verification = BackportJarVerifier.verify(input, first);
        assertEquals(8, verification.originalUnsafeSites());
        assertEquals(0, verification.patchedUnsafeSites());
        assertEquals(8, verification.eagerUseSites());
        assertEquals(2, verification.preservedCatSoundVariantJson());
        assertEquals(21, verification.preservedCatSoundOgg());
        assertEquals(BackportPatchContract.EXPECTED_CHANGED_ENTRIES, verification.changedEntries());
    }

    @Test
    void refusesAnyUnauditedInputBeforeWritingOutput() throws Exception {
        Path invalid = temporaryDirectory.resolve("not-the-audited-jar.bin");
        Path output = temporaryDirectory.resolve("must-not-exist.jar");
        Files.writeString(invalid, "not backport-1.5.jar");

        IllegalArgumentException failure = assertThrows(
                IllegalArgumentException.class, () -> BackportJarPatcher.patch(invalid, output));
        assertTrue(failure.getMessage().contains("Refusing unaudited input JAR"));
        assertTrue(Files.notExists(output));
    }
}

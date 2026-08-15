package org.xiyu.yee.xiyuslogin.data;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PlayerDataManagerPasswordResetTest {
    private static final String RESET_FILE = "xiyus_password_reset_requests.json";
    private static final UUID SYNTHETIC_UUID =
            UUID.fromString("00000000-0000-0000-0000-000000000321");

    @TempDir
    Path worldDir;

    @Test
    void pendingResetPersistsOnlyBcryptAndApprovalAppliesIt() throws Exception {
        PlayerDataManager manager = PlayerDataManager.fromWorldDirectory(worldDir.toFile());
        assertTrue(manager.registerPlayer("SyntheticUser", "old-secret", SYNTHETIC_UUID));

        manager.addPasswordResetRequest("SyntheticUser", "reason contains new-secret", "new-secret", SYNTHETIC_UUID);

        String persisted = Files.readString(worldDir.resolve(RESET_FILE), StandardCharsets.UTF_8);
        assertFalse(persisted.contains("new-secret"));
        assertFalse(persisted.contains("\"newPassword\""));

        JsonObject request = JsonParser.parseString(persisted)
                .getAsJsonObject().getAsJsonObject("syntheticuser");
        String bcryptHash = request.get("newPasswordHash").getAsString();
        assertTrue(bcryptHash.startsWith("$2"));
        assertTrue(PlayerDataManager.verifyPassword("new-secret", bcryptHash));
        assertEquals("bcrypt", request.get("passwordScheme").getAsString());
        assertEquals(2, request.get("requestDataVersion").getAsInt());

        assertThrows(NoSuchMethodException.class,
                () -> PlayerDataManager.PasswordResetRequest.class.getMethod("getNewPassword"));
        assertTrue(manager.approvePasswordReset("SyntheticUser"));
        assertEquals("bcrypt", manager.getPlayerData("SyntheticUser").getPasswordScheme());
        assertTrue(manager.loginPlayer("SyntheticUser", "new-secret"));
        assertFalse(manager.loginPlayer("SyntheticUser", "old-secret"));
    }

    @Test
    void loadingLegacyPlaintextRequestHashesAndAtomicallyRewritesIt() throws Exception {
        String legacyJson = """
                {
                  "legacyuser": {
                    "username": "LegacyUser",
                    "reason": "synthetic legacy reason",
                    "newPassword": "legacy-new-secret",
                    "requesterUUID": "00000000-0000-0000-0000-000000000321",
                    "requestTime": "2026-08-09T01:02:03",
                    "status": "pending"
                  }
                }
                """;
        Files.writeString(worldDir.resolve(RESET_FILE), legacyJson, StandardCharsets.UTF_8);

        PlayerDataManager manager = PlayerDataManager.fromWorldDirectory(worldDir.toFile());
        String migrated = Files.readString(worldDir.resolve(RESET_FILE), StandardCharsets.UTF_8);

        assertFalse(migrated.contains("legacy-new-secret"));
        assertFalse(migrated.contains("\"newPassword\""));
        JsonObject request = JsonParser.parseString(migrated)
                .getAsJsonObject().getAsJsonObject("legacyuser");
        assertTrue(PlayerDataManager.verifyPassword(
                "legacy-new-secret", request.get("newPasswordHash").getAsString()));
        assertEquals("bcrypt", request.get("passwordScheme").getAsString());
        assertEquals(2, request.get("requestDataVersion").getAsInt());
        assertTrue(manager.getPasswordResetRequests().containsKey("legacyuser"));
    }

    @Test
    void malformedResetRequestFailsClosedWithoutOverwritingSource() throws Exception {
        String malformedJson = """
                {
                  "broken": {
                    "username": "Broken",
                    "reason": "synthetic malformed request",
                    "requestTime": "2026-08-09T01:02:03",
                    "status": "pending"
                  }
                }
                """;
        Path resetFile = worldDir.resolve(RESET_FILE);
        Files.writeString(resetFile, malformedJson, StandardCharsets.UTF_8);

        assertThrows(IllegalStateException.class,
                () -> PlayerDataManager.fromWorldDirectory(worldDir.toFile()));
        assertEquals(malformedJson, Files.readString(resetFile, StandardCharsets.UTF_8));
    }

    @Test
    void registrationAndAdminResetUseBcryptAndDoNotDowngradeOnLogin() {
        PlayerDataManager manager = PlayerDataManager.fromWorldDirectory(worldDir.toFile());
        assertTrue(manager.registerPlayer("BcryptUser", "initial-secret", SYNTHETIC_UUID));

        String registeredHash = manager.getPlayerData("BcryptUser").getPasswordHash();
        assertTrue(registeredHash.startsWith("$2"));
        assertTrue(registeredHash.matches("^\\$2[aby]\\$12\\$.*"));
        assertEquals("bcrypt", manager.getPlayerData("BcryptUser").getPasswordScheme());
        assertFalse(manager.loginPlayer("BcryptUser", "wrong-secret"));
        assertEquals(registeredHash, manager.getPlayerData("BcryptUser").getPasswordHash());
        assertTrue(manager.loginPlayer("BcryptUser", "initial-secret"));
        assertEquals(registeredHash, manager.getPlayerData("BcryptUser").getPasswordHash());

        assertTrue(manager.resetPassword("BcryptUser", "admin-secret"));
        String resetHash = manager.getPlayerData("BcryptUser").getPasswordHash();
        assertTrue(resetHash.startsWith("$2"));
        assertTrue(PlayerDataManager.verifyPassword("admin-secret", resetHash));
        assertEquals("bcrypt", manager.getPlayerData("BcryptUser").getPasswordScheme());
        assertNotEquals(registeredHash, resetHash);
    }

    @Test
    void legacySha256UpgradesOnlyAfterCorrectLogin() {
        PlayerDataManager manager = PlayerDataManager.fromWorldDirectory(worldDir.toFile());
        assertTrue(manager.registerPlayer("LegacySha", "unused-secret", SYNTHETIC_UUID));
        String legacyHash = PlayerDataManager.hashLegacySha256Password("legacy-secret");
        PlayerDataManager.PlayerData data = manager.getPlayerData("LegacySha");
        data.setPasswordHash(legacyHash);
        data.setPasswordScheme("sha256");

        assertFalse(manager.loginPlayer("LegacySha", "wrong-secret"));
        assertEquals(legacyHash, data.getPasswordHash());
        assertEquals("sha256", data.getPasswordScheme());

        assertTrue(manager.loginPlayer("LegacySha", "legacy-secret"));
        assertNotEquals(legacyHash, data.getPasswordHash());
        assertTrue(data.getPasswordHash().startsWith("$2"));
        assertEquals("bcrypt", data.getPasswordScheme());
        assertTrue(PlayerDataManager.verifyPassword("legacy-secret", data.getPasswordHash()));
    }
}

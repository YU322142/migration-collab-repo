package org.xiyu.yee.xiyuslogin.data;

import at.favre.lib.crypto.bcrypt.BCrypt;
import org.junit.jupiter.api.Test;
import java.util.Base64;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PlayerDataManagerPasswordTest {
    @Test
    void verifiesAndRejectsSaltedSha256Passwords() {
        String first = PlayerDataManager.hashLegacySha256Password("migration-secret");
        String second = PlayerDataManager.hashLegacySha256Password("migration-secret");

        assertNotEquals(first, second, "each password hash must use a fresh salt");
        assertTrue(PlayerDataManager.verifyPassword("migration-secret", first));
        assertFalse(PlayerDataManager.verifyPassword("wrong-secret", first));

        String[] parts = first.split(":", -1);
        assertEquals(2, parts.length);
        assertEquals(16, Base64.getDecoder().decode(parts[0]).length);
        assertEquals(32, Base64.getDecoder().decode(parts[1]).length);
    }

    @Test
    void verifiesLegacyEasyAuthBcryptAndRejectsWrongPasswords() {
        String bcrypt = BCrypt.withDefaults()
                .hashToString(12, "legacy-secret".toCharArray());

        assertTrue(PlayerDataManager.isLegacyBcrypt(bcrypt));
        assertTrue(PlayerDataManager.verifyPassword("legacy-secret", bcrypt));
        assertFalse(PlayerDataManager.verifyPassword("wrong-secret", bcrypt));
    }

    @Test
    void rejectsEmptyAndMalformedHashes() {
        assertFalse(PlayerDataManager.verifyPassword("secret", null));
        assertFalse(PlayerDataManager.verifyPassword("secret", ""));
        assertFalse(PlayerDataManager.verifyPassword("secret", "not-a-password-hash"));
        assertFalse(PlayerDataManager.verifyPassword("secret", "bad-base64:also-bad"));
        assertFalse(PlayerDataManager.isLegacyBcrypt(null));
        assertFalse(PlayerDataManager.isLegacyBcrypt("not-bcrypt"));
    }

    @Test
    void registeringAnEmptyEasyAuthRecordPreservesMetadata() {
        PlayerDataManager.PlayerData data = new PlayerDataManager.PlayerData(
                "Legacy_User", UUID.fromString("00000000-0000-0000-0000-000000000123"));
        data.setPasswordHash("");
        data.setRegistrationTime("2025-01-02T03:04:05");
        data.setLoginCount(7);
        data.setLastIp("127.0.0.2");
        data.setLastAuthenticatedTime("2025-02-03T04:05:06");
        data.setLoginTries(3);
        data.setLastKickedTime(null);
        data.setOnlineAccount("false");
        data.setSourceDataVersion(1);
        data.setLegacyPremiumAutoLogin(true);

        data = PlayerDataManager.prepareRegistration(data, "Legacy_User", "new-secret",
                UUID.fromString("00000000-0000-0000-0000-000000000999"));
        assertNotNull(data);
        assertTrue(data.hasPassword());
        assertTrue(PlayerDataManager.verifyPassword("new-secret", data.getPasswordHash()));
        assertEquals("bcrypt", data.getPasswordScheme());
        assertEquals(UUID.fromString("00000000-0000-0000-0000-000000000123"), data.getUuid());
        assertEquals("2025-01-02T03:04:05", data.getRegistrationTime());
        assertEquals(7, data.getLoginCount());
        assertEquals("127.0.0.2", data.getLastIp());
        assertEquals("2025-02-03T04:05:06", data.getLastAuthenticatedTime());
        assertEquals(3, data.getLoginTries());
        assertTrue(data.isLegacyPremiumAutoLogin());
    }
}

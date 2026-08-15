package org.xiyu.yee.xiyuslogin.data;

import at.favre.lib.crypto.bcrypt.BCrypt;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonArray;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;
import com.google.gson.reflect.TypeToken;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.item.ItemStack;
import org.xiyu.yee.xiyuslogin.Xiyuslogin;

import java.io.*;
import java.lang.reflect.Type;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.List;
import java.util.regex.Pattern;

public class PlayerDataManager {
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().serializeNulls().create();
    private static final String DATA_FILE = "xiyus_player_data.json";
    private static final String PASSWORD_RESET_FILE = "xiyus_password_reset_requests.json";
    private static final String INVENTORY_BACKUP_DIR = "xiyus_player_inventories";
    private static final int PASSWORD_RESET_BCRYPT_COST = 12;
    private static final int PASSWORD_RESET_DATA_VERSION = 2;
    private static final String PASSWORD_RESET_SCHEME = "bcrypt";
    private static final Pattern BCRYPT_PATTERN = Pattern.compile(
            "\\A\\$2[aby]\\$(0[4-9]|[12][0-9]|3[01])\\$[./A-Za-z0-9]{53}\\z");
    
    private final File dataFile;
    private final File passwordResetFile;
    private final File inventoryBackupDir;
    private final Map<String, PlayerData> playerDataMap = new HashMap<>();
    private final Map<String, PasswordResetRequest> passwordResetRequests = new HashMap<>();
    
    public PlayerDataManager(MinecraftServer server) {
        this(server.getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toFile());
    }

    PlayerDataManager(File worldDir) {
        this.dataFile = new File(worldDir, DATA_FILE);
        this.passwordResetFile = new File(worldDir, PASSWORD_RESET_FILE);
        this.inventoryBackupDir = new File(worldDir, INVENTORY_BACKUP_DIR);
        
        if (!inventoryBackupDir.exists()) {
            inventoryBackupDir.mkdirs();
        }
        
        loadData();
    }

    static PlayerDataManager fromWorldDirectory(File worldDir) {
        return new PlayerDataManager(worldDir);
    }

    public void loadData() {
        loadPlayerData();
        loadPasswordResetRequests();
    }
    
    private void loadPlayerData() {
        if (!dataFile.exists()) {
            return;
        }
        
        try (FileReader reader = new FileReader(dataFile, StandardCharsets.UTF_8)) {
            Type type = new TypeToken<Map<String, PlayerData>>() {}.getType();
            Map<String, PlayerData> loaded = GSON.fromJson(reader, type);
            if (loaded != null) {
                playerDataMap.putAll(loaded);
                Xiyuslogin.LOGGER.info("Loaded {} player records from data file", loaded.size());
                // 调试：打印加载的玩家名称
                for (String username : loaded.keySet()) {
                    Xiyuslogin.LOGGER.debug("Loaded player data for: {}", username);
                }
            } else {
                Xiyuslogin.LOGGER.warn("Player data file exists but contains no valid data");
            }
        } catch (IOException e) {
            Xiyuslogin.LOGGER.error("Failed to load player data", e);
        }
    }
    
    private void loadPasswordResetRequests() {
        if (!passwordResetFile.exists()) {
            return;
        }

        Map<String, PasswordResetRequest> loaded = new HashMap<>();
        boolean migrated = false;
        try (Reader reader = Files.newBufferedReader(passwordResetFile.toPath(), StandardCharsets.UTF_8)) {
            JsonElement root = JsonParser.parseReader(reader);
            if (!root.isJsonObject()) {
                throw new IllegalStateException("reset request root is not an object");
            }

            for (Map.Entry<String, JsonElement> entry : root.getAsJsonObject().entrySet()) {
                if (!entry.getValue().isJsonObject()) {
                    throw new IllegalStateException("reset request entry is not an object");
                }

                JsonObject requestJson = entry.getValue().getAsJsonObject();
                String newPasswordHash = optionalJsonString(requestJson, "newPasswordHash");
                String legacyPassword = optionalJsonString(requestJson, "newPassword");

                // Migrate the old plaintext field in memory, then persist only the
                // derived BCrypt hash. The plaintext is never put back in the JSON tree.
                if (!isBcryptHash(newPasswordHash)) {
                    if (legacyPassword == null || legacyPassword.isEmpty()) {
                        throw new IllegalStateException("reset request has no supported password proof");
                    }
                    newPasswordHash = hashPasswordForReset(legacyPassword);
                    requestJson.addProperty("newPasswordHash", newPasswordHash);
                    migrated = true;
                }
                if (requestJson.has("newPassword")) {
                    requestJson.remove("newPassword");
                    migrated = true;
                }
                if (!PASSWORD_RESET_SCHEME.equalsIgnoreCase(optionalJsonString(requestJson, "passwordScheme"))) {
                    requestJson.addProperty("passwordScheme", PASSWORD_RESET_SCHEME);
                    migrated = true;
                }
                if (requestJson.has("requestDataVersion")
                        && requestJson.get("requestDataVersion").isJsonPrimitive()
                        && requestJson.get("requestDataVersion").getAsInt() == PASSWORD_RESET_DATA_VERSION) {
                    // Already at the current schema version.
                } else {
                    requestJson.addProperty("requestDataVersion", PASSWORD_RESET_DATA_VERSION);
                    migrated = true;
                }

                PasswordResetRequest request = GSON.fromJson(requestJson, PasswordResetRequest.class);
                if (!isValidResetRequest(request)) {
                    throw new IllegalStateException("reset request is missing required fields");
                }
                loaded.put(entry.getKey().toLowerCase(java.util.Locale.ROOT), request);
            }
        } catch (IOException | RuntimeException e) {
            // Do not continue with an ambiguous request file. In particular, never
            // log parser details because they can contain user-controlled values.
            throw new IllegalStateException("Unable to load password reset requests safely");
        }

        passwordResetRequests.clear();
        passwordResetRequests.putAll(loaded);
        if (migrated) {
            savePasswordResetRequests();
        }
    }
    
    public void saveData() {
        savePlayerData();
        savePasswordResetRequests();
    }
    
    private void savePlayerData() {
        try {
            if (!dataFile.getParentFile().exists()) {
                dataFile.getParentFile().mkdirs();
            }
            
            try (FileWriter writer = new FileWriter(dataFile, StandardCharsets.UTF_8)) {
                GSON.toJson(playerDataMap, writer);
            }
        } catch (IOException e) {
            Xiyuslogin.LOGGER.error("Failed to save player data", e);
        }
    }
    
    private void savePasswordResetRequests() {
        Path target = passwordResetFile.toPath();
        Path parent = target.getParent();
        Path temporary = null;
        try {
            if (parent == null) {
                throw new IllegalStateException("reset request file has no parent directory");
            }
            Files.createDirectories(parent);
            for (PasswordResetRequest request : passwordResetRequests.values()) {
                if (!isValidResetRequest(request)) {
                    throw new IllegalStateException("refusing to persist an invalid reset request");
                }
            }

            temporary = Files.createTempFile(parent, passwordResetFile.getName() + ".", ".tmp");
            try (Writer writer = Files.newBufferedWriter(temporary, StandardCharsets.UTF_8)) {
                GSON.toJson(passwordResetRequests, writer);
            }
            try {
                Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException e) {
                Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
            }
            temporary = null;
        } catch (IOException | RuntimeException e) {
            throw new IllegalStateException("Unable to persist password reset requests safely", e);
        } finally {
            if (temporary != null) {
                try {
                    Files.deleteIfExists(temporary);
                } catch (IOException ignored) {
                    // Best-effort cleanup; the target file remains untouched.
                }
            }
        }
    }

    private static String optionalJsonString(JsonObject object, String name) {
        JsonElement value = object.get(name);
        if (value == null || value.isJsonNull()) {
            return null;
        }
        if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString()) {
            throw new IllegalStateException("reset request field is not a string");
        }
        return value.getAsString();
    }

    private static String hashPasswordForReset(String password) {
        if (password == null || password.isEmpty()) {
            throw new IllegalArgumentException("reset password must not be empty");
        }
        char[] passwordChars = password.toCharArray();
        try {
            return BCrypt.withDefaults().hashToString(PASSWORD_RESET_BCRYPT_COST, passwordChars);
        } finally {
            Arrays.fill(passwordChars, '\0');
        }
    }

    private static boolean isBcryptHash(String hash) {
        return hash != null && BCRYPT_PATTERN.matcher(hash).matches();
    }

    private static boolean isValidResetRequest(PasswordResetRequest request) {
        return request != null
                && request.username != null
                && !request.username.isEmpty()
                && isBcryptHash(request.newPasswordHash)
                && PASSWORD_RESET_SCHEME.equalsIgnoreCase(request.passwordScheme)
                && request.requestDataVersion == PASSWORD_RESET_DATA_VERSION;
    }
    
    public boolean registerPlayer(String username, String password, UUID uuid) {
        if (playerDataMap.containsKey(username.toLowerCase())
                && playerDataMap.get(username.toLowerCase()).hasPassword()) {
            return false; // 用户已存在
        }
        
        String key = username.toLowerCase();
        PlayerData playerData = prepareRegistration(playerDataMap.get(key), username, password, uuid);
        
        playerDataMap.put(key, playerData);
        saveData();
        return true;
    }

    static PlayerData prepareRegistration(PlayerData playerData, String username, String password, UUID uuid) {
        if (playerData == null) {
            playerData = new PlayerData(username, uuid);
        } else {
            // Reuse an empty EasyAuth record so its UUID and audit metadata survive registration.
            playerData.setUsername(username);
            if (playerData.getUuid() == null) {
                playerData.setUuid(uuid);
            }
        }
        playerData.setPasswordHash(hashPassword(password));
        playerData.setPasswordScheme(PASSWORD_RESET_SCHEME);
        if (playerData.getRegistrationTime() == null || playerData.getRegistrationTime().isEmpty()) {
            playerData.setRegistrationTime(LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME));
        }
        return playerData;
    }
    
    public boolean loginPlayer(String username, String password) {
        PlayerData playerData = playerDataMap.get(username.toLowerCase());
        if (playerData == null) {
            return false; // 用户不存在
        }
        
        String storedHash = playerData.getPasswordHash();
        boolean verified = verifyPassword(password, storedHash);
        if (verified && !isBcryptHash(storedHash)) {
            // Upgrade the legacy salted SHA-256 representation after a successful
            // verification. Existing BCrypt hashes are deliberately left intact.
            playerData.setPasswordHash(hashPassword(password));
            playerData.setPasswordScheme(PASSWORD_RESET_SCHEME);
            saveData();
        } else if (verified && !PASSWORD_RESET_SCHEME.equalsIgnoreCase(playerData.getPasswordScheme())) {
            playerData.setPasswordScheme(PASSWORD_RESET_SCHEME);
            saveData();
        }
        return verified;
    }
    
    public PlayerData getPlayerData(String username) {
        return playerDataMap.get(username.toLowerCase());
    }

    public boolean resetPassword(String username, String newPassword) {
        PlayerData playerData = playerDataMap.get(username.toLowerCase());
        if (playerData == null) {
            return false;
        }

        playerData.setPasswordHash(hashPassword(newPassword));
        playerData.setPasswordScheme(PASSWORD_RESET_SCHEME);
        saveData();
        return true;
    }
    
    public boolean isPlayerRegistered(String username) {
        String lowerUsername = username.toLowerCase();
        PlayerData playerData = playerDataMap.get(lowerUsername);
        boolean isRegistered = playerData != null && playerData.hasPassword();
        Xiyuslogin.LOGGER.debug("Checking registration for '{}' (key: '{}'): {}", username, lowerUsername, isRegistered);
        Xiyuslogin.LOGGER.debug("Available players in map: {}", playerDataMap.keySet());
        return isRegistered;
    }
    
    // 密码重置请求管理
    public void addPasswordResetRequest(String username, String reason, String newPassword, UUID requesterUUID) {
        String safeReason = redactResetReason(reason, newPassword);
        PasswordResetRequest request = PasswordResetRequest.fromPassword(
            username, safeReason, newPassword, requesterUUID,
            LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME)
        );
        passwordResetRequests.put(username.toLowerCase(java.util.Locale.ROOT), request);
        savePasswordResetRequests();
    }
    
    public Map<String, PasswordResetRequest> getPasswordResetRequests() {
        return new HashMap<>(passwordResetRequests);
    }
    
    public PasswordResetRequest getPasswordResetRequest(String username) {
        return passwordResetRequests.get(username.toLowerCase(java.util.Locale.ROOT));
    }
    
    public boolean approvePasswordReset(String username) {
        String key = username.toLowerCase(java.util.Locale.ROOT);
        PasswordResetRequest request = passwordResetRequests.get(key);
        if (request == null) {
            return false;
        }
        
        PlayerData playerData = playerDataMap.get(key);
        if (playerData == null) {
            return false;
        }
        
        // 更新密码
        // The pending request contains only a BCrypt proof; plaintext is never
        // reconstructed or passed through the administrator command path.
        if (!isValidResetRequest(request)) {
            return false;
        }
        playerData.setPasswordHash(request.newPasswordHash);
        playerData.setPasswordScheme(PASSWORD_RESET_SCHEME);
        passwordResetRequests.remove(key);
        
        saveData();
        return true;
    }
    
    public boolean rejectPasswordReset(String username) {
        PasswordResetRequest request = passwordResetRequests.remove(username.toLowerCase(java.util.Locale.ROOT));
        if (request != null) {
            savePasswordResetRequests();
            return true;
        }
        return false;
    }
    
    // 背包备份和恢复
    public boolean backupPlayerInventory(String username, List<ItemStack> inventory, List<ItemStack> armor, List<ItemStack> offhand) {
        try {
            File backupFile = new File(inventoryBackupDir, username.toLowerCase() + ".json");
            
            JsonObject backupData = new JsonObject();
            backupData.add("inventory", GSON.toJsonTree(inventory));
            backupData.add("armor", GSON.toJsonTree(armor));
            backupData.add("offhand", GSON.toJsonTree(offhand));
            backupData.addProperty("timestamp", LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME));
            
            try (FileWriter writer = new FileWriter(backupFile, StandardCharsets.UTF_8)) {
                GSON.toJson(backupData, writer);
            }
            
            return true;
        } catch (IOException e) {
            Xiyuslogin.LOGGER.error("Failed to backup inventory for {}: {}", username, e.getMessage());
            return false;
        }
    }
    
    public boolean restorePlayerInventory(String username, net.minecraft.server.level.ServerPlayer player) {
        try {
            File backupFile = new File(inventoryBackupDir, username.toLowerCase() + ".json");
            if (!backupFile.exists()) {
                return false;
            }
            
            JsonObject backupData;
            try (FileReader reader = new FileReader(backupFile, StandardCharsets.UTF_8)) {
                backupData = GSON.fromJson(reader, JsonObject.class);
            }
            
            if (backupData != null) {
                // 这里需要实现物品栈的反序列化和设置
                // 由于涉及到复杂的Minecraft物品系统，先留空实现
                Xiyuslogin.LOGGER.info("Inventory backup found for {}, restoration logic to be implemented", username);
                
                // 删除备份文件
                backupFile.delete();
                return true;
            }
            
            return false;
        } catch (IOException e) {
            Xiyuslogin.LOGGER.error("Failed to restore inventory for {}: {}", username, e.getMessage());
            return false;
        }
    }
    
    static String hashPassword(String password) {
        return hashPasswordForReset(password);
    }

    static String hashLegacySha256Password(String password) {
        try {
            SecureRandom random = new SecureRandom();
            byte[] salt = new byte[16];
            random.nextBytes(salt);
            
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            md.update(salt);
            byte[] hashedPassword = md.digest(password.getBytes(StandardCharsets.UTF_8));
            
            return Base64.getEncoder().encodeToString(salt) + ":" + 
                   Base64.getEncoder().encodeToString(hashedPassword);
        } catch (Exception e) {
            throw new RuntimeException("Failed to hash password", e);
        }
    }
    
    static boolean verifyPassword(String password, String storedHash) {
        try {
            if (storedHash == null || storedHash.isEmpty()) {
                return false;
            }
            if (storedHash.startsWith("$2a$") || storedHash.startsWith("$2b$")
                    || storedHash.startsWith("$2y$")) {
                return BCrypt.verifyer().verify(password.toCharArray(), storedHash).verified;
            }
            String[] parts = storedHash.split(":");
            if (parts.length != 2) {
                return false;
            }
            
            byte[] salt = Base64.getDecoder().decode(parts[0]);
            byte[] storedPasswordHash = Base64.getDecoder().decode(parts[1]);
            
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            md.update(salt);
            byte[] passwordHash = md.digest(password.getBytes(StandardCharsets.UTF_8));
            
            return MessageDigest.isEqual(storedPasswordHash, passwordHash);
        } catch (Exception e) {
            return false;
        }
    }

    static boolean isLegacyBcrypt(String storedHash) {
        return storedHash != null && (storedHash.startsWith("$2a$")
                || storedHash.startsWith("$2b$") || storedHash.startsWith("$2y$"));
    }

    public static String redactResetReason(String reason, String password) {
        if (reason == null || reason.isEmpty() || password == null || password.isEmpty()) {
            return reason == null ? "" : reason;
        }
        return reason.replace(password, "[redacted]");
    }
    
    // 内部类
    public static class PlayerData {
        private String username;
        private UUID uuid;
        private String passwordHash;
        private String registrationTime;
        private String lastLoginTime;
        private int loginCount;
        private String lastIp;
        private String lastAuthenticatedTime;
        private long loginTries;
        private String lastKickedTime;
        private String onlineAccount;
        private int sourceDataVersion;
        private boolean legacyPremiumAutoLogin;
        private String passwordScheme;
        
        public PlayerData(String username, UUID uuid) {
            this.username = username;
            this.uuid = uuid;
            this.loginCount = 0;
            this.sourceDataVersion = 1;
            this.passwordScheme = PASSWORD_RESET_SCHEME;
        }
        
        // Getters and Setters
        public String getUsername() { return username; }
        public void setUsername(String username) { this.username = username; }
        
        public UUID getUuid() { return uuid; }
        public void setUuid(UUID uuid) { this.uuid = uuid; }
        
        public String getPasswordHash() { return passwordHash; }
        public void setPasswordHash(String passwordHash) { this.passwordHash = passwordHash; }

        public boolean hasPassword() { return passwordHash != null && !passwordHash.isEmpty(); }

        public String getPasswordScheme() { return passwordScheme; }
        public void setPasswordScheme(String passwordScheme) { this.passwordScheme = passwordScheme; }
        
        public String getRegistrationTime() { return registrationTime; }
        public void setRegistrationTime(String registrationTime) { this.registrationTime = registrationTime; }
        
        public String getLastLoginTime() { return lastLoginTime; }
        public void setLastLoginTime(String lastLoginTime) { this.lastLoginTime = lastLoginTime; }
        
        public int getLoginCount() { return loginCount; }
        public void setLoginCount(int loginCount) { this.loginCount = loginCount; }
        
        public void incrementLoginCount() { this.loginCount++; }

        public String getLastIp() { return lastIp; }
        public void setLastIp(String lastIp) { this.lastIp = lastIp; }

        public String getLastAuthenticatedTime() { return lastAuthenticatedTime; }
        public void setLastAuthenticatedTime(String lastAuthenticatedTime) { this.lastAuthenticatedTime = lastAuthenticatedTime; }

        public long getLoginTries() { return loginTries; }
        public void setLoginTries(long loginTries) { this.loginTries = loginTries; }

        public String getLastKickedTime() { return lastKickedTime; }
        public void setLastKickedTime(String lastKickedTime) { this.lastKickedTime = lastKickedTime; }

        public String getOnlineAccount() { return onlineAccount; }
        public void setOnlineAccount(String onlineAccount) { this.onlineAccount = onlineAccount; }

        public int getSourceDataVersion() { return sourceDataVersion; }
        public void setSourceDataVersion(int sourceDataVersion) { this.sourceDataVersion = sourceDataVersion; }

        public boolean isLegacyPremiumAutoLogin() { return legacyPremiumAutoLogin; }
        public void setLegacyPremiumAutoLogin(boolean legacyPremiumAutoLogin) { this.legacyPremiumAutoLogin = legacyPremiumAutoLogin; }
    }
    
    public static class PasswordResetRequest {
        private String username;
        private String reason;
        private String newPasswordHash;
        private String passwordScheme;
        private int requestDataVersion;
        private UUID requesterUUID;
        private String requestTime;
        private String status; // "pending", "approved", "rejected"
        
        private PasswordResetRequest(String username, String reason, String newPasswordHash,
                                     UUID requesterUUID, String requestTime, String passwordScheme,
                                     int requestDataVersion) {
            this.username = username;
            this.reason = reason;
            this.newPasswordHash = newPasswordHash;
            this.passwordScheme = passwordScheme;
            this.requestDataVersion = requestDataVersion;
            this.requesterUUID = requesterUUID;
            this.requestTime = requestTime;
            this.status = "pending";
        }

        private static PasswordResetRequest fromPassword(String username, String reason, String password,
                                                         UUID requesterUUID, String requestTime) {
            return new PasswordResetRequest(username, reason, hashPasswordForReset(password), requesterUUID,
                    requestTime, PASSWORD_RESET_SCHEME, PASSWORD_RESET_DATA_VERSION);
        }
        
        // Getters and Setters
        public String getUsername() { return username; }
        public String getReason() { return reason; }
        public UUID getRequesterUUID() { return requesterUUID; }
        public String getRequestTime() { return requestTime; }
        public String getStatus() { return status; }
        public String getPasswordScheme() { return passwordScheme; }
        public int getRequestDataVersion() { return requestDataVersion; }
        public void setStatus(String status) { this.status = status; }
    }
}

package net.conczin.immersive_paintings.neoforge.compat;

import net.conczin.immersive_paintings.ClientPaintingManager;
import net.conczin.immersive_paintings.Main;
import net.conczin.immersive_paintings.Painting;
import net.conczin.immersive_paintings.entity.ImmersivePaintingEntity;
import net.conczin.immersive_paintings.registration.Configs;
import net.conczin.immersive_paintings.util.Cache;
import net.minecraft.client.Minecraft;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import net.minecraft.world.entity.projectile.ProjectileUtil;
import net.neoforged.fml.ModList;
import net.neoforged.neoforge.client.event.ClientTickEvent;
import net.neoforged.neoforge.common.NeoForge;

import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Optional client-only bridge between Immersive Paintings and MineAstr.
 *
 * <p>The bridge deliberately uses reflection so a client without MineAstr can
 * continue loading Immersive Paintings.  Images still travel through the
 * existing Immersive Paintings cache and MineAstr's public translation API;
 * this class never connects to AstrBot directly.</p>
 */
public final class MineAstrTranslationCompat {
    static final int MAX_IMAGE_BYTES = MineAstrImageCodec.MAX_IMAGE_BYTES;
    static final int MAX_IMAGE_DIMENSION = MineAstrImageCodec.MAX_IMAGE_DIMENSION;

    private static final String MINEASTR_MOD_ID = "mineastr";
    private static final long RETRY_DELAY_MS = 30_000L;
    private static final String CONTEXT =
            "This image is displayed by Immersive Paintings. Preserve proper nouns and line breaks.";
    private static final String PROMPT =
            "Translate only text visible in the image. Do not describe the image. "
                    + "Preserve line breaks and return plain text.";

    private static final ExecutorService IMAGE_ENCODER = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, "ImmersivePaintings-MineAstrEncoder");
        thread.setDaemon(true);
        return thread;
    });

    private static final Cache<TranslationKey, Translation> TRANSLATIONS = new TranslationCache();
    private static final Map<TranslationKey, Long> RETRY_AT = new HashMap<>();
    private static final Set<TranslationKey> PENDING = new HashSet<>();

    private static Method requestImageTranslation;
    private static Method resultSourceText;
    private static Method resultTranslations;
    private static Method showEntityTranslation;
    private static Method removeTranslation;
    private static Method floatingTranslationsEnabled;
    private static Method floatingTranslationMaxDistance;
    private static Object translationsEnabledValue;
    private static Method translationsEnabledGetter;

    private static boolean initialized;
    private static boolean available;
    private static Object activeLevel;
    private static String activeDisplayId;

    private MineAstrTranslationCompat() {
    }

    /** Called from the NeoForge client setup event, never on a dedicated server. */
    public static void initialize() {
        if (initialized) {
            return;
        }
        initialized = true;
        if (!ModList.get().isLoaded(MINEASTR_MOD_ID)) {
            return;
        }

        try {
            Class<?> clientClass = Class.forName("com.mineastr.MineAstrClient");
            Class<?> resultClass = Class.forName("com.mineastr.MineAstrPayloads$ImageTranslationResult");
            Class<?> displayClass = Class.forName("com.mineastr.api.MineAstrDisplayApi");

            requestImageTranslation = clientClass.getMethod(
                    "requestImageTranslation",
                    byte[].class,
                    String.class,
                    List.class,
                    String.class,
                    String.class);
            resultSourceText = resultClass.getMethod("sourceText");
            resultTranslations = resultClass.getMethod("translations");
            try {
                showEntityTranslation = displayClass.getMethod(
                        "showEntityTranslation",
                        String.class,
                        int.class,
                        Vec3.class,
                        String.class,
                        String.class,
                        boolean.class);
            } catch (NoSuchMethodException missingSixArgumentApi) {
                // The five-argument API cannot render a custom ray target safely;
                // keep the bridge disabled instead of showing stale overlays.
                throw new ReflectiveOperationException(
                        "MineAstr 0.6.27 six-argument display API is required",
                        missingSixArgumentApi);
            }
            removeTranslation = displayClass.getMethod("remove", String.class);
            floatingTranslationsEnabled = clientClass.getMethod("areFloatingTranslationOverlaysEnabled");
            floatingTranslationMaxDistance = clientClass.getMethod("floatingTranslationMaxDistance");
            findTranslationsEnabledGetter();

            available = true;
            NeoForge.EVENT_BUS.addListener(MineAstrTranslationCompat::onClientTick);
            Main.LOGGER.info("Enabled optional MineAstr painting translation integration");
        } catch (LinkageError | ReflectiveOperationException error) {
            Main.LOGGER.warn(
                    "MineAstr is installed but its image translation API is unavailable; "
                            + "MineAstr 0.6.27 is required",
                    error);
        }
    }

    public static void onClientTick(ClientTickEvent.Post event) {
        if (available) {
            tick(Minecraft.getInstance());
        }
    }

    private static void findTranslationsEnabledGetter() {
        try {
            Class<?> configClass = Class.forName("com.mineastr.MineAstrClientConfig");
            translationsEnabledValue = configClass.getField("GAME_TRANSLATIONS_ENABLED").get(null);
            translationsEnabledGetter = translationsEnabledValue.getClass().getMethod("getAsBoolean");
        } catch (ReflectiveOperationException | RuntimeException error) {
            translationsEnabledValue = null;
            translationsEnabledGetter = null;
            Main.LOGGER.debug(
                    "MineAstr translation preference could not be read; "
                            + "the public image API remains enabled",
                    error);
        }
    }

    private static void tick(Minecraft client) {
        if (client.level != activeLevel) {
            resetForLevel(client.level);
        }

        ImmersivePaintingEntity painting = getTargetedPainting(client);
        if (!translationsEnabled() || client.screen != null || client.options.hideGui || painting == null) {
            removeActiveDisplay();
            return;
        }

        ResourceLocation motive = painting.getMotive();
        if (motive.equals(Main.locate("none"))) {
            removeActiveDisplay();
            return;
        }

        if (!Configs.CLIENT.showNSFWPaintings
                && ClientPaintingManager.getPainting(motive)
                .map(metadata -> metadata.has(Painting.Flag.NSFW))
                .orElse(false)) {
            removeActiveDisplay();
            return;
        }

        String language = normalizeLanguage(client.getLanguageManager().getSelected());
        if (language.isBlank()) {
            removeActiveDisplay();
            return;
        }

        TranslationKey key = new TranslationKey(getImageCacheKey(motive), language);
        Translation translation = TRANSLATIONS.get(key).orElse(null);
        if (translation != null) {
            if (translation.translated().isBlank()) {
                removeActiveDisplay();
            } else {
                showTranslation(painting, key, translation);
            }
            return;
        }

        removeActiveDisplay();
        long now = System.currentTimeMillis();
        if (!PENDING.isEmpty() || RETRY_AT.getOrDefault(key, 0L) > now) {
            return;
        }

        ClientPaintingManager.getFullImage(motive)
                .ifPresent(image -> requestTranslation(client, key, image));
    }

    /**
     * Resolves a painting even when the pack disables painting collision. The
     * vanilla hit result then cannot be an EntityHitResult, so MineAstr's
     * floating overlay targeter is mirrored with ProjectileUtil instead.
     */
    private static ImmersivePaintingEntity getTargetedPainting(Minecraft client) {
        if (client.level == null || client.player == null) {
            return null;
        }

        Player player = client.player;
        double maxDistance = Math.min(mineAstrTargetDistance(), player.entityInteractionRange());
        maxDistance = Math.max(1.0D, maxDistance);
        Vec3 eye = player.getEyePosition(1.0F);
        Vec3 view = player.getViewVector(1.0F);

        if (client.hitResult instanceof EntityHitResult entityHit
                && entityHit.getEntity() instanceof ImmersivePaintingEntity painting
                && eye.distanceTo(entityHit.getLocation()) <= maxDistance + 1.0E-4D) {
            return painting;
        }

        double rayDistance = maxDistance;
        if (client.hitResult != null && client.hitResult.getType() != HitResult.Type.MISS) {
            rayDistance = Math.min(
                    rayDistance,
                    eye.distanceTo(client.hitResult.getLocation()) + 0.25D);
        }

        Vec3 end = eye.add(view.scale(rayDistance));
        AABB search = player.getBoundingBox()
                .expandTowards(view.scale(rayDistance))
                .inflate(1.0D);
        EntityHitResult result = ProjectileUtil.getEntityHitResult(
                player,
                eye,
                end,
                search,
                entity -> entity instanceof ImmersivePaintingEntity
                        && !entity.isRemoved(),
                rayDistance * rayDistance);
        if (result != null && result.getEntity() instanceof ImmersivePaintingEntity painting) {
            return painting;
        }
        return null;
    }

    private static boolean translationsEnabled() {
        try {
            boolean gameEnabled = translationsEnabledValue == null || translationsEnabledGetter == null
                    || (Boolean) translationsEnabledGetter.invoke(translationsEnabledValue);
            boolean overlaysEnabled = floatingTranslationsEnabled == null
                    || (Boolean) floatingTranslationsEnabled.invoke(null);
            return gameEnabled && overlaysEnabled;
        } catch (ReflectiveOperationException | RuntimeException error) {
            Main.LOGGER.debug("Unable to read MineAstr's game translation preference", error);
            return false;
        }
    }

    private static double mineAstrTargetDistance() {
        if (floatingTranslationMaxDistance == null) {
            return 8.0D;
        }
        try {
            Object value = floatingTranslationMaxDistance.invoke(null);
            return Math.max(1.0D, ((Number) value).doubleValue());
        } catch (ReflectiveOperationException | RuntimeException error) {
            Main.LOGGER.debug("Unable to read MineAstr's target distance; using 8 blocks", error);
            return 8.0D;
        }
    }

    private static void requestTranslation(
            Minecraft client,
            TranslationKey key,
            BufferedImage image) {
        if (!PENDING.add(key)) {
            return;
        }

        CompletableFuture.supplyAsync(() -> {
            try {
                return encodeForMineAstr(image);
            } catch (IOException error) {
                throw new CompletionException(error);
            }
        }, IMAGE_ENCODER)
                .thenCompose(bytes -> invokeTranslationRequest(bytes, key.language()))
                .whenComplete((result, error) ->
                        client.execute(() -> finishRequest(key, result, error)));
    }

    @SuppressWarnings("unchecked")
    private static CompletableFuture<Object> invokeTranslationRequest(
            byte[] imageBytes,
            String language) {
        try {
            Object result = requestImageTranslation.invoke(
                    null,
                    imageBytes,
                    "image/jpeg",
                    List.of(language),
                    CONTEXT,
                    PROMPT);
            if (result instanceof CompletableFuture<?> future) {
                return (CompletableFuture<Object>) future;
            }
            return CompletableFuture.failedFuture(
                    new IllegalStateException("MineAstr returned an unsupported async result"));
        } catch (IllegalAccessException error) {
            return CompletableFuture.failedFuture(error);
        } catch (InvocationTargetException error) {
            return CompletableFuture.failedFuture(
                    error.getCause() == null ? error : error.getCause());
        }
    }

    private static void finishRequest(
            TranslationKey key,
            Object result,
            Throwable error) {
        PENDING.remove(key);
        if (error != null) {
            RETRY_AT.put(key, System.currentTimeMillis() + RETRY_DELAY_MS);
            Main.LOGGER.debug(
                    "MineAstr image translation failed for {}",
                    key.imageKey(),
                    unwrap(error));
            return;
        }

        try {
            String source = stringValue(resultSourceText.invoke(result));
            Object translationValue = resultTranslations.invoke(result);
            Map<?, ?> translations = translationValue instanceof Map<?, ?> map ? map : Map.of();
            String translated = selectTranslation(translations, key.language());
            if (translated.isBlank()) {
                translated = source;
            }

            TRANSLATIONS.set(key, new Translation(translated.strip(), source.strip()));
            RETRY_AT.remove(key);
            Main.LOGGER.debug("Cached MineAstr image translation for {}", key.imageKey());
        } catch (ReflectiveOperationException | RuntimeException extractionError) {
            RETRY_AT.put(key, System.currentTimeMillis() + RETRY_DELAY_MS);
            Main.LOGGER.warn(
                    "MineAstr returned an unreadable image translation result",
                    extractionError);
        }
    }

    static String selectTranslation(Map<?, ?> translations, String language) {
        return MineAstrImageCodec.selectTranslation(translations, language);
    }

    private static void showTranslation(
            ImmersivePaintingEntity painting,
            TranslationKey key,
            Translation translation) {
        String displayId = "immersive-painting:"
                + painting.getId()
                + ":"
                + digest(key.imageKey()).substring(0, 12);
        if (!displayId.equals(activeDisplayId)) {
            removeActiveDisplay();
            activeDisplayId = displayId;
        }

        try {
            showEntityTranslation.invoke(
                    null,
                    displayId,
                    painting.getId(),
                    new Vec3(0.0, painting.getBbHeight() + 0.2, 0.0),
                    translation.translated(),
                    translation.original(),
                    false);
        } catch (ReflectiveOperationException | RuntimeException error) {
            Main.LOGGER.warn(
                    "Failed to submit a painting translation to MineAstr's display API",
                    error);
            removeActiveDisplay();
        }
    }

    private static void resetForLevel(Object level) {
        activeLevel = level;
        RETRY_AT.clear();
        removeActiveDisplay();
    }

    private static String getImageCacheKey(ResourceLocation motive) {
        return ClientPaintingManager.getPainting(motive)
                .map(painting -> {
                    String hash = painting.hash();
                    if (!hash.isBlank()) {
                        return painting.type().getSerializedName().toLowerCase(Locale.ROOT)
                                + ":"
                                + hash;
                    }
                    return motive.toString();
                })
                .orElse(motive.toString());
    }

    private static void removeActiveDisplay() {
        String displayId = activeDisplayId;
        activeDisplayId = null;
        if (displayId == null || removeTranslation == null) {
            return;
        }

        try {
            removeTranslation.invoke(null, displayId);
        } catch (ReflectiveOperationException | RuntimeException error) {
            Main.LOGGER.debug(
                    "Failed to remove a MineAstr painting translation display",
                    error);
        }
    }

    static byte[] encodeForMineAstr(BufferedImage source) throws IOException {
        return MineAstrImageCodec.encodeForMineAstr(source);
    }

    static String normalizeLanguage(String language) {
        return MineAstrImageCodec.normalizeLanguage(language);
    }

    private static String stringValue(Object value) {
        return value == null ? "" : value.toString();
    }

    private static Throwable unwrap(Throwable error) {
        Throwable current = error;
        while ((current instanceof CompletionException || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    private static String digest(String value) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder(bytes.length * 2);
            for (byte valueByte : bytes) {
                result.append(String.format(Locale.ROOT, "%02x", valueByte & 0xff));
            }
            return result.toString();
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is unavailable", error);
        }
    }

    private record TranslationKey(String imageKey, String language) {
    }

    private record Translation(String translated, String original) {
    }

    private static final class TranslationCache extends Cache<TranslationKey, Translation> {
        private static final int FORMAT_VERSION = 1;

        private TranslationCache() {
            super(512);
        }

        @Override
        public String getCachePath(TranslationKey key) {
            return "translations-v1/"
                    + digest(key.imageKey() + '\0' + key.language())
                    + ".bin";
        }

        @Override
        public Translation decode(byte[] bytes) throws IOException {
            try (DataInputStream input = new DataInputStream(new ByteArrayInputStream(bytes))) {
                if (input.readInt() != FORMAT_VERSION) {
                    throw new IOException("Unsupported MineAstr translation cache version");
                }
                return new Translation(input.readUTF(), input.readUTF());
            }
        }

        @Override
        public byte[] encode(Translation translation) {
            try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                 DataOutputStream output = new DataOutputStream(bytes)) {
                output.writeInt(FORMAT_VERSION);
                output.writeUTF(translation.translated());
                output.writeUTF(translation.original());
                output.flush();
                return bytes.toByteArray();
            } catch (IOException error) {
                Main.LOGGER.warn("Failed to encode MineAstr translation cache entry", error);
                return null;
            }
        }
    }
}

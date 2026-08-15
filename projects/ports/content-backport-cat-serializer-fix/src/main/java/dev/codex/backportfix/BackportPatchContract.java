package dev.codex.backportfix;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

final class BackportPatchContract {
    static final String EXPECTED_INPUT_SHA256 =
            "167534c66d5e6c09dcb01152ebd37d18ced5cf6278a9228c094f937886133af5";

    static final String SERIALIZER_OWNER =
            "com/juanmuscaria/backport/world/entity/animal/BackportedEntityDataSerializers";
    static final String KEYS_OWNER = "com/juanmuscaria/backport/data/BackportedKeys";
    static final String DEFERRED_HOLDER_DESC =
            "Lnet/neoforged/neoforge/registries/DeferredHolder;";
    static final String DEFERRED_HOLDER_OWNER =
            "net/neoforged/neoforge/registries/DeferredHolder";
    static final String SERIALIZER_DESC =
            "Lnet/minecraft/network/syncher/EntityDataSerializer;";
    static final String RESOURCE_KEY_DESC = "Lnet/minecraft/resources/ResourceKey;";

    static final Map<String, SerializerSpec> SERIALIZERS;
    static final Map<String, Integer> EXPECTED_MIXIN_REPLACEMENTS;
    static final Set<String> EXPECTED_CHANGED_ENTRIES;

    static {
        Map<String, SerializerSpec> serializers = new LinkedHashMap<>();
        serializers.put("COW_VARIANT", new SerializerSpec("CODEX_EAGER_COW_VARIANT", "lambda$static$0"));
        serializers.put("PIG_VARIANT", new SerializerSpec("CODEX_EAGER_PIG_VARIANT", "lambda$static$1"));
        serializers.put("CHICKEN_VARIANT", new SerializerSpec("CODEX_EAGER_CHICKEN_VARIANT", "lambda$static$2"));
        serializers.put(
                "WOLF_SOUND_VARIANT",
                new SerializerSpec("CODEX_EAGER_WOLF_SOUND_VARIANT", "lambda$static$3"));
        serializers.put(
                "COW_SOUND_VARIANT",
                new SerializerSpec("CODEX_EAGER_COW_SOUND_VARIANT", "lambda$static$4"));
        serializers.put(
                "CHICKEN_SOUND_VARIANT",
                new SerializerSpec("CODEX_EAGER_CHICKEN_SOUND_VARIANT", "lambda$static$5"));
        serializers.put(
                "PIG_SOUND_VARIANT",
                new SerializerSpec("CODEX_EAGER_PIG_SOUND_VARIANT", "lambda$static$6"));
        serializers.put(
                "CAT_SOUND_VARIANT",
                new SerializerSpec("CODEX_EAGER_CAT_SOUND_VARIANT", "lambda$static$7"));
        SERIALIZERS = java.util.Collections.unmodifiableMap(new LinkedHashMap<>(serializers));

        Map<String, Integer> mixins = new LinkedHashMap<>();
        mixins.put(
                "com/juanmuscaria/backport/mixin/common/CatSoundVariantBackport$CatMixin.class", 1);
        mixins.put(
                "com/juanmuscaria/backport/mixin/common/ChickenVariantBackport$ChickenMixin.class", 2);
        mixins.put(
                "com/juanmuscaria/backport/mixin/common/CowVariantBackport$CowMixin.class", 2);
        mixins.put(
                "com/juanmuscaria/backport/mixin/common/PigVariantBackport$PigMixin.class", 2);
        mixins.put(
                "com/juanmuscaria/backport/mixin/common/WolfSoundVariantBackport$WolfMixin.class", 1);
        EXPECTED_MIXIN_REPLACEMENTS =
                java.util.Collections.unmodifiableMap(new LinkedHashMap<>(mixins));

        var changed = new java.util.LinkedHashSet<String>();
        changed.add(SERIALIZER_OWNER + ".class");
        changed.addAll(mixins.keySet());
        EXPECTED_CHANGED_ENTRIES = java.util.Collections.unmodifiableSet(changed);
    }

    private BackportPatchContract() {}

    record SerializerSpec(String eagerField, String supplierMethod) {}
}

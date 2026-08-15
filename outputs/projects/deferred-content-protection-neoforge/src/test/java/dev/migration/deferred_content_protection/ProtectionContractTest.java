package dev.migration.deferred_content_protection;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class ProtectionContractTest {
    private ProtectionContractTest() {
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of(requiredProperty("projectDir"));
        verifyJavaContracts(root);
        verifyResourceBoundary(root);
        System.out.println("Deferred content protection contract: PASS");
    }

    private static void verifyJavaContracts(Path root) throws IOException {
        String registry = read(root, "src/main/java/dev/migration/deferred_content_protection/DeferredContentProtection.java");
        require(registry.contains("DeferredRegister.create(BuiltInRegistries.ITEM, \"minecraft\")"),
                "carrier must register under exact minecraft namespace");
        require(registry.contains("\"netherite_horse_armor\""), "carrier ID must be exact");
        require(registry.contains("RightClickItem") && registry.contains("RightClickBlock")
                        && registry.contains("EntityInteract") && registry.contains("EntityInteractSpecific"),
                "all right-click paths must be protected");
        require(registry.contains("AnimalArmorItem.BodyType.EQUESTRIAN")
                        && registry.contains("ArmorMaterials.NETHERITE"),
                "carrier must be an equestrian AnimalArmorItem so existing horse equipment renders");
        require(registry.contains("DispenserBlock.registerBehavior")
                        && registry.contains("DispenseItemBehavior.NOOP"),
                "dispenser must keep the protected carrier in place");
        require(registry.contains("ServerStartingEvent") && registry.contains("verifyRecipeBoundary"),
                "loaded recipes must be audited at server startup");
        require(registry.contains("getIngredients") && registry.contains("getResultItem")
                        && registry.contains("throw new IllegalStateException"),
                "recipe boundary must fail server startup closed on protected input/output");
        require(registry.contains("LivingDeathEvent") && registry.contains("DEATH_CARRIER_SNAPSHOTS")
                        && registry.contains("restoreMissingDeathCarriers")
                        && registry.contains("LivingDropsEvent") && registry.contains("EntityJoinLevelEvent")
                        && registry.contains("ItemExpireEvent") && registry.contains("ItemTossEvent")
                        && registry.contains("setCanceled(true)") && registry.contains("setInvulnerable(true)"),
                "death must restore missing carriers and all world carriers must be persistent/invulnerable");
        require(registry.contains("AnvilUpdateEvent") && registry.contains("GrindstoneEvent.OnPlaceItem")
                        && registry.contains("GrindstoneEvent.OnTakeItem"),
                "anvil and grindstone paths must fail closed");

        String item = read(root, "src/main/java/dev/migration/deferred_content_protection/ProtectedDeferredItem.java");
        for (String required : List.of(
                "onDroppedByPlayer", "return false;", "canEquip", "isBookEnchantable",
                "getDefaultAttributeModifiers", "ItemAttributeModifiers.EMPTY",
                "canBeHurtBy", "getEntityLifespan", "Short.MAX_VALUE - 1",
                "onEntityItemUpdate", "setUnlimitedLifetime", "extends AnimalArmorItem",
                "isValidRepairItem", "getEnchantmentValue", "getBurnTime",
                "DispenserBlock.registerBehavior", "DispenseItemBehavior.NOOP"
        )) {
            require(item.contains(required), "missing protected-item contract: " + required);
        }
        require(item.contains("public boolean canEquip") && item.contains("return false;"),
                "renderable carrier must explicitly reject new equipment");

        String container = read(root, "src/main/java/dev/migration/deferred_content_protection/mixin/AbstractContainerMenuMixin.java");
        for (String required : List.of(
                "@Mixin(AbstractContainerMenu.class)", "method = \"clicked\"", "ClickType.THROW",
                "ClickType.CLONE", "SLOT_CLICKED_OUTSIDE", "HorseInventoryMenu", "slotId == 1",
                "ClickType.SWAP", "player.getInventory().getItem(button)",
                "ClickType.QUICK_MOVE", "ClickType.QUICK_CRAFT", "ClickType.PICKUP_ALL",
                "pickupAllSweep", "isProcessingMenu", "isProcessingSlot",
                "InventoryMenu", "CraftingMenu", "CrafterMenu", "slotId == 45",
                "AbstractFurnaceMenu", "BrewingStandMenu", "AnvilMenu", "GrindstoneMenu",
                "SmithingMenu", "StonecutterMenu", "CartographyTableMenu", "LoomMenu",
                "BeaconMenu", "MerchantMenu", "callback.cancel()", "broadcastFullState()"
        )) {
            require(container.contains(required), "missing container loss-prevention contract: " + required);
        }
        require(!container.contains("ChestMenu") && !container.contains("ShulkerBoxMenu")
                        && !container.contains("HopperMenu") && !container.contains("DispenserMenu"),
                "ordinary storage/container transfer must remain available");

        String horse = read(root, "src/main/java/dev/migration/deferred_content_protection/mixin/AbstractHorseMixin.java");
        require(horse.contains("@Mixin(AbstractHorse.class)")
                        && horse.contains("method = \"equipBodyArmor")
                        && horse.contains("DeferredContentProtection.isProtected(stack)")
                        && horse.contains("callback.cancel()"),
                "direct horse-equipment path must reject new protected carriers");

        String recipe = read(root, "src/main/java/dev/migration/deferred_content_protection/mixin/RecipeManagerMixin.java");
        require(recipe.contains("@Mixin(RecipeManager.class)")
                        && recipe.contains("getRecipeFor(") && recipe.contains("getRecipesFor")
                        && recipe.contains("containsProtectedCarrier")
                        && recipe.contains("Optional.empty()") && recipe.contains("List.of()"),
                "recipe lookup and recipe-list paths must reject protected inputs centrally");

        String entity = read(root, "src/main/java/dev/migration/deferred_content_protection/mixin/EntityMixin.java");
        require(entity.contains("@Mixin(Entity.class)") && entity.contains("method = \"onBelowWorld\"")
                        && entity.contains("getSharedSpawnPos") && entity.contains("setUnlimitedLifetime")
                        && entity.contains("setInvulnerable(true)") && entity.contains("callback.cancel()"),
                "protected ground carriers must be rescued instead of discarded below the world");

        String mixinConfig = read(root, "src/main/resources/deferred_content_protection.mixins.json");
        require(mixinConfig.contains("AbstractHorseMixin")
                        && mixinConfig.contains("AbstractContainerMenuMixin")
                        && mixinConfig.contains("EntityMixin")
                        && mixinConfig.contains("RecipeManagerMixin")
                        && !mixinConfig.contains("HorseInventoryMenuMixin"),
                "mixin configuration must contain only the active protection mixins");
    }

    private static void verifyResourceBoundary(Path root) throws IOException {
        Path resources = root.resolve("src/main/resources");
        require(Files.isRegularFile(resources.resolve("assets/minecraft/models/item/netherite_horse_armor.json")),
                "carrier model missing");
        require(Files.isRegularFile(resources.resolve("assets/minecraft/textures/item/netherite_horse_armor.png")),
                "carrier item texture missing");
        require(Files.isRegularFile(resources.resolve("assets/minecraft/textures/entity/horse/armor/horse_armor_netherite.png")),
                "preserved equipped-entity texture missing");
        require(Files.isRegularFile(resources.resolve("assets/minecraft/lang/en_us.json")),
                "English protected-name translation missing");
        require(Files.isRegularFile(resources.resolve("assets/minecraft/lang/zh_cn.json")),
                "Chinese protected-name translation missing");
        try (var paths = Files.walk(resources)) {
            List<Path> forbidden = paths
                    .filter(Files::isRegularFile)
                    .filter(path -> {
                        String value = path.toString().replace('\\', '/');
                        return value.contains("/recipe/")
                                || value.contains("/recipes/")
                                || value.contains("/advancement/")
                                || value.contains("/advancements/");
                    })
                    .toList();
            require(forbidden.isEmpty(), "first-release carrier must not add recipes or advancements: " + forbidden);
        }
    }

    private static String read(Path root, String relative) throws IOException {
        return Files.readString(root.resolve(relative), StandardCharsets.UTF_8);
    }

    private static String requiredProperty(String name) {
        String value = System.getProperty(name);
        if (value == null || value.isBlank()) {
            throw new AssertionError("Missing system property " + name);
        }
        return value;
    }

    private static void require(boolean value, String message) {
        if (!value) {
            throw new AssertionError(message);
        }
    }
}

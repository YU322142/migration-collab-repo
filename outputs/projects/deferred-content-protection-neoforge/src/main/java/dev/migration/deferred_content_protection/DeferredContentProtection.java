package dev.migration.deferred_content_protection;

import com.mojang.logging.LogUtils;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.animal.horse.AbstractHorse;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ArmorMaterials;
import net.minecraft.world.item.AnimalArmorItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.item.crafting.RecipeHolder;
import net.minecraft.world.level.GameRules;
import net.minecraft.world.level.block.DispenserBlock;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.AnvilUpdateEvent;
import net.neoforged.neoforge.event.GrindstoneEvent;
import net.neoforged.neoforge.event.entity.EntityJoinLevelEvent;
import net.neoforged.neoforge.event.entity.item.ItemExpireEvent;
import net.neoforged.neoforge.event.entity.item.ItemTossEvent;
import net.neoforged.neoforge.event.entity.living.LivingDeathEvent;
import net.neoforged.neoforge.event.entity.living.LivingDropsEvent;
import net.neoforged.neoforge.event.entity.player.PlayerInteractEvent;
import net.neoforged.neoforge.event.server.ServerStartingEvent;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;
import org.slf4j.Logger;

@Mod(DeferredContentProtection.MOD_ID)
public final class DeferredContentProtection {
    public static final String MOD_ID = "deferred_content_protection";
    public static final ResourceLocation NETHERITE_HORSE_ARMOR_ID =
            ResourceLocation.fromNamespaceAndPath("minecraft", "netherite_horse_armor");
    public static final DeferredRegister<Item> ITEMS =
            DeferredRegister.create(BuiltInRegistries.ITEM, "minecraft");
    public static final DeferredHolder<Item, Item> NETHERITE_HORSE_ARMOR = ITEMS.register(
            "netherite_horse_armor",
            () -> new ProtectedDeferredItem(
                    ArmorMaterials.NETHERITE,
                    AnimalArmorItem.BodyType.EQUESTRIAN,
                    false,
                    new Item.Properties().stacksTo(1).fireResistant()
            )
    );
    private static final Map<UUID, List<ItemStack>> DEATH_CARRIER_SNAPSHOTS =
            new ConcurrentHashMap<>();
    private static final Logger LOGGER = LogUtils.getLogger();

    public DeferredContentProtection(IEventBus modBus) {
        ITEMS.register(modBus);
        NeoForge.EVENT_BUS.addListener(this::rightClickItem);
        NeoForge.EVENT_BUS.addListener(this::rightClickBlock);
        NeoForge.EVENT_BUS.addListener(this::entityInteract);
        NeoForge.EVENT_BUS.addListener(this::entityInteractSpecific);
        NeoForge.EVENT_BUS.addListener(this::anvilUpdate);
        NeoForge.EVENT_BUS.addListener(this::grindstonePlace);
        NeoForge.EVENT_BUS.addListener(this::grindstoneTake);
        NeoForge.EVENT_BUS.addListener(this::livingDeath);
        NeoForge.EVENT_BUS.addListener(this::livingDrops);
        NeoForge.EVENT_BUS.addListener(this::entityJoinLevel);
        NeoForge.EVENT_BUS.addListener(this::itemExpire);
        NeoForge.EVENT_BUS.addListener(this::itemToss);
        NeoForge.EVENT_BUS.addListener(this::serverStarting);
        LOGGER.warn("Deferred content protection enabled for {}", NETHERITE_HORSE_ARMOR_ID);
    }

    public static boolean isProtected(ItemStack stack) {
        return !stack.isEmpty() && stack.getItem() == NETHERITE_HORSE_ARMOR.get();
    }

    private static void notifyBlocked(Player player) {
        if (!player.level().isClientSide) {
            player.displayClientMessage(
                    net.minecraft.network.chat.Component.translatable("deferred_content_protection.blocked"),
                    true
            );
        }
    }

    private void rightClickItem(PlayerInteractEvent.RightClickItem event) {
        if (isProtected(event.getItemStack())) {
            event.setCancellationResult(InteractionResult.FAIL);
            event.setCanceled(true);
            notifyBlocked(event.getEntity());
        }
    }

    private void rightClickBlock(PlayerInteractEvent.RightClickBlock event) {
        if (isProtected(event.getItemStack())) {
            event.setCancellationResult(InteractionResult.FAIL);
            event.setCanceled(true);
            notifyBlocked(event.getEntity());
        }
    }

    private void entityInteract(PlayerInteractEvent.EntityInteract event) {
        if (isProtected(event.getItemStack())) {
            event.setCancellationResult(InteractionResult.FAIL);
            event.setCanceled(true);
            notifyBlocked(event.getEntity());
        }
    }

    private void entityInteractSpecific(PlayerInteractEvent.EntityInteractSpecific event) {
        if (isProtected(event.getItemStack())) {
            event.setCancellationResult(InteractionResult.FAIL);
            event.setCanceled(true);
            notifyBlocked(event.getEntity());
        }
    }

    private void anvilUpdate(AnvilUpdateEvent event) {
        if (isProtected(event.getLeft()) || isProtected(event.getRight())) {
            event.setCanceled(true);
            notifyBlocked(event.getPlayer());
        }
    }

    private void grindstonePlace(GrindstoneEvent.OnPlaceItem event) {
        if (isProtected(event.getTopItem()) || isProtected(event.getBottomItem())) {
            event.setCanceled(true);
        }
    }

    private void grindstoneTake(GrindstoneEvent.OnTakeItem event) {
        if (isProtected(event.getTopItem()) || isProtected(event.getBottomItem())) {
            event.setCanceled(true);
            if (event.getPlayer() != null) {
                notifyBlocked(event.getPlayer());
            }
        }
    }

    private void livingDrops(LivingDropsEvent event) {
        restoreMissingDeathCarriers(event);
        for (ItemEntity drop : event.getDrops()) {
            protectDroppedCarrier(drop);
        }
    }

    private void entityJoinLevel(EntityJoinLevelEvent event) {
        if (event.getEntity() instanceof ItemEntity itemEntity) {
            protectDroppedCarrier(itemEntity);
        }
    }

    private void itemExpire(ItemExpireEvent event) {
        protectDroppedCarrier(event.getEntity());
    }

    private void itemToss(ItemTossEvent event) {
        if (isProtected(event.getEntity().getItem())) {
            event.setCanceled(true);
            notifyBlocked(event.getPlayer());
        }
    }

    private void serverStarting(ServerStartingEvent event) {
        Item protectedItem = NETHERITE_HORSE_ARMOR.get();
        DispenserBlock.registerBehavior(protectedItem, net.minecraft.core.dispenser.DispenseItemBehavior.NOOP);
        verifyRecipeBoundary(event.getServer());
        LOGGER.warn("Deferred carrier automation lock installed for {}", NETHERITE_HORSE_ARMOR_ID);
    }

    private void livingDeath(LivingDeathEvent event) {
        LivingEntity entity = event.getEntity();
        if (entity.level().isClientSide) {
            return;
        }
        List<ItemStack> snapshot = snapshotProtectedCarriers(entity);
        if (snapshot.isEmpty()) {
            DEATH_CARRIER_SNAPSHOTS.remove(entity.getUUID());
        } else {
            DEATH_CARRIER_SNAPSHOTS.put(entity.getUUID(), snapshot);
        }
    }

    private static List<ItemStack> snapshotProtectedCarriers(LivingEntity entity) {
        List<ItemStack> snapshot = new ArrayList<>();
        if (entity instanceof Player player) {
            if (player.level().getGameRules().getBoolean(GameRules.RULE_KEEPINVENTORY)) {
                return snapshot;
            }
            for (int slot = 0; slot < player.getInventory().getContainerSize(); slot++) {
                addProtectedCopy(snapshot, player.getInventory().getItem(slot));
            }
        }
        if (entity instanceof AbstractHorse horse) {
            for (int slot = 0; slot < horse.getInventory().getContainerSize(); slot++) {
                addProtectedCopy(snapshot, horse.getInventory().getItem(slot));
            }
        }
        if (entity instanceof Mob mob) {
            addProtectedCopy(snapshot, mob.getBodyArmorItem());
        }
        return snapshot;
    }

    private static void addProtectedCopy(List<ItemStack> snapshot, ItemStack stack) {
        if (isProtected(stack)) {
            snapshot.add(stack.copy());
        }
    }

    private static void restoreMissingDeathCarriers(LivingDropsEvent event) {
        List<ItemStack> missing = DEATH_CARRIER_SNAPSHOTS.remove(event.getEntity().getUUID());
        if (missing == null || missing.isEmpty()) {
            return;
        }

        for (ItemEntity drop : event.getDrops()) {
            ItemStack dropped = drop.getItem();
            if (!isProtected(dropped)) {
                continue;
            }
            int available = dropped.getCount();
            for (ItemStack expected : missing) {
                if (available == 0) {
                    break;
                }
                if (!expected.isEmpty() && ItemStack.isSameItemSameComponents(dropped, expected)) {
                    int matched = Math.min(available, expected.getCount());
                    expected.shrink(matched);
                    available -= matched;
                }
            }
        }

        for (ItemStack expected : missing) {
            if (!expected.isEmpty()) {
                ItemEntity restored = new ItemEntity(
                        event.getEntity().level(),
                        event.getEntity().getX(),
                        event.getEntity().getY(),
                        event.getEntity().getZ(),
                        expected
                );
                protectDroppedCarrier(restored);
                event.getDrops().add(restored);
                LOGGER.warn(
                        "Restored protected deferred carrier to death drops for entity {} ({})",
                        event.getEntity().getUUID(),
                        event.getEntity().getType()
                );
            }
        }
    }

    private static void protectDroppedCarrier(ItemEntity itemEntity) {
        if (isProtected(itemEntity.getItem())) {
            itemEntity.setUnlimitedLifetime();
            itemEntity.setInvulnerable(true);
        }
    }

    private static void verifyRecipeBoundary(MinecraftServer server) {
        List<ResourceLocation> offenders = new ArrayList<>();
        for (RecipeHolder<?> holder : server.getRecipeManager().getRecipes()) {
            boolean outputMatch = isProtected(holder.value().getResultItem(server.registryAccess()));
            boolean inputMatch = false;
            for (Ingredient ingredient : holder.value().getIngredients()) {
                for (ItemStack candidate : ingredient.getItems()) {
                    if (isProtected(candidate)) {
                        inputMatch = true;
                        break;
                    }
                }
                if (inputMatch) {
                    break;
                }
            }
            if (inputMatch || outputMatch) {
                offenders.add(holder.id());
            }
        }
        if (!offenders.isEmpty()) {
            throw new IllegalStateException(
                    "Protected deferred item appears in loaded recipes: " + offenders
            );
        }
    }
}

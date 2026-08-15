package com.bmt.nautilus_equivalence;

import com.blackgear.vanillabackport.client.registries.ModSoundEvents;
import com.blackgear.vanillabackport.common.level.entity.mob.animal.nautilus.AbstractNautilus;
import com.blackgear.vanillabackport.common.level.entity.mob.animal.nautilus.ZombieNautilus;
import com.blackgear.vanillabackport.common.registries.entities.ModEntityTypes;
import com.blackgear.vanillabackport.common.registries.entities.ModMemoryModuleTypes;
import com.blackgear.vanillabackport.common.registries.entities.ModMobEffects;
import com.blackgear.vanillabackport.common.registries.entities.ModSensorTypes;
import com.blackgear.vanillabackport.common.registries.items.ModArmorMaterials;
import com.blackgear.vanillabackport.common.registries.items.ModItems;
import com.blackgear.vanillabackport.core.mixin.common.access.ParrotAccessor;
import com.bmt.nautilus_equivalence.loot.NautilusLootModifiers;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.event.entity.EntityAttributeCreationEvent;
import net.neoforged.neoforge.network.event.RegisterPayloadHandlersEvent;
import com.blackgear.vanillabackport.core.network.ClientboundNautilusScreenOpenPacket;
import net.minecraft.world.entity.SpawnPlacementTypes;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.CreativeModeTabs;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.levelgen.Heightmap;
import net.neoforged.fml.event.lifecycle.FMLCommonSetupEvent;
import net.neoforged.neoforge.event.BuildCreativeModeTabContentsEvent;
import net.neoforged.neoforge.event.entity.RegisterSpawnPlacementsEvent;

@Mod(NautilusEquivalence.MOD_ID)
public final class NautilusEquivalence {
    public static final String MOD_ID = "nautilus_equivalence";

    public NautilusEquivalence(IEventBus modBus) {
        ModArmorMaterials.ARMOR_MATERIALS.register(modBus);
        ModItems.ITEMS.register(modBus);
        ModEntityTypes.ENTITIES.register(modBus);
        ModMemoryModuleTypes.MEMORIES.register(modBus);
        ModSensorTypes.SENSORS.register(modBus);
        ModMobEffects.EFFECTS.register(modBus);
        ModSoundEvents.SOUNDS.register(modBus);
        NautilusLootModifiers.register(modBus);
        modBus.addListener(this::registerAttributes);
        modBus.addListener(this::registerPayloads);
        modBus.addListener(this::registerSpawnPlacements);
        modBus.addListener(this::addCreativeItems);
        modBus.addListener(this::commonSetup);
    }

    private void registerAttributes(EntityAttributeCreationEvent event) {
        event.put(ModEntityTypes.NAUTILUS.get(), AbstractNautilus.createAttributes().build());
        event.put(ModEntityTypes.ZOMBIE_NAUTILUS.get(), ZombieNautilus.createAttributes().build());
    }

    private void registerPayloads(RegisterPayloadHandlersEvent event) {
        event.registrar(MOD_ID).versioned("1")
            .playToClient(ClientboundNautilusScreenOpenPacket.TYPE,
                ClientboundNautilusScreenOpenPacket.STREAM_CODEC,
                ClientboundNautilusScreenOpenPacket::handler);
    }

    private void registerSpawnPlacements(RegisterSpawnPlacementsEvent event) {
        event.register(
            ModEntityTypes.NAUTILUS.get(),
            SpawnPlacementTypes.IN_WATER,
            Heightmap.Types.MOTION_BLOCKING_NO_LEAVES,
            AbstractNautilus::checkNautilusSpawnRules,
            RegisterSpawnPlacementsEvent.Operation.REPLACE
        );
    }

    private void addCreativeItems(BuildCreativeModeTabContentsEvent event) {
        CreativeModeTab.TabVisibility visibility = CreativeModeTab.TabVisibility.PARENT_AND_SEARCH_TABS;
        if (event.getTabKey() == CreativeModeTabs.COMBAT) {
            ItemStack previous = Items.WOLF_ARMOR.getDefaultInstance();
            for (var item : java.util.List.of(
                ModItems.COPPER_NAUTILUS_ARMOR,
                ModItems.IRON_NAUTILUS_ARMOR,
                ModItems.GOLDEN_NAUTILUS_ARMOR,
                ModItems.DIAMOND_NAUTILUS_ARMOR,
                ModItems.NETHERITE_NAUTILUS_ARMOR
            )) {
                ItemStack next = item.get().getDefaultInstance();
                event.insertAfter(previous, next, visibility);
                previous = next;
            }
        } else if (event.getTabKey() == CreativeModeTabs.SPAWN_EGGS) {
            event.insertAfter(Items.MULE_SPAWN_EGG.getDefaultInstance(), ModItems.NAUTILUS_SPAWN_EGG.get().getDefaultInstance(), visibility);
            event.insertAfter(Items.ZOMBIE_HORSE_SPAWN_EGG.getDefaultInstance(), ModItems.ZOMBIE_NAUTILUS_SPAWN_EGG.get().getDefaultInstance(), visibility);
        }
    }

    private void commonSetup(FMLCommonSetupEvent event) {
        event.enqueueWork(() -> ParrotAccessor.nautilusEquivalence$getMobSoundMap().put(
            ModEntityTypes.ZOMBIE_NAUTILUS.get(),
            ModSoundEvents.PARROT_IMITATE_ZOMBIE_NAUTILUS.get()
        ));
    }
}

package pers.solid.mishang.uc.migration;

import com.mojang.logging.LogUtils;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.ItemLike;
import net.minecraft.world.level.block.Block;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.fml.event.lifecycle.FMLCommonSetupEvent;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.BuildCreativeModeTabContentsEvent;
import net.neoforged.neoforge.event.server.ServerAboutToStartEvent;
import org.slf4j.Logger;
import pers.solid.mishang.uc.blockentity.MishangucBlockEntities;

import java.util.LinkedHashMap;
import java.util.Map;

@Mod(MishangPaleOakEquivalence.MOD_ID)
public final class MishangPaleOakEquivalence {
    public static final String MOD_ID = "mishanguc_pale_oak_equivalence";
    private static final Logger LOGGER = LogUtils.getLogger();
    private static final ResourceKey<CreativeModeTab> SIGNS_TAB = tabKey("signs");
    private static final ResourceKey<CreativeModeTab> DECORATIONS_TAB = tabKey("decorations");
    private static final ResourceKey<CreativeModeTab> COLORED_BLOCKS_TAB = tabKey("colored_blocks");

    public MishangPaleOakEquivalence(IEventBus modBus) {
        MishangPaleOakParticles.register(modBus);
        MishangPaleOakContent.register(modBus);
        modBus.addListener(this::commonSetup);
        modBus.addListener(this::addToCreativeTabs);
        NeoForge.EVENT_BUS.addListener(this::guardRegistries);
    }

    private void commonSetup(FMLCommonSetupEvent event) {
        event.enqueueWork(() -> {
            MishangPaleOakContent.extendBlockEntityTypes();
            LOGGER.info("Extended Mishang block-entity types for all pale oak signs and colored blocks");
        });
    }

    private void addToCreativeTabs(BuildCreativeModeTabContentsEvent event) {
        if (event.getTabKey().equals(SIGNS_TAB)) {
            insertAfter(event, "dark_oak_wood_wall_sign", MishangPaleOakContent.PALE_OAK_WOOD_WALL_SIGN.get());
            insertAfter(event, "stripped_dark_oak_wood_wall_sign",
                    MishangPaleOakContent.STRIPPED_PALE_OAK_WOOD_WALL_SIGN.get());
            insertAfter(event, "dark_oak_wall_sign", MishangPaleOakContent.PALE_OAK_WALL_SIGN.get());
            insertAfter(event, "dark_oak_wood_hung_sign", MishangPaleOakContent.PALE_OAK_WOOD_HUNG_SIGN.get());
            insertAfter(event, "stripped_dark_oak_wood_hung_sign",
                    MishangPaleOakContent.STRIPPED_PALE_OAK_WOOD_HUNG_SIGN.get());
            insertAfter(event, "dark_oak_hung_sign", MishangPaleOakContent.PALE_OAK_HUNG_SIGN.get());
            insertAfter(event, "dark_oak_hung_sign_bar", MishangPaleOakContent.PALE_OAK_HUNG_SIGN_BAR.get());
            insertAfter(event, "stripped_dark_oak_hung_sign_bar",
                    MishangPaleOakContent.STRIPPED_PALE_OAK_HUNG_SIGN_BAR.get());
            insertAfter(event, "dark_oak_wood_standing_sign",
                    MishangPaleOakContent.PALE_OAK_WOOD_STANDING_SIGN.get());
            insertAfter(event, "stripped_dark_oak_wood_standing_sign",
                    MishangPaleOakContent.STRIPPED_PALE_OAK_WOOD_STANDING_SIGN.get());
            insertAfter(event, "dark_oak_standing_sign", MishangPaleOakContent.PALE_OAK_STANDING_SIGN.get());
        } else if (event.getTabKey().equals(DECORATIONS_TAB)) {
            insertAfter(event, "simple_dark_oak_handrail", MishangPaleOakContent.SIMPLE_PALE_OAK.base().get());
            insertAfter(event, "simple_dark_oak_plank_handrail",
                    MishangPaleOakContent.SIMPLE_PALE_OAK_PLANK.base().get());
            insertAfter(event, "glass_dark_oak_handrail", MishangPaleOakContent.GLASS_PALE_OAK.base().get());
            insertAfter(event, "colored_decorated_dark_oak_handrail",
                    MishangPaleOakContent.COLORED_DECORATED_PALE_OAK.base().get());
            insertAfter(event, "colored_decorated_stripped_dark_oak_handrail",
                    MishangPaleOakContent.COLORED_DECORATED_STRIPPED_PALE_OAK.base().get());
        } else if (event.getTabKey().equals(COLORED_BLOCKS_TAB)) {
            insertAfter(event, "colored_dark_oak_leaves", MishangPaleOakContent.COLORED_PALE_OAK_LEAVES.get());
        }
    }

    private void guardRegistries(ServerAboutToStartEvent event) {
        Map<String, String> failures = new LinkedHashMap<>();
        if (MishangPaleOakContent.allBlocks().size() != 37) {
            failures.put("block_count", "expected 37, got " + MishangPaleOakContent.allBlocks().size());
        }
        if (MishangPaleOakContent.allItems().size() != 17) {
            failures.put("item_count", "expected 17, got " + MishangPaleOakContent.allItems().size());
        }
        MishangPaleOakContent.allBlocks().forEach(holder -> checkRegistered(failures, "block", holder.get()));
        MishangPaleOakContent.allItems().forEach(holder -> {
            ResourceLocation key = BuiltInRegistries.ITEM.getKey(holder.get());
            if (key == null || !"mishanguc".equals(key.getNamespace())) {
                failures.put("item:" + key, "not registered in mishanguc namespace");
            }
        });
        checkBlockEntity(failures, "colored_pale_oak_leaves",
                MishangucBlockEntities.SIMPLE_COLORED_BLOCK_ENTITY,
                MishangPaleOakContent.COLORED_PALE_OAK_LEAVES.get());
        checkBlockEntity(failures, "pale_oak_hung_sign", MishangucBlockEntities.HUNG_SIGN_BLOCK_ENTITY,
                MishangPaleOakContent.PALE_OAK_HUNG_SIGN.get());
        checkBlockEntity(failures, "pale_oak_wall_sign", MishangucBlockEntities.WALL_SIGN_BLOCK_ENTITY,
                MishangPaleOakContent.PALE_OAK_WALL_SIGN.get());
        checkBlockEntity(failures, "pale_oak_standing_sign", MishangucBlockEntities.STANDING_SIGN_BLOCK_ENTITY,
                MishangPaleOakContent.PALE_OAK_STANDING_SIGN.get());
        if (!failures.isEmpty()) {
            throw new IllegalStateException("Mishang pale oak equivalence guard failed: " + failures);
        }
        LOGGER.info("Mishang pale oak equivalence guard passed: 37 blocks, 17 items, and block-entity NBT support");
    }

    private static void checkRegistered(Map<String, String> failures, String kind, Block block) {
        ResourceLocation key = BuiltInRegistries.BLOCK.getKey(block);
        if (key == null || !"mishanguc".equals(key.getNamespace())) {
            failures.put(kind + ":" + key, "not registered in mishanguc namespace");
        }
    }

    private static void checkBlockEntity(Map<String, String> failures, String id,
                                         net.minecraft.world.level.block.entity.BlockEntityType<?> type,
                                         Block block) {
        if (!MishangPaleOakContent.isValidFor(type, block)) {
            failures.put("block_entity:" + id, "original Mishang block-entity type rejects this block");
        }
    }

    private static void insertAfter(BuildCreativeModeTabContentsEvent event, String existingPath, ItemLike addition) {
        ItemStack anchor = new ItemStack(BuiltInRegistries.ITEM.get(mishangId(existingPath)));
        event.insertAfter(anchor, new ItemStack(addition), CreativeModeTab.TabVisibility.PARENT_AND_SEARCH_TABS);
    }

    private static ResourceKey<CreativeModeTab> tabKey(String path) {
        return ResourceKey.create(Registries.CREATIVE_MODE_TAB, mishangId(path));
    }

    private static ResourceLocation mishangId(String path) {
        return ResourceLocation.fromNamespaceAndPath("mishanguc", path);
    }
}

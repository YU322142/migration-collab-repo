package pers.solid.mishang.uc.migration;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.BlockEntityType;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;
import pers.solid.mishang.uc.block.ColoredGlassHandrailBlock;
import pers.solid.mishang.uc.block.ColoredLeavesBlock;
import pers.solid.mishang.uc.block.GlassHandrailBlock;
import pers.solid.mishang.uc.block.HandrailBlock;
import pers.solid.mishang.uc.block.HungSignBarBlock;
import pers.solid.mishang.uc.block.HungSignBlock;
import pers.solid.mishang.uc.block.SimpleHandrailBlock;
import pers.solid.mishang.uc.block.StandingSignBlock;
import pers.solid.mishang.uc.block.WallSignBlock;
import pers.solid.mishang.uc.blockentity.MishangucBlockEntities;
import pers.solid.mishang.uc.item.HungSignBlockItem;
import pers.solid.mishang.uc.item.NamedBlockItem;
import pers.solid.mishang.uc.item.StandingSignBlockItem;
import pers.solid.mishang.uc.item.WallSignBlockItem;
import pers.solid.mishang.uc.migration.mixin.BlockEntityTypeAccessor;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.BiFunction;
import java.util.function.Supplier;

public final class MishangPaleOakContent {
    private static final String MISHANG_ID = "mishanguc";
    private static final DeferredRegister<Block> BLOCKS = DeferredRegister.create(Registries.BLOCK, MISHANG_ID);
    private static final DeferredRegister<Item> ITEMS = DeferredRegister.create(Registries.ITEM, MISHANG_ID);

    private static final List<DeferredHolder<Block, ? extends Block>> ALL_BLOCKS = new ArrayList<>(37);
    private static final List<DeferredHolder<Item, ? extends Item>> ALL_ITEMS = new ArrayList<>(17);
    private static final List<DeferredHolder<Block, ? extends Block>> COLORED_BLOCKS = new ArrayList<>(11);
    private static final List<DeferredHolder<Block, ? extends Block>> TRANSLUCENT_BLOCKS = new ArrayList<>(15);

    public static final HandrailSet<SimpleHandrailBlock> SIMPLE_PALE_OAK = registerHandrail(
            "simple_pale_oak_handrail", MishangPaleOakContent::createSimplePaleOak);
    public static final HandrailSet<SimpleHandrailBlock> SIMPLE_PALE_OAK_PLANK = registerHandrail(
            "simple_pale_oak_plank_handrail", MishangPaleOakContent::createSimplePaleOakPlank);
    public static final HandrailSet<GlassHandrailBlock> GLASS_PALE_OAK = registerHandrail(
            "glass_pale_oak_handrail", MishangPaleOakContent::createGlassPaleOak);
    public static final HandrailSet<ColoredGlassHandrailBlock> COLORED_DECORATED_PALE_OAK = registerHandrail(
            "colored_decorated_pale_oak_handrail", MishangPaleOakContent::createColoredDecoratedPaleOak);
    public static final HandrailSet<ColoredGlassHandrailBlock> COLORED_DECORATED_STRIPPED_PALE_OAK = registerHandrail(
            "colored_decorated_stripped_pale_oak_handrail",
            MishangPaleOakContent::createColoredDecoratedStrippedPaleOak);

    public static final DeferredHolder<Block, ColoredLeavesBlock> COLORED_PALE_OAK_LEAVES = block(
            "colored_pale_oak_leaves", MishangPaleOakContent::createColoredPaleOakLeaves);

    public static final DeferredHolder<Block, WallSignBlock> PALE_OAK_WOOD_WALL_SIGN = wallSign(
            "pale_oak_wood_wall_sign", () -> wallSignBlock("pale_oak_wood", "block/pale_oak_log"));
    public static final DeferredHolder<Block, WallSignBlock> STRIPPED_PALE_OAK_WOOD_WALL_SIGN = wallSign(
            "stripped_pale_oak_wood_wall_sign",
            () -> wallSignBlock("stripped_pale_oak_wood", "block/stripped_pale_oak_log"));
    public static final DeferredHolder<Block, WallSignBlock> PALE_OAK_WALL_SIGN = wallSign(
            "pale_oak_wall_sign", () -> new WallSignBlock(minecraftBlock("pale_oak_planks")));

    public static final DeferredHolder<Block, HungSignBlock> PALE_OAK_WOOD_HUNG_SIGN = hungSign(
            "pale_oak_wood_hung_sign", MishangPaleOakContent::createPaleOakWoodHungSign);
    public static final DeferredHolder<Block, HungSignBlock> STRIPPED_PALE_OAK_WOOD_HUNG_SIGN = hungSign(
            "stripped_pale_oak_wood_hung_sign", MishangPaleOakContent::createStrippedPaleOakWoodHungSign);
    public static final DeferredHolder<Block, HungSignBlock> PALE_OAK_HUNG_SIGN = hungSign(
            "pale_oak_hung_sign", MishangPaleOakContent::createPaleOakHungSign);
    public static final DeferredHolder<Block, HungSignBarBlock> PALE_OAK_HUNG_SIGN_BAR = hungSignBar(
            "pale_oak_hung_sign_bar", () -> hungSignBarBlock("pale_oak_wood", "block/pale_oak_log"));
    public static final DeferredHolder<Block, HungSignBarBlock> STRIPPED_PALE_OAK_HUNG_SIGN_BAR = hungSignBar(
            "stripped_pale_oak_hung_sign_bar",
            () -> hungSignBarBlock("stripped_pale_oak_wood", "block/stripped_pale_oak_log"));

    public static final DeferredHolder<Block, StandingSignBlock> PALE_OAK_WOOD_STANDING_SIGN = standingSign(
            "pale_oak_wood_standing_sign", MishangPaleOakContent::createPaleOakWoodStandingSign);
    public static final DeferredHolder<Block, StandingSignBlock> STRIPPED_PALE_OAK_WOOD_STANDING_SIGN = standingSign(
            "stripped_pale_oak_wood_standing_sign", MishangPaleOakContent::createStrippedPaleOakWoodStandingSign);
    public static final DeferredHolder<Block, StandingSignBlock> PALE_OAK_STANDING_SIGN = standingSign(
            "pale_oak_standing_sign", MishangPaleOakContent::createPaleOakStandingSign);

    static {
        item("simple_pale_oak_handrail", SIMPLE_PALE_OAK.base(), NamedBlockItem::new);
        item("simple_pale_oak_plank_handrail", SIMPLE_PALE_OAK_PLANK.base(), NamedBlockItem::new);
        item("glass_pale_oak_handrail", GLASS_PALE_OAK.base(), NamedBlockItem::new);
        item("colored_decorated_pale_oak_handrail", COLORED_DECORATED_PALE_OAK.base(), NamedBlockItem::new);
        item("colored_decorated_stripped_pale_oak_handrail",
                COLORED_DECORATED_STRIPPED_PALE_OAK.base(), NamedBlockItem::new);
        item("colored_pale_oak_leaves", COLORED_PALE_OAK_LEAVES, NamedBlockItem::new);

        COLORED_BLOCKS.add(COLORED_PALE_OAK_LEAVES);
        addHandrailBlocks(COLORED_BLOCKS, COLORED_DECORATED_PALE_OAK);
        addHandrailBlocks(COLORED_BLOCKS, COLORED_DECORATED_STRIPPED_PALE_OAK);
        addHandrailBlocks(TRANSLUCENT_BLOCKS, GLASS_PALE_OAK);
        addHandrailBlocks(TRANSLUCENT_BLOCKS, COLORED_DECORATED_PALE_OAK);
        addHandrailBlocks(TRANSLUCENT_BLOCKS, COLORED_DECORATED_STRIPPED_PALE_OAK);
    }

    private MishangPaleOakContent() {
    }

    public static void register(IEventBus modBus) {
        BLOCKS.register(modBus);
        ITEMS.register(modBus);
    }

    public static List<DeferredHolder<Block, ? extends Block>> allBlocks() {
        return List.copyOf(ALL_BLOCKS);
    }

    public static List<DeferredHolder<Item, ? extends Item>> allItems() {
        return List.copyOf(ALL_ITEMS);
    }

    public static List<DeferredHolder<Block, ? extends Block>> coloredBlocks() {
        return List.copyOf(COLORED_BLOCKS);
    }

    public static List<DeferredHolder<Block, ? extends Block>> translucentBlocks() {
        return List.copyOf(TRANSLUCENT_BLOCKS);
    }

    public static void extendBlockEntityTypes() {
        addValidBlocks(MishangucBlockEntities.SIMPLE_COLORED_BLOCK_ENTITY,
                COLORED_BLOCKS.stream().map(DeferredHolder::get).toList());
        addValidBlocks(MishangucBlockEntities.HUNG_SIGN_BLOCK_ENTITY,
                List.of(PALE_OAK_WOOD_HUNG_SIGN.get(), STRIPPED_PALE_OAK_WOOD_HUNG_SIGN.get(),
                        PALE_OAK_HUNG_SIGN.get()));
        addValidBlocks(MishangucBlockEntities.WALL_SIGN_BLOCK_ENTITY,
                List.of(PALE_OAK_WOOD_WALL_SIGN.get(), STRIPPED_PALE_OAK_WOOD_WALL_SIGN.get(),
                        PALE_OAK_WALL_SIGN.get()));
        addValidBlocks(MishangucBlockEntities.STANDING_SIGN_BLOCK_ENTITY,
                List.of(PALE_OAK_WOOD_STANDING_SIGN.get(), STRIPPED_PALE_OAK_WOOD_STANDING_SIGN.get(),
                        PALE_OAK_STANDING_SIGN.get()));
    }

    public static boolean isValidFor(BlockEntityType<?> type, Block block) {
        return ((BlockEntityTypeAccessor) (Object) type).mishangEquivalence$getValidBlocks().contains(block);
    }

    private static void addValidBlocks(BlockEntityType<?> type, List<? extends Block> blocks) {
        BlockEntityTypeAccessor accessor = (BlockEntityTypeAccessor) (Object) type;
        Set<Block> validBlocks = new HashSet<>(accessor.mishangEquivalence$getValidBlocks());
        validBlocks.addAll(blocks);
        accessor.mishangEquivalence$setValidBlocks(Set.copyOf(validBlocks));
    }

    private static SimpleHandrailBlock createSimplePaleOak() {
        SimpleHandrailBlock block = new SimpleHandrailBlock(minecraftBlock("pale_oak_wood"));
        block.texture = minecraftId("block/pale_oak_log");
        return block;
    }

    private static SimpleHandrailBlock createSimplePaleOakPlank() {
        return new SimpleHandrailBlock(minecraftBlock("pale_oak_planks"));
    }

    private static GlassHandrailBlock createGlassPaleOak() {
        Block base = minecraftBlock("pale_oak_wood");
        return new GlassHandrailBlock(base, BlockBehaviour.Properties.ofFullCopy(base).strength(1.0F),
                "block/pale_oak_log", "block/pale_oak_planks");
    }

    private static ColoredGlassHandrailBlock createColoredDecoratedPaleOak() {
        Block base = minecraftBlock("pale_oak_wood");
        return new ColoredGlassHandrailBlock(base, BlockBehaviour.Properties.ofFullCopy(base).strength(1.0F),
                "block/pale_oak_log", "mishanguc:block/pale_planks");
    }

    private static ColoredGlassHandrailBlock createColoredDecoratedStrippedPaleOak() {
        Block base = minecraftBlock("stripped_pale_oak_wood");
        return new ColoredGlassHandrailBlock(base, BlockBehaviour.Properties.ofFullCopy(base).strength(1.0F),
                "block/stripped_pale_oak_log", "mishanguc:block/pale_planks");
    }

    private static ColoredLeavesBlock createColoredPaleOakLeaves() {
        Block leaves = minecraftBlock("pale_oak_leaves");
        return new PaleOakColoredLeavesBlock(BlockBehaviour.Properties.ofFullCopy(leaves), null,
                "block/pale_oak_leaves");
    }

    private static WallSignBlock wallSignBlock(String baseId, String texture) {
        WallSignBlock block = new WallSignBlock(minecraftBlock(baseId));
        block.texture = minecraftId(texture);
        return block;
    }

    private static HungSignBlock createPaleOakWoodHungSign() {
        HungSignBlock block = new HungSignBlock(minecraftBlock("pale_oak_wood"));
        block.baseTexture = minecraftId("block/pale_oak_log");
        block.barTexture = minecraftId("block/pale_oak_log");
        return block;
    }

    private static HungSignBlock createStrippedPaleOakWoodHungSign() {
        HungSignBlock block = new HungSignBlock(minecraftBlock("stripped_pale_oak_wood"));
        block.baseTexture = minecraftId("block/stripped_pale_oak_log");
        return block;
    }

    private static HungSignBlock createPaleOakHungSign() {
        HungSignBlock block = new HungSignBlock(minecraftBlock("pale_oak_planks"));
        block.barTexture = minecraftId("block/pale_oak_log");
        block.textureTop = minecraftId("block/pale_oak_log");
        return block;
    }

    private static HungSignBarBlock hungSignBarBlock(String baseId, String texture) {
        HungSignBarBlock block = new HungSignBarBlock(minecraftBlock(baseId));
        block.texture = minecraftId(texture);
        return block;
    }

    private static StandingSignBlock createPaleOakWoodStandingSign() {
        StandingSignBlock block = new StandingSignBlock(minecraftBlock("pale_oak_wood"));
        block.baseTexture = minecraftId("block/pale_oak_log");
        return block;
    }

    private static StandingSignBlock createStrippedPaleOakWoodStandingSign() {
        StandingSignBlock block = new StandingSignBlock(minecraftBlock("stripped_pale_oak_wood"));
        block.baseTexture = minecraftId("block/stripped_pale_oak_log");
        return block;
    }

    private static StandingSignBlock createPaleOakStandingSign() {
        StandingSignBlock block = new StandingSignBlock(minecraftBlock("pale_oak_planks"));
        block.barTexture = minecraftId("block/pale_oak_log");
        return block;
    }

    private static <T extends HandrailBlock> HandrailSet<T> registerHandrail(String name, Supplier<T> factory) {
        DeferredHolder<Block, T> base = block(name, factory);
        DeferredHolder<Block, Block> central = block(name + "_central", () -> base.get().central());
        DeferredHolder<Block, Block> corner = block(name + "_corner", () -> base.get().corner());
        DeferredHolder<Block, Block> outer = block(name + "_outer", () -> base.get().outer());
        DeferredHolder<Block, Block> stair = block(name + "_stair", () -> base.get().stair());
        return new HandrailSet<>(base, central, corner, outer, stair);
    }

    private static <T extends Block> DeferredHolder<Block, T> block(String name, Supplier<T> supplier) {
        DeferredHolder<Block, T> holder = BLOCKS.register(name, supplier);
        ALL_BLOCKS.add(holder);
        return holder;
    }

    private static DeferredHolder<Block, WallSignBlock> wallSign(String name, Supplier<WallSignBlock> supplier) {
        DeferredHolder<Block, WallSignBlock> block = block(name, supplier);
        item(name, block, WallSignBlockItem::new);
        return block;
    }

    private static DeferredHolder<Block, HungSignBlock> hungSign(String name, Supplier<HungSignBlock> supplier) {
        DeferredHolder<Block, HungSignBlock> block = block(name, supplier);
        item(name, block, HungSignBlockItem::new);
        return block;
    }

    private static DeferredHolder<Block, HungSignBarBlock> hungSignBar(
            String name, Supplier<HungSignBarBlock> supplier) {
        DeferredHolder<Block, HungSignBarBlock> block = block(name, supplier);
        item(name, block, NamedBlockItem::new);
        return block;
    }

    private static DeferredHolder<Block, StandingSignBlock> standingSign(
            String name, Supplier<StandingSignBlock> supplier) {
        DeferredHolder<Block, StandingSignBlock> block = block(name, supplier);
        item(name, block, StandingSignBlockItem::new);
        return block;
    }

    private static <T extends Item> DeferredHolder<Item, T> item(
            String name, Supplier<? extends Block> block,
            BiFunction<Block, Item.Properties, T> factory) {
        DeferredHolder<Item, T> holder = ITEMS.register(name,
                () -> factory.apply(block.get(), new Item.Properties()));
        ALL_ITEMS.add(holder);
        return holder;
    }

    private static void addHandrailBlocks(
            List<DeferredHolder<Block, ? extends Block>> output, HandrailSet<?> handrail) {
        output.addAll(handrail.blocks());
    }

    private static Block minecraftBlock(String path) {
        ResourceLocation id = minecraftId(path);
        Block block = BuiltInRegistries.BLOCK.get(id);
        if (block == Blocks.AIR || !id.equals(BuiltInRegistries.BLOCK.getKey(block))) {
            throw new IllegalStateException("Required Content Backport block is missing: " + id);
        }
        return block;
    }

    private static ResourceLocation minecraftId(String path) {
        return ResourceLocation.fromNamespaceAndPath("minecraft", path);
    }

    public record HandrailSet<T extends HandrailBlock>(
            DeferredHolder<Block, T> base,
            DeferredHolder<Block, Block> central,
            DeferredHolder<Block, Block> corner,
            DeferredHolder<Block, Block> outer,
            DeferredHolder<Block, Block> stair) {
        public List<DeferredHolder<Block, ? extends Block>> blocks() {
            return List.of(base, central, corner, outer, stair);
        }
    }
}

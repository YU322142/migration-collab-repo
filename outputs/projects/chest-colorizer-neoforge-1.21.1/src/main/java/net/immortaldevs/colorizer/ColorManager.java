package net.immortaldevs.colorizer;

import javax.annotation.Nullable;
import net.immortaldevs.colorizer.block.ColorizedBarrelBlock;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ServerData;
import net.minecraft.client.resources.model.Material;
import net.minecraft.client.renderer.Sheets;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.DyeItem;
import net.minecraft.world.level.block.BarrelBlock;
import net.minecraft.world.level.block.ChestBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.ChestType;

public final class ColorManager {
    private static final Material WHITE = createChestMaterial("white");
    private static final Material WHITE_LEFT = createChestMaterial("white_left");
    private static final Material WHITE_RIGHT = createChestMaterial("white_right");
    private static final Material LIGHT_GRAY = createChestMaterial("light_gray");
    private static final Material LIGHT_GRAY_LEFT = createChestMaterial("light_gray_left");
    private static final Material LIGHT_GRAY_RIGHT = createChestMaterial("light_gray_right");
    private static final Material GRAY = createChestMaterial("gray");
    private static final Material GRAY_LEFT = createChestMaterial("gray_left");
    private static final Material GRAY_RIGHT = createChestMaterial("gray_right");
    private static final Material BLACK = createChestMaterial("black");
    private static final Material BLACK_LEFT = createChestMaterial("black_left");
    private static final Material BLACK_RIGHT = createChestMaterial("black_right");
    private static final Material BROWN = createChestMaterial("brown");
    private static final Material BROWN_LEFT = createChestMaterial("brown_left");
    private static final Material BROWN_RIGHT = createChestMaterial("brown_right");
    private static final Material RED = createChestMaterial("red");
    private static final Material RED_LEFT = createChestMaterial("red_left");
    private static final Material RED_RIGHT = createChestMaterial("red_right");
    private static final Material ORANGE = createChestMaterial("orange");
    private static final Material ORANGE_LEFT = createChestMaterial("orange_left");
    private static final Material ORANGE_RIGHT = createChestMaterial("orange_right");
    private static final Material YELLOW = createChestMaterial("yellow");
    private static final Material YELLOW_LEFT = createChestMaterial("yellow_left");
    private static final Material YELLOW_RIGHT = createChestMaterial("yellow_right");
    private static final Material LIME = createChestMaterial("lime");
    private static final Material LIME_LEFT = createChestMaterial("lime_left");
    private static final Material LIME_RIGHT = createChestMaterial("lime_right");
    private static final Material GREEN = createChestMaterial("green");
    private static final Material GREEN_LEFT = createChestMaterial("green_left");
    private static final Material GREEN_RIGHT = createChestMaterial("green_right");
    private static final Material CYAN = createChestMaterial("cyan");
    private static final Material CYAN_LEFT = createChestMaterial("cyan_left");
    private static final Material CYAN_RIGHT = createChestMaterial("cyan_right");
    private static final Material LIGHT_BLUE = createChestMaterial("light_blue");
    private static final Material LIGHT_BLUE_LEFT = createChestMaterial("light_blue_left");
    private static final Material LIGHT_BLUE_RIGHT = createChestMaterial("light_blue_right");
    private static final Material BLUE = createChestMaterial("blue");
    private static final Material BLUE_LEFT = createChestMaterial("blue_left");
    private static final Material BLUE_RIGHT = createChestMaterial("blue_right");
    private static final Material PURPLE = createChestMaterial("purple");
    private static final Material PURPLE_LEFT = createChestMaterial("purple_left");
    private static final Material PURPLE_RIGHT = createChestMaterial("purple_right");
    private static final Material MAGENTA = createChestMaterial("magenta");
    private static final Material MAGENTA_LEFT = createChestMaterial("magenta_left");
    private static final Material MAGENTA_RIGHT = createChestMaterial("magenta_right");
    private static final Material PINK = createChestMaterial("pink");
    private static final Material PINK_LEFT = createChestMaterial("pink_left");
    private static final Material PINK_RIGHT = createChestMaterial("pink_right");

    private ColorManager() {
    }

    @Nullable
    public static Material getColorizedChestMaterial(BlockEntity entity, ChestType type) {
        String worldName = getLevelName();
        if (worldName == null) {
            return null;
        }
        BlockColor color = getChestColor(worldName, entity, type);
        if (color == null || color == BlockColor.DEFAULT) {
            return null;
        }

        return switch (color) {
            case WHITE -> chooseMaterial(type, WHITE, WHITE_LEFT, WHITE_RIGHT);
            case LIGHT_GRAY -> chooseMaterial(type, LIGHT_GRAY, LIGHT_GRAY_LEFT, LIGHT_GRAY_RIGHT);
            case GRAY -> chooseMaterial(type, GRAY, GRAY_LEFT, GRAY_RIGHT);
            case BLACK -> chooseMaterial(type, BLACK, BLACK_LEFT, BLACK_RIGHT);
            case BROWN -> chooseMaterial(type, BROWN, BROWN_LEFT, BROWN_RIGHT);
            case RED -> chooseMaterial(type, RED, RED_LEFT, RED_RIGHT);
            case ORANGE -> chooseMaterial(type, ORANGE, ORANGE_LEFT, ORANGE_RIGHT);
            case YELLOW -> chooseMaterial(type, YELLOW, YELLOW_LEFT, YELLOW_RIGHT);
            case LIME -> chooseMaterial(type, LIME, LIME_LEFT, LIME_RIGHT);
            case GREEN -> chooseMaterial(type, GREEN, GREEN_LEFT, GREEN_RIGHT);
            case CYAN -> chooseMaterial(type, CYAN, CYAN_LEFT, CYAN_RIGHT);
            case LIGHT_BLUE -> chooseMaterial(type, LIGHT_BLUE, LIGHT_BLUE_LEFT, LIGHT_BLUE_RIGHT);
            case BLUE -> chooseMaterial(type, BLUE, BLUE_LEFT, BLUE_RIGHT);
            case PURPLE -> chooseMaterial(type, PURPLE, PURPLE_LEFT, PURPLE_RIGHT);
            case MAGENTA -> chooseMaterial(type, MAGENTA, MAGENTA_LEFT, MAGENTA_RIGHT);
            case PINK -> chooseMaterial(type, PINK, PINK_LEFT, PINK_RIGHT);
            case DEFAULT -> null;
        };
    }

    public static BlockState getColorizedBarrelState(BlockState state, BlockPos position) {
        if (!state.is(net.minecraft.world.level.block.Blocks.BARREL)) {
            return state;
        }
        BlockColor color = getColor(position);
        if (!BlockColor.isExplicit(color)) {
            return state;
        }
        return ChestColorizer.barrelBlock().defaultBlockState()
                .setValue(ColorizedBarrelBlock.COLOR, color)
                .setValue(BarrelBlock.FACING, state.getValue(BarrelBlock.FACING))
                .setValue(BarrelBlock.OPEN, state.getValue(BarrelBlock.OPEN));
    }

    public static void updateColor(BlockPos position, DyeItem dyeItem) {
        ColorizerConfig.setColor(getLevelName(), position, BlockColor.fromDyeColor(dyeItem.getDyeColor()));
        markBlockRenderDirty(position);
    }

    public static void clearColor(BlockPos position) {
        ColorizerConfig.removeColor(getLevelName(), position);
        markBlockRenderDirty(position);
    }

    public static void clearChestColor(BlockPos position, BlockState state) {
        String worldName = getLevelName();
        ColorizerConfig.removeColor(worldName, position);
        if (state.hasProperty(ChestBlock.FACING) && state.hasProperty(ChestBlock.TYPE)) {
            Direction direction = state.getValue(ChestBlock.FACING);
            ChestType type = state.getValue(ChestBlock.TYPE);
            if (type == ChestType.LEFT) {
                ColorizerConfig.removeColor(worldName, position.relative(direction.getClockWise()));
            } else if (type == ChestType.RIGHT) {
                ColorizerConfig.removeColor(worldName, position.relative(direction.getCounterClockWise()));
            }
        }
        markBlockRenderDirty(position);
    }

    private static BlockColor getColor(BlockPos position) {
        BlockColor color = ColorizerConfig.getColor(getLevelName(), position);
        return color == null ? BlockColor.DEFAULT : color;
    }

    @Nullable
    private static BlockColor getChestColor(String worldName, BlockEntity entity, ChestType type) {
        BlockPos position = entity.getBlockPos();
        BlockColor color = ColorizerConfig.getColor(worldName, position);
        BlockState state = entity.getBlockState();
        if (color == null && state.hasProperty(ChestBlock.FACING)) {
            Direction direction = state.getValue(ChestBlock.FACING);
            if (type == ChestType.LEFT) {
                color = ColorizerConfig.getColor(worldName, position.relative(direction.getClockWise()));
            } else if (type == ChestType.RIGHT) {
                color = ColorizerConfig.getColor(worldName, position.relative(direction.getCounterClockWise()));
            }
        }
        return color;
    }

    @Nullable
    private static String getLevelName() {
        Minecraft client = Minecraft.getInstance();
        if (client.isSingleplayer() && client.getSingleplayerServer() != null) {
            return client.getSingleplayerServer().getWorldData().getLevelName();
        }
        ServerData server = client.getCurrentServer();
        return server == null ? null : server.ip;
    }

    private static void markBlockRenderDirty(BlockPos position) {
        Minecraft client = Minecraft.getInstance();
        client.execute(() -> {
            if (client.level == null) {
                return;
            }
            BlockState state = client.level.getBlockState(position);
            client.level.sendBlockUpdated(position, state, state, 0);
        });
    }

    private static Material chooseMaterial(ChestType type, Material normal, Material left, Material right) {
        return switch (type) {
            case LEFT -> left;
            case RIGHT -> right;
            case SINGLE -> normal;
        };
    }

    private static Material createChestMaterial(String variant) {
        return new Material(
                Sheets.CHEST_SHEET,
                ResourceLocation.fromNamespaceAndPath(ChestColorizer.MOD_ID, "entity/chest/" + variant)
        );
    }
}

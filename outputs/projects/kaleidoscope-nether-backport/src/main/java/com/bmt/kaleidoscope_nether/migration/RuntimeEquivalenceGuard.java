package com.bmt.kaleidoscope_nether.migration;

import com.mojang.logging.LogUtils;
import net.minecraft.core.Direction;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.food.FoodProperties;
import net.minecraft.world.item.Equipable;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.HorizontalDirectionalBlock;
import net.minecraft.world.level.material.FlowingFluid;
import net.minecraft.world.level.material.Fluid;
import net.minecraft.world.level.material.FluidState;
import net.neoforged.fml.ModList;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.server.ServerAboutToStartEvent;
import org.slf4j.Logger;

public final class RuntimeEquivalenceGuard {
    private static final Logger LOGGER = LogUtils.getLogger();

    private RuntimeEquivalenceGuard() {
    }

    public static void register() {
        NeoForge.EVENT_BUS.addListener(RuntimeEquivalenceGuard::verify);
    }

    private static void verify(ServerAboutToStartEvent event) {
        verifyFood("giant_beast_croissant");
        verifyFood("magma_sweet_and_sour_pork");
        verifyFluidPair("warped_juice", "flowing_warped_juice", event);
        verifyFluidPair("crimson_juice", "flowing_crimson_juice", event);

        boolean standaloneDolls = !ModList.get().isLoaded("kaleidoscope_doll");
        for (int index = 0; index < 13; index++) {
            verifyDoll(index, standaloneDolls);
        }
        LOGGER.info("Kaleidoscope Nether equivalence guard passed: 2 foods, 4 fluids, 13 dolls");
    }

    private static void verifyFood(String path) {
        Item item = BuiltInRegistries.ITEM.get(KaleidoscopeNetherEquivalence.netherId(path));
        require(item != Items.AIR, "Missing food item: " + path);
        ItemStack stack = item.getDefaultInstance();
        FoodProperties food = stack.get(DataComponents.FOOD);
        require(food != null, "Missing food component: " + path);
        require(food.nutrition() == 2, "Wrong nutrition: " + path);
        require(close(food.saturation(), 1.2F), "Wrong saturation: " + path);
        require(food.canAlwaysEat(), "Food must always be edible: " + path);
        require(close(food.eatSeconds(), 1.6F), "Wrong eating duration: " + path);
        require(food.usingConvertsTo().isEmpty(), "Unexpected food remainder: " + path);
        require(food.effects().isEmpty(), "Unexpected food effects: " + path);
        require(stack.has(DataComponents.FIRE_RESISTANT), "Missing fire resistance: " + path);
        require(stack.getMaxStackSize() == 64, "Wrong max stack size: " + path);
    }

    private static void verifyFluidPair(String sourcePath, String flowingPath, ServerAboutToStartEvent event) {
        Fluid sourceFluid = BuiltInRegistries.FLUID.get(KaleidoscopeNetherEquivalence.netherId(sourcePath));
        Fluid flowingFluid = BuiltInRegistries.FLUID.get(KaleidoscopeNetherEquivalence.netherId(flowingPath));
        require(sourceFluid instanceof FlowingFluid, "Missing source fluid: " + sourcePath);
        require(flowingFluid instanceof FlowingFluid, "Missing flowing fluid: " + flowingPath);
        FlowingFluid source = (FlowingFluid) sourceFluid;
        FlowingFluid flowing = (FlowingFluid) flowingFluid;
        require(source.getSource() == sourceFluid, "Wrong source link: " + sourcePath);
        require(source.getFlowing() == flowingFluid, "Wrong flowing link: " + sourcePath);
        require(flowing.getSource() == sourceFluid, "Wrong source link: " + flowingPath);
        require(flowing.getFlowing() == flowingFluid, "Wrong flowing link: " + flowingPath);

        FluidState sourceState = sourceFluid.defaultFluidState();
        FluidState flowingState = flowingFluid.defaultFluidState();
        require(sourceState.isSource() && sourceState.getAmount() == 8, "Wrong source state: " + sourcePath);
        require(!flowingState.isSource() && flowingState.getAmount() == 7, "Wrong flowing state: " + flowingPath);
        require(sourceFluid.getTickDelay(event.getServer().overworld()) == 20, "Wrong tick delay: " + sourcePath);
        require(flowingFluid.getTickDelay(event.getServer().overworld()) == 20, "Wrong tick delay: " + flowingPath);
        require(sourceFluid.getBucket() == Items.AIR, "Unexpected bucket: " + sourcePath);
        require(flowingFluid.getBucket() == Items.AIR, "Unexpected bucket: " + flowingPath);
        require(sourceState.createLegacyBlock().isAir(), "Unexpected fluid block: " + sourcePath);
        require(flowingState.createLegacyBlock().isAir(), "Unexpected fluid block: " + flowingPath);
    }

    private static void verifyDoll(int index, boolean standaloneDolls) {
        String path = "doll_" + index;
        Block block = BuiltInRegistries.BLOCK.get(KaleidoscopeNetherEquivalence.netherId(path));
        Item item = BuiltInRegistries.ITEM.get(KaleidoscopeNetherEquivalence.netherId(path));
        require(item != Items.AIR, "Missing doll item: " + path);
        if (!standaloneDolls) {
            return;
        }
        require(block instanceof NetherDollBlock, "Wrong doll block implementation: " + path);
        require(item instanceof NetherDollItem, "Wrong doll item implementation: " + path);
        require(block.defaultBlockState().getValue(HorizontalDirectionalBlock.FACING) == Direction.NORTH,
                "Wrong default doll facing: " + path);
        require(item.getDefaultInstance().getMaxStackSize() == 1, "Wrong doll stack size: " + path);
        require(item instanceof Equipable && ((Equipable) item).getEquipmentSlot() == EquipmentSlot.HEAD,
                "Doll is not head-equippable: " + path);
    }

    private static boolean close(float actual, float expected) {
        return Math.abs(actual - expected) < 0.0001F;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException("Kaleidoscope Nether equivalence check failed: " + message);
        }
    }
}

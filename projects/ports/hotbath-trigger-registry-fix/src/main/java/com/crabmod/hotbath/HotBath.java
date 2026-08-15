package com.crabmod.hotbath;

import com.crabmod.hotbath.client.particle.CustomDripParticle;
import com.crabmod.hotbath.client.particle.HotBathBubbleParticle;
import com.crabmod.hotbath.compat.ColdSweatCompat;
import com.crabmod.hotbath.compat.ColdSweatIntegration;
import com.crabmod.hotbath.compat.LegendarySurvivalOverhaulIntegration;
import com.crabmod.hotbath.compat.LSOCompat;
import com.crabmod.hotbath.compat.ToughAsNailsCompat;
import com.crabmod.hotbath.compat.ToughAsNailsIntegration;
import com.crabmod.hotbath.fluid_details.HotbathFluidType;
import com.crabmod.hotbath.item.ItemGroup;
import com.crabmod.hotbath.registers.BlocksRegister;
import com.crabmod.hotbath.registers.EntityRegister;
import com.crabmod.hotbath.registers.FluidsRegister;
import com.crabmod.hotbath.registers.ItemRegister;
import com.crabmod.hotbath.registers.ParticleRegister;
import com.mojang.logging.LogUtils;
import net.minecraft.client.Minecraft;
import net.minecraft.client.particle.BubbleParticle;
import net.minecraft.client.renderer.ItemBlockRenderTypes;
import net.minecraft.client.renderer.RenderType;
import net.minecraft.client.renderer.entity.EntityRenderers;
import net.minecraft.client.renderer.entity.ThrownItemRenderer;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.level.material.Fluids;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.fml.common.Mod;
import net.neoforged.fml.event.lifecycle.FMLClientSetupEvent;
import net.neoforged.fml.event.lifecycle.FMLCommonSetupEvent;
import net.neoforged.fml.loading.FMLEnvironment;
import net.neoforged.neoforge.client.event.RegisterParticleProvidersEvent;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.common.brewing.BrewingRecipeRegistry;
import net.neoforged.neoforge.event.server.ServerStartingEvent;
import org.slf4j.Logger;

// The value here should match an entry in the META-INF/mods.toml file
@Mod(HotBath.MOD_ID)
public class HotBath {
    // Define mod id in a common place for everything to reference
    public static final String MOD_ID = "hotbath";
    // Directly reference a slf4j logger
    public static final Logger LOGGER = LogUtils.getLogger();

    public HotBath(ModContainer modContainer, IEventBus modEventBus) {
        ItemGroup.register(modEventBus);
        FluidsRegister.register(modEventBus);
        BlocksRegister.register(modEventBus);
        ItemRegister.register(modEventBus);
        ParticleRegister.register(modEventBus);
        EntityRegister.register(modEventBus);
        HotbathFluidType.register(modEventBus);
        // Register the commonSetup method for modloading
        modEventBus.addListener(this::commonSetup);

        // Register ourselves for server and other game events we are interested in
        NeoForge.EVENT_BUS.register(this);
//    modEventBus.addListener(this::addCreative);

        if (FMLEnvironment.dist == Dist.CLIENT) {
            modEventBus.addListener(ClientModEvents::onClientSetup);
            modEventBus.addListener(ClientModEvents::registerParticles);
        }
    }

    private void commonSetup(final FMLCommonSetupEvent event) {
        LOGGER.info("HELLO FROM COMMON SETUP");

        if (ColdSweatIntegration.isColdSweatLoaded()) {
            LOGGER.info("Cold Sweat detected! Temperature integration enabled.");
            try {
                ColdSweatCompat.init();
                LOGGER.info("Cold Sweat event handler registered successfully.");
            } catch (Exception e) {
                LOGGER.error("Failed to register Cold Sweat event handler: {}", e.getMessage(), e);
            }
        }

        if (ToughAsNailsIntegration.isToughAsNailsLoaded()) {
            LOGGER.info("Tough As Nails detected! Temperature integration enabled.");
            try {
                ToughAsNailsCompat.init();
                LOGGER.info("Tough As Nails integration registered successfully.");
            } catch (Exception e) {
                LOGGER.error("Failed to initialize Tough As Nails integration: {}", e.getMessage(), e);
            }
        }

        if (LegendarySurvivalOverhaulIntegration.isLSOLoaded()) {
            LOGGER.info("Legendary Survival Overhaul detected! Integration enabled.");
            try {
                LSOCompat.init();
                LOGGER.info("LSO integration registered successfully.");
            } catch (Exception e) {
                LOGGER.error("Failed to register LSO integration: {}", e.getMessage(), e);
            }
        }
    }

    // You can use SubscribeEvent and let the Event Bus discover methods to call
    @SubscribeEvent
    public void onServerStarting(ServerStartingEvent event) {
        // Do something when the server starts
        LOGGER.info("HELLO from server starting");
    }

    // You can use EventBusSubscriber to automatically register all static methods in the class
    // annotated with @SubscribeEvent
    public static class ClientModEvents {
        @SubscribeEvent
        public static void onClientSetup(FMLClientSetupEvent event) {
            EntityRenderers.register(EntityRegister.THROWN_BATH_WATER.get(), ThrownItemRenderer::new);

            ItemBlockRenderTypes.setRenderLayer(FluidsRegister.HOT_WATER_FLUID.get(), RenderType.translucent());
            ItemBlockRenderTypes.setRenderLayer(FluidsRegister.HOT_WATER_FLOWING.get(), RenderType.translucent());
            ItemBlockRenderTypes.setRenderLayer(FluidsRegister.HONEY_BATH_FLUID.get(), RenderType.translucent());
            ItemBlockRenderTypes.setRenderLayer(FluidsRegister.HONEY_BATH_FLOWING.get(), RenderType.translucent());
            ItemBlockRenderTypes.setRenderLayer(FluidsRegister.MILK_BATH_FLUID.get(), RenderType.translucent());
            ItemBlockRenderTypes.setRenderLayer(FluidsRegister.MILK_BATH_FLOWING.get(), RenderType.translucent());
            ItemBlockRenderTypes.setRenderLayer(FluidsRegister.HERBAL_BATH_FLUID.get(), RenderType.translucent());
            ItemBlockRenderTypes.setRenderLayer(FluidsRegister.HERBAL_BATH_FLOWING.get(), RenderType.translucent());
            ItemBlockRenderTypes.setRenderLayer(FluidsRegister.PEONY_BATH_FLUID.get(), RenderType.translucent());
            ItemBlockRenderTypes.setRenderLayer(FluidsRegister.PEONY_BATH_FLOWING.get(), RenderType.translucent());
            ItemBlockRenderTypes.setRenderLayer(FluidsRegister.ROSE_BATH_FLUID.get(), RenderType.translucent());
            ItemBlockRenderTypes.setRenderLayer(FluidsRegister.ROSE_BATH_FLOWING.get(), RenderType.translucent());
        }

        @SubscribeEvent
        public static void registerParticles(RegisterParticleProvidersEvent event) {
            event.registerSpriteSet(ParticleRegister.HOT_WATER_SPLASH.get(), net.minecraft.client.particle.SplashParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.HONEY_WATER_SPLASH.get(), net.minecraft.client.particle.SplashParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.MILK_WATER_SPLASH.get(), net.minecraft.client.particle.SplashParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.HERBAL_WATER_SPLASH.get(), net.minecraft.client.particle.SplashParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.PEONY_WATER_SPLASH.get(), net.minecraft.client.particle.SplashParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.ROSE_WATER_SPLASH.get(), net.minecraft.client.particle.SplashParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.HOT_WATER_EFFECT.get(), net.minecraft.client.particle.SpellParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.HONEY_BATH_EFFECT.get(), net.minecraft.client.particle.SpellParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.MILK_BATH_EFFECT.get(), net.minecraft.client.particle.SpellParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.HERBAL_BATH_EFFECT.get(), net.minecraft.client.particle.SpellParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.PEONY_BATH_EFFECT.get(), net.minecraft.client.particle.SpellParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.ROSE_BATH_EFFECT.get(), net.minecraft.client.particle.SpellParticle.Provider::new);

            // Bubbles
            event.registerSpriteSet(ParticleRegister.HOT_WATER_BUBBLE.get(), HotBathBubbleParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.HONEY_BATH_BUBBLE.get(), HotBathBubbleParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.MILK_BATH_BUBBLE.get(), HotBathBubbleParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.HERBAL_BATH_BUBBLE.get(), HotBathBubbleParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.PEONY_BATH_BUBBLE.get(), HotBathBubbleParticle.Provider::new);
            event.registerSpriteSet(ParticleRegister.ROSE_BATH_BUBBLE.get(), HotBathBubbleParticle.Provider::new);

            // Dripping (Hanging)
            event.registerSpriteSet(ParticleRegister.DRIPPING_HOT_WATER.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, ParticleRegister.FALLING_HOT_WATER.get(), ParticleRegister.LANDING_HOT_WATER.get()));
            event.registerSpriteSet(ParticleRegister.DRIPPING_HONEY_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, ParticleRegister.FALLING_HONEY_BATH.get(), ParticleRegister.LANDING_HONEY_BATH.get()));
            event.registerSpriteSet(ParticleRegister.DRIPPING_MILK_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, ParticleRegister.FALLING_MILK_BATH.get(), ParticleRegister.LANDING_MILK_BATH.get()));
            event.registerSpriteSet(ParticleRegister.DRIPPING_HERBAL_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, ParticleRegister.FALLING_HERBAL_BATH.get(), ParticleRegister.LANDING_HERBAL_BATH.get()));
            event.registerSpriteSet(ParticleRegister.DRIPPING_PEONY_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, ParticleRegister.FALLING_PEONY_BATH.get(), ParticleRegister.LANDING_PEONY_BATH.get()));
            event.registerSpriteSet(ParticleRegister.DRIPPING_ROSE_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, ParticleRegister.FALLING_ROSE_BATH.get(), ParticleRegister.LANDING_ROSE_BATH.get()));

            // Falling
            event.registerSpriteSet(ParticleRegister.FALLING_HOT_WATER.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, null, ParticleRegister.LANDING_HOT_WATER.get()));
            event.registerSpriteSet(ParticleRegister.FALLING_HONEY_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, null, ParticleRegister.LANDING_HONEY_BATH.get()));
            event.registerSpriteSet(ParticleRegister.FALLING_MILK_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, null, ParticleRegister.LANDING_MILK_BATH.get()));
            event.registerSpriteSet(ParticleRegister.FALLING_HERBAL_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, null, ParticleRegister.LANDING_HERBAL_BATH.get()));
            event.registerSpriteSet(ParticleRegister.FALLING_PEONY_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, null, ParticleRegister.LANDING_PEONY_BATH.get()));
            event.registerSpriteSet(ParticleRegister.FALLING_ROSE_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, null, ParticleRegister.LANDING_ROSE_BATH.get()));

            // Landing
            event.registerSpriteSet(ParticleRegister.LANDING_HOT_WATER.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, null, null));
            event.registerSpriteSet(ParticleRegister.LANDING_HONEY_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, null, null));
            event.registerSpriteSet(ParticleRegister.LANDING_MILK_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, null, null));
            event.registerSpriteSet(ParticleRegister.LANDING_HERBAL_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, null, null));
            event.registerSpriteSet(ParticleRegister.LANDING_PEONY_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, null, null));
            event.registerSpriteSet(ParticleRegister.LANDING_ROSE_BATH.get(), 
                sprite -> new CustomDripParticle.Factory(sprite, net.minecraft.world.level.material.Fluids.WATER, null, null));
        }
    }

    @SubscribeEvent
    public void onBrewingRecipeRegister(net.neoforged.neoforge.event.brewing.RegisterBrewingRecipesEvent event) {
        event.getBuilder().addRecipe(Ingredient.of(ItemRegister.HOT_WATER_BOTTLE.get()), Ingredient.of(Items.GUNPOWDER), ItemRegister.SPLASH_HOT_WATER_BOTTLE.get().getDefaultInstance());
        event.getBuilder().addRecipe(Ingredient.of(ItemRegister.HONEY_BATH_BOTTLE.get()), Ingredient.of(Items.GUNPOWDER), ItemRegister.SPLASH_HONEY_BATH_BOTTLE.get().getDefaultInstance());
        event.getBuilder().addRecipe(Ingredient.of(ItemRegister.MILK_BATH_BOTTLE.get()), Ingredient.of(Items.GUNPOWDER), ItemRegister.SPLASH_MILK_BATH_BOTTLE.get().getDefaultInstance());
        event.getBuilder().addRecipe(Ingredient.of(ItemRegister.HERBAL_BATH_BOTTLE.get()), Ingredient.of(Items.GUNPOWDER), ItemRegister.SPLASH_HERBAL_BATH_BOTTLE.get().getDefaultInstance());
        event.getBuilder().addRecipe(Ingredient.of(ItemRegister.PEONY_BATH_BOTTLE.get()), Ingredient.of(Items.GUNPOWDER), ItemRegister.SPLASH_PEONY_BATH_BOTTLE.get().getDefaultInstance());
        event.getBuilder().addRecipe(Ingredient.of(ItemRegister.ROSE_BATH_BOTTLE.get()), Ingredient.of(Items.GUNPOWDER), ItemRegister.SPLASH_ROSE_BATH_BOTTLE.get().getDefaultInstance());
    }
}
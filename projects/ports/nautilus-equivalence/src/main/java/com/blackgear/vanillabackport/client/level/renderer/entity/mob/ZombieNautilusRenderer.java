package com.blackgear.vanillabackport.client.level.renderer.entity.mob;

import com.blackgear.vanillabackport.client.level.layer.SimpleEquipmentLayer;
import com.blackgear.vanillabackport.client.level.model.entity.nautilus.NautilusModel;
import com.blackgear.vanillabackport.client.level.model.entity.nautilus.ZombieNautilusCoralModel;
import com.blackgear.vanillabackport.client.registries.ModModelLayers;
import com.blackgear.vanillabackport.common.level.entity.mob.animal.nautilus.AbstractNautilus;
import com.blackgear.vanillabackport.common.level.entity.mob.animal.nautilus.ZombieNautilus;
import com.blackgear.vanillabackport.common.level.entity.mob.animal.nautilus.ZombieNautilusVariant;
import com.blackgear.vanillabackport.common.level.item.NautilusArmorItem;
import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraft.client.renderer.entity.MobRenderer;
import net.minecraft.resources.ResourceLocation;

import java.util.Optional;

public class ZombieNautilusRenderer extends MobRenderer<ZombieNautilus, NautilusModel<ZombieNautilus>> {
    private final NautilusModel<ZombieNautilus> normalModel;
    private final NautilusModel<ZombieNautilus> warmModel;
    
    public ZombieNautilusRenderer(EntityRendererProvider.Context context) {
        super(context, new NautilusModel<>(context.bakeLayer(ModModelLayers.ZOMBIE_NAUTILUS)), 0.7F);
        this.normalModel = this.model;
        this.warmModel = new ZombieNautilusCoralModel<>(context.bakeLayer(ModModelLayers.ZOMBIE_NAUTILUS_CORAL));
        this.addLayer(new SimpleEquipmentLayer<>(
            this,
            entity -> entity.getBodyArmorItem().getItem() instanceof NautilusArmorItem armor
                ? Optional.ofNullable(armor.getTexture())
                : Optional.empty(),
            entity -> true,
            new NautilusModel<>(context.bakeLayer(ModModelLayers.NAUTILUS_ARMOR)),
            null
        ));
        this.addLayer(SimpleEquipmentLayer.of(
            this,
            NautilusRenderer.NAUTILUS_SADDLE_LOCATION,
            AbstractNautilus::isSaddled,
            new NautilusModel<>(context.bakeLayer(ModModelLayers.NAUTILUS_SADDLE)),
            null
        ));
    }
    
    @Override
    public ResourceLocation getTextureLocation(ZombieNautilus entity) {
        return entity.getVariantData().texture();
    }
    
    @Override
    public void render(ZombieNautilus entity, float entityYaw, float partialTicks, PoseStack poseStack, MultiBufferSource buffer, int packedLight) {
        this.model = entity.getVariantData().model() == ZombieNautilusVariant.ModelType.WARM
            ? this.warmModel
            : this.normalModel;
        super.render(entity, entityYaw, partialTicks, poseStack, buffer, packedLight);
    }
}

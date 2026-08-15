package com.github.ysbbbbbb.kaleidoscopecookery.crafting.soupbase;

import com.github.ysbbbbbb.kaleidoscopecookery.api.client.render.ISoupBaseRender;
import com.github.ysbbbbbb.kaleidoscopecookery.client.render.soupbase.MobSoupBaseRender;
import com.github.ysbbbbbb.kaleidoscopecookery.mixin.MobBucketItemAccessor;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.item.Item;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;

public class MobSoupBase extends FluidSoupBase {
    private final EntityType<?> type;

    public MobSoupBase(ResourceLocation name, Item bucket, int bubbleColor) {
        super(name, bucket, bubbleColor);
        if (bucket instanceof MobBucketItemAccessor accessor && accessor.kaleidoscope$GetFishType() != null) {
            this.type = accessor.kaleidoscope$GetFishType();
        } else {
            throw new IllegalArgumentException("Mob bucket item must have a valid entity type!");
        }
    }

    public MobSoupBase(ResourceLocation name, Item bucket) {
        this(name, bucket, 0x3F76E4);
    }

    @Override
    @OnlyIn(Dist.CLIENT)
    public ISoupBaseRender getRender() {
        return new MobSoupBaseRender(this.fluid, this.type);
    }
}

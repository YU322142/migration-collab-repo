package com.github.ysbbbbbb.kaleidoscopecookery.datagen;

import com.github.ysbbbbbb.kaleidoscopecookery.KaleidoscopeCookery;
import com.github.ysbbbbbb.kaleidoscopecookery.init.ModParticles;
import net.minecraft.data.PackOutput;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.common.data.ExistingFileHelper;
import net.minecraftforge.common.data.ParticleDescriptionProvider;

public class ParticleDescriptionGenerator extends ParticleDescriptionProvider {
    public ParticleDescriptionGenerator(PackOutput output, ExistingFileHelper fileHelper) {
        super(output, fileHelper);
    }

    @Override
    protected void addDescriptions() {
        this.spriteSet(ModParticles.COOKING.get(), new ResourceLocation("generic"), 8, true);
        this.spriteSet(ModParticles.STOCKPOT.get(), new ResourceLocation(KaleidoscopeCookery.MOD_ID, "stockpot"), 5, false);
    }
}

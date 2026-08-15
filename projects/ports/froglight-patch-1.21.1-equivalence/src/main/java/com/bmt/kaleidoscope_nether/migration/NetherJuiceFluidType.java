package com.bmt.kaleidoscope_nether.migration;

import net.minecraft.resources.ResourceLocation;
import net.neoforged.neoforge.client.extensions.common.IClientFluidTypeExtensions;
import net.neoforged.neoforge.fluids.FluidType;

import java.util.function.Consumer;

public final class NetherJuiceFluidType extends FluidType {
    private final ResourceLocation stillTexture;
    private final ResourceLocation flowingTexture;

    public NetherJuiceFluidType(ResourceLocation id) {
        super(Properties.create().canConvertToSource(false));
        stillTexture = ResourceLocation.fromNamespaceAndPath(id.getNamespace(), "block/" + id.getPath() + "_still");
        flowingTexture = ResourceLocation.fromNamespaceAndPath(id.getNamespace(), "block/" + id.getPath() + "_flow");
    }

    @Override
    public void initializeClient(Consumer<IClientFluidTypeExtensions> consumer) {
        consumer.accept(new IClientFluidTypeExtensions() {
            @Override
            public ResourceLocation getStillTexture() {
                return stillTexture;
            }

            @Override
            public ResourceLocation getFlowingTexture() {
                return flowingTexture;
            }
        });
    }
}

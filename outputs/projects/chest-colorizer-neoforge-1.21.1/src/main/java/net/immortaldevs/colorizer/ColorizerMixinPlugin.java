package net.immortaldevs.colorizer;

import java.util.Collections;
import java.util.List;
import java.util.Set;
import net.neoforged.fml.loading.FMLLoader;
import org.objectweb.asm.tree.ClassNode;
import org.spongepowered.asm.mixin.extensibility.IMixinConfigPlugin;
import org.spongepowered.asm.mixin.extensibility.IMixinInfo;

public final class ColorizerMixinPlugin implements IMixinConfigPlugin {
    private static final String SECTION_COMPILER_MIXIN =
            "net.immortaldevs.colorizer.mixin.SectionCompilerMixin";
    private static final String SODIUM_MIXIN = "net.immortaldevs.colorizer.mixin.sodium.LevelSliceMixin";

    @Override
    public boolean shouldApplyMixin(String targetClassName, String mixinClassName) {
        return shouldApplyRenderMixin(
                mixinClassName,
                FMLLoader.getLoadingModList().getModFileById("sodium") != null);
    }

    static boolean shouldApplyRenderMixin(String mixinClassName, boolean sodiumPresent) {
        if (SODIUM_MIXIN.equals(mixinClassName)) {
            return sodiumPresent;
        }
        if (SECTION_COMPILER_MIXIN.equals(mixinClassName)) {
            return !sodiumPresent;
        }
        return true;
    }

    @Override
    public void onLoad(String mixinPackage) {
    }

    @Override
    public String getRefMapperConfig() {
        return null;
    }

    @Override
    public void acceptTargets(Set<String> myTargets, Set<String> otherTargets) {
    }

    @Override
    public List<String> getMixins() {
        return Collections.emptyList();
    }

    @Override
    public void preApply(String targetClassName, ClassNode targetClass, String mixinClassName, IMixinInfo mixinInfo) {
    }

    @Override
    public void postApply(String targetClassName, ClassNode targetClass, String mixinClassName, IMixinInfo mixinInfo) {
    }
}

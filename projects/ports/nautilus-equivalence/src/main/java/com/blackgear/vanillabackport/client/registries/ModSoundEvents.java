package com.blackgear.vanillabackport.client.registries;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.sounds.SoundEvent;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;

public final class ModSoundEvents {
    public static final DeferredRegister<SoundEvent> SOUNDS =
        DeferredRegister.create(BuiltInRegistries.SOUND_EVENT, "minecraft");

    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_AMBIENT = sound("entity.nautilus.ambient");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_AMBIENT_ON_LAND = sound("entity.nautilus.ambient_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_DASH = sound("entity.nautilus.dash");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_DASH_ON_LAND = sound("entity.nautilus.dash_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_DASH_READY = sound("entity.nautilus.dash_ready");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_DASH_READY_ON_LAND = sound("entity.nautilus.dash_ready_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_DEATH = sound("entity.nautilus.death");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_DEATH_ON_LAND = sound("entity.nautilus.death_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_EAT = sound("entity.nautilus.eat");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_HURT = sound("entity.nautilus.hurt");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_HURT_ON_LAND = sound("entity.nautilus.hurt_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_SWIM = sound("entity.nautilus.swim");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_RIDING = sound("entity.nautilus.riding");

    public static final DeferredHolder<SoundEvent, SoundEvent> BABY_NAUTILUS_AMBIENT = sound("entity.baby_nautilus.ambient");
    public static final DeferredHolder<SoundEvent, SoundEvent> BABY_NAUTILUS_AMBIENT_ON_LAND = sound("entity.baby_nautilus.ambient_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> BABY_NAUTILUS_DEATH = sound("entity.baby_nautilus.death");
    public static final DeferredHolder<SoundEvent, SoundEvent> BABY_NAUTILUS_DEATH_ON_LAND = sound("entity.baby_nautilus.death_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> BABY_NAUTILUS_EAT = sound("entity.baby_nautilus.eat");
    public static final DeferredHolder<SoundEvent, SoundEvent> BABY_NAUTILUS_HURT = sound("entity.baby_nautilus.hurt");
    public static final DeferredHolder<SoundEvent, SoundEvent> BABY_NAUTILUS_HURT_ON_LAND = sound("entity.baby_nautilus.hurt_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> BABY_NAUTILUS_SWIM = sound("entity.baby_nautilus.swim");

    public static final DeferredHolder<SoundEvent, SoundEvent> ZOMBIE_NAUTILUS_AMBIENT = sound("entity.zombie_nautilus.ambient");
    public static final DeferredHolder<SoundEvent, SoundEvent> ZOMBIE_NAUTILUS_AMBIENT_ON_LAND = sound("entity.zombie_nautilus.ambient_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> ZOMBIE_NAUTILUS_DASH = sound("entity.zombie_nautilus.dash");
    public static final DeferredHolder<SoundEvent, SoundEvent> ZOMBIE_NAUTILUS_DASH_ON_LAND = sound("entity.zombie_nautilus.dash_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> ZOMBIE_NAUTILUS_DASH_READY = sound("entity.zombie_nautilus.dash_ready");
    public static final DeferredHolder<SoundEvent, SoundEvent> ZOMBIE_NAUTILUS_DASH_READY_ON_LAND = sound("entity.zombie_nautilus.dash_ready_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> ZOMBIE_NAUTILUS_DEATH = sound("entity.zombie_nautilus.death");
    public static final DeferredHolder<SoundEvent, SoundEvent> ZOMBIE_NAUTILUS_DEATH_ON_LAND = sound("entity.zombie_nautilus.death_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> ZOMBIE_NAUTILUS_EAT = sound("entity.zombie_nautilus.eat");
    public static final DeferredHolder<SoundEvent, SoundEvent> ZOMBIE_NAUTILUS_HURT = sound("entity.zombie_nautilus.hurt");
    public static final DeferredHolder<SoundEvent, SoundEvent> ZOMBIE_NAUTILUS_HURT_ON_LAND = sound("entity.zombie_nautilus.hurt_land");
    public static final DeferredHolder<SoundEvent, SoundEvent> ZOMBIE_NAUTILUS_SWIM = sound("entity.zombie_nautilus.swim");
    public static final DeferredHolder<SoundEvent, SoundEvent> PARROT_IMITATE_ZOMBIE_NAUTILUS = sound("entity.parrot.imitate.zombie_nautilus");

    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_SADDLE_UNDERWATER_EQUIP = sound("item.nautilus_saddle_underwater_equip");
    public static final DeferredHolder<SoundEvent, SoundEvent> NAUTILUS_SADDLE_EQUIP = sound("item.nautilus_saddle_equip");
    public static final DeferredHolder<SoundEvent, SoundEvent> ARMOR_EQUIP_NAUTILUS = sound("item.armor.equip_nautilus");
    public static final DeferredHolder<SoundEvent, SoundEvent> ARMOR_UNEQUIP_NAUTILUS = sound("item.armor.unequip_nautilus");
    public static final DeferredHolder<SoundEvent, SoundEvent> SADDLE_UNEQUIP = sound("item.saddle.unequip");

    private static DeferredHolder<SoundEvent, SoundEvent> sound(String id) {
        return SOUNDS.register(id, () -> SoundEvent.createVariableRangeEvent(ResourceLocation.withDefaultNamespace(id)));
    }

    private ModSoundEvents() {
    }
}

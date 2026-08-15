/*
 * Copyright (C) 2025  DragonsPlus
 * SPDX-License-Identifier: LGPL-3.0-or-later
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

package plus.dragons.createenchantmentindustry.integration.apothic_enchanting.common.contraptions.actors.enderWovenBag;

import com.mojang.serialization.Codec;
import io.netty.buffer.ByteBuf;
import java.util.*;
import java.util.function.Function;
import javax.annotation.Nullable;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.NbtOps;
import net.minecraft.nbt.Tag;
import net.minecraft.network.chat.Component;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.Level;
import plus.dragons.createenchantmentindustry.integration.apothic_enchanting.config.CEIAConfig;

public class StoredEntities {
    public static final Codec<StoredEntities> CODEC = CompoundTag.CODEC.listOf().xmap(StoredEntities::new, (s) -> s.entityTags);
    public static final StreamCodec<ByteBuf, StoredEntities> STREAM_CODEC = ByteBufCodecs.COMPOUND_TAG.apply(
            ByteBufCodecs.list(256)).map(StoredEntities::new, (s) -> s.entityTags);

    private List<CompoundTag> entityTags;
    private Map<Component, Integer> nameCache = new HashMap<>();

    @Override
    public int hashCode() {
        return Objects.hash(this.entityTags, this.nameCache);
    }

    @Override
    public boolean equals(Object obj) {
        if (obj == this) {
            return true;
        } else {
            return obj instanceof StoredEntities ex
                    && this.entityTags == ex.entityTags
                    && this.nameCache == ex.nameCache;
        }
    }

    public StoredEntities(List<CompoundTag> entityTags) {
        this.entityTags = entityTags;
    }

    public StoredEntities() {
        this(new ArrayList<>());
    }

    public Map<Component, Integer> getEntityNames(Level level) {
        if (entityTags.isEmpty()) return new HashMap<>();
        if (nameCache.isEmpty()) {
            for (CompoundTag tag : entityTags) {
                var component = EntityType.loadEntityRecursive(tag, level, Function.identity()).getName();
                if (nameCache.containsKey(component))
                    nameCache.put(component, nameCache.get(component) + 1);
                else nameCache.put(component, 1);
            }
        }
        return nameCache;
    }

    @Nullable
    public Entity pop(Level level) {
        if (entityTags.isEmpty()) return null;
        var tag = entityTags.getLast();
        entityTags = new ArrayList<>(entityTags);
        entityTags.removeLast();
        nameCache.clear();
        return EntityType.loadEntityRecursive(tag, level, Function.identity());
    }

    @Nullable
    public Entity peak(Level level) {
        if (entityTags.isEmpty()) return null;
        var tag = entityTags.getLast();
        return EntityType.loadEntityRecursive(tag, level, Function.identity());
    }

    public void push(Entity entity) {
        CompoundTag tag = new CompoundTag();
        entity.save(tag);
        entityTags = new ArrayList<>(entityTags);
        entityTags.add(tag);
        nameCache.clear();
    }

    public int count() {
        return entityTags.size();
    }

    public boolean full() {
        return count() >= CEIAConfig.server().utility().enderWovenBagCapacity.get();
    }

    public static StoredEntities parse(HolderLookup.Provider lookupProvider, Tag tag) {
        return CODEC.parse(lookupProvider.createSerializationContext(NbtOps.INSTANCE), tag).result().get();
    }

    public Tag tag(HolderLookup.Provider lookupProvider) {
        return CODEC.encodeStart(lookupProvider.createSerializationContext(NbtOps.INSTANCE), this).getOrThrow();
    }
}

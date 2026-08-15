package com.tom.storagemod.inventory;

import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.Stack;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;

import com.tom.storagemod.block.IInventoryCable;
import com.tom.storagemod.util.BlockFace;
import com.tom.storagemod.util.WorldStates;

public class InventoryCableNetwork {
	private static final long INCOMPLETE_RESCAN_TICKS = 100L;
	private final Level level;
	private Map<BlockPos, CableCache> caches = new HashMap<>();

	public InventoryCableNetwork(Level level) {
		this.level = level;
	}

	public Collection<BlockPos> getNetworkNodes(BlockPos from) {
		long gameTime = level.getGameTime();
		CableCache cache = caches.get(from);
		if (cache != null) {
			if (cache.complete || gameTime < cache.retryAt)return cache.attached;
			invalidate(cache);
		}
		Set<BlockPos> checked = new HashSet<>();
		Stack<BlockFace> next = new Stack<>();
		Set<BlockPos> cables = new HashSet<>();
		Set<BlockPos> attached = new HashSet<>();
		boolean complete = true;
		long retryAt = Long.MAX_VALUE;
		next.add(new BlockFace(from, null));
		while (!next.isEmpty()) {
			BlockFace p = next.pop();
			if (checked.contains(p.pos()))continue;
			checked.add(p.pos());
			if (!level.isLoaded(p.pos())) {
				complete = false;
				continue;
			}
			BlockState st = level.getBlockState(p.pos());
			if (st.getBlock() instanceof IInventoryCable c && (p.from() == null || c.canConnectFrom(st, p.from()))) {
				CableCache cc = caches.get(p.pos());
				if (cc != null) {
					if (!cc.complete && gameTime >= cc.retryAt) {
						invalidate(cc);
					} else {
					cables.addAll(cc.cables);
					attached.addAll(cc.attached);
					checked.addAll(cc.cables);
					complete &= cc.complete;
					retryAt = Math.min(retryAt, cc.retryAt);
					continue;
					}
				}
				if (c.isFunctionalNode())attached.add(p.pos());
				else cables.add(p.pos());
				next.addAll(c.nextScan(level, st, p.pos()));
			}
		}
		if (!complete)retryAt = Math.min(retryAt, gameTime + INCOMPLETE_RESCAN_TICKS);
		CableCache cc = new CableCache(Set.copyOf(cables), Set.copyOf(attached), complete, retryAt);
		cables.forEach(p -> caches.put(p, cc));
		return cc.attached;
	}

	public void markNodeInvalid(BlockPos pos) {
		CableCache cc = caches.get(pos);
		if (cc != null)invalidate(cc);
	}

	private void invalidate(CableCache cache) {
		cache.cables.forEach(pos -> caches.remove(pos, cache));
	}

	public void markNodeInvalid(BlockFace pos) {
		markNodeInvalid(pos.pos());
	}

	public static InventoryCableNetwork getNetwork(Level level) {
		return WorldStates.cableNetworks.computeIfAbsent(level, InventoryCableNetwork::new);
	}

	private static record CableCache(Set<BlockPos> cables, Set<BlockPos> attached,
			boolean complete, long retryAt) {}
}

package com.tom.storagemod.block.entity;

import java.util.ArrayDeque;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import java.util.Set;
import java.util.Stack;
import java.util.function.Consumer;
import java.util.function.UnaryOperator;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import com.tom.storagemod.Config;
import com.tom.storagemod.Content;
import com.tom.storagemod.StorageTags;
import com.tom.storagemod.api.MultiblockInventoryAPI;
import com.tom.storagemod.block.IInventoryNode;
import com.tom.storagemod.inventory.BlockFilter;
import com.tom.storagemod.inventory.IInventoryAccess;
import com.tom.storagemod.inventory.IInventoryAccess.IInventory;
import com.tom.storagemod.inventory.IInventoryConnectorReference;
import com.tom.storagemod.inventory.InventoryCableNetwork;
import com.tom.storagemod.inventory.MultiInventoryAccess;
import com.tom.storagemod.inventory.PlatformInventoryAccess.BlockInventoryAccess;
import com.tom.storagemod.inventory.PlatformMultiInventoryAccess;
import com.tom.storagemod.platform.PlatformBlockEntity;
import com.tom.storagemod.util.BlockFace;
import com.tom.storagemod.util.InventoryConnectorConfigUtil;
import com.tom.storagemod.util.Priority;
import com.tom.storagemod.util.Priority.IPriority;
import com.tom.storagemod.util.TickerUtil.TickableServer;

public class InventoryConnectorBlockEntity extends PlatformBlockEntity implements TickableServer, IInventoryConnector, IInventory, IInventoryConnectorReference {
	private MultiInventoryAccess handler = new PlatformMultiInventoryAccess();
	private Map<BlockFace, BlockInventoryAccess> invAccesses = new HashMap<>();
	private Set<IInventoryAccess> connectedInvs = new HashSet<>();
	private Set<IInventoryConnector> linkedConnectors = new HashSet<>();
	private Set<BlockFace> interfaces = new HashSet<>();
	/** Connector tick counter (once per 20 game ticks, staggered). */
	private int scanGeneration;
	/** Last exact connector graph that was successfully applied to handler.build. */
	private NetworkTopologySnapshot lastBuildTopology;
	/** Bumped only when the exact local inventory/interface topology changes. */
	private long topologyVersion;
	private Set<InventoryEndpointTopology> localInventoryTopology = Set.of();
	private Set<BlockFace> localInterfaceTopology = Set.of();
	private Set<BlockFilter> activeFilters = Set.of();
	private Map<BlockFace, IInventoryAccess> endpointAccesses = Map.of();
	/**
	 * Full flood-fill every N connector ticks (N*20 game ticks).
	 * Between full scans only cable links + build signature are refreshed.
	 * The two-stage logical-key / physical-root de-duplication is unchanged.
	 */
	private static final int FULL_TOUCH_SCAN_EVERY = 5;

	public InventoryConnectorBlockEntity(BlockPos p_155229_, BlockState p_155230_) {
		super(Content.connectorBE.get(), p_155229_, p_155230_);
	}

	@Override
	public void updateServer() {
		long time = level.getGameTime();
		if(time % 20 == Math.abs(worldPosition.hashCode()) % 20) {
			scanGeneration++;
			activeFilters.forEach(filter -> {
				if (level.isLoaded(filter.getMainPos()))filter.refresh(level);
			});
			// Full touch flood-fill is the expensive path (hasInventoryAt over scan range).
			// Throttle it; cable + signature still run every connector tick so linked
			// network changes propagate without shrinking freefall/search gameplay.
			// First build always full-scans; empty connectors must not force full every tick.
			boolean fullTouch = lastBuildTopology == null || (scanGeneration % FULL_TOUCH_SCAN_EVERY == 1);
			if (fullTouch) {
				detectTouchingInventories();
			} else {
				refreshLocalEndpointTopology();
			}
			detectCableNetwork();
			NetworkTopologySnapshot topology = computeNetworkTopology();
			if (!topology.equals(lastBuildTopology)) {
				handler.build(this, linkedConnectors);
				// Commit only after a successful build. A failed build must be retried.
				lastBuildTopology = topology;
			} else {
				// Some modded inventories can change slot count without changing their
				// block/topology identity. Keep platform offset tables current.
				handler.refreshShape();
			}
		}
	}

	/**
	 * Mirrors MultiInventoryAccess.build's graph traversal and records connector identity
	 * together with its exact local revision. No lossy hash or position/version split is used.
	 */
	private NetworkTopologySnapshot computeNetworkTopology() {
		Queue<IInventoryConnector> queue = new ArrayDeque<>();
		queue.add(this);
		queue.addAll(linkedConnectors);
		Set<IInventoryConnector> visited = Collections.newSetFromMap(new IdentityHashMap<>());
		Set<ConnectorTopology> connectors = new HashSet<>();
		while (!queue.isEmpty()) {
			IInventoryConnector connector = queue.poll();
			if (!visited.add(connector))continue;
			queue.addAll(connector.getConnectedConnectors());
			if (connector instanceof InventoryConnectorBlockEntity inventoryConnector) {
				connectors.add(new ConnectorTopology(connector, inventoryConnector.topologyVersion, Set.of()));
			} else {
				Set<AccessTopology> accesses = new HashSet<>();
				for (IInventoryAccess access : connector.getConnectedInventories()) {
					accesses.add(new AccessTopology(access, access.getTopologyKey(), IPriority.get(access)));
				}
				connectors.add(new ConnectorTopology(connector, 0L, Set.copyOf(accesses)));
			}
		}
		return new NetworkTopologySnapshot(Set.copyOf(connectors));
	}

	long getTopologyVersion() {
		return topologyVersion;
	}

	private record InventoryEndpointTopology(BlockFace face, BlockInventoryAccess access, Object trackingKey, Priority priority) {}
	private record AccessTopology(IInventoryAccess access, Object trackingKey, Priority priority) {}
	private record ConnectorTopology(IInventoryConnector connector, long revision, Set<AccessTopology> fallbackAccesses) {}
	private record NetworkTopologySnapshot(Set<ConnectorTopology> connectors) {}

	/**
	 * Re-evaluate cheap dynamic keys between flood-fills. In particular, Create
	 * vault merge/split events change the controller key and must immediately
	 * re-run de-duplication even when the same member faces remain connected.
	 */
	private void refreshLocalEndpointTopology() {
		if (localInventoryTopology.isEmpty())return;
		Set<InventoryEndpointTopology> next = new HashSet<>();
		for (InventoryEndpointTopology endpoint : localInventoryTopology) {
			IInventoryAccess access = endpointAccesses.get(endpoint.face());
			if (access == null)continue;
			next.add(new InventoryEndpointTopology(endpoint.face(), endpoint.access(),
					access.getTopologyKey(), IPriority.get(access)));
		}
		Set<InventoryEndpointTopology> nextTopology = Set.copyOf(next);
		if (!nextTopology.equals(localInventoryTopology)) {
			localInventoryTopology = nextTopology;
			topologyVersion++;
		}
	}

	private void detectCableNetwork() {
		linkedConnectors.clear();
		Collection<BlockPos> netBlocks = InventoryCableNetwork.getNetwork(level).getNetworkNodes(worldPosition);

		for (BlockPos p : netBlocks) {
			if (!level.isLoaded(p))continue;

			BlockEntity be = level.getBlockEntity(p);
			if (be == this)continue;
			if (be instanceof IInventoryConnector te)
				linkedConnectors.add(te);
		}
	}

	private void detectTouchingInventories() {
		BlockFilter connFilter = BlockFilter.getFilterAt(level, worldPosition);
		UnaryOperator<IInventoryAccess> wrapper = connFilter != null ? i -> connFilter.wrap(level, i) : UnaryOperator.identity();

		connectedInvs.clear();
		Map<BlockPos, Direction> connected = new HashMap<>();
		Set<BlockFilter> blockFilters = new HashSet<>();
		Set<BlockFace> interfaces = new HashSet<>();
		Set<InventoryEndpointTopology> endpointTopology = new HashSet<>();
		Map<BlockFace, IInventoryAccess> nextEndpointAccesses = new HashMap<>();

		Stack<BlockPos> toCheck = new Stack<>();
		Set<BlockPos> checkedBlocks = new HashSet<>();
		toCheck.add(worldPosition);
		checkedBlocks.add(worldPosition);
		int maxRange = Config.get().invConnectorScanRange;
		maxRange *= maxRange;
		boolean onlyTrims = Config.get().onlyTrims;

		Consumer<BlockPos> mbCheck = opos -> {
			if (!level.isLoaded(opos))return;
			BlockFilter f = BlockFilter.getFilterAt(level, opos);
			if (f != null)blockFilters.add(f);
			if (!onlyTrims)toCheck.add(opos);
			checkedBlocks.add(opos);
		};

		while (!toCheck.isEmpty()) {
			BlockPos cp = toCheck.pop();
			for (Direction d : Direction.values()) {
				BlockPos p = cp.relative(d);
				if(!checkedBlocks.contains(p) && p.distSqr(worldPosition) < maxRange) {
					checkedBlocks.add(p);
					if (!level.isLoaded(p))continue;
					BlockState state = level.getBlockState(p);
					if(state.is(StorageTags.TRIMS)) {
						toCheck.add(p);
					} else if(state.getBlock() instanceof IInventoryNode) {
						interfaces.add(new BlockFace(p, Direction.DOWN));
						toCheck.add(p);
					} else if(InventoryConnectorConfigUtil.canConnect(state) && BlockInventoryAccess.hasInventoryAt(level, p, state, d.getOpposite())) {
						BlockFilter f = BlockFilter.getFilterAt(level, p);
						if (f != null)blockFilters.add(f);
						connected.put(p, d.getOpposite());
						if (!onlyTrims)toCheck.add(p);

						MultiblockInventoryAPI.EVENT.invoker().detectMultiblocks(level, p, state, mbCheck);
					}
				}
			}
		}

		blockFilters.forEach(f -> f.getConnectedBlocks().forEach(connected::remove));

		Map<BlockFace, BlockInventoryAccess> invA = new HashMap<>();
		connected.forEach((p, d) -> {
			BlockFace s = new BlockFace(p, d);
			BlockInventoryAccess acc = invAccesses.remove(s);
			if (acc == null) {
				acc = new BlockInventoryAccess();
				acc.onLoad(level, p, d, this);
			}
			invA.put(s, acc);
			IInventoryAccess access = wrapper.apply(acc);
			connectedInvs.add(access);
			nextEndpointAccesses.put(s, access);
			endpointTopology.add(new InventoryEndpointTopology(s, acc, access.getTopologyKey(), IPriority.get(access)));
		});
		blockFilters.forEach(f -> {
			if (f.skip())return;
			BlockFace s = new BlockFace(f.getMainPos(), f.getSide());
			BlockInventoryAccess acc = invAccesses.remove(s);
			if (acc == null) {
				acc = new BlockInventoryAccess();
				acc.onLoad(level, f.getMainPos(), f.getSide(), this);
			}
			invA.put(s, acc);
			IInventoryAccess access = wrapper.apply(f.wrap(level, acc));
			connectedInvs.add(access);
			nextEndpointAccesses.put(s, access);
			endpointTopology.add(new InventoryEndpointTopology(s, acc, access.getTopologyKey(), IPriority.get(access)));
		});
		invAccesses.values().forEach(IInventoryAccess::markInvalid);
		invAccesses.clear();
		invAccesses = invA;

		if (!this.interfaces.equals(interfaces)) {
			var net = InventoryCableNetwork.getNetwork(level);
			this.interfaces.forEach(net::markNodeInvalid);
			this.interfaces = interfaces;
			net.markNodeInvalid(worldPosition);
		}

		for (BlockFace blockFace : this.interfaces) {
			if (level.getBlockEntity(blockFace.pos()) instanceof InventoryInterfaceBlockEntity ii)
				ii.setConnectorAccess(this);
		}

		Set<InventoryEndpointTopology> nextInventoryTopology = Set.copyOf(endpointTopology);
		Set<BlockFace> nextInterfaceTopology = Set.copyOf(interfaces);
		endpointAccesses = Map.copyOf(nextEndpointAccesses);
		if (!nextInventoryTopology.equals(localInventoryTopology) || !nextInterfaceTopology.equals(localInterfaceTopology)) {
			topologyVersion++;
			localInventoryTopology = nextInventoryTopology;
			localInterfaceTopology = nextInterfaceTopology;
		}
		Set<BlockFilter> nextActiveFilters = new HashSet<>(blockFilters);
		if (connFilter != null)nextActiveFilters.add(connFilter);
		activeFilters = Set.copyOf(nextActiveFilters);
	}

	@Override
	public void setRemoved() {
		super.setRemoved();
		invAccesses.clear();
		handler.clear();
		lastBuildTopology = null;
		localInventoryTopology = Set.of();
		localInterfaceTopology = Set.of();
		activeFilters = Set.of();
		endpointAccesses = Map.of();
	}

	public UsageInfo getUsage() {
		return new UsageInfo(handler.getInventoryCount(), handler.getSlotCount(), handler.getFreeSlotCount());
	}

	public record UsageInfo(int blocks, int all, int free) {}

	@Override
	public IInventoryAccess getMergedHandler() {
		return handler;
	}

	@Override
	public Set<IInventoryAccess> getConnectedInventories() {
		return connectedInvs;
	}

	public Set<BlockFace> getInterfaces() {
		return interfaces;
	}

	@Override
	public boolean hasConnectedInventories() {
		return !isRemoved();
	}

	@Override
	public IInventoryAccess getInventoryAccess() {
		return handler;
	}

	public List<BlockPos> getConnectedBlocks() {
		return invAccesses.keySet().stream().map(b -> b.pos()).toList();
	}

	@Override
	public Collection<IInventoryConnector> getConnectedConnectors() {
		return linkedConnectors;
	}

	@Override
	public IInventoryConnector getConnectorRef() {
		return this;
	}
}

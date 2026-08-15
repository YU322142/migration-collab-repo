package com.tom.storagemod.block.entity;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;
import java.util.Queue;
import java.util.Set;
import java.util.UUID;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.MenuProvider;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

import com.tom.storagemod.Config;
import com.tom.storagemod.Content;
import com.tom.storagemod.block.InventoryCableConnectorBlock;
import com.tom.storagemod.inventory.BlockFilter;
import com.tom.storagemod.inventory.IInventoryAccess;
import com.tom.storagemod.inventory.IInventoryConnectorReference;
import com.tom.storagemod.inventory.IInventoryLink;
import com.tom.storagemod.inventory.InventoryCableNetwork;
import com.tom.storagemod.inventory.MultiInventoryAccess;
import com.tom.storagemod.inventory.PlatformInventoryAccess;
import com.tom.storagemod.inventory.PlatformInventoryAccess.BlockInventoryAccess;
import com.tom.storagemod.inventory.PlatformMultiInventoryAccess;
import com.tom.storagemod.inventory.RemoteConnections;
import com.tom.storagemod.inventory.RemoteConnections.Channel;
import com.tom.storagemod.menu.InventoryLinkMenu;
import com.tom.storagemod.util.BeaconLevelCalc;
import com.tom.storagemod.util.Priority;
import com.tom.storagemod.util.Priority.IPriority;
import com.tom.storagemod.util.TickerUtil.TickableServer;

public class InventoryCableConnectorBlockEntity extends PaintedBlockEntity implements MenuProvider, TickableServer, IInventoryConnector, IInventoryLink {
	private static final String CHANNEL_TAG = "channel";
	private BlockInventoryAccess block = new BlockInventoryAccess();
	private MultiInventoryAccess mergedHandler = new PlatformMultiInventoryAccess();
	private Set<IInventoryConnector> linkedConnectors = new HashSet<>();
	private Collection<IInventoryAccess> filteredMerge = Collections.emptyList();
	private IInventoryAccess self = block;
	private UUID channel = null;
	private int beaconLevel = -1;
	/** Last exact cable/remote graph successfully applied to mergedHandler. */
	private CableTopologySnapshot lastCableBuildTopology;

	public InventoryCableConnectorBlockEntity(BlockPos p_155229_, BlockState p_155230_) {
		super(Content.cableConnectorBE.get(), p_155229_, p_155230_);
	}

	@Override
	public void onLoad() {
		super.onLoad();
		if (!level.isClientSide) {
			BlockState state = level.getBlockState(worldPosition);
			Direction facing = state.getValue(InventoryCableConnectorBlock.FACING);
			BlockPos target = worldPosition.relative(facing);
			block.onLoad(level, target, facing.getOpposite(), this);
			if (channel != null && level.isLoaded(target) && level.getBlockState(target).is(Blocks.BEACON)) {
				Channel chn = RemoteConnections.get(level).getChannel(channel);
				if (chn != null)chn.register((ServerLevel) level, worldPosition);
			}
			lastCableBuildTopology = null;
		}
	}

	@Override
	public AbstractContainerMenu createMenu(int p_39954_, Inventory p_39955_, Player p_39956_) {
		return new InventoryLinkMenu(p_39954_, p_39955_, this);
	}

	@Override
	public void updateServer() {
		long time = level.getGameTime();
		if(time % 20 == Math.abs(worldPosition.hashCode()) % 20) {
			BlockState state = level.getBlockState(worldPosition);
			Direction facing = state.getValue(InventoryCableConnectorBlock.FACING);
			BlockPos pos = worldPosition.relative(facing);
			BlockState st = level.getBlockState(pos);
			BlockEntity targetEntity = level.getBlockEntity(pos);
			boolean targetIsConnectorReference = targetEntity instanceof IInventoryConnectorReference;
			IInventoryConnector referenceRoot = targetIsConnectorReference
					? ((IInventoryConnectorReference) targetEntity).getConnectorRef() : null;
			BlockFilter filter = BlockFilter.getFilterAt(level, worldPosition);
			if (filter != null)filter.refresh(level);

			// Stage cable and remote links before comparing the exact topology.
			Set<IInventoryConnector> nextLinked = new HashSet<>();
			Collection<BlockPos> netBlocks = InventoryCableNetwork.getNetwork(level).getNetworkNodes(worldPosition);
			for (BlockPos p : netBlocks) {
				if (!level.isLoaded(p))continue;
				BlockEntity be = level.getBlockEntity(p);
				if (be == this)continue;
				if (be instanceof IInventoryConnector te)
					nextLinked.add(te);
			}

			int nextBeaconLevel = -1;
			if (st.is(Blocks.BEACON)) {
				nextBeaconLevel = BeaconLevelCalc.calcBeaconLevel(level, pos.getX(), pos.getY(), pos.getZ());
				if (channel != null) {
					Channel chn = RemoteConnections.get(level).getChannel(channel);
					if (chn != null) {
						chn.register((ServerLevel) level, worldPosition);
						Set<IInventoryLink> links = chn.findOthers((ServerLevel) level, worldPosition, nextBeaconLevel);
						links.forEach(link -> nextLinked.add(link.getConnector()));
					}
				}
			}

			CableTopologySnapshot topology = new CableTopologySnapshot(pos, st, channel,
					nextBeaconLevel, targetIsConnectorReference, referenceRoot,
					filter == null ? null : filter.getRouteKey(),
					filter == null ? Priority.NORMAL : filter.getPriority(),
					computeConnectorTopology(nextLinked, referenceRoot));
			if (topology.equals(lastCableBuildTopology)) {
				if (self == mergedHandler)mergedHandler.refreshShape();
				return;
			}

			mergedHandler.clear();
			linkedConnectors = nextLinked;
			beaconLevel = nextBeaconLevel;
			if (st.is(Blocks.BEACON)) {
				self = mergedHandler;
				mergedHandler.build(this, linkedConnectors);
			} else {
				if (targetIsConnectorReference) {
					if (referenceRoot != null) {
						self = mergedHandler;
						mergedHandler.build(referenceRoot, Collections.emptyList());

						if (filter != null) {
							List<IInventoryAccess> invs = new ArrayList<>();
							for (IInventoryAccess a : mergedHandler.getConnected()) {
								invs.add(filter.wrap(level, a));
							}
							filteredMerge = invs;
							mergedHandler.build(this, Collections.emptyList());
						} else filteredMerge = mergedHandler.getConnected();
					} else {
						self = PlatformInventoryAccess.EMPTY;
					}
				} else {
					// The facing/target block may have changed without recreating this BE.
					// Refresh the lazy access only when the exact topology changed.
					block.onLoad(level, pos, facing.getOpposite(), this);
					if (filter != null)self = filter.wrap(level, block);
					else self = block;
				}
			}
			// Commit only after every required build completed successfully.
			lastCableBuildTopology = topology;
		}
	}

	private Set<ConnectorTopology> computeConnectorTopology(Collection<IInventoryConnector> roots,
			IInventoryConnector referenceRoot) {
		Queue<IInventoryConnector> queue = new ArrayDeque<>(roots);
		if (referenceRoot != null)queue.add(referenceRoot);
		Set<IInventoryConnector> visited = Collections.newSetFromMap(new IdentityHashMap<>());
		Set<ConnectorTopology> topology = new HashSet<>();
		while (!queue.isEmpty()) {
			IInventoryConnector connector = queue.poll();
			if (!visited.add(connector))continue;
			queue.addAll(connector.getConnectedConnectors());
			if (connector instanceof InventoryConnectorBlockEntity inventoryConnector) {
				topology.add(new ConnectorTopology(connector,
						inventoryConnector.getTopologyVersion(), Set.of()));
			} else {
				Set<AccessTopology> accesses = new HashSet<>();
				for (IInventoryAccess access : connector.getConnectedInventories()) {
					accesses.add(new AccessTopology(access, access.getTopologyKey(), IPriority.get(access)));
				}
				topology.add(new ConnectorTopology(connector, 0L, Set.copyOf(accesses)));
			}
		}
		return Set.copyOf(topology);
	}

	private record AccessTopology(IInventoryAccess access, Object trackingKey, Priority priority) {}
	private record ConnectorTopology(IInventoryConnector connector, long revision, Set<AccessTopology> accesses) {}
	private record CableTopologySnapshot(BlockPos targetPos, BlockState targetState, UUID channel,
			int beaconLevel, boolean targetIsConnectorReference, IInventoryConnector referenceRoot,
			Object filterRoute, Priority filterPriority, Set<ConnectorTopology> connectors) {}

	@Override
	public Component getDisplayName() {
		return Component.translatable("menu.toms_storage.inventory_connector");
	}

	public boolean stillValid(Player player) {
		if(channel != null) {
			Channel chn = RemoteConnections.get(level).getChannel(channel);
			if(chn != null && !chn.publicChannel && !chn.owner.equals(player.getUUID()))
				return false;
		}
		if (this.level.getBlockEntity(this.worldPosition) != this || beaconLevel < 0) {
			return false;
		} else {
			return !(player.distanceToSqr(this.worldPosition.getX() + 0.5D, this.worldPosition.getY() + 0.5D, this.worldPosition.getZ() + 0.5D) > 64.0D);
		}
	}

	@Override
	public IInventoryAccess getMergedHandler() {
		return self;
	}

	@Override
	public Collection<IInventoryAccess> getConnectedInventories() {
		return beaconLevel >= 0 ? Collections.emptyList() : self == mergedHandler ? filteredMerge : Collections.singleton(self);
	}

	@Override
	public boolean hasConnectedInventories() {
		return !isRemoved() && beaconLevel >= 0;
	}

	@Override
	public void loadAdditional(CompoundTag nbt, HolderLookup.Provider provider) {
		super.loadAdditional(nbt, provider);
		if(nbt.contains(CHANNEL_TAG)) {
			channel = nbt.getUUID(CHANNEL_TAG);
		} else {
			channel = null;
		}
	}

	@Override
	public void saveAdditional(CompoundTag nbt, HolderLookup.Provider provider) {
		super.saveAdditional(nbt, provider);
		if(channel != null) {
			nbt.putUUID(CHANNEL_TAG, channel);
		}
	}

	@Override
	public IInventoryConnector getConnector() {
		return this;
	}

	@Override
	public boolean isAccessibleFrom(ServerLevel world, BlockPos blockPos, int level) {
		int cLocalLvl = Config.get().invLinkBeaconLvl;
		int cSDLvl = Config.get().invLinkBeaconLvlSameDim;
		int cCDLvl = Config.get().invLinkBeaconLvlCrossDim;
		int lvl = Math.max(beaconLevel, level);
		int lvlM = Math.min(beaconLevel, level);
		if (cLocalLvl == -1)return false;
		if (cCDLvl != -1 && lvl >= cCDLvl && (lvlM > 0 || cCDLvl == 0))return true;
		if (!this.level.dimension().equals(world.dimension()))return false;
		if (cSDLvl != -1 && lvl >= cSDLvl && (lvlM > 0 || cSDLvl == 0))return true;
		int range = Config.get().invLinkBeaconRange;
		range *= range;
		return blockPos.distSqr(worldPosition) < range;
	}

	@Override
	public UUID getChannel() {
		return channel;
	}

	public void setChannel(UUID chn) {
		if (Objects.equals(channel, chn))return;
		if (channel != null && level instanceof ServerLevel serverLevel) {
			Channel oldChannel = RemoteConnections.get(level).getChannel(channel);
			if (oldChannel != null)oldChannel.unregister(serverLevel, worldPosition);
		}
		this.channel = chn;
		lastCableBuildTopology = null;
		setChanged();
	}

	public int getBeaconLevel() {
		return beaconLevel;
	}

	@Override
	public Collection<IInventoryConnector> getConnectedConnectors() {
		return linkedConnectors;
	}

	public boolean hasBeacon() {
		BlockState state = level.getBlockState(worldPosition);
		Direction facing = state.getValue(InventoryCableConnectorBlock.FACING);
		BlockPos pos = worldPosition.relative(facing);
		BlockState st = level.getBlockState(pos);
		return st.is(Blocks.BEACON);
	}
}

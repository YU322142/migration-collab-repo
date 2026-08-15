package com.migration.createsaveddata;

import com.mojang.logging.LogUtils;
import com.simibubi.create.Create;
import com.simibubi.create.content.logistics.packagerLink.LogisticsNetwork;
import com.simibubi.create.content.logistics.packagerLink.RequestPromiseQueue;
import com.simibubi.create.content.trains.entity.Train;
import com.simibubi.create.content.trains.graph.TrackGraph;
import com.simibubi.create.content.trains.graph.TrackNode;
import com.simibubi.create.content.trains.schedule.ScheduleEntry;
import com.simibubi.create.content.trains.signal.SignalEdgeGroup;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.server.ServerStartedEvent;
import org.slf4j.Logger;

import java.lang.reflect.Field;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;

@Mod(CreateSavedDataProbe.MOD_ID)
public final class CreateSavedDataProbe {
    public static final String MOD_ID = "create_saveddata_probe";
    private static final Logger LOGGER = LogUtils.getLogger();

    public CreateSavedDataProbe() {
        NeoForge.EVENT_BUS.addListener(this::serverStarted);
    }

    private void serverStarted(ServerStartedEvent event) {
        TreeMap<String, TrackGraph> graphs = sorted(Create.RAILWAYS.trackNetworks);
        TreeMap<String, Train> trains = sorted(Create.RAILWAYS.trains);
        TreeMap<String, LogisticsNetwork> networks = sorted(Create.LOGISTICS.logisticsNetworks);
        LOGGER.info(
                "CREATE_SAVEDDATA_PROBE_BEGIN graphs={} signal_groups={} trains={} logistics={}",
                graphs.size(), Create.RAILWAYS.signalEdgeGroups.size(), trains.size(), networks.size());
        TreeMap<String, Integer> signalColors = new TreeMap<>();
        for (SignalEdgeGroup group : Create.RAILWAYS.signalEdgeGroups.values()) {
            signalColors.merge(group.color.name(), 1, Integer::sum);
        }
        LOGGER.info("CREATE_SAVEDDATA_SIGNAL_COLORS {}", signalColors);
        graphs.forEach((id, graph) -> {
            int directedEdges = 0;
            for (TrackNode node : graph.getNodes().stream().map(graph::locateNode).toList()) {
                directedEdges += graph.getConnectionsFrom(node).size();
            }
            LOGGER.info("CREATE_SAVEDDATA_GRAPH id={} nodes={} directed_edges={} checksum={}",
                    id, graph.getNodes().size(), directedEdges, graph.getChecksum());
        });
        trains.forEach((id, train) -> LOGGER.info(
                "CREATE_SAVEDDATA_TRAIN id={} owner={} graph={} carriages={} spacing={} double_ended={} name={} runtime_state={} schedule_entries={} condition_columns={} conditions={}",
                id,
                train.owner,
                train.graph == null ? null : train.graph.id,
                train.carriages.size(),
                train.carriageSpacing,
                train.doubleEnded,
                train.name.getString(),
                train.runtime.state,
                scheduleEntryCount(train),
                conditionColumnCount(train),
                conditionCount(train)));
        networks.forEach((id, network) -> LOGGER.info(
                "CREATE_SAVEDDATA_LOGISTICS id={} owner={} locked={} total_links={} loaded_links={} promises={}",
                id,
                network.owner,
                network.locked,
                network.totalLinks.size(),
                network.loadedLinks.size(),
                promiseCount(network.panelPromises)));
        LOGGER.info("CREATE_SAVEDDATA_PROBE_END graphs={} signal_groups={} trains={} logistics={}",
                graphs.size(), Create.RAILWAYS.signalEdgeGroups.size(), trains.size(), networks.size());
    }

    private static int promiseCount(RequestPromiseQueue queue) {
        try {
            Field field = RequestPromiseQueue.class.getDeclaredField("promisesByItem");
            field.setAccessible(true);
            Map<?, ?> byItem = (Map<?, ?>) field.get(queue);
            int count = 0;
            for (Object value : byItem.values()) {
                count += ((Collection<?>) value).size();
            }
            return count;
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("Could not inspect RequestPromiseQueue", exception);
        }
    }

    private static int scheduleEntryCount(Train train) {
        return train.runtime.schedule == null ? 0 : train.runtime.schedule.entries.size();
    }

    private static int conditionColumnCount(Train train) {
        if (train.runtime.schedule == null) {
            return 0;
        }
        int count = 0;
        for (ScheduleEntry entry : train.runtime.schedule.entries) {
            count += entry.conditions.size();
        }
        return count;
    }

    private static int conditionCount(Train train) {
        if (train.runtime.schedule == null) {
            return 0;
        }
        int count = 0;
        for (ScheduleEntry entry : train.runtime.schedule.entries) {
            for (List<?> column : entry.conditions) {
                count += column.size();
            }
        }
        return count;
    }

    private static <T> TreeMap<String, T> sorted(Map<UUID, T> values) {
        TreeMap<String, T> result = new TreeMap<>();
        values.forEach((id, value) -> result.put(id.toString(), value));
        return result;
    }
}

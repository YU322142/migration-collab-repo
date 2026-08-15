package com.antigravity.create_dynamic_blocking;

import com.mojang.logging.LogUtils;
import com.simibubi.create.Create;
import com.simibubi.create.content.trains.entity.Carriage;
import com.simibubi.create.content.trains.entity.Train;
import com.simibubi.create.content.trains.entity.TravellingPoint;
import com.simibubi.create.content.trains.graph.TrackEdge;
import com.simibubi.create.content.trains.graph.TrackGraph;
import org.slf4j.Logger;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class DynamicBlockingHandler {
    private static final Logger LOGGER = LogUtils.getLogger();

    private DynamicBlockingHandler() {
    }

    public static void enforceSpacing(Train currentTrain, boolean backwards) {
        if (currentTrain.graph == null || !DynamicBlockingConfig.enabled || currentTrain.carriages.isEmpty()) {
            return;
        }

        TrackGraph graph = currentTrain.graph;
        TravellingPoint leadingPoint = !backwards
                ? currentTrain.carriages.getFirst().getLeadingPoint()
                : currentTrain.carriages.getLast().getTrailingPoint();
        if (leadingPoint == null || leadingPoint.edge == null) {
            return;
        }

        double currentSpeed = Math.abs(currentTrain.speed);
        if (currentSpeed < 0.001 && Math.abs(currentTrain.targetSpeed) < 0.001) {
            return;
        }

        double acceleration = currentTrain.acceleration();
        double scanDistance = DynamicBlockingMath.scanDistance(
                currentSpeed,
                acceleration,
                DynamicBlockingConfig.slowdownDistance,
                DynamicBlockingConfig.maxScanDistance
        );
        if (scanDistance <= 0.0) {
            return;
        }

        Map<TrackEdge, List<TravellingPoint>> occupancy = new HashMap<>();
        for (Train otherTrain : Create.RAILWAYS.trains.values()) {
            if (otherTrain == currentTrain || otherTrain.graph != graph || otherTrain.derailed) {
                continue;
            }
            for (Carriage carriage : otherTrain.carriages) {
                addPoint(occupancy, carriage.getLeadingPoint());
                addPoint(occupancy, carriage.getTrailingPoint());
            }
        }

        TravellingPoint scout = new TravellingPoint();
        scout.node1 = leadingPoint.node1;
        scout.node2 = leadingPoint.node2;
        scout.edge = leadingPoint.edge;
        scout.position = leadingPoint.position;

        double closestDistance = Double.MAX_VALUE;
        double accumulatedDistance = 0.0;
        double travelDirection = backwards ? -1.0 : 1.0;
        for (int i = 0; i < 256 && accumulatedDistance <= scanDistance && scout.edge != null; i++) {
            TrackEdge currentEdge = scout.edge;
            boolean movingToNode2 = travelDirection > 0.0;
            List<TravellingPoint> obstacles = occupancy.get(currentEdge);
            if (obstacles != null) {
                for (TravellingPoint obstacle : obstacles) {
                    double distance = -1.0;
                    if (movingToNode2 && obstacle.position > scout.position + 0.1) {
                        distance = obstacle.position - scout.position;
                    } else if (!movingToNode2 && obstacle.position < scout.position - 0.1) {
                        distance = scout.position - obstacle.position;
                    }
                    if (distance > 0.0) {
                        closestDistance = Math.min(closestDistance, accumulatedDistance + distance);
                    }
                }
            }
            if (closestDistance < Double.MAX_VALUE) {
                break;
            }

            double edgeLength = currentEdge.getLength();
            double toEnd = movingToNode2 ? edgeLength - scout.position : scout.position;
            double requestedTravel = travelDirection * (toEnd + 0.1);
            double actualTravel = scout.travel(
                    graph,
                    requestedTravel,
                    currentTrain.navigation.controlSignalScout(),
                    scout.ignoreEdgePoints(),
                    scout.ignoreTurns()
            );
            if (Math.abs(actualTravel) < 0.001) {
                break;
            }
            accumulatedDistance += Math.abs(actualTravel);
        }

        if (closestDistance >= scanDistance || closestDistance == Double.MAX_VALUE) {
            return;
        }
        if (closestDistance <= DynamicBlockingConfig.finalStopDistance) {
            currentTrain.speed = 0.0;
            currentTrain.targetSpeed = 0.0;
            return;
        }

        double availableDistance = closestDistance - DynamicBlockingConfig.finalStopDistance;
        double maxSafeSpeed = DynamicBlockingMath.maxSafeSpeed(acceleration, availableDistance);
        double topSpeed = currentTrain.maxSpeed() * currentTrain.throttle;
        if (maxSafeSpeed > topSpeed) {
            return;
        }

        double sign = backwards ? -1.0 : 1.0;
        if (currentSpeed > maxSafeSpeed) {
            currentTrain.speed = sign * maxSafeSpeed;
            currentTrain.targetSpeed = sign * maxSafeSpeed;
            if (DynamicBlockingConfig.debugLogging) {
                LOGGER.info(
                        "[动态闭塞] v4拓扑扫描: 距离={}m, 限速={}",
                        String.format("%.2f", closestDistance),
                        String.format("%.2f", maxSafeSpeed)
                );
            }
        }
    }

    private static void addPoint(Map<TrackEdge, List<TravellingPoint>> occupancy, TravellingPoint point) {
        if (point != null && point.edge != null) {
            occupancy.computeIfAbsent(point.edge, ignored -> new ArrayList<>()).add(point);
        }
    }
}

package com.migration.diagnostic;

import com.mojang.logging.LogUtils;
import net.minecraft.commands.Commands;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.item.crafting.RecipeHolder;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import net.neoforged.neoforge.event.server.ServerStartedEvent;
import org.slf4j.Logger;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

@Mod(RecipeSetDiagnostic.MOD_ID)
public final class RecipeSetDiagnostic {
    public static final String MOD_ID = "recipe_set_diagnostic";
    private static final Logger LOGGER = LogUtils.getLogger();

    public RecipeSetDiagnostic() {
        NeoForge.EVENT_BUS.addListener(this::serverStarted);
        NeoForge.EVENT_BUS.addListener(this::registerCommands);
    }

    private void serverStarted(ServerStartedEvent event) {
        dumpRecipeSet(event.getServer());
    }

    private void registerCommands(RegisterCommandsEvent event) {
        event.getDispatcher().register(Commands.literal("recipe_set_diagnostic")
                .requires(source -> source.hasPermission(4))
                .executes(context -> {
                    dumpRecipeSet(context.getSource().getServer());
                    return 1;
                }));
    }

    private void dumpRecipeSet(MinecraftServer server) {
        List<String> ids = server.getRecipeManager().getRecipes().stream()
                .map(RecipeHolder::id)
                .map(ResourceLocation::toString)
                .sorted()
                .toList();
        Map<String, Integer> namespaceCounts = new TreeMap<>();
        for (String id : ids) {
            String namespace = id.substring(0, id.indexOf(':'));
            namespaceCounts.merge(namespace, 1, Integer::sum);
        }

        String label = System.getProperty("recipeDiagnostic.runLabel", "unlabeled");
        String hash = sha256(ids);
        LOGGER.info("RECIPE_SET_BEGIN label={} total={} sha256={}", label, ids.size(), hash);
        namespaceCounts.forEach((namespace, count) ->
                LOGGER.info("RECIPE_NAMESPACE label={} namespace={} count={}", label, namespace, count));
        ids.forEach(id -> LOGGER.info("RECIPE_ID label={} id={}", label, id));
        LOGGER.info("RECIPE_SET_END label={} total={} sha256={}", label, ids.size(), hash);
    }

    private static String sha256(List<String> ids) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            for (String id : ids) {
                digest.update(id.getBytes(StandardCharsets.UTF_8));
                digest.update((byte) '\n');
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }
}

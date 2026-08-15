package com.bmt.waypointfire.command;

import com.bmt.waypointfire.ParitySemantics;
import com.mojang.brigadier.StringReader;
import com.mojang.brigadier.arguments.ArgumentType;
import com.mojang.brigadier.context.CommandContext;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import com.mojang.brigadier.exceptions.DynamicCommandExceptionType;
import com.mojang.brigadier.suggestion.Suggestions;
import com.mojang.brigadier.suggestion.SuggestionsBuilder;
import java.util.Collection;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import net.minecraft.commands.SharedSuggestionProvider;
import net.minecraft.network.chat.Component;

/** Backport of the 1.21.11 three- or six-digit hexadecimal color argument. */
public final class HexColorArgument implements ArgumentType<Integer> {
    private static final Collection<String> EXAMPLES = List.of("F00", "FF0000");
    private static final DynamicCommandExceptionType INVALID = new DynamicCommandExceptionType(
        value -> Component.translatable("argument.hexcolor.invalid", value)
    );

    private HexColorArgument() {}

    public static HexColorArgument hexColor() {
        return new HexColorArgument();
    }

    public static int getHexColor(CommandContext<?> context, String name) {
        return context.getArgument(name, Integer.class);
    }

    @Override
    public Integer parse(StringReader reader) throws CommandSyntaxException {
        String value = reader.readUnquotedString();
        try {
            return ParitySemantics.parseHexColor(value);
        } catch (IllegalArgumentException exception) {
            throw INVALID.createWithContext(reader, value);
        }
    }

    @Override
    public <S> CompletableFuture<Suggestions> listSuggestions(CommandContext<S> context, SuggestionsBuilder builder) {
        return SharedSuggestionProvider.suggest(EXAMPLES, builder);
    }

    @Override
    public Collection<String> getExamples() {
        return EXAMPLES;
    }

}

import com.sk89q.worldedit.neoforge.internal.NeoForgeTransmogrifier;
import com.sk89q.worldedit.registry.state.DirectionalProperty;
import com.sk89q.worldedit.registry.state.Property;
import net.minecraft.core.Direction;
import net.minecraft.util.StringRepresentable;
import net.minecraft.world.level.block.state.properties.BooleanProperty;
import net.minecraft.world.level.block.state.properties.DirectionProperty;
import net.minecraft.world.level.block.state.properties.EnumProperty;
import net.minecraft.world.level.block.state.properties.IntegerProperty;

import java.lang.reflect.Constructor;
import java.util.Collection;
import java.util.List;

/**
 * Offline regression probe for WorldEdit 7.3.8's NeoForge property cache.
 * This does not bootstrap or launch Minecraft.
 */
public final class DirectionPropertyCacheProbe {
    public static void main(String[] args) throws Exception {
        boolean expectFixed = args.length == 1 && args[0].equals("fixed");

        // Use the protected constructors with an empty value collection so the
        // Direction enum itself is not initialized. This keeps the regression
        // probe a small classpath-only test rather than a game bootstrap.
        Constructor<EnumProperty> genericConstructor = EnumProperty.class.getDeclaredConstructor(
            String.class, Class.class, Collection.class
        );
        genericConstructor.setAccessible(true);
        @SuppressWarnings("unchecked")
        EnumProperty<Direction> genericDirection = genericConstructor.newInstance(
            "facing", Direction.class, List.of()
        );

        Constructor<DirectionProperty> dedicatedConstructor = DirectionProperty.class.getDeclaredConstructor(
            String.class, Collection.class
        );
        dedicatedConstructor.setAccessible(true);
        DirectionProperty dedicatedDirection = dedicatedConstructor.newInstance("facing", List.of());

        if (!genericDirection.equals(dedicatedDirection)
            || !dedicatedDirection.equals(genericDirection)
            || genericDirection.hashCode() != dedicatedDirection.hashCode()) {
            throw new AssertionError("Test prerequisite failed: equivalent direction properties no longer collide");
        }

        Property<?> first = NeoForgeTransmogrifier.transmogToWorldEditProperty(genericDirection);
        Property<?> second = NeoForgeTransmogrifier.transmogToWorldEditProperty(dedicatedDirection);
        boolean fixed = first instanceof DirectionalProperty && second instanceof DirectionalProperty;

        EnumProperty<ProbeEnum> ordinaryEnum = EnumProperty.create("probe_enum", ProbeEnum.class);
        Property<?> ordinaryWorldEdit = NeoForgeTransmogrifier.transmogToWorldEditProperty(ordinaryEnum);
        Property<?> booleanWorldEdit = NeoForgeTransmogrifier.transmogToWorldEditProperty(
            BooleanProperty.create("probe_boolean")
        );
        Property<?> integerWorldEdit = NeoForgeTransmogrifier.transmogToWorldEditProperty(
            IntegerProperty.create("probe_integer", 0, 2)
        );

        if (!(ordinaryWorldEdit instanceof com.sk89q.worldedit.registry.state.EnumProperty)
            || !(booleanWorldEdit instanceof com.sk89q.worldedit.registry.state.BooleanProperty)
            || !(integerWorldEdit instanceof com.sk89q.worldedit.registry.state.IntegerProperty)) {
            throw new AssertionError("A non-direction property mapping changed unexpectedly");
        }

        System.out.println("minecraft_equal=true");
        System.out.println("minecraft_hash_equal=true");
        System.out.println("first_worldedit_property=" + first.getClass().getName());
        System.out.println("second_worldedit_property=" + second.getClass().getName());
        System.out.println("ordinary_enum_mapping=" + ordinaryWorldEdit.getClass().getName());
        System.out.println("boolean_mapping=" + booleanWorldEdit.getClass().getName());
        System.out.println("integer_mapping=" + integerWorldEdit.getClass().getName());
        System.out.println("fixed=" + fixed);

        if (fixed != expectFixed) {
            throw new AssertionError("Expected fixed=" + expectFixed + " but observed fixed=" + fixed);
        }
    }

    private DirectionPropertyCacheProbe() {
    }

    private enum ProbeEnum implements StringRepresentable {
        ALPHA,
        BETA;

        @Override
        public String getSerializedName() {
            return name().toLowerCase(java.util.Locale.ROOT);
        }
    }
}

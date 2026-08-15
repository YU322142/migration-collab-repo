# Content Backport 1.5 entity-data serializer timing fix

This project deterministically patches the original `backport-1.5.jar` without
recompiling or redistributing its unavailable source tree.

The original mod registers eight custom animal entity-data serializers through
NeoForge `DeferredHolder`s, but five mixin static initializers call
`DeferredHolder.get()` while registries may temporarily be unbound. The first
observed failure is `backport:cat_sound_variant` during `Cat.<clinit>`.

The patch creates the same eight serializer objects eagerly, registers those
exact objects under the original registry names, and makes the five affected
mixins use the eager objects. Registry keys, mod id/version metadata, codecs,
NBT keys, data packs, sounds, textures, and every unrelated class/resource are
left byte-for-byte unchanged.

Build and verify with Java 21:

```powershell
<path-to-gradlew.bat> -p . --no-daemon clean check
```

The replacement JAR is written to:

`build/libs/backport-1.5-cat-serializer-fix.1.jar`

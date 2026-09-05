# Create Chute Unload Guard

This NeoForge 1.21.1 compatibility mod restores the guard present in the
1.21.11 source `ChuteBlockEntity.onAdded()` implementation:

```java
if (level == null || !AbstractChuteBlock.isChute(level.getBlockState(pos))) {
    setRemoved();
    return;
}
```

Create 6.0.10 calls `refreshBlockState()` unconditionally. During a rapid
client chunk-center change, a stale block-entity ticker can remain active
briefly while `ClientLevel.getBlockState(pos)` resolves through the empty
chunk to `minecraft:void_air`. The unconditional refresh then fails vanilla's
block-entity state validation.

The mixin is deliberately limited to `ChuteBlockEntity.onAdded()`. It changes
neither world data nor global block-entity validation.

Build and verify with the pinned Gradle 8.8 runtime:

```powershell
$env:GRADLE_USER_HOME = '<AUDIT_ROOT>\gradle-cache-chest-colorizer'
& '<AUDIT_ROOT>\gradle-cache-chest-colorizer\wrapper\dists\gradle-8.8-bin\dl7vupf4psengwqhwktix4v1\gradle-8.8\bin\gradle.bat' clean check jar --offline --no-daemon --max-workers=20
```

Install the resulting JAR in both the server and client `mods` directories.
It is locked to Minecraft 1.21.1, NeoForge 21.1.241, and Create 6.0.10.

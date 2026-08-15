# Kaleidoscope Cookery migration.4 independent audit

- Status: `PASS_BYTE_REPRODUCIBLE_SCOPE_AND_RESOURCE_PRESERVED`
- migration.3: `A061FB1E953AD815144304F7567B30876DBBC07B8565069871771F0AAEB63D3F`
- build1: `9113FD81FABED5B2E8FB969AC858F1FE5707E0FF6ADC7C037D407B3D80633C17`
- build2: `9113FD81FABED5B2E8FB969AC858F1FE5707E0FF6ADC7C037D407B3D80633C17`
- final-build1/final-build2 are byte-identical, including all ZIP entry metadata.
- migration.3 -> migration.4 changes exactly two class entries and two version metadata entries.
- All other entries, including every assets/ and data/ gameplay resource, are byte-identical.
- ZIP CRC passes and duplicate entry count is zero for all three JARs.
- No JAR was installed; Java/Minecraft/Prism was not started or touched by this audit.

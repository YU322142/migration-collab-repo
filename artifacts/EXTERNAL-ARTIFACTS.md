# External artifacts index

这些制品不进入 Git；路径和哈希用于协作者在本机核对。路径不存在时应标记
`UNAVAILABLE`，不要静默替换。

| 名称 | 路径 | SHA-256 / manifest | 用途与状态 |
|---|---|---|---|
| latest server input | `D:\Down\mechanomania-matched-runtime-attempt13-2.zip` | `ECCD0C6D28A9444DBBCEB3AAEDBBB882E3EEF82B4DDD2547C729571F21891A92` | 最新测试输入；只读 |
| terrain OTA bundle | `D:\Trans\migration-audit-work\protected-terrain-ota-20260815\bundle` | manifest `02EFC30B640FF1C54EF44D0AEC993825BF41803838AD62A07DC5694F3F4911FD` | 槽位级；需停服 CAS |
| entity OTA bundle | `D:\Trans\migration-audit-work\protected-entity-ota-20260815\bundle` | manifest `D5B64C32CE711B04A2D38E1BD6EF0023542939050E96E9B246957CAC0767CB1D` | relocation；需独立动态验证 |
| vanilla V donor | `D:\Trans\migration-audit-work\vanilla-reference-v-20260815\strict-reference-world\vanilla-reference-v` | manifest `4BD4883295C8E0EFDF584A81AEB4FE19DAAA0EA0AE0B4B3BC3455E9768B2FCB1` | 29,305 chunk donor |
| heightmap compat | `D:\Trans\migration-audit-work\heightmap-384-to-544-compat-20260815\build-1\heightmap-384-to-544-compat-1.0.0+neoforge.1.21.1.jar` | `AD26B1F429F0E39FCD19D6EFD151DF93A62F3B0F7262312C7BA1D8340E13EFBF` | 外部测试制品；不提交 JAR |
| MineAstr 0.6.27 | `D:\Trans\migration-audit-work\mineastr-0.6.27-upgrade-20260815\mineastr-neoforge-1.21.1-0.6.27.jar` | `0C449AEE1BCB2A05F11C5A662C9F245FA9246514388CAE8E086C296D6643B574` | BOTH-side candidate |
| Immersive Paintings MineAstr overlay | `D:\Trans\migration-audit-work\immersive-paintings-mineastr-fix-artifacts-20260816\immersive_paintings-neoforge-1.21.1-0.7.8-migration.2.jar` | `13BE228AACDDBADEF680EE3FB989CCCF3029689DE2ECB09F1B2429189CE21E69` | Detached candidate; replace migration.1 only after disposable test |

MCModSync 的 catalog 只保留在 `artifacts/mcmodsync-disabled/` 作为格式研究资料。
当前全局禁用；服务端不安装，测试也不打开。

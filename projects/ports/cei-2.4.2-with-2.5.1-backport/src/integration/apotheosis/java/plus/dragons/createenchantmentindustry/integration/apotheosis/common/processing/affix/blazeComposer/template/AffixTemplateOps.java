/*
 * Copyright (C) 2025  DragonsPlus
 * SPDX-License-Identifier: LGPL-3.0-or-later
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

package plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer.template;

import dev.shadowsoffire.apotheosis.Apoth;
import dev.shadowsoffire.apotheosis.affix.Affix;
import dev.shadowsoffire.apotheosis.affix.AffixHelper;
import dev.shadowsoffire.apotheosis.affix.AffixInstance;
import dev.shadowsoffire.apotheosis.affix.ItemAffixes;
import dev.shadowsoffire.apotheosis.loot.LootCategory;
import dev.shadowsoffire.apotheosis.loot.LootRarity;
import dev.shadowsoffire.placebo.reload.DynamicHolder;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.Style;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.ItemStack;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer.AffixComposingRules;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer.BlazeComposerMode;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer.BlazeComposingCost;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.processing.affix.blazeComposer.OverlimitAffixHelper;
import plus.dragons.createenchantmentindustry.integration.apotheosis.common.registry.CEIAXDataComponents;
import plus.dragons.createenchantmentindustry.integration.apotheosis.config.CEIAXConfig;

public class AffixTemplateOps {
    private static final float EPSILON = 0.0001F;
    private static final float MINIMUM_LEVEL = 0.01F;
    private static final float MINIMUM_LEVEL_IMPROVEMENT = 0.01F;

    public static Result compose(BlazeComposerMode mode, boolean superMode, float blockedSuperPenalty, ItemStack firstInput, ItemStack secondInput) {
        return compose(mode, superMode, blockedSuperPenalty, 0, 0, firstInput, secondInput);
    }

    public static Result compose(BlazeComposerMode mode, boolean superMode, float blockedSuperPenalty, float previewMinPenalty, float previewMaxPenalty, ItemStack firstInput, ItemStack secondInput) {
        if (firstInput.isEmpty() && secondInput.isEmpty())
            return Result.emptyInput();
        blockedSuperPenalty = superMode ? blockedSuperPenalty : 0;
        PenaltyPreview penaltyPreview = superMode ? PenaltyPreview.of(previewMinPenalty, previewMaxPenalty) : PenaltyPreview.none();
        return switch (mode) {
            case EXTRACT -> extract(superMode, blockedSuperPenalty, penaltyPreview, firstInput, secondInput);
            case APPLY -> apply(superMode, blockedSuperPenalty, penaltyPreview, firstInput, secondInput);
            case MERGE -> merge(superMode, blockedSuperPenalty, penaltyPreview, firstInput, secondInput);
        };
    }

    public static Result extract(boolean superMode, float blockedSuperPenalty, ItemStack equipmentInput, ItemStack templateInput) {
        return extract(superMode, blockedSuperPenalty, PenaltyPreview.none(), equipmentInput, templateInput);
    }

    private static Result extract(boolean superMode, float blockedSuperPenalty, PenaltyPreview penaltyPreview, ItemStack equipmentInput, ItemStack templateInput) {
        if (equipmentInput.isEmpty())
            return incomplete(FailureReason.MISSING_AFFIXED_EQUIPMENT);
        if (templateInput.isEmpty())
            return incomplete(FailureReason.MISSING_BLANK_TEMPLATE);

        AffixTemplateItem templateItem = getTemplateItem(templateInput);
        if (templateItem == null || !isBlankTemplate(templateInput))
            return invalid(FailureReason.REQUIRES_BLANK_TEMPLATE);
        Result modeFailure = validateTemplateMode(templateItem.tier(), superMode);
        if (modeFailure != null)
            return modeFailure;

        DynamicHolder<LootRarity> rarity = AffixHelper.getRarity(equipmentInput);
        if (!rarity.isBound())
            return invalid(FailureReason.EQUIPMENT_HAS_NO_RARITY);

        LootCategory category = LootCategory.forItem(equipmentInput);
        if (category.isNone())
            return invalid(FailureReason.ITEM_HAS_NO_LOOT_CATEGORY, equipmentInput.getHoverName().copy());

        AffixInstance instance = firstAffix(equipmentInput);
        if (instance == null)
            return invalid(FailureReason.EQUIPMENT_HAS_NO_AFFIX);

        AffixTemplateEntry entry = new AffixTemplateEntry(
                instance.affix(),
                instance.level(),
                List.of(category.getKey()),
                instance.level() > Affix.MAX_LEVEL);
        AffixTemplateData data = AffixTemplateData.single(rarity, entry);
        Result levelFailure = validateExtractionLevel(templateItem.tier(), superMode, entry);
        if (levelFailure != null)
            return levelFailure;
        Result holdFailure = validateEntryLevel(templateItem.tier(), data.rarity(), entry);
        if (holdFailure != null)
            return holdFailure;
        if (AffixComposingRules.INSTANCE.denies(BlazeComposerMode.EXTRACT, superMode, entry, data.rarity()))
            return invalid(FailureReason.AFFIX_DENIED_BY_RULE, AffixTemplateDisplay.affixName(instance), modeName(BlazeComposerMode.EXTRACT));

        ItemStack equipment = single(equipmentInput);
        OverlimitAffixHelper.removeAffix(equipment, instance.affix());
        rebuildAffixName(equipment);
        ItemStack template = single(templateInput);
        AffixTemplateEntry resultEntry = entry.withLevel(applyBlockedSuperPenalty(entry.level(), MINIMUM_LEVEL, blockedSuperPenalty));
        AffixTemplateData resultData = AffixTemplateData.single(rarity, resultEntry);
        setTemplateData(template, resultData);
        List<Component> resultDescriptions = new ArrayList<>();
        resultDescriptions.add(AffixTemplateDisplay.describeRemovedAffix(equipment, instance));
        resultDescriptions.addAll(describeTemplateResult(
                resultData,
                template,
                penaltyPreview,
                Map.of(entryId(resultEntry), MINIMUM_LEVEL)));
        int cost = BlazeComposingCost.calculate(
                BlazeComposingCost.Operation.EXTRACT_SNAPSHOT,
                BlazeComposerMode.EXTRACT,
                templateItem.tier(),
                data.rarity(),
                entry,
                0,
                entry.level());
        return Result.ready(
                equipment,
                template,
                cost,
                resultDescriptions);
    }

    public static Result apply(boolean superMode, float blockedSuperPenalty, ItemStack equipmentInput, ItemStack templateInput) {
        return apply(superMode, blockedSuperPenalty, PenaltyPreview.none(), equipmentInput, templateInput);
    }

    private static Result apply(boolean superMode, float blockedSuperPenalty, PenaltyPreview penaltyPreview, ItemStack equipmentInput, ItemStack templateInput) {
        if (equipmentInput.isEmpty())
            return incomplete(FailureReason.MISSING_EQUIPMENT);
        if (templateInput.isEmpty())
            return incomplete(FailureReason.MISSING_FILLED_TEMPLATE);

        AffixTemplateItem templateItem = getTemplateItem(templateInput);
        AffixTemplateData data = getTemplateData(templateInput);
        if (templateItem == null || data == null)
            return invalid(FailureReason.REQUIRES_FILLED_TEMPLATE);
        Result modeFailure = validateTemplateMode(templateItem.tier(), superMode);
        if (modeFailure != null)
            return modeFailure;
        Result dataFailure = validateTemplateData(data);
        if (dataFailure != null)
            return dataFailure;

        ItemStack equipment = single(equipmentInput);
        DynamicHolder<LootRarity> existingRarity = AffixHelper.getRarity(equipment);
        if (!existingRarity.isBound()) {
            equipment.set(Apoth.Components.RARITY, data.rarity());
        } else if (!existingRarity.equals(data.rarity())) {
            if (!CEIAXConfig.server().affixes().allowRarityMismatchApplying.get())
                return invalid(FailureReason.RARITY_MISMATCH_DISALLOWED, rarityName(existingRarity), AffixTemplateDisplay.rarityName(data));
            equipment.set(Apoth.Components.RARITY, data.rarity());
        }

        LootCategory category = LootCategory.forItem(equipment);
        if (category.isNone())
            return invalid(FailureReason.ITEM_HAS_NO_LOOT_CATEGORY, equipment.getHoverName().copy());

        boolean allowExclusiveBypass = superMode && CEIAXConfig.server().affixes().allowExclusiveSetBypassInSuperApplying.get();
        ItemAffixes.Builder compatibilityBuilder = equipment.getOrDefault(Apoth.Components.AFFIXES, ItemAffixes.EMPTY).toBuilder();
        Map<DynamicHolder<Affix>, Float> currentLevels = new HashMap<>();
        AffixHelper.getAffixes(equipment).forEach((affix, instance) -> currentLevels.put(affix, instance.level()));
        Map<DynamicHolder<Affix>, Float> changedLevels = new LinkedHashMap<>();
        List<AcceptedEntry> accepted = new ArrayList<>();
        List<RejectedEntry> rejected = new ArrayList<>();
        List<BlazeComposingCost.EntryCost> costs = new ArrayList<>();
        int bypassedConflicts = 0;

        for (AffixTemplateEntry entry : data.entries()) {
            RejectedEntry rejection = validateApplyingEntry(superMode, equipment, templateItem.tier(), data, entry, category, compatibilityBuilder, currentLevels, allowExclusiveBypass);
            if (rejection != null) {
                rejected.add(rejection);
                continue;
            }

            ItemAffixes compatibilityAffixes = compatibilityBuilder.build().toBuilder().remove(entry.affix()).build();
            bypassedConflicts += countExclusiveConflicts(entry, compatibilityAffixes);

            float currentLevel = currentLevels.getOrDefault(entry.affix(), 0F);
            float maxLevel = maxLevel(templateItem.tier(), data.rarity(), entry);
            float resultLevel = resultLevel(currentLevel, entry.level(), maxLevel);
            float costLevel = resultLevel;
            float minimumLevel = currentLevel <= 0
                    ? MINIMUM_LEVEL
                    : minimumImprovedLevel(currentLevel, resultLevel);
            resultLevel = applyBlockedSuperPenalty(resultLevel, minimumLevel, blockedSuperPenalty);
            changedLevels.put(entry.affix(), resultLevel);
            currentLevels.put(entry.affix(), resultLevel);
            compatibilityBuilder.put(entry.affix(), Math.min(resultLevel, Affix.MAX_LEVEL));
            BlazeComposingCost.Operation operation = currentLevel <= 0
                    ? BlazeComposingCost.Operation.APPLY_NEW_TEMPLATE
                    : BlazeComposingCost.Operation.APPLY_UPGRADE_DELTA;
            AffixTemplateEntry costEntry = entry.withLevel(costLevel);
            costs.add(new BlazeComposingCost.EntryCost(operation, costEntry, currentLevel, costLevel));
            accepted.add(new AcceptedEntry(entry, currentLevel, resultLevel, costLevel, minimumLevel));
        }

        if (accepted.isEmpty()) {
            return Result.invalid(
                    FailureReason.NO_APPLICABLE_AFFIXES.message(),
                    rejected.stream()
                            .map(rejection -> AffixTemplateDisplay.describeRejectedEntry(data, rejection.entry(), equipment, rejection.reason()))
                            .toList());
        }

        OverlimitAffixHelper.setAffixLevels(equipment, changedLevels);
        rebuildAffixName(equipment);
        float extraCost = BlazeComposingCost.exclusiveSetBypassCost(
                bypassedConflicts,
                CEIAXConfig.server().affixes().superExclusiveSetApplyExtraCostMultiplier.getF());
        int cost = BlazeComposingCost.calculate(BlazeComposerMode.APPLY, templateItem.tier(), data.rarity(), costs, extraCost);
        List<Component> descriptions = accepted.stream()
                .map(acceptedEntry -> describeAcceptedApply(equipment, acceptedEntry, penaltyPreview))
                .toList();
        List<Component> warnings = rejected.stream()
                .map(rejection -> AffixTemplateDisplay.describeLostEntry(data, rejection.entry(), equipment, rejection.reason()))
                .toList();
        return Result.ready(
                equipment,
                ItemStack.EMPTY,
                cost,
                descriptions,
                warnings);
    }

    public static Result merge(boolean superMode, float blockedSuperPenalty, ItemStack firstTemplateInput, ItemStack secondTemplateInput) {
        return merge(superMode, blockedSuperPenalty, PenaltyPreview.none(), firstTemplateInput, secondTemplateInput);
    }

    private static Result merge(boolean superMode, float blockedSuperPenalty, PenaltyPreview penaltyPreview, ItemStack firstTemplateInput, ItemStack secondTemplateInput) {
        if (firstTemplateInput.isEmpty())
            return incomplete(FailureReason.MISSING_FILLED_TEMPLATE);
        if (secondTemplateInput.isEmpty())
            return incomplete(FailureReason.MISSING_SECOND_FILLED_TEMPLATE);

        AffixTemplateItem firstItem = getTemplateItem(firstTemplateInput);
        AffixTemplateItem secondItem = getTemplateItem(secondTemplateInput);
        AffixTemplateData firstData = getTemplateData(firstTemplateInput);
        AffixTemplateData secondData = getTemplateData(secondTemplateInput);
        if (firstItem == null || firstData == null)
            return invalid(FailureReason.FIRST_REQUIRES_FILLED_TEMPLATE);
        if (secondItem == null || secondData == null)
            return invalid(FailureReason.SECOND_REQUIRES_FILLED_TEMPLATE);
        Result firstModeFailure = validateTemplateMode(firstItem.tier(), superMode);
        if (firstModeFailure != null)
            return firstModeFailure;
        Result secondModeFailure = validateTemplateMode(secondItem.tier(), superMode);
        if (secondModeFailure != null)
            return secondModeFailure;
        Result firstDataFailure = validateTemplateData(firstData);
        if (firstDataFailure != null)
            return firstDataFailure;
        Result secondDataFailure = validateTemplateData(secondData);
        if (secondDataFailure != null)
            return secondDataFailure;
        if (firstItem.tier() != secondItem.tier())
            return invalid(FailureReason.TEMPLATE_TIER_MISMATCH);
        if (!firstData.rarity().equals(secondData.rarity()))
            return invalid(FailureReason.TEMPLATE_RARITY_MISMATCH, AffixTemplateDisplay.rarityName(firstData), AffixTemplateDisplay.rarityName(secondData));

        AffixTemplateTier tier = firstItem.tier();
        ItemStack result = single(firstTemplateInput);
        Result ruleFailure = validateMergingRules(superMode, tier, firstData, secondData, result);
        if (ruleFailure != null)
            return ruleFailure;

        LinkedHashMap<ResourceLocation, AffixTemplateEntry> resultEntries = entryMap(firstData.entries());
        Map<ResourceLocation, Float> penaltyMinimums = new HashMap<>();
        List<BlazeComposingCost.EntryCost> costs = new ArrayList<>();
        boolean changed = false;
        boolean blockedByLevelIndependent = false;

        for (AffixTemplateEntry entry : secondData.entries()) {
            ResourceLocation id = entryId(entry);
            AffixTemplateEntry existing = resultEntries.get(id);
            if (existing == null) {
                resultEntries.put(id, entry);
                penaltyMinimums.put(id, MINIMUM_LEVEL);
                costs.add(new BlazeComposingCost.EntryCost(BlazeComposingCost.Operation.MERGE_UPGRADE_DELTA, entry, 0, entry.level()));
                changed = true;
                continue;
            }

            float maxLevel = maxLevel(tier, firstData.rarity(), existing);
            float lowerInputLevel = Math.min(existing.level(), entry.level());
            float highestInputLevel = Math.max(existing.level(), entry.level());
            float resultLevel = highestInputLevel;
            if (nearlyEqual(existing.level(), entry.level())) {
                if (canUpgrade(existing, firstData.rarity(), result)) {
                    resultLevel = Math.min(existing.level() + CEIAXConfig.server().affixes().affixTemplateMergeStep.getF(), maxLevel);
                } else {
                    blockedByLevelIndependent = true;
                }
            }
            if (resultLevel > maxLevel + EPSILON)
                return invalid(
                        FailureReason.TEMPLATE_CANNOT_HOLD_LEVEL,
                        AffixTemplateDisplay.formatLevel(resultLevel),
                        AffixTemplateDisplay.formatLevel(maxLevel));
            AffixTemplateEntry merged = existing.mergeMetadata(entry, resultLevel);
            resultEntries.put(id, merged);
            if (resultLevel > lowerInputLevel + EPSILON) {
                penaltyMinimums.put(id, minimumImprovedLevel(lowerInputLevel, resultLevel));
                costs.add(new BlazeComposingCost.EntryCost(BlazeComposingCost.Operation.MERGE_UPGRADE_DELTA, merged, lowerInputLevel, resultLevel));
                changed = true;
            }
        }

        List<AffixTemplateEntry> mergedEntries = resultEntries.values().stream()
                .sorted(Comparator.comparing(AffixTemplateOps::entryId))
                .toList();

        List<ExclusiveConflict> conflicts = findExclusiveConflicts(mergedEntries);
        if (!conflicts.isEmpty()) {
            ExclusiveConflict conflict = conflicts.getFirst();
            if (!superMode || !CEIAXConfig.server().affixes().allowExclusiveSetBypassInSuperMerging.get()) {
                return invalid(
                        FailureReason.TEMPLATE_AFFIXES_INCOMPATIBLE,
                        AffixTemplateDisplay.affixName(conflict.first(), firstData.rarity(), result),
                        AffixTemplateDisplay.affixName(conflict.second(), firstData.rarity(), result));
            }
        }

        if (!changed) {
            return blockedByLevelIndependent
                    ? invalid(FailureReason.LEVEL_INDEPENDENT_AFFIX)
                    : invalid(FailureReason.WOULD_NOT_IMPROVE);
        }

        List<AffixTemplateEntry> resultEntryList = applyBlockedSuperPenalty(mergedEntries, penaltyMinimums, blockedSuperPenalty);
        AffixTemplateData resultData = new AffixTemplateData(firstData.rarity(), resultEntryList);
        setTemplateData(result, resultData);
        float extraCost = BlazeComposingCost.exclusiveSetBypassCost(
                conflicts.size(),
                CEIAXConfig.server().affixes().superExclusiveSetMergeExtraCostMultiplier.getF());
        int cost = BlazeComposingCost.calculate(BlazeComposerMode.MERGE, tier, firstData.rarity(), costs, extraCost);
        List<Component> resultDescriptions = describeTemplateResult(resultData, result, penaltyPreview, penaltyMinimums);
        return Result.ready(
                result,
                ItemStack.EMPTY,
                cost,
                resultDescriptions);
    }

    public static AffixTemplateItem getTemplateItem(ItemStack stack) {
        return stack.getItem() instanceof AffixTemplateItem template ? template : null;
    }

    public static AffixTemplateData getTemplateData(ItemStack stack) {
        return stack.get(CEIAXDataComponents.AFFIX_TEMPLATE.get());
    }

    public static void setTemplateData(ItemStack stack, AffixTemplateData data) {
        stack.set(CEIAXDataComponents.AFFIX_TEMPLATE.get(), data);
    }

    public static boolean isBlankTemplate(ItemStack stack) {
        return getTemplateItem(stack) != null && getTemplateData(stack) == null;
    }

    public static boolean isFilledTemplate(ItemStack stack) {
        return getTemplateItem(stack) != null && getTemplateData(stack) != null;
    }

    private static Result incomplete(FailureReason reason, Object... args) {
        return Result.incomplete(reason.message(args));
    }

    private static Result invalid(FailureReason reason, Object... args) {
        return Result.invalid(reason.message(args));
    }

    private static Component modeName(BlazeComposerMode mode) {
        return Component.translatable("create_enchantment_industry.gui.blaze_composer.mode." + mode.getSerializedName());
    }

    private static Component rarityName(DynamicHolder<LootRarity> rarity) {
        return Component.translatable(rarity.getId().toLanguageKey("rarity"))
                .withStyle(style -> rarity.isBound() ? style.withColor(rarity.get().color()) : style);
    }

    private static Result validateTemplateData(AffixTemplateData data) {
        if (data.isEmpty())
            return invalid(FailureReason.EMPTY_TEMPLATE_DATA);
        if (!data.isBound())
            return invalid(FailureReason.UNBOUND_TEMPLATE_DATA);
        return null;
    }

    private static Result validateTemplateMode(AffixTemplateTier tier, boolean superMode) {
        if (tier.matchesSuperMode(superMode))
            return null;
        return superMode
                ? invalid(FailureReason.NORMAL_TEMPLATE_REQUIRES_NORMAL_MODE)
                : invalid(FailureReason.APOTHEOTIC_TEMPLATE_REQUIRES_SUPER_MODE);
    }

    private static Result validateExtractionLevel(AffixTemplateTier tier, boolean superMode, AffixTemplateEntry entry) {
        if (superMode)
            return null;
        if (entry.level() > Affix.MAX_LEVEL + EPSILON)
            return invalid(
                    FailureReason.OVERLIMIT_AFFIX_REQUIRES_SUPER_TEMPLATE,
                    AffixTemplateDisplay.formatLevel(entry.level()),
                    AffixTemplateDisplay.formatLevel(Affix.MAX_LEVEL));
        if (tier == AffixTemplateTier.BRASS && entry.level() > Affix.STANDARD_MAX_LEVEL + EPSILON)
            return invalid(
                    FailureReason.ADVANCED_AFFIX_REQUIRES_CRYSTAL_TEMPLATE,
                    AffixTemplateDisplay.formatLevel(entry.level()),
                    AffixTemplateDisplay.formatLevel(Affix.STANDARD_MAX_LEVEL));
        return null;
    }

    private static Result validateEntryLevel(AffixTemplateTier tier, DynamicHolder<LootRarity> rarity, AffixTemplateEntry entry) {
        float maxLevel = maxLevel(tier, rarity, entry);
        if (entry.level() <= maxLevel + EPSILON)
            return null;
        return invalid(
                FailureReason.TEMPLATE_CANNOT_HOLD_LEVEL,
                AffixTemplateDisplay.formatLevel(entry.level()),
                AffixTemplateDisplay.formatLevel(maxLevel));
    }

    private static Result validateMergingRules(boolean superMode, AffixTemplateTier tier, AffixTemplateData firstData, AffixTemplateData secondData, ItemStack stack) {
        for (AffixTemplateEntry entry : firstData.entries()) {
            Result failure = validateMergeEntry(superMode, tier, firstData, entry, stack);
            if (failure != null)
                return failure;
        }
        for (AffixTemplateEntry entry : secondData.entries()) {
            Result failure = validateMergeEntry(superMode, tier, firstData, entry, stack);
            if (failure != null)
                return failure;
        }
        return null;
    }

    private static Result validateMergeEntry(boolean superMode, AffixTemplateTier tier, AffixTemplateData data, AffixTemplateEntry entry, ItemStack stack) {
        Result levelFailure = validateEntryLevel(tier, data.rarity(), entry);
        if (levelFailure != null)
            return levelFailure;
        if (AffixComposingRules.INSTANCE.denies(BlazeComposerMode.MERGE, superMode, entry, data.rarity()))
            return invalid(FailureReason.AFFIX_DENIED_BY_RULE, AffixTemplateDisplay.affixName(entry, data.rarity(), stack), modeName(BlazeComposerMode.MERGE));
        return null;
    }

    private static RejectedEntry validateApplyingEntry(
            boolean superMode,
            ItemStack equipment,
            AffixTemplateTier tier,
            AffixTemplateData data,
            AffixTemplateEntry entry,
            LootCategory category,
            ItemAffixes.Builder compatibilityBuilder,
            Map<DynamicHolder<Affix>, Float> currentLevels,
            boolean allowExclusiveBypass) {
        if (AffixComposingRules.INSTANCE.denies(BlazeComposerMode.APPLY, superMode, entry, data.rarity()))
            return reject(entry, RejectionReason.DENIED_BY_RULE, modeName(BlazeComposerMode.APPLY));

        float maxLevel = maxLevel(tier, data.rarity(), entry);
        if (entry.level() > maxLevel + EPSILON)
            return reject(
                    entry,
                    RejectionReason.TEMPLATE_CANNOT_HOLD_LEVEL,
                    AffixTemplateDisplay.formatLevel(entry.level()),
                    AffixTemplateDisplay.formatLevel(maxLevel));

        if (!entry.affix().get().canApplyTo(equipment, category, data.rarity().get()))
            return reject(entry, RejectionReason.CANNOT_APPLY_TO_ITEM, equipment.getHoverName().copy());

        ItemAffixes compatibilityAffixes = compatibilityBuilder.build().toBuilder().remove(entry.affix()).build();
        if (!entry.affix().get().isCompatibleWith(compatibilityAffixes) && !allowExclusiveBypass)
            return reject(entry, RejectionReason.INCOMPATIBLE_WITH_EQUIPMENT, equipment.getHoverName().copy());

        float currentLevel = currentLevels.getOrDefault(entry.affix(), 0F);
        if (currentLevel > 0 && nearlyEqual(currentLevel, entry.level()) && !canUpgrade(entry, data.rarity(), equipment))
            return reject(entry, RejectionReason.LEVEL_INDEPENDENT);

        float resultLevel = resultLevel(currentLevel, entry.level(), maxLevel);
        if (resultLevel > maxLevel + EPSILON)
            return reject(
                    entry,
                    RejectionReason.TEMPLATE_CANNOT_HOLD_LEVEL,
                    AffixTemplateDisplay.formatLevel(resultLevel),
                    AffixTemplateDisplay.formatLevel(maxLevel));
        if (resultLevel <= currentLevel + EPSILON) {
            return currentLevel >= maxLevel - EPSILON
                    ? reject(entry, RejectionReason.ALREADY_AT_TEMPLATE_CAP, AffixTemplateDisplay.formatLevel(maxLevel))
                    : reject(entry, RejectionReason.WOULD_NOT_IMPROVE);
        }
        return null;
    }

    private static RejectedEntry reject(AffixTemplateEntry entry, RejectionReason reason, Object... args) {
        return new RejectedEntry(entry, reason.message(args));
    }

    private static float resultLevel(float currentLevel, float templateLevel, float maxLevel) {
        if (currentLevel <= 0)
            return templateLevel;
        if (nearlyEqual(currentLevel, templateLevel))
            return Math.min(currentLevel + CEIAXConfig.server().affixes().affixTemplateMergeStep.getF(), maxLevel);
        return Math.max(currentLevel, templateLevel);
    }

    private static float maxLevel(AffixTemplateTier tier, DynamicHolder<LootRarity> rarity, AffixTemplateEntry entry) {
        return AffixComposingRules.INSTANCE.getMaxLevel(entry, rarity, tier.getMaxLevel());
    }

    private static boolean canUpgrade(AffixTemplateEntry entry, DynamicHolder<LootRarity> rarity, ItemStack stack) {
        return CEIAXConfig.server().affixes().allowLevelIndependentAffixUpgrade.get()
                || !entry.toInstance(rarity, stack).isLevelIndependent();
    }

    private static Component describeAcceptedApply(ItemStack equipment, AcceptedEntry accepted, PenaltyPreview penaltyPreview) {
        if (penaltyPreview.active()) {
            return AffixTemplateDisplay.describeEquipmentAffixUpgradeRange(
                    equipment,
                    accepted.entry().affix(),
                    accepted.beforeLevel(),
                    penaltyPreview.minResultLevel(accepted.costLevel(), accepted.minimumLevel()),
                    penaltyPreview.maxResultLevel(accepted.costLevel(), accepted.minimumLevel()));
        }
        return AffixTemplateDisplay.describeEquipmentAffixUpgrade(
                equipment,
                accepted.entry().affix(),
                accepted.beforeLevel(),
                accepted.resultLevel());
    }

    private static List<Component> describeTemplateResult(AffixTemplateData data, ItemStack stack, PenaltyPreview penaltyPreview, Map<ResourceLocation, Float> penaltyMinimums) {
        List<Component> result = new ArrayList<>();
        if (data.size() > 1)
            result.add(AffixTemplateDisplay.describeTemplate(data, stack));
        for (AffixTemplateEntry entry : data.entries()) {
            Float minimumLevel = penaltyMinimums.get(entryId(entry));
            if (penaltyPreview.active() && minimumLevel != null) {
                result.add(AffixTemplateDisplay.describeTemplateEntryRange(
                        data,
                        entry,
                        penaltyPreview.minResultLevel(entry.level(), minimumLevel),
                        penaltyPreview.maxResultLevel(entry.level(), minimumLevel),
                        stack));
            } else {
                result.add(AffixTemplateDisplay.describeTemplateEntry(data, entry, stack));
            }
        }
        return result;
    }

    private static List<AffixTemplateEntry> applyBlockedSuperPenalty(List<AffixTemplateEntry> entries, Map<ResourceLocation, Float> minimumLevels, float penalty) {
        if (penalty <= EPSILON)
            return entries;
        return entries.stream()
                .map(entry -> {
                    Float minimumLevel = minimumLevels.get(entryId(entry));
                    return minimumLevel == null ? entry : entry.withLevel(applyBlockedSuperPenalty(entry.level(), minimumLevel, penalty));
                })
                .toList();
    }

    private static float applyBlockedSuperPenalty(float level, float minimumLevel, float penalty) {
        if (penalty <= EPSILON)
            return level;
        return Math.min(level, Math.max(minimumLevel, level - penalty));
    }

    private static float minimumImprovedLevel(float currentLevel, float resultLevel) {
        return Math.min(resultLevel, currentLevel + MINIMUM_LEVEL_IMPROVEMENT);
    }

    private static AffixInstance firstAffix(ItemStack stack) {
        return AffixHelper.getAffixes(stack).values().stream()
                .filter(AffixInstance::isValid)
                .sorted(Comparator.comparing(instance -> instance.affix().getId()))
                .findFirst()
                .orElse(null);
    }

    private static LinkedHashMap<ResourceLocation, AffixTemplateEntry> entryMap(List<AffixTemplateEntry> entries) {
        LinkedHashMap<ResourceLocation, AffixTemplateEntry> result = new LinkedHashMap<>();
        entries.stream()
                .sorted(Comparator.comparing(AffixTemplateOps::entryId))
                .forEach(entry -> result.put(entryId(entry), entry));
        return result;
    }

    private static List<ExclusiveConflict> findExclusiveConflicts(List<AffixTemplateEntry> entries) {
        List<ExclusiveConflict> conflicts = new ArrayList<>();
        for (int i = 0; i < entries.size(); i++) {
            AffixTemplateEntry first = entries.get(i);
            for (int j = i + 1; j < entries.size(); j++) {
                AffixTemplateEntry second = entries.get(j);
                if (!first.affix().get().isCompatibleWith(second.affix().get())) {
                    conflicts.add(new ExclusiveConflict(first, second));
                }
            }
        }
        return conflicts;
    }

    private static int countExclusiveConflicts(AffixTemplateEntry entry, ItemAffixes affixes) {
        if (affixes.isEmpty())
            return 0;
        return (int) affixes.liveAffixes()
                .filter(affix -> !entry.affix().get().isCompatibleWith(affix))
                .count();
    }

    private static ResourceLocation entryId(AffixTemplateEntry entry) {
        return entry.affix().getId();
    }

    private static void rebuildAffixName(ItemStack stack) {
        var affixes = AffixHelper.getAffixes(stack);
        if (affixes.isEmpty()) {
            stack.remove(Apoth.Components.AFFIX_NAME);
            stack.remove(Apoth.Components.RARITY);
            stack.remove(CEIAXDataComponents.OVERLIMIT_AFFIXES.get());
            return;
        }
        DynamicHolder<LootRarity> rarity = AffixHelper.getRarity(stack);
        if (!rarity.isBound()) {
            stack.remove(Apoth.Components.AFFIX_NAME);
            return;
        }
        List<Affix> nameList = new ArrayList<>(affixes.values().stream()
                .filter(AffixInstance::isValid)
                .sorted(Comparator.comparing(instance -> instance.affix().getId()))
                .map(AffixInstance::getAffix)
                .toList());
        if (nameList.isEmpty()) {
            stack.remove(Apoth.Components.AFFIX_NAME);
            return;
        }
        String key = nameList.size() > 1 ? "misc.apotheosis.affix_name.three" : "misc.apotheosis.affix_name.two";
        MutableComponent name = Component.translatable(key, nameList.get(0).getName(true), "", nameList.size() > 1 ? nameList.get(1).getName(false) : "")
                .withStyle(Style.EMPTY.withColor(rarity.get().color()).withItalic(false));
        AffixHelper.setName(stack, name);
        stack.remove(Apoth.Components.TOUCHED_BY_MALICE);
    }

    private static ItemStack single(ItemStack stack) {
        ItemStack copy = stack.copy();
        copy.setCount(1);
        return copy;
    }

    private static boolean nearlyEqual(float first, float second) {
        return Math.abs(first - second) <= EPSILON;
    }

    private record AcceptedEntry(AffixTemplateEntry entry, float beforeLevel, float resultLevel, float costLevel, float minimumLevel) {}

    private record RejectedEntry(AffixTemplateEntry entry, Component reason) {}

    private record ExclusiveConflict(AffixTemplateEntry first, AffixTemplateEntry second) {}

    private record PenaltyPreview(float minPenalty, float maxPenalty) {
        public static PenaltyPreview none() {
            return new PenaltyPreview(0, 0);
        }

        public static PenaltyPreview of(float first, float second) {
            return new PenaltyPreview(Math.max(0, Math.min(first, second)), Math.max(0, Math.max(first, second)));
        }

        public boolean active() {
            return maxPenalty > EPSILON;
        }

        public float minResultLevel(float level, float minimumLevel) {
            return Math.min(
                    applyBlockedSuperPenalty(level, minimumLevel, minPenalty),
                    applyBlockedSuperPenalty(level, minimumLevel, maxPenalty));
        }

        public float maxResultLevel(float level, float minimumLevel) {
            return Math.max(
                    applyBlockedSuperPenalty(level, minimumLevel, minPenalty),
                    applyBlockedSuperPenalty(level, minimumLevel, maxPenalty));
        }
    }

    public enum Status {
        EMPTY_INPUT,
        INCOMPLETE_INPUT,
        INVALID,
        READY
    }

    public record Result(
            Status status,
            Component failure,
            ItemStack primaryOutput,
            ItemStack secondaryOutput,
            int cost,
            List<Component> outputDescriptions,
            List<Component> warningDescriptions) {
        public static Result emptyInput() {
            return new Result(Status.EMPTY_INPUT, Component.empty(), ItemStack.EMPTY, ItemStack.EMPTY, 0, List.of(), List.of());
        }

        public static Result incomplete(Component failure) {
            return new Result(Status.INCOMPLETE_INPUT, failure, ItemStack.EMPTY, ItemStack.EMPTY, 0, List.of(), List.of());
        }

        public static Result invalid(Component failure) {
            return new Result(Status.INVALID, failure, ItemStack.EMPTY, ItemStack.EMPTY, 0, List.of(), List.of());
        }

        public static Result invalid(Component failure, List<Component> warnings) {
            return new Result(Status.INVALID, failure, ItemStack.EMPTY, ItemStack.EMPTY, 0, List.of(), List.copyOf(warnings));
        }

        public static Result ready(ItemStack primaryOutput, ItemStack secondaryOutput, int cost, Component... descriptions) {
            return ready(primaryOutput, secondaryOutput, cost, List.of(descriptions), List.of());
        }

        public static Result ready(ItemStack primaryOutput, ItemStack secondaryOutput, int cost, List<Component> descriptions) {
            return ready(primaryOutput, secondaryOutput, cost, descriptions, List.of());
        }

        public static Result ready(ItemStack primaryOutput, ItemStack secondaryOutput, int cost, List<Component> descriptions, List<Component> warnings) {
            return new Result(Status.READY, Component.empty(), primaryOutput, secondaryOutput, cost, List.copyOf(descriptions), List.copyOf(warnings));
        }

        public boolean valid() {
            return status == Status.READY && cost > 0 && (!primaryOutput.isEmpty() || !secondaryOutput.isEmpty());
        }
    }

    private enum FailureReason {
        MISSING_AFFIXED_EQUIPMENT("missing_affixed_equipment"),
        MISSING_EQUIPMENT("missing_equipment"),
        MISSING_BLANK_TEMPLATE("missing_blank_template"),
        MISSING_FILLED_TEMPLATE("missing_filled_template"),
        MISSING_SECOND_FILLED_TEMPLATE("missing_second_filled_template"),
        REQUIRES_BLANK_TEMPLATE("requires_blank_template"),
        REQUIRES_FILLED_TEMPLATE("requires_filled_template"),
        FIRST_REQUIRES_FILLED_TEMPLATE("first_requires_filled_template"),
        SECOND_REQUIRES_FILLED_TEMPLATE("second_requires_filled_template"),
        NORMAL_TEMPLATE_REQUIRES_NORMAL_MODE("normal_template_requires_normal_mode"),
        APOTHEOTIC_TEMPLATE_REQUIRES_SUPER_MODE("apotheotic_template_requires_super_mode"),
        ADVANCED_AFFIX_REQUIRES_CRYSTAL_TEMPLATE("advanced_affix_requires_crystal_template"),
        OVERLIMIT_AFFIX_REQUIRES_SUPER_TEMPLATE("overlimit_affix_requires_super_template"),
        EMPTY_TEMPLATE_DATA("empty_template_data"),
        UNBOUND_TEMPLATE_DATA("unbound_template_data"),
        EQUIPMENT_HAS_NO_RARITY("equipment_has_no_rarity"),
        EQUIPMENT_HAS_NO_AFFIX("equipment_has_no_affix"),
        ITEM_HAS_NO_LOOT_CATEGORY("item_has_no_loot_category"),
        TEMPLATE_CANNOT_HOLD_LEVEL("template_cannot_hold_level"),
        AFFIX_DENIED_BY_RULE("affix_denied_by_rule"),
        RARITY_MISMATCH_DISALLOWED("rarity_mismatch_disallowed"),
        TEMPLATE_AFFIXES_INCOMPATIBLE("template_affixes_incompatible"),
        TEMPLATE_TIER_MISMATCH("template_tier_mismatch"),
        TEMPLATE_RARITY_MISMATCH("template_rarity_mismatch"),
        LEVEL_INDEPENDENT_AFFIX("level_independent_affix"),
        WOULD_NOT_IMPROVE("would_not_improve"),
        ALREADY_AT_TEMPLATE_CAP("already_at_template_cap"),
        NO_APPLICABLE_AFFIXES("no_applicable_affixes");

        private final String key;

        FailureReason(String key) {
            this.key = key;
        }

        public Component message(Object... args) {
            return Component.translatable("create_enchantment_industry.gui.goggles.blaze_composer.failure." + key, args);
        }
    }

    private enum RejectionReason {
        DENIED_BY_RULE("denied_by_rule"),
        TEMPLATE_CANNOT_HOLD_LEVEL("template_cannot_hold_level"),
        CANNOT_APPLY_TO_ITEM("cannot_apply_to_item"),
        INCOMPATIBLE_WITH_EQUIPMENT("incompatible_with_equipment"),
        LEVEL_INDEPENDENT("level_independent"),
        WOULD_NOT_IMPROVE("would_not_improve"),
        ALREADY_AT_TEMPLATE_CAP("already_at_template_cap");

        private final String key;

        RejectionReason(String key) {
            this.key = key;
        }

        public Component message(Object... args) {
            return Component.translatable("create_enchantment_industry.gui.goggles.blaze_composer.lost_reason." + key, args);
        }
    }
}

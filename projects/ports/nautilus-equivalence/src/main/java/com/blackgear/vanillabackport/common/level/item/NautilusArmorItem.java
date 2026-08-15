package com.blackgear.vanillabackport.common.level.item;

import com.blackgear.vanillabackport.client.registries.ModSoundEvents;
import com.blackgear.vanillabackport.common.level.entity.mob.animal.nautilus.AbstractNautilus;
import com.blackgear.vanillabackport.core.data.tags.ModEntityTypeTags;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.dispenser.BlockSource;
import net.minecraft.core.dispenser.DefaultDispenseItemBehavior;
import net.minecraft.core.dispenser.DispenseItemBehavior;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.EquipmentSlotGroup;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.ai.attributes.AttributeModifier;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ArmorItem;
import net.minecraft.world.item.ArmorMaterial;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.component.ItemAttributeModifiers;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.DispenserBlock;
import net.minecraft.world.phys.AABB;

import java.util.List;

public class NautilusArmorItem extends ArmorItem {
	private static final DispenseItemBehavior DISPENSE_BEHAVIOR = new DefaultDispenseItemBehavior() {
		@Override
		protected ItemStack execute(BlockSource source, ItemStack stack) {
			return dispenseNautilusArmor(source, stack) ? stack : super.execute(source, stack);
		}
	};
	private final ResourceLocation textureLocation;
	private final int defense;
	private final float toughness;
	private final ItemAttributeModifiers attributeModifiers;

	public NautilusArmorItem(Holder<ArmorMaterial> material, Properties properties, int defense, float toughness, float knockbackResistance) {
		this(material, properties, defense, toughness, createAttributeModifiers(defense, toughness, knockbackResistance));
	}

	private NautilusArmorItem(Holder<ArmorMaterial> material, Properties properties, int defense, float toughness, ItemAttributeModifiers attributeModifiers) {
		super(material, Type.BODY, properties.attributes(attributeModifiers));
		this.defense = defense;
		this.toughness = toughness;
		this.attributeModifiers = attributeModifiers;
		DispenserBlock.registerBehavior(this, DISPENSE_BEHAVIOR);
		String materialName = material.unwrapKey().orElseThrow().location().getPath();
		this.textureLocation = ResourceLocation.withDefaultNamespace("textures/entity/nautilus/armor/" + materialName + ".png");
	}

	private static ItemAttributeModifiers createAttributeModifiers(int defense, float toughness, float knockbackResistance) {
		ItemAttributeModifiers.Builder builder = ItemAttributeModifiers.builder();
		ResourceLocation id = ResourceLocation.withDefaultNamespace("armor.body");
		builder.add(Attributes.ARMOR, new AttributeModifier(id, defense, AttributeModifier.Operation.ADD_VALUE), EquipmentSlotGroup.BODY);
		builder.add(Attributes.ARMOR_TOUGHNESS, new AttributeModifier(id, toughness, AttributeModifier.Operation.ADD_VALUE), EquipmentSlotGroup.BODY);
		if (knockbackResistance > 0.0F) {
			builder.add(Attributes.KNOCKBACK_RESISTANCE, new AttributeModifier(id, knockbackResistance, AttributeModifier.Operation.ADD_VALUE), EquipmentSlotGroup.BODY);
		}
		return builder.build();
	}

	private static boolean dispenseNautilusArmor(BlockSource source, ItemStack stack) {
		BlockPos targetPos = source.pos().relative(source.state().getValue(DispenserBlock.FACING));
		List<LivingEntity> targets = source.level().getEntitiesOfClass(
			LivingEntity.class,
			new AABB(targetPos),
			entity -> !entity.isSpectator()
				&& entity.isAlive()
				&& entity.getItemBySlot(EquipmentSlot.BODY).isEmpty()
				&& stack.canEquip(EquipmentSlot.BODY, entity)
		);
		if (targets.isEmpty()) {
			return false;
		}

		LivingEntity target = targets.getFirst();
		target.setItemSlot(EquipmentSlot.BODY, stack.split(1));
		if (target instanceof Mob mob) {
			mob.setDropChance(EquipmentSlot.BODY, 2.0F);
			mob.setPersistenceRequired();
		}
		return true;
	}

	@Override
	public boolean canEquip(ItemStack stack, EquipmentSlot slot, LivingEntity entity) {
		return slot == EquipmentSlot.BODY
			&& entity.getType().is(ModEntityTypeTags.CAN_WEAR_NAUTILUS_ARMOR)
			&& entity.canUseSlot(EquipmentSlot.BODY);
	}

	@Override
	public InteractionResult interactLivingEntity(ItemStack stack, Player player, LivingEntity entity, InteractionHand hand) {
		if (!(entity instanceof AbstractNautilus nautilus)
			|| !nautilus.isAlive()
			|| !this.canEquip(stack, EquipmentSlot.BODY, nautilus)
			|| !nautilus.getItemBySlot(EquipmentSlot.BODY).isEmpty()) {
			return InteractionResult.PASS;
		}

		if (!entity.level().isClientSide()) {
			nautilus.equipBodyArmor(player, stack);
		}
		return InteractionResult.sidedSuccess(entity.level().isClientSide());
	}

	@Override
	public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
		return InteractionResultHolder.pass(player.getItemInHand(hand));
	}

	@Override
	public Holder<SoundEvent> getEquipSound() {
		return ModSoundEvents.ARMOR_EQUIP_NAUTILUS;
	}

	@Override
	public ItemAttributeModifiers getDefaultAttributeModifiers() {
		return this.attributeModifiers;
	}

	@Override
	public int getDefense() {
		return this.defense;
	}

	@Override
	public float getToughness() {
		return this.toughness;
	}

	public ResourceLocation getTexture() {
		return this.textureLocation;
	}
}

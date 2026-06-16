from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

import config
from callbacks import InventoryManagementCallback, AllCategoriesCallback
from db import session_commit
from enums.add_type import AddType
from enums.bot_entity import BotEntity
from enums.entity_type import EntityType
from enums.item_type import ItemType
from enums.language import Language
from handlers.admin.constants import AdminConstants, InventoryManagementStates
from models.item import ItemDTO
from repositories.category import CategoryRepository
from repositories.item import ItemRepository
from repositories.subcategory import SubcategoryRepository
from services.media import MediaService
from services.notification import NotificationService
from utils.utils import get_text, get_bot_photo_id


class InventoryManagementService:
    PIN_GROUP_LABELS = {
        "hot": "🔥 Hot",
        "sale": "⚡ Sale",
        "new": "🆕 Mới về",
        "push": "📦 Nên mua",
    }

    @staticmethod
    async def get_inventory_management_menu(language: Language) -> tuple[str, InlineKeyboardBuilder]:
        kb_builder = InlineKeyboardBuilder()
        kb_builder.button(text=get_text(language, BotEntity.ADMIN, "add_items"),
                          callback_data=InventoryManagementCallback.create(level=1, entity_type=EntityType.ITEM))
        kb_builder.button(text=get_text(language, BotEntity.ADMIN, "delete_entity").format(
            entity=EntityType.CATEGORY.get_localized(language)
        ),
            callback_data=InventoryManagementCallback.create(level=2,
                                                             entity_type=EntityType.CATEGORY))
        kb_builder.button(text=get_text(language, BotEntity.ADMIN, "delete_entity").format(
            entity=EntityType.SUBCATEGORY.get_localized(language)
        ),
            callback_data=InventoryManagementCallback.create(level=2,
                                                             entity_type=EntityType.SUBCATEGORY))
        kb_builder.button(text="✏️ Sửa sản phẩm",
                          callback_data=InventoryManagementCallback.create(level=4,
                                                                           entity_type=EntityType.SUBCATEGORY))
        kb_builder.button(text="📋 Sản phẩm nổi bật",
                          callback_data=InventoryManagementCallback.create(level=11,
                                                                           entity_type=EntityType.SUBCATEGORY,
                                                                           edit_action="pinned_list"))
        kb_builder.button(text="⚡ Gửi sản phẩm nhanh",
                          callback_data=InventoryManagementCallback.create(level=7,
                                                                           entity_type=EntityType.SUBCATEGORY,
                                                                           edit_action="quick_send"))
        kb_builder.adjust(1)
        kb_builder.row(AdminConstants.back_to_main_button(language))
        return get_text(language, BotEntity.ADMIN, "inventory_management"), kb_builder

    @staticmethod
    async def get_add_items_type(callback_data: InventoryManagementCallback,
                                 language: Language) -> tuple[str, InlineKeyboardBuilder]:
        kb_builder = InlineKeyboardBuilder()
        kb_builder.button(text=get_text(language, BotEntity.ADMIN, "add_items_json"),
                          callback_data=InventoryManagementCallback.create(1, AddType.JSON, EntityType.ITEM))
        kb_builder.button(text=get_text(language, BotEntity.ADMIN, "add_items_txt"),
                          callback_data=InventoryManagementCallback.create(1, AddType.TXT, EntityType.ITEM))
        kb_builder.button(text=get_text(language, BotEntity.ADMIN, "add_items_menu"),
                          callback_data=InventoryManagementCallback.create(1, AddType.MENU, EntityType.ITEM))
        kb_builder.adjust(1)
        kb_builder.row(callback_data.get_back_button(language))
        return get_text(language, BotEntity.ADMIN, "add_items_msg"), kb_builder

    @staticmethod
    async def get_add_item_msg(callback_data: InventoryManagementCallback, state: FSMContext, language: Language):
        kb_markup = InlineKeyboardBuilder()
        kb_markup.button(text=get_text(language, BotEntity.COMMON, 'cancel'),
                         callback_data=InventoryManagementCallback.create(1))
        await state.update_data(add_type=callback_data.add_type.value)
        await state.set_state(InventoryManagementStates.document)
        match callback_data.add_type:
            case AddType.JSON:
                return get_text(language, BotEntity.ADMIN, "add_items_json_msg"), kb_markup
            case AddType.TXT:
                return get_text(language, BotEntity.ADMIN, "add_items_txt_msg"), kb_markup
            case AddType.MENU:
                kb_markup = InlineKeyboardBuilder()
                kb_markup.button(
                    text=f"🔦 {ItemType.PHYSICAL.get_localized(language)} / Đèn pin",
                    callback_data=callback_data.model_copy(update={"item_type": ItemType.PHYSICAL})
                )
                kb_markup.button(
                    text=f"💾 {ItemType.DIGITAL.get_localized(language)}",
                    callback_data=callback_data.model_copy(update={"item_type": ItemType.DIGITAL})
                )
                kb_markup.row(callback_data.get_back_button(language))
                kb_markup.adjust(1)
                return get_text(language, BotEntity.ADMIN, "add_items_item_type"), kb_markup

    @staticmethod
    async def delete_confirmation(callback_data: InventoryManagementCallback,
                                  session: AsyncSession, language: Language) -> tuple[str, InlineKeyboardBuilder]:
        callback_data.confirmation = True
        kb_builder = InlineKeyboardBuilder()
        kb_builder.button(text=get_text(language, BotEntity.COMMON, "confirm"),
                          callback_data=callback_data)
        kb_builder.button(text=get_text(language, BotEntity.COMMON, "cancel"),
                          callback_data=InventoryManagementCallback.create(0))
        match callback_data.entity_type:
            case EntityType.CATEGORY:
                category = await CategoryRepository.get_by_id(callback_data.entity_id, session)
                return get_text(language, BotEntity.ADMIN, "delete_entity_confirmation").format(
                    entity=callback_data.entity_type.name.capitalize(),
                    entity_name=category.name
                ), kb_builder
            case EntityType.SUBCATEGORY:
                subcategory = await SubcategoryRepository.get_by_id(callback_data.entity_id, session)
                return get_text(language, BotEntity.ADMIN, "delete_entity_confirmation").format(
                    entity=callback_data.entity_type.name.capitalize(),
                    entity_name=subcategory.name
                ), kb_builder

    @staticmethod
    async def delete_entity(callback_data: InventoryManagementCallback,
                            session: AsyncSession,
                            language: Language) -> tuple[str, InlineKeyboardBuilder]:
        kb_builder = InlineKeyboardBuilder()
        kb_builder.row(AdminConstants.back_to_main_button(language))
        match callback_data.entity_type:
            case EntityType.CATEGORY:
                category = await CategoryRepository.get_by_id(callback_data.entity_id, session)
                await ItemRepository.delete_unsold_by_category_id(callback_data.entity_id, session)
                await session_commit(session)
                return get_text(language, BotEntity.ADMIN, "successfully_deleted").format(
                    entity_name=category.name,
                    entity_to_delete=callback_data.entity_type.name.capitalize()), kb_builder
            case EntityType.SUBCATEGORY:
                subcategory = await SubcategoryRepository.get_by_id(callback_data.entity_id, session)
                await ItemRepository.delete_unsold_by_subcategory_id(callback_data.entity_id, session)
                await session_commit(session)
                return get_text(language, BotEntity.ADMIN, "successfully_deleted").format(
                    entity_name=subcategory.name,
                    entity_to_delete=callback_data.entity_type.name.capitalize()), kb_builder

    @staticmethod
    async def add_item_menu(message: Message,
                            state: FSMContext,
                            session: AsyncSession,
                            language: Language) -> tuple[str, InlineKeyboardBuilder]:
        current_state = await state.get_state()
        state_data = await state.get_data()
        await NotificationService.edit_reply_markup(message.bot,
                                                    state_data['chat_id'],
                                                    state_data['msg_id'])
        kb_builder = InlineKeyboardBuilder()
        cancel_button = InlineKeyboardButton(text=get_text(language, BotEntity.COMMON, "cancel"),
                                             callback_data=InventoryManagementCallback.create(1).pack())
        if current_state == InventoryManagementStates.category:
            await state.update_data(category_name=message.html_text)
            await state.set_state(InventoryManagementStates.subcategory)
            msg = get_text(language, BotEntity.ADMIN, "add_items_subcategory")
        elif current_state == InventoryManagementStates.subcategory:
            await state.update_data(subcategory_name=message.html_text)
            await state.set_state(InventoryManagementStates.description)
            msg = get_text(language, BotEntity.ADMIN, "add_items_description")
        elif current_state == InventoryManagementStates.description:
            await state.update_data(description=message.html_text)
            await state.set_state(InventoryManagementStates.private_data)
            if ItemType(state_data['item_type'].upper()) == ItemType.PHYSICAL:
                msg = get_text(language, BotEntity.ADMIN, "add_items_private_data_physical")
            else:
                msg = get_text(language, BotEntity.ADMIN, "add_items_private_data")
        elif current_state == InventoryManagementStates.private_data:
            success_msg = get_text(language, BotEntity.ADMIN, "add_items_price").format(
                    currency_text=config.CURRENCY.get_localized_text())
            if ItemType(state_data['item_type'].upper()) == ItemType.PHYSICAL:
                if message.html_text.isdecimal():
                    await state.update_data(items_qty=int(message.html_text))
                    await state.set_state(InventoryManagementStates.price)
                    msg = success_msg
                else:
                    msg = get_text(language, BotEntity.ADMIN, "add_items_private_data_physical")
            else:
                await state.update_data(private_data=message.html_text)
                await state.set_state(InventoryManagementStates.price)
                msg = success_msg
        else:
            try:
                price = float(message.html_text)
                assert (price > 0)
                await state.update_data(price=message.html_text)
                state_data = await state.get_data()
                item_type = ItemType(state_data['item_type'].upper())
                category = await CategoryRepository.get_or_create(state_data['category_name'], session)
                subcategory = await SubcategoryRepository.get_or_create(state_data['subcategory_name'], session)
                if item_type == ItemType.PHYSICAL:
                    items_list = [ItemDTO(item_type=item_type,
                                          category_id=category.id,
                                          subcategory_id=subcategory.id,
                                          description=state_data['description'],
                                          price=float(state_data['price']),
                                          private_data=None) for _ in range(state_data['items_qty'])]
                else:
                    items_list = [ItemDTO(item_type=item_type,
                                          category_id=category.id,
                                          subcategory_id=subcategory.id,
                                          description=state_data['description'],
                                          price=float(state_data['price']),
                                          private_data=private_data) for private_data in
                                  state_data['private_data'].split('\n')]
                await ItemRepository.add_many(items_list, session)
                await session_commit(session)
                await state.clear()
                msg = get_text(language, BotEntity.ADMIN, "add_items_success").format(adding_result=len(items_list))
                cancel_button.text = get_text(language, BotEntity.COMMON, "back_button")
            except Exception as _:
                msg = get_text(language, BotEntity.ADMIN, "add_items_price").format(
                    currency_text=config.CURRENCY.get_localized_text())
        kb_builder.row(cancel_button)
        return msg, kb_builder

    @staticmethod
    async def get_edit_product_actions(callback_data: InventoryManagementCallback,
                                       state: FSMContext,
                                       session: AsyncSession,
                                       language: Language) -> tuple[str, InlineKeyboardBuilder]:
        subcategory = await SubcategoryRepository.get_by_id(callback_data.entity_id, session)
        unsold_items = await ItemRepository.get_unsold_by_subcategory_id(callback_data.entity_id, session)
        await state.update_data(subcategory_id=callback_data.entity_id)
        kb_builder = InlineKeyboardBuilder()
        actions = [
            ("🏷 Sửa tên", "name"),
            ("📝 Sửa mô tả", "description"),
            ("💰 Sửa giá", "price"),
            ("📦 Sửa số lượng tồn", "quantity"),
            ("📌 Quản lý ghim", "pin_manage"),
        ]
        for text, action in actions:
            next_level = 9 if action == "pin_manage" else 6
            kb_builder.button(
                text=text,
                callback_data=InventoryManagementCallback.create(
                    level=next_level,
                    entity_type=EntityType.SUBCATEGORY,
                    entity_id=callback_data.entity_id,
                    edit_action=action,
                )
            )
        kb_builder.button(text=get_text(language, BotEntity.COMMON, "back_button"),
                          callback_data=InventoryManagementCallback.create(level=4, entity_type=EntityType.SUBCATEGORY))
        kb_builder.adjust(1)
        sample = unsold_items[0] if unsold_items else None
        msg = (
            f"✏️ <b>Sửa sản phẩm:</b> {subcategory.name}\n\n"
            f"📦 Tồn chưa bán: <b>{len(unsold_items)}</b>\n"
        )
        if sample:
            pin_group = InventoryManagementService.PIN_GROUP_LABELS.get((sample.pin_group or "").lower(), "Chưa chọn")
            pin_label = sample.pin_label or "Chưa đặt"
            pin_priority = sample.pin_priority if sample.is_pinned else "-"
            pin_status = "Đang ghim" if sample.is_pinned else "Chưa ghim"
            msg += f"💰 Giá hiện tại: <b>{config.CURRENCY.get_localized_symbol()}{sample.price:,.0f}</b>\n"
            msg += f"📝 Mô tả hiện tại:\n{sample.description}\n\n"
            msg += f"📌 Trạng thái ghim: <b>{pin_status}</b>\n"
            msg += f"🏷 Nhóm ghim: <b>{pin_group}</b>\n"
            msg += f"🔖 Nhãn ghim: <b>{pin_label}</b>\n"
            msg += f"🔢 Ưu tiên: <b>{pin_priority}</b>\n\n"
        msg += "Chọn thông tin muốn sửa:"
        return msg, kb_builder

    @staticmethod
    async def get_pin_management_menu(callback_data: InventoryManagementCallback,
                                      session: AsyncSession,
                                      language: Language) -> tuple[str, InlineKeyboardBuilder]:
        subcategory = await SubcategoryRepository.get_by_id(callback_data.entity_id, session)
        unsold_items = await ItemRepository.get_unsold_by_subcategory_id(callback_data.entity_id, session)
        sample = unsold_items[0] if unsold_items else None
        kb_builder = InlineKeyboardBuilder()
        kb_builder.button(text="✅ Bật ghim", callback_data=InventoryManagementCallback.create(
            level=10, entity_type=EntityType.SUBCATEGORY, entity_id=callback_data.entity_id, edit_action="pin_enable"))
        kb_builder.button(text="🔥 Nhóm ghim", callback_data=InventoryManagementCallback.create(
            level=6, entity_type=EntityType.SUBCATEGORY, entity_id=callback_data.entity_id, edit_action="pin_group"))
        kb_builder.button(text="🏷 Nhãn ghim", callback_data=InventoryManagementCallback.create(
            level=6, entity_type=EntityType.SUBCATEGORY, entity_id=callback_data.entity_id, edit_action="pin_label"))
        kb_builder.button(text="🔢 Độ ưu tiên", callback_data=InventoryManagementCallback.create(
            level=6, entity_type=EntityType.SUBCATEGORY, entity_id=callback_data.entity_id, edit_action="pin_priority"))
        kb_builder.button(text="❌ Bỏ ghim", callback_data=InventoryManagementCallback.create(
            level=10, entity_type=EntityType.SUBCATEGORY, entity_id=callback_data.entity_id, edit_action="pin_disable"))
        kb_builder.button(text="⬅️ Về DS nổi bật",
                          callback_data=InventoryManagementCallback.create(level=11,
                                                                           entity_type=EntityType.SUBCATEGORY,
                                                                           edit_action="pinned_list"))
        kb_builder.button(text=get_text(language, BotEntity.COMMON, "back_button"),
                          callback_data=InventoryManagementCallback.create(level=5, entity_type=EntityType.SUBCATEGORY, entity_id=callback_data.entity_id))
        kb_builder.adjust(1)
        if sample:
            pin_status = "Đang ghim" if sample.is_pinned else "Chưa ghim"
            pin_group = InventoryManagementService.PIN_GROUP_LABELS.get((sample.pin_group or "").lower(), "Chưa chọn")
            pin_label = sample.pin_label or "Chưa đặt"
            pin_priority = sample.pin_priority if sample.is_pinned else 999
        else:
            pin_status, pin_group, pin_label, pin_priority = "Chưa ghim", "Chưa chọn", "Chưa đặt", 999
        msg = (
            f"📌 <b>Quản lý ghim:</b> {subcategory.name}\n\n"
            f"Trạng thái: <b>{pin_status}</b>\n"
            f"Nhóm ghim: <b>{pin_group}</b>\n"
            f"Nhãn ghim: <b>{pin_label}</b>\n"
            f"Ưu tiên: <b>{pin_priority}</b>\n\n"
            f"Chọn thao tác muốn cập nhật:"
        )
        return msg, kb_builder

    @staticmethod
    async def get_pinned_products_admin_list(language: Language,
                                             session: AsyncSession) -> tuple[str, InlineKeyboardBuilder]:
        pinned_items = await ItemRepository.get_pinned_items(session)
        kb_builder = InlineKeyboardBuilder()
        kb_builder.button(text=get_text(language, BotEntity.COMMON, "back_button"),
                          callback_data=InventoryManagementCallback.create(level=0))

        if not pinned_items:
            msg = (
                "📋 <b>Sản phẩm nổi bật</b>\n\n"
                "Hiện chưa có sản phẩm nào đang được ghim.\n"
                "Anh vào <b>Sửa sản phẩm → 📌 Quản lý ghim</b> để bật nổi bật cho từng món."
            )
            kb_builder.adjust(1)
            return msg, kb_builder

        category_map = {
            category.id: category
            for category in await CategoryRepository.get_by_ids(
                list({item.category_id for item in pinned_items if item.category_id is not None}),
                session
            )
        }
        subcategory_map = {
            subcategory.id: subcategory
            for subcategory in await SubcategoryRepository.get_by_ids(
                list({item.subcategory_id for item in pinned_items if item.subcategory_id is not None}),
                session
            )
        }

        lines: list[str] = []
        seen_subcategories: set[int] = set()
        visible_index = 1
        for item in pinned_items:
            if item.subcategory_id is None or item.subcategory_id in seen_subcategories:
                continue
            seen_subcategories.add(item.subcategory_id)
            subcategory = subcategory_map.get(item.subcategory_id)
            category = category_map.get(item.category_id)
            available_qty = await ItemRepository.get_available_qty(item.item_type, item.category_id, item.subcategory_id, session)
            badge = InventoryManagementService.PIN_GROUP_LABELS.get((item.pin_group or "").lower(), "📌 Nổi bật")
            subcategory_name = subcategory.name if subcategory is not None else f"Sản phẩm #{item.subcategory_id}"
            category_name = category.name if category is not None else "Khác"
            label = item.pin_label or "Chưa đặt"
            price_text = f"{config.CURRENCY.get_localized_symbol()}{item.price:,.0f}"
            stock_text = f"{available_qty} còn hàng" if available_qty > 0 else "Hết hàng"
            lines.append(
                f"{visible_index}. {badge} <b>{subcategory_name}</b>\n"
                f"   🗂️ {category_name} | 🔖 {label}\n"
                f"   🔢 Ưu tiên: <b>{item.pin_priority}</b> | 💰 {price_text} | 📦 {stock_text}"
            )
            kb_builder.button(
                text=f"{visible_index}. {subcategory_name}",
                callback_data=InventoryManagementCallback.create(level=9,
                                                                 entity_type=EntityType.SUBCATEGORY,
                                                                 entity_id=item.subcategory_id,
                                                                 edit_action="pin_manage")
            )
            visible_index += 1

        msg = "📋 <b>Sản phẩm nổi bật</b>\n\n" + "\n\n".join(lines)
        kb_builder.adjust(1)
        return msg, kb_builder

    @staticmethod
    async def request_edit_value(callback_data: InventoryManagementCallback,
                                 state: FSMContext,
                                 language: Language) -> tuple[str, InlineKeyboardBuilder]:
        await state.update_data(subcategory_id=callback_data.entity_id, edit_action=callback_data.edit_action)
        await state.set_state(InventoryManagementStates.edit_value)
        kb_builder = InlineKeyboardBuilder()
        kb_builder.button(text=get_text(language, BotEntity.COMMON, "cancel"),
                          callback_data=InventoryManagementCallback.create(level=5,
                                                                           entity_type=EntityType.SUBCATEGORY,
                                                                           entity_id=callback_data.entity_id))
        labels = {
            "name": "tên sản phẩm mới",
            "description": "mô tả mới",
            "price": "giá mới",
            "quantity": "số lượng tồn mới",
            "pin_group": "nhóm ghim mới",
            "pin_label": "nhãn ghim mới",
            "pin_priority": "độ ưu tiên ghim mới",
        }
        warnings = {
            "name": "",
            "description": "\n⚠️ Chỉ áp dụng cho hàng chưa bán.",
            "price": "\n⚠️ Chỉ áp dụng cho hàng chưa bán. Nhập số, ví dụ: 850000",
            "quantity": "\n⚠️ Nếu giảm số lượng, bot sẽ xóa bớt hàng chưa bán.",
            "pin_group": "\n⚠️ Nhập một trong các giá trị: <code>hot</code>, <code>sale</code>, <code>new</code>, <code>push</code>.",
            "pin_label": "\n⚠️ Ví dụ: <code>Deal sáng tuần này</code>",
            "pin_priority": "\n⚠️ Nhập số nguyên dương, số càng nhỏ càng ưu tiên.",
        }
        action = callback_data.edit_action
        return f"Nhập {labels.get(action, 'giá trị mới')}:{warnings.get(action, '')}", kb_builder

    @staticmethod
    async def receive_edit_value(message: Message,
                                 state: FSMContext,
                                 session: AsyncSession,
                                 language: Language) -> tuple[str, InlineKeyboardBuilder]:
        state_data = await state.get_data()
        await NotificationService.edit_reply_markup(message.bot, state_data['chat_id'], state_data['msg_id'])
        subcategory_id = state_data['subcategory_id']
        action = state_data['edit_action']
        value = message.html_text.strip()
        subcategory = await SubcategoryRepository.get_by_id(subcategory_id, session)
        unsold_items = await ItemRepository.get_unsold_by_subcategory_id(subcategory_id, session)
        if action == "name":
            subcategory.name = value
            await SubcategoryRepository.update(subcategory, session)
            result = f"✅ Đã đổi tên sản phẩm thành: <b>{value}</b>"
        elif action == "description":
            await ItemRepository.update_unsold_description(subcategory_id, value, session)
            result = f"✅ Đã cập nhật mô tả cho {len(unsold_items)} hàng chưa bán."
        elif action == "price":
            try:
                price = float(value)
                assert price > 0
            except Exception:
                return "Giá không hợp lệ. Anh nhập số, ví dụ: <code>850000</code>", InlineKeyboardBuilder()
            await ItemRepository.update_unsold_price(subcategory_id, price, session)
            result = f"✅ Đã cập nhật giá cho {len(unsold_items)} hàng chưa bán: <b>{config.CURRENCY.get_localized_symbol()}{price:,.0f}</b>"
        elif action == "quantity":
            if not value.isdecimal():
                return "Số lượng không hợp lệ. Anh nhập số nguyên, ví dụ: <code>10</code>", InlineKeyboardBuilder()
            new_qty = int(value)
            current_qty = len(unsold_items)
            if new_qty > current_qty:
                sample = unsold_items[0] if unsold_items else None
                if sample is None:
                    return "Không thể tăng số lượng vì không còn item mẫu để copy.", InlineKeyboardBuilder()
                items_to_add = [ItemDTO(item_type=sample.item_type,
                                        category_id=sample.category_id,
                                        subcategory_id=sample.subcategory_id,
                                        description=sample.description,
                                        price=sample.price,
                                        private_data=None,
                                        is_pinned=sample.is_pinned,
                                        pin_group=sample.pin_group,
                                        pin_label=sample.pin_label,
                                        pin_priority=sample.pin_priority) for _ in range(new_qty - current_qty)]
                await ItemRepository.add_many(items_to_add, session)
                result = f"✅ Đã tăng tồn kho từ {current_qty} lên {new_qty}."
            elif new_qty < current_qty:
                await ItemRepository.delete_unsold_limit(subcategory_id, current_qty - new_qty, session)
                result = f"✅ Đã giảm tồn kho từ {current_qty} xuống {new_qty}."
            else:
                result = f"✅ Số lượng tồn không đổi: {current_qty}."
        elif action == "pin_group":
            normalized = value.lower()
            if normalized not in InventoryManagementService.PIN_GROUP_LABELS:
                return "Nhóm ghim không hợp lệ. Nhập một trong các giá trị: <code>hot</code>, <code>sale</code>, <code>new</code>, <code>push</code>.", InlineKeyboardBuilder()
            sample = unsold_items[0] if unsold_items else None
            await ItemRepository.update_unsold_pin_metadata(
                subcategory_id,
                session,
                is_pinned=True,
                pin_group=normalized,
                pin_label=sample.pin_label if sample and sample.pin_label else InventoryManagementService.PIN_GROUP_LABELS[normalized],
                pin_priority=sample.pin_priority if sample else 999,
            )
            result = f"✅ Đã cập nhật nhóm ghim thành <b>{InventoryManagementService.PIN_GROUP_LABELS[normalized]}</b>."
        elif action == "pin_label":
            if not value:
                return "Nhãn ghim không được để trống.", InlineKeyboardBuilder()
            sample = unsold_items[0] if unsold_items else None
            await ItemRepository.update_unsold_pin_metadata(
                subcategory_id,
                session,
                is_pinned=True,
                pin_group=sample.pin_group if sample and sample.pin_group else "hot",
                pin_label=value,
                pin_priority=sample.pin_priority if sample else 999,
            )
            result = f"✅ Đã cập nhật nhãn ghim thành: <b>{value}</b>."
        elif action == "pin_priority":
            if not value.isdecimal():
                return "Độ ưu tiên không hợp lệ. Anh nhập số nguyên dương, ví dụ: <code>1</code>", InlineKeyboardBuilder()
            priority = int(value)
            sample = unsold_items[0] if unsold_items else None
            await ItemRepository.update_unsold_pin_metadata(
                subcategory_id,
                session,
                is_pinned=True,
                pin_group=sample.pin_group if sample and sample.pin_group else "hot",
                pin_label=sample.pin_label if sample and sample.pin_label else "📌 Nổi bật",
                pin_priority=priority,
            )
            result = f"✅ Đã cập nhật độ ưu tiên ghim thành: <b>{priority}</b>."
        else:
            result = "Không nhận diện được thao tác sửa."
        await session_commit(session)
        await state.clear()
        kb_builder = InlineKeyboardBuilder()
        kb_builder.button(text=get_text(language, BotEntity.COMMON, "back_button"),
                          callback_data=InventoryManagementCallback.create(level=5,
                                                                           entity_type=EntityType.SUBCATEGORY,
                                                                           entity_id=subcategory_id))
        return result, kb_builder

    @staticmethod
    async def get_quick_product_card(callback_data: InventoryManagementCallback,
                                     session: AsyncSession,
                                     language: Language):
        subcategory = await SubcategoryRepository.get_by_id(callback_data.entity_id, session)
        unsold_items = await ItemRepository.get_unsold_by_subcategory_id(callback_data.entity_id, session)
        if not unsold_items:
            return None, None, f"⚠️ Sản phẩm <b>{subcategory.name}</b> hiện hết hàng, chưa tạo card gửi nhanh."
        sample = unsold_items[0]
        pin_badge = ""
        if sample.is_pinned:
            badge = InventoryManagementService.PIN_GROUP_LABELS.get((sample.pin_group or "").lower(), "📌 Nổi bật")
            pin_badge = f"{badge} {sample.pin_label or ''}\n"
        caption = (
            f"{pin_badge}🔦 <b>{subcategory.name}</b>\n\n"
            f"💰 Giá: <b>{config.CURRENCY.get_localized_symbol()}{sample.price:,.0f}</b>\n"
            f"📦 Còn hàng: <b>{len(unsold_items)}</b>\n\n"
            f"{sample.description}\n\n"
            f"👇 Bấm để xem / mua sản phẩm"
        )
        media_id = subcategory.media_id or f"0{get_bot_photo_id()}"
        media = MediaService.convert_to_media(media_id, caption)
        kb_builder = InlineKeyboardBuilder()
        kb_builder.button(
            text="🛒 Xem / mua ngay",
            callback_data=AllCategoriesCallback.create(
                level=3,
                item_type=sample.item_type,
                category_id=sample.category_id,
                subcategory_id=sample.subcategory_id,
            )
        )
        return media, kb_builder, None

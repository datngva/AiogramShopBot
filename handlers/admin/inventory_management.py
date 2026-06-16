from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from callbacks import InventoryManagementCallback, AddType
from db import session_commit
from enums.language import Language
from handlers.admin.constants import InventoryManagementStates
from handlers.common.common import enable_search
from repositories.item import ItemRepository
from services.admin import AdminService
from services.inventory_management import InventoryManagementService
from services.item import ItemService
from services.notification import NotificationService
from utils.custom_filters import AdminIdFilter

inventory_management = Router()


async def inventory_management_menu(**kwargs):
    callback: CallbackQuery = kwargs.get("callback")
    state: FSMContext = kwargs.get("state")
    language: Language = kwargs.get("language")
    await state.clear()
    msg, kb_builder = await InventoryManagementService.get_inventory_management_menu(language)
    await callback.message.edit_text(text=msg, reply_markup=kb_builder.as_markup())


async def add_items(**kwargs):
    callback: CallbackQuery = kwargs.get("callback")
    callback_data: InventoryManagementCallback = kwargs.get("callback_data")
    state: FSMContext = kwargs.get("state")
    language: Language = kwargs.get("language")
    if callback_data.add_type is None:
        msg, kb_builder = await InventoryManagementService.get_add_items_type(callback_data, language)
    else:
        msg, kb_builder = await InventoryManagementService.get_add_item_msg(callback_data, state, language)
    message = await callback.message.edit_text(text=msg, reply_markup=kb_builder.as_markup())
    await state.update_data(msg_id=message.message_id, chat_id=message.chat.id)


async def delete_entity(**kwargs):
    callback: CallbackQuery = kwargs.get("callback")
    session: AsyncSession = kwargs.get("session")
    callback_data: InventoryManagementCallback = kwargs.get("callback_data")
    state: FSMContext = kwargs.get("state")
    language: Language = kwargs.get("language")
    state_data = await state.get_data()
    if callback_data.is_filter_enabled and state_data.get('filter') is not None:
        msg, kb_builder = await AdminService.get_entity_picker(callback_data, session, state, language)
    elif callback_data.is_filter_enabled:
        media, kb_builder = await enable_search(callback_data, callback_data.entity_type, None,
                                                state, InventoryManagementStates.filter_entity, language)
        await state.update_data(entity_type=callback_data.entity_type.value, callback_prefix=callback_data.__prefix__)
        msg = media.caption
    else:
        await state.update_data(filter=None)
        await state.set_state()
        msg, kb_builder = await AdminService.get_entity_picker(callback_data, session, state, language)
    await callback.message.edit_text(text=msg, reply_markup=kb_builder.as_markup())


async def confirm_delete(**kwargs):
    callback: CallbackQuery = kwargs.get("callback")
    callback_data: InventoryManagementCallback = kwargs.get("callback_data")
    session: AsyncSession = kwargs.get("session")
    language: Language = kwargs.get("language")
    if callback_data.confirmation is False:
        msg, kb_builder = await InventoryManagementService.delete_confirmation(callback_data, session, language)
    else:
        msg, kb_builder = await InventoryManagementService.delete_entity(callback_data, session, language)
    await callback.message.edit_text(text=msg, reply_markup=kb_builder.as_markup())


async def edit_product_picker(**kwargs):
    callback: CallbackQuery = kwargs.get("callback")
    callback_data: InventoryManagementCallback = kwargs.get("callback_data")
    session: AsyncSession = kwargs.get("session")
    state: FSMContext = kwargs.get("state")
    language: Language = kwargs.get("language")
    await state.update_data(filter=None)
    await state.set_state()
    msg, kb_builder = await AdminService.get_entity_picker(callback_data, session, state, language)
    await callback.message.edit_text(text="✏️ Chọn sản phẩm muốn sửa:\n\n" + msg, reply_markup=kb_builder.as_markup())


async def edit_product_actions(**kwargs):
    callback: CallbackQuery = kwargs.get("callback")
    callback_data: InventoryManagementCallback = kwargs.get("callback_data")
    session: AsyncSession = kwargs.get("session")
    state: FSMContext = kwargs.get("state")
    language: Language = kwargs.get("language")
    msg, kb_builder = await InventoryManagementService.get_edit_product_actions(callback_data, state, session, language)
    await callback.message.edit_text(text=msg, reply_markup=kb_builder.as_markup())


async def request_edit_value(**kwargs):
    callback: CallbackQuery = kwargs.get("callback")
    callback_data: InventoryManagementCallback = kwargs.get("callback_data")
    state: FSMContext = kwargs.get("state")
    language: Language = kwargs.get("language")
    msg, kb_builder = await InventoryManagementService.request_edit_value(callback_data, state, language)
    message = await callback.message.edit_text(text=msg, reply_markup=kb_builder.as_markup())
    await state.update_data(msg_id=message.message_id, chat_id=message.chat.id)


async def quick_product_picker(**kwargs):
    callback: CallbackQuery = kwargs.get("callback")
    callback_data: InventoryManagementCallback = kwargs.get("callback_data")
    session: AsyncSession = kwargs.get("session")
    state: FSMContext = kwargs.get("state")
    language: Language = kwargs.get("language")
    await state.update_data(filter=None)
    await state.set_state()
    msg, kb_builder = await AdminService.get_entity_picker(callback_data, session, state, language)
    await callback.message.edit_text(text="⚡ Chọn sản phẩm muốn tạo card gửi nhanh:\n\n" + msg,
                                     reply_markup=kb_builder.as_markup())


async def send_quick_product_card(**kwargs):
    callback: CallbackQuery = kwargs.get("callback")
    callback_data: InventoryManagementCallback = kwargs.get("callback_data")
    session: AsyncSession = kwargs.get("session")
    language: Language = kwargs.get("language")
    media, kb_builder, error_msg = await InventoryManagementService.get_quick_product_card(callback_data,
                                                                                           session,
                                                                                           language)
    if error_msg:
        await callback.message.answer(text=error_msg)
        return
    await NotificationService.answer_media(callback.message, media, kb_builder.as_markup())
    await callback.message.answer("✅ Anh có thể forward card sản phẩm phía trên cho khách.")


async def pin_management_menu(**kwargs):
    callback: CallbackQuery = kwargs.get("callback")
    callback_data: InventoryManagementCallback = kwargs.get("callback_data")
    session: AsyncSession = kwargs.get("session")
    language: Language = kwargs.get("language")
    msg, kb_builder = await InventoryManagementService.get_pin_management_menu(callback_data, session, language)
    await callback.message.edit_text(text=msg, reply_markup=kb_builder.as_markup())


async def pinned_products_list(**kwargs):
    callback: CallbackQuery = kwargs.get("callback")
    session: AsyncSession = kwargs.get("session")
    language: Language = kwargs.get("language")
    msg, kb_builder = await InventoryManagementService.get_pinned_products_admin_list(language, session)
    await callback.message.edit_text(text=msg, reply_markup=kb_builder.as_markup())


async def toggle_pin_status(**kwargs):
    callback: CallbackQuery = kwargs.get("callback")
    callback_data: InventoryManagementCallback = kwargs.get("callback_data")
    session: AsyncSession = kwargs.get("session")
    language: Language = kwargs.get("language")
    if callback_data.edit_action == "pin_disable":
        await ItemRepository.clear_unsold_pin_metadata(callback_data.entity_id, session)
        await session_commit(session)
        msg = "✅ Đã bỏ ghim sản phẩm thành công."
    else:
        unsold_items = await ItemRepository.get_unsold_by_subcategory_id(callback_data.entity_id, session)
        sample = unsold_items[0] if unsold_items else None
        await ItemRepository.update_unsold_pin_metadata(
            callback_data.entity_id,
            session,
            is_pinned=True,
            pin_group=sample.pin_group if sample and sample.pin_group else "hot",
            pin_label=sample.pin_label if sample and sample.pin_label else "📌 Nổi bật",
            pin_priority=sample.pin_priority if sample else 999,
        )
        await session_commit(session)
        msg = "✅ Đã bật ghim sản phẩm thành công."
    kb_builder = InlineKeyboardBuilder()
    kb_builder.button(text="⬅️ Về quản lý ghim", callback_data=InventoryManagementCallback.create(
        level=9, entity_type=callback_data.entity_type, entity_id=callback_data.entity_id, edit_action="pin_manage"))
    await callback.message.edit_text(text=msg, reply_markup=kb_builder.as_markup())


@inventory_management.message(AdminIdFilter(), F.document, StateFilter(InventoryManagementStates.document))
async def add_items_document(message: Message, state: FSMContext, session: AsyncSession, language: Language):
    state_data = await state.get_data()
    await NotificationService.edit_reply_markup(message.bot,
                                                state_data['chat_id'],
                                                state_data['msg_id'])
    add_type = AddType(int(state_data['add_type']))
    file_name = message.document.file_name
    file_id = message.document.file_id
    file = await message.bot.get_file(file_id)
    await message.bot.download_file(file.file_path, file_name)
    msg = await ItemService.add_items(file_name, add_type, session, language)
    await message.answer(text=msg)
    await state.clear()


@inventory_management.message(AdminIdFilter(), F.text, StateFilter(InventoryManagementStates.item_type,
                                                                   InventoryManagementStates.category,
                                                                   InventoryManagementStates.subcategory,
                                                                   InventoryManagementStates.price,
                                                                   InventoryManagementStates.description,
                                                                   InventoryManagementStates.private_data))
async def add_items_menu(message: Message, state: FSMContext, session: AsyncSession, language: Language):
    msg, kb_builder = await InventoryManagementService.add_item_menu(message, state, session, language)
    message = await message.answer(text=msg, reply_markup=kb_builder.as_markup())
    await state.update_data(msg_id=message.message_id, chat_id=message.chat.id)


@inventory_management.message(AdminIdFilter(), F.text, StateFilter(InventoryManagementStates.edit_value))
async def receive_edit_value(message: Message, state: FSMContext, session: AsyncSession, language: Language):
    msg, kb_builder = await InventoryManagementService.receive_edit_value(message, state, session, language)
    await message.answer(text=msg, reply_markup=kb_builder.as_markup())


@inventory_management.message(AdminIdFilter(), F.text, StateFilter(InventoryManagementStates.filter_entity))
async def receive_filter_message(message: Message, state: FSMContext, session: AsyncSession, language: Language):
    await state.update_data(filter=message.html_text)
    msg, kb_builder = await AdminService.get_entity_picker(None, session, state, language)
    await message.answer(text=msg, reply_markup=kb_builder.as_markup())


@inventory_management.callback_query(AdminIdFilter(), InventoryManagementCallback.filter())
async def inventory_management_navigation(callback: CallbackQuery,
                                          state: FSMContext,
                                          callback_data: InventoryManagementCallback,
                                          session: AsyncSession,
                                          language: Language):
    if callback_data.add_type == AddType.MENU and callback_data.item_type is not None:
        await state.update_data(item_type=callback_data.item_type.value)
        await state.set_state(InventoryManagementStates.category)
        await callback.message.edit_text(
            text="🗂️ <b>Nhập danh mục sản phẩm:</b>\nVí dụ: <code>Đèn pin</code>",
            reply_markup=None
        )
        return

    current_level = callback_data.level

    levels = {
        0: inventory_management_menu,
        1: add_items,
        2: delete_entity,
        3: confirm_delete,
        4: edit_product_picker,
        5: edit_product_actions,
        6: request_edit_value,
        7: quick_product_picker,
        8: send_quick_product_card,
        9: pin_management_menu,
        10: toggle_pin_status,
        11: pinned_products_list,
    }

    current_level_function = levels[current_level]

    kwargs = {
        "callback": callback,
        "state": state,
        "session": session,
        "callback_data": callback_data,
        "language": language
    }

    await current_level_function(**kwargs)

from json import load
from pathlib import Path

from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import config
from callbacks import AddType, AllCategoriesCallback
from db import session_commit
from enums.announcement_type import AnnouncementType
from enums.bot_entity import BotEntity
from enums.item_type import ItemType
from enums.keyboard_button import KeyboardButton
from enums.language import Language
from models.category import CategoryDTO
from models.item import ItemDTO
from models.subcategory import SubcategoryDTO
from repositories.button_media import ButtonMediaRepository
from repositories.category import CategoryRepository
from repositories.item import ItemRepository
from repositories.subcategory import SubcategoryRepository
from services.media import MediaService
from utils.utils import get_text, get_bot_photo_id


class ItemService:
    ANNOUNCEMENT_MESSAGE_LIMIT = 4000

    @staticmethod
    def _wrap_announcement_chunk(content: str) -> str:
        return f"<b>{content}</b>"

    @staticmethod
    def _split_category_into_blocks(header: str,
                                    category_header: str,
                                    subcategory_lines: list[str]) -> list[str]:
        max_content_length = ItemService.ANNOUNCEMENT_MESSAGE_LIMIT - len("<b></b>")
        category_blocks: list[str] = []
        current_block = category_header
        for line in subcategory_lines:
            if len(header + current_block + line) <= max_content_length:
                current_block += line
                continue
            if current_block != category_header:
                category_blocks.append(current_block)
                current_block = category_header + line
            else:
                category_blocks.append(current_block + line)
                current_block = category_header
        if current_block != category_header or not category_blocks:
            category_blocks.append(current_block)
        return category_blocks

    @staticmethod
    def _build_announcement_chunks(header: str, category_blocks: list[str]) -> list[str]:
        max_content_length = ItemService.ANNOUNCEMENT_MESSAGE_LIMIT - len("<b></b>")
        chunks: list[str] = []
        current_content = header
        for block in category_blocks:
            if len(current_content + block) <= max_content_length:
                current_content += block
                continue
            if current_content != header:
                chunks.append(ItemService._wrap_announcement_chunk(current_content))
            current_content = header + block
        if current_content == header and chunks:
            return chunks
        chunks.append(ItemService._wrap_announcement_chunk(current_content))
        return chunks

    @staticmethod
    async def create_announcement_message(announcement_type: AnnouncementType,
                                          session: AsyncSession,
                                          language: Language) -> list[str]:
        if announcement_type == AnnouncementType.CURRENT_STOCK:
            items = await ItemRepository.get_in_stock(session)
            header = get_text(language, BotEntity.ADMIN, "current_stock_header")
        else:
            items = await ItemRepository.get_new(session)
            header = get_text(language, BotEntity.ADMIN, "restocking_message_header")
        filtered_items = {}
        category_map = {
            category.id: category
            for category in await CategoryRepository.get_by_ids(
                [item.category_id for item in items],
                session
            )
        }
        subcategory_map = {
            subcategory.id: subcategory
            for subcategory in await SubcategoryRepository.get_by_ids(
                [item.subcategory_id for item in items],
                session
            )
        }
        for item in items:
            category = category_map[item.category_id]
            subcategory = subcategory_map[item.subcategory_id]
            if category.name not in filtered_items:
                filtered_items[category.name] = {}
            if subcategory.name not in filtered_items[category.name]:
                filtered_items[category.name][subcategory.name] = []
            filtered_items[category.name][subcategory.name].append(item)
        category_blocks = []
        for category, subcategory_item_dict in filtered_items.items():
            category_header = get_text(language, BotEntity.ADMIN, "restocking_message_category").format(
                category=category
            )
            subcategory_lines = []
            for subcategory, item in subcategory_item_dict.items():
                subcategory_lines.append(get_text(language, BotEntity.USER, "subcategory_button").format(
                    subcategory_name=subcategory,
                    available_quantity=len(item),
                    subcategory_price=item[0].price,
                    currency_sym=config.CURRENCY.get_localized_symbol()) + "\n")
            category_blocks.extend(
                ItemService._split_category_into_blocks(header, category_header, subcategory_lines)
            )
        return ItemService._build_announcement_chunks(header, category_blocks)

    @staticmethod
    async def build_product_announcement_context(item_id: int,
                                                 session: AsyncSession) -> tuple[ItemDTO, CategoryDTO, SubcategoryDTO]:
        item = await ItemRepository.get_by_id(item_id, session)
        category = await CategoryRepository.get_by_id(item.category_id, session)
        subcategory = await SubcategoryRepository.get_by_id(item.subcategory_id, session)
        return item, category, subcategory

    @staticmethod
    async def build_product_announcement_button_text(item_id: int,
                                                     session: AsyncSession) -> str:
        item, category, subcategory = await ItemService.build_product_announcement_context(item_id, session)
        new_badge = "🆕 " if item.is_new else ""
        return (
            f"{new_badge}{subcategory.name} | "
            f"{config.CURRENCY.get_localized_symbol()}{item.price:,.0f} | "
            f"{category.name}"
        )

    @staticmethod
    async def build_product_announcement_payload(item_id: int,
                                                 session: AsyncSession):
        item, _, subcategory = await ItemService.build_product_announcement_context(item_id, session)
        caption = (
            "🆕 <b>Sản phẩm mới đã lên kệ!</b>\n\n"
            f"🔦 <b>{subcategory.name}</b>\n"
            f"💰 Giá: {config.CURRENCY.get_localized_symbol()}{item.price:,.0f}\n\n"
            f"{item.description}\n\n"
            "Nhanh tay xem ngay trong shop nhé!"
        )
        media = MediaService.convert_to_media(subcategory.media_id, caption=caption)
        return media, caption

    @staticmethod
    async def parse_items_json(path_to_file: str, session: AsyncSession | Session):
        with open(path_to_file, 'r', encoding='utf-8') as file:
            items = load(file)
            items_list = []
            for item in items:
                item_type = ItemType(item['item_type'].upper())
                category = await CategoryRepository.get_or_create(item['category'], session)
                subcategory = await SubcategoryRepository.get_or_create(item['subcategory'], session)
                item.pop('item_type')
                item.pop('category')
                item.pop('subcategory')
                if item_type == ItemType.PHYSICAL:
                    item.pop('private_data')
                items_list.append(ItemDTO(
                    item_type=item_type,
                    category_id=category.id,
                    subcategory_id=subcategory.id,
                    **item
                ))
            return items_list

    @staticmethod
    async def parse_items_txt(path_to_file: str, session: AsyncSession | Session):
        with open(path_to_file, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            items_list = []
            for line in lines:
                item_type, category_name, subcategory_name, description, price, private_data = line.split(';')
                item_type = ItemType(item_type.upper())
                if item_type == ItemType.PHYSICAL:
                    private_data = None
                category = await CategoryRepository.get_or_create(category_name, session)
                subcategory = await SubcategoryRepository.get_or_create(subcategory_name, session)
                items_list.append(ItemDTO(
                    item_type=item_type,
                    category_id=category.id,
                    subcategory_id=subcategory.id,
                    price=float(price),
                    description=description,
                    private_data=private_data
                ))
            return items_list

    @staticmethod
    async def add_items(path_to_file: str,
                        add_type: AddType,
                        session: AsyncSession | Session,
                        language: Language) -> str:
        try:
            items = []
            if add_type == AddType.JSON:
                items += await ItemService.parse_items_json(path_to_file, session)
            else:
                items += await ItemService.parse_items_txt(path_to_file, session)
            await ItemRepository.add_many(items, session)
            await session_commit(session)
            return get_text(language, BotEntity.ADMIN, "add_items_success").format(adding_result=len(items))
        except Exception as e:
            return get_text(language, BotEntity.ADMIN, "add_items_err").format(adding_result=e)
        finally:
            Path(path_to_file).unlink(missing_ok=True)

    @staticmethod
    async def get_all_types(callback_data: AllCategoriesCallback,
                            session: AsyncSession,
                            language: Language) -> tuple[InputMediaPhoto, InlineKeyboardBuilder]:
        callback_data = callback_data or AllCategoriesCallback.create(0)
        kb_builder = InlineKeyboardBuilder()
        available_item_types = await ItemRepository.get_available_item_types(session)
        for item_type in available_item_types:
            kb_builder.button(
                text=item_type.get_localized(language),
                callback_data=callback_data.model_copy(update={"level": callback_data.level + 1,
                                                               "item_type": item_type})
            )
        kb_builder.button(
            text=get_text(language, BotEntity.USER, "pick_all_item_types"),
            callback_data=callback_data.model_copy(update={"level": callback_data.level + 1,
                                                           "item_type": None})
        )
        kb_builder.adjust(1)
        caption = get_text(language, BotEntity.USER, "pick_item_type")
        button_media = await ButtonMediaRepository.get_by_button(
            KeyboardButton.ALL_CATEGORIES, session
        )
        return MediaService.convert_to_media(button_media.media_id, caption=caption), kb_builder

    @staticmethod
    async def get_pinned_products(session: AsyncSession,
                                  language: Language) -> tuple[InputMediaPhoto, InlineKeyboardBuilder]:
        pinned_items = await ItemRepository.get_pinned_items(session)
        kb_builder = InlineKeyboardBuilder()
        default_media = f"0{get_bot_photo_id()}"
        try:
            button_media = await ButtonMediaRepository.get_by_button(
                KeyboardButton.PINNED_PRODUCTS, session
            )
            pinned_media_id = button_media.media_id or default_media
        except Exception:
            pinned_media_id = default_media
        if not pinned_items:
            caption = "📌 <b>Hiện chưa có sản phẩm nổi bật.</b>\n\nAnh/chị quay lại sau nhé, shop sẽ ghim hàng hot tại đây."
            return MediaService.convert_to_media(pinned_media_id, caption=caption), kb_builder

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
        group_badges = {
            "hot": "🔥 Hot",
            "sale": "⚡ Sale",
            "new": "🆕 Mới về",
            "push": "📦 Nên mua",
        }

        featured_lines: list[str] = []
        seen_subcategories: set[int] = set()
        for item in pinned_items:
            if item.subcategory_id is None or item.subcategory_id in seen_subcategories:
                continue
            seen_subcategories.add(item.subcategory_id)
            subcategory = subcategory_map.get(item.subcategory_id)
            category = category_map.get(item.category_id)
            available_qty = await ItemRepository.get_available_qty(item.item_type, item.category_id, item.subcategory_id, session)
            if available_qty <= 0:
                continue
            badge = group_badges.get((item.pin_group or "").lower(), "📌 Nổi bật")
            label = item.pin_label or badge
            subcategory_name = subcategory.name if subcategory is not None else f"Sản phẩm #{item.subcategory_id}"
            category_name = category.name if category is not None else "Khác"
            featured_lines.append(
                f"{badge} <b>{subcategory_name}</b> — {label}\n"
                f"   🗂️ {category_name} | 💰 {config.CURRENCY.get_localized_symbol()}{item.price:,.0f} | 📦 {available_qty}"
            )
            kb_builder.button(
                text=f"📌 {subcategory_name} | {config.CURRENCY.get_localized_symbol()}{item.price:,.0f} | Còn: {available_qty}",
                callback_data=AllCategoriesCallback.create(
                    level=3,
                    item_type=item.item_type,
                    category_id=item.category_id,
                    subcategory_id=item.subcategory_id,
                )
            )

        kb_builder.adjust(1)
        if not featured_lines:
            caption = "📌 <b>Hiện chưa có sản phẩm nổi bật.</b>\n\nTạm thời các sản phẩm ghim đang hết hàng."
            return MediaService.convert_to_media(pinned_media_id, caption=caption), kb_builder
        caption = "📌 <b>Sản phẩm nổi bật</b>\n\n" + "\n\n".join(featured_lines) + "\n\nChọn sản phẩm anh/chị muốn xem:"
        return MediaService.convert_to_media(pinned_media_id, caption=caption), kb_builder

import datetime
import math

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

import config
from db import session_execute, session_flush
from models.coupon import CouponDTO, Coupon, CouponUsageDTO, CouponUsage
from utils.utils import calculate_max_page


class CouponRepository:
    @staticmethod
    async def create(coupon_dto: CouponDTO, session: AsyncSession) -> CouponDTO:
        coupon = Coupon(**coupon_dto.model_dump())
        session.add(coupon)
        await session_flush(session)
        return CouponDTO.model_validate(coupon, from_attributes=True)

    @staticmethod
    async def get_paginated(page: int, session: AsyncSession) -> list[CouponDTO]:
        stmt = (select(Coupon).order_by(Coupon.id)
                .limit(config.PAGE_ENTRIES)
                .offset(page * config.PAGE_ENTRIES))
        coupons = await session_execute(stmt, session)
        return [CouponDTO.model_validate(coupon, from_attributes=True) for coupon in coupons.scalars().all()]

    @staticmethod
    async def get_max_page(session: AsyncSession) -> int:
        stmt = (select(func.count(Coupon.id)))
        coupons_qty = await session_execute(stmt, session)
        coupons_qty = coupons_qty.scalar_one()
        return calculate_max_page(coupons_qty)

    @staticmethod
    async def get_by_id(coupon_id: int, session: AsyncSession) -> CouponDTO:
        stmt = select(Coupon).where(Coupon.id == coupon_id)
        coupon = await session_execute(stmt, session)
        return CouponDTO.model_validate(coupon.scalar_one(), from_attributes=True)

    @staticmethod
    async def update(coupon_dto: CouponDTO, session: AsyncSession):
        stmt = update(Coupon).where(Coupon.id == coupon_dto.id).values(**coupon_dto.model_dump())
        await session_execute(stmt, session)

    @staticmethod
    async def delete(coupon_id: int, session: AsyncSession):
        coupon = await session.get(Coupon, coupon_id)
        if coupon is not None:
            await session.delete(coupon)

    @staticmethod
    async def get_by_code(code: str, session: AsyncSession) -> CouponDTO | None:
        now_time = datetime.datetime.now(datetime.UTC)
        stmt = select(Coupon).where(Coupon.code == code,
                                    Coupon.is_active == True,
                                    Coupon.start_datetime <= now_time,
                                    Coupon.expire_datetime > now_time)
        coupon = await session_execute(stmt, session)
        coupon = coupon.scalar_one_or_none()
        if coupon is not None:
            coupon = CouponDTO.model_validate(coupon, from_attributes=True)
        return coupon


class CouponUsageRepository:
    @staticmethod
    async def create(coupon_usage_dto: CouponUsageDTO, session: AsyncSession) -> CouponUsageDTO:
        coupon_usage = CouponUsage(**coupon_usage_dto.model_dump())
        session.add(coupon_usage)
        await session_flush(session)
        return CouponUsageDTO.model_validate(coupon_usage, from_attributes=True)

    @staticmethod
    async def count_by_coupon_id(coupon_id: int, session: AsyncSession) -> int:
        stmt = select(func.count(CouponUsage.id)).where(CouponUsage.coupon_id == coupon_id)
        result = await session_execute(stmt, session)
        return result.scalar_one()

    @staticmethod
    async def count_by_coupon_and_user(coupon_id: int, user_id: int, session: AsyncSession) -> int:
        stmt = select(func.count(CouponUsage.id)).where(CouponUsage.coupon_id == coupon_id,
                                                        CouponUsage.user_id == user_id)
        result = await session_execute(stmt, session)
        return result.scalar_one()

from sqlalchemy import Column, Integer, String, Numeric, DateTime, func

from app.database.session import Base


class Order(Base):
    """订单表：给 Agent 的"数据类工具"当靶子的演示数据

    先做一张简单的业务表（部门 / 金额 / 时间），
    Day 7 让 Agent 能"查数据"，Day 8 再做自然语言自动转任意 SQL。
    """

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    department = Column(String(50), nullable=False)  # 部门，如"销售一部"
    amount = Column(Numeric(10, 2), nullable=False)  # 订单金额
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 下单时间

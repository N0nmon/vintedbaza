from datetime import datetime
from sqlalchemy import BigInteger, String, Boolean, Integer, ForeignKey, DateTime, Float, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), nullable=True)
    is_admin: Mapped[bool] = mapped_column(default=False)

class Product(Base):
    __tablename__ = 'products'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    photo_id: Mapped[str] = mapped_column(String, nullable=False)
    purchase_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default='0.0')
    platform_id: Mapped[str] = mapped_column(String(50), nullable=True)
    category_id: Mapped[int] = mapped_column(ForeignKey('categories.id'), nullable=True)
    category: Mapped["Category"] = relationship(back_populates="products", lazy="joined")

class Stock(Base):
    __tablename__ = 'stock'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    size: Mapped[str] = mapped_column(String(10), nullable=False)
    is_available: Mapped[bool] = mapped_column(default=True)
    product: Mapped["Product"] = relationship(back_populates=None, lazy="joined")

class Sale(Base):
    __tablename__ = 'sales'
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey('stock.id'))
    seller_id: Mapped[int] = mapped_column(ForeignKey('users.user_id'))
    price: Mapped[float] = mapped_column(Float, nullable=False)
    account: Mapped[str] = mapped_column(String(100), nullable=True) # Новое поле
    label_link: Mapped[str] = mapped_column(String, nullable=True)
    screenshot_path: Mapped[str] = mapped_column(String, nullable=True)
    sale_date: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='0')
    stock_item: Mapped["Stock"] = relationship(back_populates=None, lazy="joined")
    seller: Mapped["User"] = relationship(back_populates=None, lazy="joined")

class UserProductAccess(Base):
    __tablename__ = 'user_product_access'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.user_id', ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete="CASCADE"))
    
    __table_args__ = (UniqueConstraint('user_id', 'product_id', name='_user_product_uc'),)

# --- НАЧАЛО БЛОКА: Обновленный класс PlatformAccount ---
class PlatformAccount(Base):
    __tablename__ = 'platform_accounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    # Имя для отображения (например, "7b")
    display_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    # Имя для поиска в теле письма (например, "Vinted_МойАкк")
    search_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
# --- КОНЕЦ БЛОКА ---

class AccountAssignment(Base):
    __tablename__ = 'account_assignments'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.user_id', ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey('platform_accounts.id', ondelete="CASCADE"))

    __table_args__ = (UniqueConstraint('user_id', 'account_id', name='_user_account_uc'),)

class SystemState(Base):
    __tablename__ = 'system_state'
    # Ключ для нашей переменной, например "favorites_counter"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    # Значение счетчика
    value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

class Category(Base):
    __tablename__ = 'categories'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    
    # Связь "один ко многим" с товарами
    products: Mapped[list["Product"]] = relationship(back_populates="category")
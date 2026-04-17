"""
TradeMind AI — Database Manager
SQLite via SQLAlchemy.  All tables are created automatically on first run.
"""
import json
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    create_engine, Column, Integer, Float, String, Boolean,
    DateTime, Date, Text, ForeignKey, event
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, relationship
from sqlalchemy.pool import StaticPool

from app.config import DB_PATH


# ─── ORM Base ────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ─── Models ──────────────────────────────────────────────────────────────────
class Trade(Base):
    __tablename__ = "trades"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    order_id      = Column(String(64), unique=True, nullable=True)
    symbol        = Column(String(20), nullable=False)
    exchange      = Column(String(10), default="NSE")
    direction     = Column(String(4), nullable=False)   # BUY / SELL
    quantity      = Column(Integer, nullable=False)
    entry_price   = Column(Float, nullable=False)
    exit_price    = Column(Float, nullable=True)
    stop_loss     = Column(Float, nullable=True)
    target        = Column(Float, nullable=True)
    pnl           = Column(Float, default=0.0)
    status        = Column(String(16), default="OPEN")  # OPEN/CLOSED/CANCELLED
    strategy      = Column(String(64), nullable=True)
    ai_reason     = Column(Text, nullable=True)
    entry_time    = Column(DateTime, default=datetime.now)
    exit_time     = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, default=datetime.now)


class Position(Base):
    __tablename__ = "positions"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    symbol        = Column(String(20), unique=True, nullable=False)
    exchange      = Column(String(10), default="NSE")
    quantity      = Column(Integer, default=0)
    avg_price     = Column(Float, default=0.0)
    current_price = Column(Float, default=0.0)
    pnl           = Column(Float, default=0.0)
    pnl_pct       = Column(Float, default=0.0)
    updated_at    = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class PortfolioHistory(Base):
    __tablename__ = "portfolio_history"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, unique=True, default=date.today)
    total_value   = Column(Float, default=0.0)
    cash          = Column(Float, default=0.0)
    invested      = Column(Float, default=0.0)
    daily_pnl     = Column(Float, default=0.0)
    total_pnl     = Column(Float, default=0.0)


class Strategy(Base):
    __tablename__ = "strategies"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    name          = Column(String(64), unique=True, nullable=False)
    description   = Column(Text, nullable=True)
    is_active     = Column(Boolean, default=False)
    parameters    = Column(Text, default="{}")   # JSON blob
    win_rate      = Column(Float, default=0.0)
    total_trades  = Column(Integer, default=0)
    total_pnl     = Column(Float, default=0.0)
    created_at    = Column(DateTime, default=datetime.now)
    updated_at    = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def get_parameters(self) -> Dict:
        return json.loads(self.parameters or "{}")

    def set_parameters(self, params: Dict):
        self.parameters = json.dumps(params)


class Alert(Base):
    __tablename__ = "alerts"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    level         = Column(String(16), default="INFO")  # INFO/WARNING/DANGER
    title         = Column(String(128), nullable=False)
    message       = Column(Text, nullable=True)
    is_read       = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=datetime.now)


class AILog(Base):
    __tablename__ = "ai_logs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    role          = Column(String(16), nullable=False)   # user / assistant
    content       = Column(Text, nullable=False)
    context_type  = Column(String(32), nullable=True)    # trade_analysis / chat / etc.
    created_at    = Column(DateTime, default=datetime.now)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key   = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)


# ─── Manager ─────────────────────────────────────────────────────────────────
class DatabaseManager:
    def __init__(self):
        db_url = f"sqlite:///{DB_PATH}"
        self.engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        # Enable WAL mode for better concurrent read performance
        @event.listens_for(self.engine, "connect")
        def set_wal(conn, _):
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")

        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=True)

    def initialise(self):
        """Create all tables and seed default strategies."""
        Base.metadata.create_all(self.engine)
        self._seed_defaults()

    def session(self) -> Session:
        return self.SessionLocal()

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _seed_defaults(self):
        with self.session() as s:
            if s.query(Strategy).count() == 0:
                defaults = [
                    Strategy(name="Momentum Breakout",
                             description="Buys when price breaks above 20-period high with volume confirmation.",
                             parameters=json.dumps({"period": 20, "volume_mult": 1.5})),
                    Strategy(name="Mean Reversion",
                             description="Buys oversold stocks (RSI < 30) and sells overbought (RSI > 70).",
                             parameters=json.dumps({"rsi_period": 14, "oversold": 30, "overbought": 70})),
                    Strategy(name="VWAP Pullback",
                             description="Enters long when price pulls back to VWAP in an uptrend.",
                             parameters=json.dumps({"deviation_pct": 0.5})),
                ]
                s.add_all(defaults)
                s.commit()

    # ── Trade CRUD ───────────────────────────────────────────────────────────
    def add_trade(self, **kwargs) -> Trade:
        with self.session() as s:
            trade = Trade(**kwargs)
            s.add(trade)
            s.commit()
            s.refresh(trade)
            return trade

    def get_trades(self, status: Optional[str] = None, limit: int = 200) -> List[Trade]:
        with self.session() as s:
            q = s.query(Trade)
            if status:
                q = q.filter(Trade.status == status)
            return q.order_by(Trade.entry_time.desc()).limit(limit).all()

    def close_trade(self, trade_id: int, exit_price: float) -> Optional[Trade]:
        with self.session() as s:
            trade = s.get(Trade, trade_id)
            if trade:
                trade.exit_price = exit_price
                trade.exit_time  = datetime.now()
                mult = 1 if trade.direction == "BUY" else -1
                trade.pnl = mult * (exit_price - trade.entry_price) * trade.quantity
                trade.status = "CLOSED"
                s.commit()
                s.refresh(trade)
            return trade

    # ── Portfolio Snapshot ───────────────────────────────────────────────────
    def save_portfolio_snapshot(self, **kwargs):
        with self.session() as s:
            today = date.today()
            existing = s.query(PortfolioHistory).filter_by(snapshot_date=today).first()
            if existing:
                for k, v in kwargs.items():
                    setattr(existing, k, v)
            else:
                s.add(PortfolioHistory(snapshot_date=today, **kwargs))
            s.commit()

    def get_portfolio_history(self, days: int = 30) -> List[PortfolioHistory]:
        with self.session() as s:
            return (s.query(PortfolioHistory)
                    .order_by(PortfolioHistory.snapshot_date.desc())
                    .limit(days).all())

    # ── Settings ─────────────────────────────────────────────────────────────
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.session() as s:
            row = s.get(AppSetting, key)
            return row.value if row else default

    def set_setting(self, key: str, value: Any):
        with self.session() as s:
            row = s.get(AppSetting, key)
            if row:
                row.value = str(value)
            else:
                s.add(AppSetting(key=key, value=str(value)))
            s.commit()

    # ── Alerts ───────────────────────────────────────────────────────────────
    def add_alert(self, title: str, message: str = "", level: str = "INFO"):
        with self.session() as s:
            s.add(Alert(title=title, message=message, level=level))
            s.commit()

    def get_alerts(self, unread_only: bool = False, limit: int = 50) -> List[Alert]:
        with self.session() as s:
            q = s.query(Alert)
            if unread_only:
                q = q.filter(Alert.is_read == False)
            return q.order_by(Alert.created_at.desc()).limit(limit).all()

    # ── AI Chat Log ──────────────────────────────────────────────────────────
    def log_ai_message(self, role: str, content: str, context_type: str = "chat"):
        with self.session() as s:
            s.add(AILog(role=role, content=content, context_type=context_type))
            s.commit()

    def get_ai_history(self, limit: int = 50) -> List[AILog]:
        with self.session() as s:
            return (s.query(AILog)
                    .order_by(AILog.created_at.asc())
                    .limit(limit).all())

    # ── Stats helpers ────────────────────────────────────────────────────────
    def get_today_stats(self) -> Dict:
        today = date.today()
        with self.session() as s:
            trades = s.query(Trade).filter(
                Trade.entry_time >= datetime.combine(today, datetime.min.time()),
                Trade.status == "CLOSED"
            ).all()
            wins   = [t for t in trades if t.pnl > 0]
            losses = [t for t in trades if t.pnl <= 0]
            return {
                "total_trades": len(trades),
                "wins":         len(wins),
                "losses":       len(losses),
                "win_rate":     (len(wins) / len(trades) * 100) if trades else 0,
                "total_pnl":    sum(t.pnl for t in trades),
                "best_trade":   max((t.pnl for t in trades), default=0),
                "worst_trade":  min((t.pnl for t in trades), default=0),
            }

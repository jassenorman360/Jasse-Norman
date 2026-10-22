from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
import os

DATABASE_URL = os.getenv('DATABASE_URL','sqlite:///./safewatch.db')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
def now(): return datetime.now(timezone.utc)
class Base(DeclarativeBase): pass
class Case(Base):
    __tablename__='cases'
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    url: Mapped[str|None] = mapped_column(Text,nullable=True)
    description: Mapped[str] = mapped_column(Text,default='')
    status: Mapped[str] = mapped_column(String(30),default='new')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    evidence: Mapped[list['Evidence']] = relationship(back_populates='case',cascade='all, delete-orphan')
    analysis: Mapped['Analysis|None'] = relationship(back_populates='case',uselist=False,cascade='all, delete-orphan')
    reviews: Mapped[list['Review']] = relationship(back_populates='case',cascade='all, delete-orphan')
class Evidence(Base):
    __tablename__='evidence'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('cases.id'))
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    bytes: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[str] = mapped_column(String(80))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    case: Mapped[Case] = relationship(back_populates='evidence')
class Analysis(Base):
    __tablename__='analyses'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('cases.id'),unique=True)
    transcript: Mapped[str] = mapped_column(Text,default='')
    language: Mapped[str] = mapped_column(String(40),default='unknown')
    tags: Mapped[list] = mapped_column(JSON,default=list)
    indicators: Mapped[list] = mapped_column(JSON,default=list)
    model_notes: Mapped[str] = mapped_column(Text,default='')
    case: Mapped[Case] = relationship(back_populates='analysis')
class Review(Base):
    __tablename__='reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('cases.id'))
    reviewer: Mapped[str] = mapped_column(String(100))
    decision: Mapped[str] = mapped_column(String(20))
    rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    case: Mapped[Case] = relationship(back_populates='reviews')
